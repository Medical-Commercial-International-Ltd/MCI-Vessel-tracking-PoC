from __future__ import annotations

import hashlib
import json
from bisect import bisect_left, bisect_right
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app import __version__
from app.ais_data import (
    MarineCadastreTrackStore,
    TimedPosition,
    bearing_degrees,
    haversine_nm,
    segment_positions,
)
from app.hurdat import HurdatStorm, InterpolatedStormPoint, category_for_wind, load_hurdat_storms
from app.models import (
    AnalysisDocument,
    AnalysisInput,
    AnalysisStatistics,
    AuditRecord,
    ClosestApproach,
    DataQuality,
    EncounterDocument,
    EncounterExposure,
    Position,
    SourceReference,
    StormDetails,
    VesselIdentity,
)
from app.repositories import AnalysisRepository
from app.scoring import EncounterInputs, aggregate_risk, score_encounter


class RealAnalysisService:
    """Matches real MarineCadastre AIS tracks to official NHC HURDAT2 best tracks."""

    def __init__(self, repository: AnalysisRepository, cache_dir: Path):
        self.repository = repository
        self.cache_dir = cache_dir
        self.tracks = MarineCadastreTrackStore(cache_dir)
        self.hurdat_paths = [
            cache_dir / "storms" / "hurdat2-atlantic.txt",
            cache_dir / "storms" / "hurdat2-pacific.txt",
        ]

    def analyse(self, analysis_input: AnalysisInput, created_by: str) -> AnalysisDocument:
        started = datetime.now(timezone.utc)
        vessel_record = self.tracks.resolve_vessel(
            analysis_input.identifier_type,
            analysis_input.identifier,
        )
        if vessel_record is None:
            raise ValueError(
                "This IMO is not present in the local MarineCadastre vessel registry. "
                "Use a registered MMSI or add the vessel identity to the AIS cache."
            )

        segments = self.tracks.load_segments(
            vessel_record.mmsi,
            analysis_input.period.from_date,
            analysis_input.period.to_date,
        )
        if not segments:
            years = ", ".join(str(year) for year in self.tracks.available_years) or "none"
            raise ValueError(
                f"No MarineCadastre AIS tracks were found for MMSI {vessel_record.mmsi} "
                f"in the selected period. Cached track years: {years}."
            )

        positions = _unique_positions(
            position
            for segment in segments
            for position in segment_positions(segment)
            if analysis_input.period.from_date <= position.timestamp.date() <= analysis_input.period.to_date
        )
        if not positions:
            raise ValueError("AIS track segments were found, but they contained no usable positions.")

        storms = load_hurdat_storms(
            self.hurdat_paths,
            analysis_input.period.from_date.year,
            analysis_input.period.to_date.year,
        )
        if not storms:
            raise ValueError("No NHC HURDAT2 storm records are available for the selected period.")

        analysis_id = f"analysis_{uuid4().hex}"
        encounters = self._match_encounters(
            analysis_id,
            positions,
            storms,
            analysis_input.storm_proximity_nm,
        )
        event_scores = [encounter.risk.event_score for encounter in encounters]
        coverage_years = sorted({position.timestamp.year for position in positions})
        requested_years = set(
            range(analysis_input.period.from_date.year, analysis_input.period.to_date.year + 1)
        )
        available_years = set(self.tracks.available_years)
        unavailable_years = sorted(requested_years - available_years)
        unobserved_years = sorted((requested_years & available_years) - set(coverage_years))
        observed_days = len({position.timestamp.date() for position in positions})
        confidence = "MEDIUM" if observed_days >= 30 else "LOW"
        warnings = [
            "MarineCadastre vessel-track geometry is authoritative AIS-derived data, but timestamps between each segment's endpoints are distance-interpolated.",
            "MarineCadastre AIS is land-receiver data and may not capture vessel activity beyond normal coastal receiver range.",
        ]
        if unavailable_years:
            warnings.insert(
                0,
                "No cached MarineCadastre vessel tracks are available for "
                + ", ".join(str(year) for year in unavailable_years)
                + ".",
            )
        if unobserved_years:
            warnings.append(
                "No AIS tracks for this vessel were observed in "
                + ", ".join(str(year) for year in unobserved_years)
                + "; this does not prove the vessel was absent."
            )

        primary_segment = max(segments, key=lambda segment: (segment.end - segment.start).total_seconds())
        distance_nm = round(sum(segment.distance_nm for segment in segments), 1)
        duration_hours = sum(
            max(0, (segment.end - segment.start).total_seconds()) / 3600 for segment in segments
        )
        speeds = [
            segment.distance_nm / hours
            for segment in segments
            if (hours := (segment.end - segment.start).total_seconds() / 3600) > 0
        ]
        hours_total = round(
            sum(encounter.exposure.duration_within_200_nm_hours for encounter in encounters),
            1,
        )
        hours_wind = round(
            sum(
                encounter.exposure.duration_within_34_kt_wind_field_hours
                for encounter in encounters
            ),
            1,
        )
        completed = datetime.now(timezone.utc)
        calculation_payload = {
            "input": analysis_input.model_dump(mode="json", by_alias=True),
            "mmsi": vessel_record.mmsi,
            "encounters": [encounter.model_dump(mode="json", by_alias=True) for encounter in encounters],
            "model": "TC-EXPOSURE-v0.1-real",
        }
        calculation_hash = hashlib.sha256(
            json.dumps(calculation_payload, sort_keys=True, default=str).encode()
        ).hexdigest()
        risk = aggregate_risk(event_scores, confidence)
        analysis = AnalysisDocument(
            id=analysis_id,
            analysis_id=analysis_id,
            status="completed",
            is_synthetic=False,
            synthetic_notice=None,
            created_at=completed,
            created_by=created_by,
            input=analysis_input,
            vessel=VesselIdentity(
                name=vessel_record.name,
                imo=vessel_record.imo,
                mmsi=[vessel_record.mmsi],
                vessel_type=_friendly_vessel_type(primary_segment.vessel_group),
                flag=None,
                length_m=vessel_record.length_m or primary_segment.length_m,
                width_m=vessel_record.width_m or primary_segment.width_m,
                draft_m=vessel_record.draft_m or primary_segment.draft_m,
            ),
            risk=risk,
            statistics=AnalysisStatistics(
                ais_observation_count=len(positions),
                observed_days=observed_days,
                named_storm_encounters=len(encounters),
                hours_within_200_nm=hours_total,
                hours_within_34_kt_wind_field=hours_wind,
                minimum_distance_nm=min(
                    (encounter.closest_approach.distance_nm for encounter in encounters),
                    default=None,
                ),
                distance_travelled_nm=distance_nm,
                average_speed_kt=round(distance_nm / duration_hours, 1) if duration_hours else 0,
                maximum_speed_kt=round(max(speeds), 1) if speeds else 0,
            ),
            encounter_ids=[encounter.id for encounter in encounters],
            data_quality=DataQuality(
                rating=confidence,
                identity_confidence="HIGH" if vessel_record.name != f"MMSI {vessel_record.mmsi}" else "MEDIUM",
                years_covered=coverage_years,
                significant_storm_period_gaps=len(unavailable_years),
                warnings=warnings,
            ),
            sources=[
                SourceReference(
                    provider="NOAA / BOEM / U.S. Coast Guard",
                    dataset="MarineCadastre AIS Vessel Tracks",
                    retrieved_at=completed,
                ),
                SourceReference(
                    provider="NOAA National Hurricane Center",
                    dataset="HURDAT2 Atlantic and NE/NC Pacific best tracks",
                    retrieved_at=completed,
                ),
            ],
            audit=AuditRecord(
                calculation_started_at=started,
                calculation_completed_at=completed,
                application_version=__version__,
                calculation_hash=calculation_hash,
            ),
        )
        self.repository.save_analysis(analysis)
        for encounter in encounters:
            self.repository.save_encounter(encounter)
        return analysis

    def _match_encounters(
        self,
        analysis_id: str,
        positions: list[TimedPosition],
        storms: list[HurdatStorm],
        proximity_nm: float,
    ) -> list[EncounterDocument]:
        timestamps = [position.timestamp for position in positions]
        matches = []
        for storm in storms:
            start_index = bisect_left(timestamps, storm.start)
            end_index = bisect_right(timestamps, storm.end)
            hits: list[tuple[TimedPosition, InterpolatedStormPoint, float, str]] = []
            for vessel_position in positions[start_index:end_index]:
                storm_position = storm.at(vessel_position.timestamp)
                if storm_position is None:
                    continue
                distance = haversine_nm(
                    vessel_position.latitude,
                    vessel_position.longitude,
                    storm_position.latitude,
                    storm_position.longitude,
                )
                if distance <= proximity_nm:
                    hits.append(
                        (
                            vessel_position,
                            storm_position,
                            distance,
                            _wind_field(vessel_position, storm_position, distance),
                        )
                    )
            if not hits:
                continue
            closest = min(hits, key=lambda hit: hit[2])
            maximum_wind = max(hit[1].wind_kt for hit in hits)
            strongest_field = max(
                (hit[3] for hit in hits),
                key=lambda field: {"OUTSIDE 34KT": 0, "34KT": 1, "50KT": 2, "64KT": 3}[field],
            )
            duration = _exposure_duration_hours(hits)
            wind_duration = _exposure_duration_hours(
                [hit for hit in hits if hit[3] != "OUTSIDE 34KT"]
            )
            event_risk = score_encounter(
                EncounterInputs(
                    distance_nm=closest[2],
                    maximum_wind_kt=maximum_wind,
                    strongest_wind_field=strongest_field,
                    duration_hours=duration,
                )
            )
            matches.append(
                (storm, closest, maximum_wind, strongest_field, duration, wind_duration, event_risk)
            )

        matches.sort(key=lambda match: match[1][0].timestamp)
        encounters = []
        for index, (storm, closest, maximum_wind, field, duration, wind_duration, event_risk) in enumerate(matches, 1):
            vessel_position, storm_position, distance, _ = closest
            encounters.append(
                EncounterDocument(
                    id=f"encounter_{index:03d}",
                    analysis_id=analysis_id,
                    storm=StormDetails(
                        id=storm.storm_id,
                        name=storm.name.title(),
                        classification=storm_position.status,
                        category=category_for_wind(maximum_wind),
                    ),
                    closest_approach=ClosestApproach(
                        timestamp=vessel_position.timestamp,
                        distance_nm=round(distance, 1),
                        vessel_position=Position(
                            coordinates=(vessel_position.longitude, vessel_position.latitude)
                        ),
                        storm_position=Position(
                            coordinates=(storm_position.longitude, storm_position.latitude)
                        ),
                    ),
                    exposure=EncounterExposure(
                        duration_within_200_nm_hours=duration,
                        duration_within_34_kt_wind_field_hours=wind_duration,
                        strongest_wind_field=field,
                        maximum_storm_wind_kt=maximum_wind,
                    ),
                    risk=event_risk,
                )
            )
        return encounters


def _unique_positions(positions) -> list[TimedPosition]:
    unique = {
        (position.timestamp, round(position.longitude, 6), round(position.latitude, 6)): position
        for position in positions
    }
    return sorted(unique.values(), key=lambda position: position.timestamp)


def _wind_field(
    vessel: TimedPosition,
    storm: InterpolatedStormPoint,
    distance_nm: float,
) -> str:
    bearing = bearing_degrees(storm.latitude, storm.longitude, vessel.latitude, vessel.longitude)
    quadrant = 0 if bearing < 90 else 1 if bearing < 180 else 2 if bearing < 270 else 3
    if storm.radii_64[quadrant] > 0 and distance_nm <= storm.radii_64[quadrant]:
        return "64KT"
    if storm.radii_50[quadrant] > 0 and distance_nm <= storm.radii_50[quadrant]:
        return "50KT"
    if storm.radii_34[quadrant] > 0 and distance_nm <= storm.radii_34[quadrant]:
        return "34KT"
    return "OUTSIDE 34KT"


def _exposure_duration_hours(hits) -> float:
    timestamps = sorted({hit[0].timestamp for hit in hits})
    if not timestamps:
        return 0
    duration = 0.25
    for left, right in zip(timestamps, timestamps[1:]):
        gap = (right - left).total_seconds() / 3600
        if gap <= 6:
            duration += min(gap, 1.0)
    return round(duration, 1)


def _friendly_vessel_type(raw: str) -> str:
    normalized = raw.strip()
    return {
        "Cargo": "Cargo",
        "Tanker": "Tanker",
        "Passenger": "Passenger",
        "TugTow": "Tug/Tow",
        "Pleasure Craft/Sailing": "Pleasure Craft/Sailing",
        "Not Available": "Unknown",
    }.get(normalized, normalized or "Unknown")
