"""Search recorded AIS positions near ports and NHC storm tracks."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from app.ais_data import TrackSegment, _decode_gpkg_multiline, _parse_datetime, haversine_nm, segment_positions
from app.hurdat import HurdatStorm, load_hurdat_storms


@dataclass(frozen=True)
class LookupWindow:
    start: datetime
    end: datetime
    min_lon: float
    max_lon: float
    min_lat: float
    max_lat: float


@dataclass(frozen=True)
class LookupResult:
    mmsi: str
    name: str
    vessel_group: str
    vessel_type_code: int | None
    length_m: float | None
    timestamp: datetime
    distance_nm: float
    storm_distance_nm: float | None = None
    port_distance_nm: float | None = None


@dataclass(frozen=True)
class LookupResponse:
    results: list[LookupResult]
    inspected_segments: int
    truncated: bool


class EventLookupService:
    MAX_SEGMENTS = 100_000

    def __init__(self, cache_dir: Path, port_file: Path):
        self.cache_dir = cache_dir
        self.track_dir = cache_dir / "tracks"
        self.registry_file = cache_dir / "vessels" / "registry.json"
        self.port_file = port_file
        self.storm_paths = [
            cache_dir / "storms" / "hurdat2-atlantic.txt",
            cache_dir / "storms" / "hurdat2-pacific.txt",
        ]

    @property
    def years(self) -> list[int]:
        return sorted(
            int(match.group(1))
            for path in self.track_dir.glob("AISVesselTracks*.gpkg")
            if (match := re.search(r"(20\d{2})", path.stem))
        )

    def storms(self) -> list[HurdatStorm]:
        years = self.years
        if not years:
            return []
        return load_hurdat_storms(self.storm_paths, min(years), max(years))

    def ports(self) -> list[dict]:
        if not self.port_file.exists():
            return []
        return json.loads(self.port_file.read_text(encoding="utf-8"))["ports"]

    @lru_cache(maxsize=1)
    def vessel_groups(self) -> list[str]:
        """Read the AIS category vocabulary from the latest cached monthly table."""
        groups: set[str] = set()
        years = self.years
        if not years:
            return []
        path = self.track_dir / f"AISVesselTracks{years[-1]}.gpkg"
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            tables = [row[0] for row in connection.execute(
                "SELECT table_name FROM gpkg_contents WHERE data_type = 'features' ORDER BY table_name"
            )]
            if tables:
                quoted = _quote(tables[0])
                groups.update(
                    str(row[0]).strip() for row in connection.execute(
                        f"SELECT DISTINCT VesselGroup FROM {quoted}"
                    ) if row[0]
                )
        return sorted(groups)

    def search(
        self,
        *,
        selected_date: date | None,
        port_id: str | None,
        storm_id: str | None,
        radius_nm: float,
        vessel_group: str | None,
        min_length_m: float | None,
        yacht_candidates: bool,
    ) -> LookupResponse:
        if not 1 <= radius_nm <= 500:
            raise ValueError("Distance must be between 1 and 500 nautical miles.")
        if min_length_m is not None and not 0 <= min_length_m <= 500:
            raise ValueError("Minimum vessel length must be between 0 and 500 metres.")
        if vessel_group and vessel_group not in self.vessel_groups():
            raise ValueError("Choose an available AIS vessel type.")

        if not port_id and not storm_id:
            raise ValueError("Choose a storm, a port, or both.")
        port = next((item for item in self.ports() if item["id"] == port_id), None) if port_id else None
        storm = next((item for item in self.storms() if item.storm_id == storm_id), None) if storm_id else None
        if port_id and port is None:
            raise ValueError("Choose a listed port.")
        if storm_id and storm is None:
            raise ValueError("Choose a listed storm.")
        if storm:
            windows = _storm_windows(storm, selected_date, radius_nm)
            if not windows:
                raise ValueError("The selected date is outside this storm's recorded track.")
            if port:
                coordinate = port["coordinates"]
                windows = [
                    intersection
                    for window in windows
                    if (intersection := _intersect_windows(
                        window,
                        _window(window.start, window.end, coordinate[0], coordinate[0],
                                coordinate[1], coordinate[1], radius_nm),
                    )) is not None
                ]
        else:
            if selected_date is None:
                raise ValueError("Choose a date for a port-only search.")
            coordinate = port["coordinates"]
            start = datetime.combine(selected_date, time.min, timezone.utc)
            end = start + timedelta(days=1)
            windows = [_window(start, end, coordinate[0], coordinate[0], coordinate[1], coordinate[1], radius_nm)]

        names = self._names()
        results: dict[str, LookupResult] = {}
        seen: set[tuple[int, str, int]] = set()
        inspected = 0
        truncated = False
        effective_length = max(min_length_m or 0, 24) if yacht_candidates else min_length_m
        for year in self.years:
            path = self.track_dir / f"AISVesselTracks{year}.gpkg"
            year_windows = [window for window in windows if window.start.year <= year <= window.end.year]
            if not year_windows:
                continue
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30) as connection:
                tables = [row[0] for row in connection.execute(
                    "SELECT table_name FROM gpkg_contents WHERE data_type = 'features'"
                )]
                for table in tables:
                    for window in year_windows:
                        if not _table_overlaps_window(table, year, window):
                            continue
                        quoted = _quote(table)
                        rtree = _quote(f"rtree_{table}_Shape")
                        where = [
                            "r.minX <= ?", "r.maxX >= ?", "r.minY <= ?", "r.maxY >= ?",
                            "t.TrackEndTime >= ?", "t.TrackStartTime < ?",
                            "t.MMSI BETWEEN 200000000 AND 799999999",
                        ]
                        params: list = [
                            window.max_lon, window.min_lon, window.max_lat, window.min_lat,
                            window.start.strftime("%Y-%m-%dT%H:%M:%S"),
                            window.end.strftime("%Y-%m-%dT%H:%M:%S"),
                        ]
                        if vessel_group:
                            where.append("t.VesselGroup = ?")
                            params.append(vessel_group)
                        if yacht_candidates:
                            where.append("(t.VesselGroup = 'Pleasure Craft/Sailing' OR t.VesselType IN (36, 37))")
                        if effective_length is not None:
                            where.append("t.Length >= ?")
                            params.append(effective_length)
                        query = (
                            f"SELECT t.OBJECTID, t.MMSI, t.Shape, t.TrackStartTime, t.TrackEndTime, "
                            f"t.VesselGroup, t.VesselType, t.Length FROM {quoted} AS t "
                            f"JOIN {rtree} AS r ON t.OBJECTID = r.id WHERE " + " AND ".join(where)
                        )
                        for row in connection.execute(query, params):
                            object_id, raw_mmsi, shape, raw_start, raw_end, group, type_code, length = row
                            key = (year, table, object_id)
                            if key in seen:
                                continue
                            seen.add(key)
                            if inspected >= self.MAX_SEGMENTS:
                                truncated = True
                                break
                            inspected += 1
                            segment = TrackSegment(
                                start=_parse_datetime(raw_start), end=_parse_datetime(raw_end),
                                lines=_decode_gpkg_multiline(bytes(shape)),
                                vessel_group=group or "Unknown",
                                vessel_type_code=int(type_code) if type_code is not None else None,
                                length_m=float(length) if length is not None else None,
                                width_m=None, draft_m=None,
                            )
                            match = _closest_match(segment, window, storm, port, radius_nm)
                            if match is None:
                                continue
                            distance, timestamp, storm_distance, port_distance = match
                            mmsi = str(raw_mmsi)
                            candidate = LookupResult(
                                mmsi=mmsi, name=names.get(mmsi, f"MMSI {mmsi}"),
                                vessel_group=segment.vessel_group,
                                vessel_type_code=segment.vessel_type_code,
                                length_m=segment.length_m, timestamp=timestamp,
                                distance_nm=distance,
                                storm_distance_nm=storm_distance,
                                port_distance_nm=port_distance,
                            )
                            if mmsi not in results or distance < results[mmsi].distance_nm:
                                results[mmsi] = candidate
                        if truncated:
                            break
                    if truncated:
                        break
            if truncated:
                break
        return LookupResponse(
            results=sorted(results.values(), key=lambda item: (item.distance_nm, item.mmsi)),
            inspected_segments=inspected,
            truncated=truncated,
        )

    def _names(self) -> dict[str, str]:
        if not self.registry_file.exists():
            return {}
        payload = json.loads(self.registry_file.read_text(encoding="utf-8"))
        return {str(item["mmsi"]): item["name"] for item in payload.get("vessels", []) if item.get("name")}


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _window(start, end, min_lon, max_lon, min_lat, max_lat, radius_nm):
    lat_pad = radius_nm / 60 + 0.05
    latitude = max(abs(min_lat), abs(max_lat)) + lat_pad
    lon_pad = min(180, radius_nm / max(1, 60 * math.cos(math.radians(min(latitude, 89)))) + 0.05)
    return LookupWindow(start, end, max(-180, min_lon - lon_pad), min(180, max_lon + lon_pad),
                        max(-90, min_lat - lat_pad), min(90, max_lat + lat_pad))


def _intersect_windows(left: LookupWindow, right: LookupWindow) -> LookupWindow | None:
    overlap = LookupWindow(
        max(left.start, right.start), min(left.end, right.end),
        max(left.min_lon, right.min_lon), min(left.max_lon, right.max_lon),
        max(left.min_lat, right.min_lat), min(left.max_lat, right.max_lat),
    )
    if (overlap.start >= overlap.end or overlap.min_lon > overlap.max_lon
            or overlap.min_lat > overlap.max_lat):
        return None
    return overlap


def _storm_windows(storm: HurdatStorm, selected_date: date | None, radius_nm: float) -> list[LookupWindow]:
    by_day: dict[date, list[LookupWindow]] = {}
    for left, right in zip(storm.points, storm.points[1:]):
        if right.timestamp - left.timestamp > timedelta(hours=12):
            continue
        days = {left.timestamp.date(), right.timestamp.date()}
        for day in days:
            if selected_date is not None and day != selected_date:
                continue
            day_start = datetime.combine(day, time.min, timezone.utc)
            day_end = day_start + timedelta(days=1)
            window = _window(max(left.timestamp, day_start),
                             min(right.timestamp + timedelta(seconds=1), day_end),
                             min(left.longitude, right.longitude), max(left.longitude, right.longitude),
                             min(left.latitude, right.latitude), max(left.latitude, right.latitude), radius_nm)
            by_day.setdefault(day, []).append(window)
    return [
        LookupWindow(
            min(item.start for item in items), max(item.end for item in items),
            min(item.min_lon for item in items), max(item.max_lon for item in items),
            min(item.min_lat for item in items), max(item.max_lat for item in items),
        )
        for _, items in sorted(by_day.items())
    ]


def _table_overlaps_window(table: str, year: int, window: LookupWindow) -> bool:
    match = re.search(r"_(\d{2})$", table)
    if not match:
        return True
    month = int(match.group(1))
    first = datetime(year, month, 1, tzinfo=timezone.utc)
    last = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=timezone.utc)
    return first < window.end and last > window.start


def _closest_match(
    segment: TrackSegment,
    window: LookupWindow,
    storm: HurdatStorm | None,
    port: dict | None,
    radius_nm: float,
):
    positions = segment_positions(segment)
    closest = None
    for index, position in enumerate(positions):
        samples = [position]
        if index + 1 < len(positions):
            following = positions[index + 1]
            if following.timestamp - position.timestamp <= timedelta(hours=6):
                for fraction in (0.25, 0.5, 0.75):
                    samples.append(type(position)(
                        timestamp=position.timestamp + (following.timestamp - position.timestamp) * fraction,
                        longitude=position.longitude + (following.longitude - position.longitude) * fraction,
                        latitude=position.latitude + (following.latitude - position.latitude) * fraction,
                    ))
        for sample in samples:
            if not window.start <= sample.timestamp < window.end:
                continue
            storm_distance = None
            if storm:
                target = storm.at(sample.timestamp)
                if target is None:
                    continue
                storm_distance = haversine_nm(
                    sample.latitude, sample.longitude, target.latitude, target.longitude,
                )
                if storm_distance > radius_nm:
                    continue
            port_distance = None
            if port:
                port_distance = haversine_nm(
                    sample.latitude, sample.longitude,
                    port["coordinates"][1], port["coordinates"][0],
                )
                if port_distance > radius_nm:
                    continue
            distance = max(value for value in (storm_distance, port_distance) if value is not None)
            if closest is None or distance < closest[0]:
                closest = (distance, sample.timestamp, storm_distance, port_distance)
    return closest
