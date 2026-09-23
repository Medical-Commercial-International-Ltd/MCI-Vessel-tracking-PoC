from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app import __version__
from app.models import (
    AnalysisDocument,
    AnalysisInput,
    AnalysisStatistics,
    AuditRecord,
    ClosestApproach,
    DataQuality,
    DatePeriod,
    EncounterDocument,
    EncounterExposure,
    Position,
    SourceReference,
    StormDetails,
    VesselIdentity,
)
from app.repositories import AnalysisRepository
from app.scoring import EncounterInputs, aggregate_risk, score_encounter


VESSEL_NAMES = [
    "MCI Meridian",
    "MCI Atlas",
    "MCI Endeavour",
    "MCI Northstar",
    "MCI Horizon",
    "MCI Vanguard",
    "MCI Mariner",
    "MCI Resolute",
]
VESSEL_TYPES = ["Cargo", "Tanker", "Passenger", "Tug/Tow", "Other"]
FLAGS = ["GBR", "LBR", "PAN", "MHL", "SGP", "NOR", "USA"]
STORM_NAMES = ["DEMO ALPHA", "DEMO BRAVO", "DEMO CORDELIA", "DEMO DORIAN", "DEMO ECHO"]
COASTAL_POSITIONS = [
    (-79.4, 31.8),
    (-74.2, 37.4),
    (-90.1, 28.2),
    (-96.3, 27.1),
    (-122.8, 38.0),
    (-157.8, 21.2),
    (-66.1, 18.0),
]


def validate_identifier(identifier_type: str, identifier: str) -> str:
    normalized = identifier.strip().upper().replace(" ", "")
    if identifier_type == "MMSI":
        if not re.fullmatch(r"\d{9}", normalized):
            raise ValueError("MMSI must contain exactly nine digits")
        return normalized
    normalized = normalized.removeprefix("IMO")
    if not re.fullmatch(r"\d{7}", normalized):
        raise ValueError("IMO must contain exactly seven digits")
    weighted = sum(int(digit) * weight for digit, weight in zip(normalized[:6], range(7, 1, -1)))
    if weighted % 10 != int(normalized[-1]):
        raise ValueError("IMO check digit is invalid")
    return normalized


class DemoAnalysisService:
    """Deterministic synthetic provider used until NOAA ingestion is enabled."""

    def __init__(self, repository: AnalysisRepository):
        self.repository = repository

    def analyse(
        self,
        analysis_input: AnalysisInput,
        created_by: str,
        *,
        created_at: datetime | None = None,
        seed_suffix: str = "",
    ) -> AnalysisDocument:
        started = datetime.now(timezone.utc)
        seed_material = f"{analysis_input.identifier}:{seed_suffix}".encode()
        seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")
        generator = random.Random(seed)
        analysis_id = f"analysis_{uuid4().hex}"
        encounter_count = generator.choices([0, 1, 2, 3, 4, 5], [20, 25, 22, 16, 10, 7])[0]
        encounters: list[EncounterDocument] = []
        event_scores: list[int] = []

        for index in range(encounter_count):
            encounter = self._make_encounter(
                generator,
                analysis_id,
                index,
                analysis_input.period,
            )
            encounters.append(encounter)
            event_scores.append(encounter.risk.event_score)

        confidence = generator.choices(["HIGH", "MEDIUM", "LOW"], [78, 18, 4])[0]
        risk = aggregate_risk(event_scores, confidence)
        vessel_type = generator.choice(VESSEL_TYPES)
        identifier = analysis_input.identifier
        vessel = VesselIdentity(
            name=generator.choice(VESSEL_NAMES),
            imo=identifier if analysis_input.identifier_type == "IMO" else _valid_demo_imo(generator),
            mmsi=[identifier] if analysis_input.identifier_type == "MMSI" else [str(generator.randint(200_000_000, 799_999_999))],
            vessel_type=vessel_type,
            flag=generator.choice(FLAGS),
            length_m=round(generator.uniform(85, 310), 1),
            width_m=round(generator.uniform(14, 48), 1),
            draft_m=round(generator.uniform(4, 15), 1),
        )

        observed_days = generator.randint(220, 1040)
        hours_total = round(sum(item.exposure.duration_within_200_nm_hours for item in encounters), 1)
        hours_wind = round(
            sum(
                item.exposure.duration_within_200_nm_hours
                for item in encounters
                if item.exposure.strongest_wind_field not in {"OUTSIDE 34KT", "UNKNOWN"}
            ),
            1,
        )
        warnings = []
        gaps = 0 if confidence == "HIGH" else generator.randint(1, 4)
        if gaps:
            warnings.append(f"{gaps} material AIS gap(s) overlap a storm observation window")

        completed = datetime.now(timezone.utc)
        created = created_at or completed
        calculation_payload = {
            "input": analysis_input.model_dump(mode="json", by_alias=True),
            "scores": event_scores,
            "model": "TC-EXPOSURE-v0.1",
        }
        calculation_hash = hashlib.sha256(
            json.dumps(calculation_payload, sort_keys=True).encode()
        ).hexdigest()
        analysis = AnalysisDocument(
            id=analysis_id,
            analysis_id=analysis_id,
            status="completed",
            created_at=created,
            created_by=created_by,
            input=analysis_input,
            vessel=vessel,
            risk=risk,
            statistics=AnalysisStatistics(
                ais_observation_count=generator.randint(8_000, 95_000),
                observed_days=observed_days,
                named_storm_encounters=encounter_count,
                hours_within_200_nm=hours_total,
                hours_within_34_kt_wind_field=hours_wind,
                minimum_distance_nm=min(
                    (item.closest_approach.distance_nm for item in encounters),
                    default=None,
                ),
                distance_travelled_nm=round(generator.uniform(18_000, 160_000), 1),
                average_speed_kt=round(generator.uniform(8, 17), 1),
                maximum_speed_kt=round(generator.uniform(17, 27), 1),
            ),
            encounter_ids=[item.id for item in encounters],
            data_quality=DataQuality(
                rating=confidence,
                identity_confidence="HIGH" if analysis_input.identifier_type == "IMO" else confidence,
                years_covered=list(range(analysis_input.period.from_date.year, analysis_input.period.to_date.year + 1)),
                significant_storm_period_gaps=gaps,
                warnings=warnings,
            ),
            sources=[
                SourceReference(
                    provider="MCI POC",
                    dataset="Synthetic AIS and NOAA-compatible storm fixture",
                    retrieved_at=completed,
                )
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

    def _make_encounter(
        self,
        generator: random.Random,
        analysis_id: str,
        index: int,
        period: DatePeriod,
    ) -> EncounterDocument:
        distance = round(generator.uniform(12, 198), 1)
        wind = generator.choice([40, 52, 67, 78, 91, 104, 121, 142])
        if distance < 45 and wind >= 64:
            field = generator.choice(["50KT", "64KT"])
        elif distance < 95:
            field = generator.choice(["34KT", "50KT", "OUTSIDE 34KT"])
        else:
            field = "OUTSIDE 34KT"
        duration = round(generator.uniform(0.5, 31), 1)
        event_risk = score_encounter(
            EncounterInputs(
                distance_nm=distance,
                maximum_wind_kt=wind,
                strongest_wind_field=field,
                duration_hours=duration,
            )
        )
        start = datetime.combine(period.from_date, datetime.min.time(), tzinfo=timezone.utc)
        end = datetime.combine(period.to_date, datetime.min.time(), tzinfo=timezone.utc)
        timestamp = start + timedelta(seconds=generator.randint(0, max(1, int((end - start).total_seconds()))))
        vessel_lon, vessel_lat = generator.choice(COASTAL_POSITIONS)
        storm_lon = vessel_lon + generator.uniform(-1.8, 1.8)
        storm_lat = vessel_lat + generator.uniform(-1.8, 1.8)
        category = _category_for_wind(wind)
        classification = "HU" if wind >= 64 else "TS"
        encounter_id = f"encounter_{index + 1:03d}"
        return EncounterDocument(
            id=encounter_id,
            analysis_id=analysis_id,
            storm=StormDetails(
                id=f"DEMO{index + 1:02d}{timestamp.year}",
                name=STORM_NAMES[index % len(STORM_NAMES)],
                classification=classification,
                category=category,
            ),
            closest_approach=ClosestApproach(
                timestamp=timestamp,
                distance_nm=distance,
                vessel_position=Position(coordinates=(vessel_lon, vessel_lat)),
                storm_position=Position(coordinates=(storm_lon, storm_lat)),
            ),
            exposure=EncounterExposure(
                duration_within_200_nm_hours=duration,
                strongest_wind_field=field,
                maximum_storm_wind_kt=wind,
            ),
            risk=event_risk,
        )


def seed_demo_portfolio(repository: AnalysisRepository, count: int = 248) -> None:
    if repository.list_analyses("mci"):
        return
    service = DemoAnalysisService(repository)
    now = datetime.now(timezone.utc)
    for index in range(count):
        mmsi = str(200_000_000 + index).zfill(9)
        service.analyse(
            AnalysisInput(
                identifier_type="MMSI",
                identifier=mmsi,
                period=DatePeriod(from_date=date(2021, 1, 1), to_date=date(2025, 12, 31)),
            ),
            "demo-seed@mciuw.com",
            created_at=now - timedelta(days=(index * 3) % 365, hours=index % 19),
            seed_suffix=f"seed-{index}",
        )


def dashboard_summary(analyses: list[AnalysisDocument]) -> dict[str, Any]:
    band_order = ["LOW", "MODERATE", "ELEVATED", "HIGH", "SEVERE"]
    bands = Counter(item.risk.band for item in analyses)
    confidence = Counter(item.risk.confidence for item in analyses)
    vessel_types = Counter(item.vessel.vessel_type for item in analyses)
    monthly: dict[str, int] = defaultdict(int)
    for item in analyses:
        monthly[item.created_at.strftime("%Y-%m")] += 1
    month_keys = sorted(monthly)[-12:]
    total = len(analyses)
    average = round(sum(item.risk.score for item in analyses) / total) if total else 0
    encounters = sum(item.statistics.named_storm_encounters for item in analyses)
    return {
        "total": total,
        "averageScore": average,
        "highOrSevere": bands["HIGH"] + bands["SEVERE"],
        "encounters": encounters,
        "highConfidencePercent": round((confidence["HIGH"] / total) * 100) if total else 0,
        "bands": [{"name": name, "count": bands[name]} for name in band_order],
        "vesselTypes": [
            {"name": name, "count": count}
            for name, count in vessel_types.most_common()
        ],
        "months": [
            {"label": datetime.strptime(key, "%Y-%m").strftime("%b"), "count": monthly[key]}
            for key in month_keys
        ],
    }


def _category_for_wind(wind_kt: int) -> int | None:
    if wind_kt >= 137:
        return 5
    if wind_kt >= 113:
        return 4
    if wind_kt >= 96:
        return 3
    if wind_kt >= 83:
        return 2
    if wind_kt >= 64:
        return 1
    return None


def _valid_demo_imo(generator: random.Random) -> str:
    first_six = str(generator.randint(1_000_000, 9_999_999))[:6]
    checksum = sum(int(digit) * weight for digit, weight in zip(first_six, range(7, 1, -1))) % 10
    return first_six + str(checksum)
