"""Compare a saved real assessment with an independent one-minute integration.

Reads the same cached source tracks, without saving or changing assessments.
Controlled tests separately cover source date clipping and interval de-duplication.
"""
from __future__ import annotations

import argparse
import json
import math

from app.config import get_settings
from app.exposure import track_intervals
from app.hurdat import load_hurdat_storms
from app.ais_data import MarineCadastreTrackStore, segment_positions
from app.repositories import FileAnalysisRepository


def distance_nm(lat1, lon1, lat2, lon2):
    # Independent spherical-vector distance (production uses haversine).
    a, b, delta = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    dot = math.sin(a) * math.sin(b) + math.cos(a) * math.cos(b) * math.cos(delta)
    return 3440.065 * math.acos(max(-1, min(1, dot)))


def verify(analysis_id):
    settings = get_settings()
    analysis = FileAnalysisRepository(settings.analyses_dir).get_analysis("mci", analysis_id)
    if analysis is None or analysis.is_synthetic:
        raise ValueError("Supply the ID of a saved real-data assessment")
    request = analysis.input
    segments = MarineCadastreTrackStore(settings.ais_cache_dir).load_segments(
        analysis.vessel.mmsi[0], request.period.from_date, request.period.to_date)
    intervals = track_intervals(segments)
    storms = load_hurdat_storms([settings.ais_cache_dir / "storms" / f"hurdat2-{basin}.txt"
                               for basin in ("atlantic", "pacific")],
                              request.period.from_date.year - 1, request.period.to_date.year)
    storms = [storm for storm in storms if storm.name.upper() not in {"UNNAMED", "NOT NAMED", "UNKNOWN"}]
    positions = {(point.timestamp, round(point.longitude, 6), round(point.latitude, 6)): point
                 for segment in segments for point in segment_positions(segment)}
    encountered = set()
    closest = None
    for point in positions.values():
        for storm in storms:
            storm_point = storm.at(point.timestamp)
            if storm_point is None:
                continue
            separation = distance_nm(point.latitude, point.longitude, storm_point.latitude, storm_point.longitude)
            if separation <= request.storm_proximity_nm:
                encountered.add(storm.storm_id)
                closest = separation if closest is None else min(closest, separation)
    distance, hours, speeds = 0, 0, []
    exposure_seconds, wind_seconds = 0, 0
    for left, right in intervals:
        seconds = (right.timestamp - left.timestamp).total_seconds()
        travelled = distance_nm(left.latitude, left.longitude, right.latitude, right.longitude)
        distance += travelled
        hours += seconds / 3600
        speeds.append(travelled / (seconds / 3600))
        if seconds > 6 * 3600:
            continue
        active = [storm for storm in storms if storm.start <= right.timestamp and storm.end >= left.timestamp]
        if not active:
            continue
        steps = max(1, math.ceil(seconds / 60))
        for step in range(steps):
            fraction = (step + 0.5) / steps
            timestamp = left.timestamp + (right.timestamp - left.timestamp) * fraction
            latitude = left.latitude + (right.latitude - left.latitude) * fraction
            longitude = (left.longitude + ((right.longitude - left.longitude + 180) % 360 - 180) * fraction + 180) % 360 - 180
            exposed = windy = False
            for storm in active:
                point = storm.at(timestamp)
                if point is None:
                    continue
                separation = distance_nm(latitude, longitude, point.latitude, point.longitude)
                if separation > request.storm_proximity_nm:
                    continue
                encountered.add(storm.storm_id)
                closest = separation if closest is None else min(closest, separation)
                exposed = True
                lat1, lat2, delta = math.radians(point.latitude), math.radians(latitude), math.radians(longitude - point.longitude)
                bearing = math.degrees(math.atan2(math.sin(delta) * math.cos(lat2),
                    math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta))) % 360
                quadrant = int(bearing // 90)
                windy |= any(radii[quadrant] > 0 and separation <= radii[quadrant]
                             for radii in (point.radii_34, point.radii_50, point.radii_64))
            exposure_seconds += seconds / steps if exposed else 0
            wind_seconds += seconds / steps if windy else 0
    reference = {
        "ais_observation_count": len(positions),
        "observed_days": len({point.timestamp.date() for point in positions.values()}),
        "named_storm_encounters": len(encountered),
        "minimum_distance_nm": round(closest, 1) if closest is not None else None,
        "distance_travelled_nm": round(distance, 1),
        "average_speed_kt": round(distance / hours, 1) if hours else 0,
        "maximum_speed_kt": round(max(speeds, default=0), 1),
        "hours_within_200_nm": round(exposure_seconds / 3600, 1),
        "hours_within_34_kt_wind_field": round(wind_seconds / 3600, 1),
    }
    actual = analysis.statistics.model_dump()
    comparisons = {key: {"saved": actual[key], "reference": value,
                         "difference": round(actual[key] - value, 3) if value is not None and actual[key] is not None else None}
                   for key, value in reference.items()}
    print(json.dumps({"analysis_id": analysis_id, "reference_step_minutes": 1,
                      "comparisons": comparisons}, indent=2))
    for key, value in reference.items():
        if value is None:
            assert actual[key] is None
            continue
        tolerance = 0 if key in {"ais_observation_count", "observed_days", "named_storm_encounters"} else 0.2
        if abs(actual[key] - value) > tolerance + 1e-9:
            raise AssertionError(f"{key} differs beyond the numerical check tolerance")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis_id")
    verify(parser.parse_args().analysis_id)
