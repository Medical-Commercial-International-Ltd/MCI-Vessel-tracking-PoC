from __future__ import annotations

import json
import math
import re
import sqlite3
import struct
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class VesselRecord:
    mmsi: str
    name: str
    imo: str | None
    vessel_type_code: int | None
    length_m: float | None
    width_m: float | None
    draft_m: float | None


@dataclass(frozen=True)
class TrackSegment:
    start: datetime
    end: datetime
    lines: tuple[tuple[tuple[float, float], ...], ...]
    vessel_group: str
    vessel_type_code: int | None
    length_m: float | None
    width_m: float | None
    draft_m: float | None

    @property
    def distance_nm(self) -> float:
        return sum(
            haversine_nm(left[1], left[0], right[1], right[0])
            for line in self.lines
            for left, right in zip(line, line[1:])
        )


@dataclass(frozen=True)
class TimedPosition:
    timestamp: datetime
    longitude: float
    latitude: float


class MarineCadastreTrackStore:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.track_dir = cache_dir / "tracks"
        self.registry_path = cache_dir / "vessels" / "registry.json"

    @property
    def available_years(self) -> list[int]:
        years = []
        for path in self.track_dir.glob("AISVesselTracks*.gpkg"):
            match = re.search(r"(20\d{2})", path.stem)
            if match:
                years.append(int(match.group(1)))
        return sorted(set(years))

    def resolve_vessel(self, identifier_type: str, identifier: str) -> VesselRecord | None:
        normalized = identifier.upper().removeprefix("IMO")
        for vessel in self._registry():
            if identifier_type == "MMSI" and vessel.mmsi == normalized:
                return vessel
            if identifier_type == "IMO" and vessel.imo == normalized:
                return vessel
        if identifier_type == "MMSI":
            return VesselRecord(
                mmsi=normalized,
                name=f"MMSI {normalized}",
                imo=None,
                vessel_type_code=None,
                length_m=None,
                width_m=None,
                draft_m=None,
            )
        return None

    def load_segments(self, mmsi: str, from_date: date, to_date: date) -> list[TrackSegment]:
        start = datetime.combine(from_date, datetime.min.time(), tzinfo=timezone.utc)
        end = datetime.combine(to_date, datetime.max.time(), tzinfo=timezone.utc)
        results: list[TrackSegment] = []
        seen: set[tuple[datetime, datetime, bytes]] = set()
        for path in sorted(self.track_dir.glob("AISVesselTracks*.gpkg")):
            match = re.search(r"(20\d{2})", path.stem)
            if not match:
                continue
            year = int(match.group(1))
            if year < from_date.year or year > to_date.year:
                continue
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
            try:
                tables = [
                    row[0]
                    for row in connection.execute(
                        "SELECT table_name FROM gpkg_contents WHERE data_type = 'features'"
                    )
                    if _table_overlaps_period(row[0], year, from_date, to_date)
                ]
                for table_name in tables:
                    quoted = table_name.replace('"', '""')
                    query = (
                        f'SELECT Shape, TrackStartTime, TrackEndTime, VesselType, Length, Width, Draft, VesselGroup '
                        f'FROM "{quoted}" WHERE MMSI = ? AND TrackEndTime >= ? AND TrackStartTime <= ?'
                    )
                    for row in connection.execute(query, (int(mmsi), start.isoformat(), end.isoformat())):
                        geometry, raw_start, raw_end, vessel_type, length, width, draft, group = row
                        segment_start = _parse_datetime(raw_start)
                        segment_end = _parse_datetime(raw_end)
                        key = (segment_start, segment_end, bytes(geometry))
                        if key in seen:
                            continue
                        seen.add(key)
                        lines = _decode_gpkg_multiline(bytes(geometry))
                        if not lines:
                            continue
                        results.append(
                            TrackSegment(
                                start=max(segment_start, start),
                                end=min(segment_end, end),
                                lines=lines,
                                vessel_group=(group or "Unknown").strip() or "Unknown",
                                vessel_type_code=int(vessel_type) if vessel_type is not None else None,
                                length_m=float(length) if length is not None else None,
                                width_m=float(width) if width is not None else None,
                                draft_m=float(draft) if draft is not None else None,
                            )
                        )
            finally:
                connection.close()
        return sorted(results, key=lambda segment: segment.start)

    def _registry(self) -> list[VesselRecord]:
        if not self.registry_path.exists():
            return []
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        records = []
        for item in payload.get("vessels", []):
            raw_imo = item.get("imo")
            records.append(
                VesselRecord(
                    mmsi=str(item["mmsi"]),
                    name=(item.get("name") or f"MMSI {item['mmsi']}").strip(),
                    imo=str(raw_imo).upper().removeprefix("IMO") if raw_imo else None,
                    vessel_type_code=item.get("vesselType"),
                    length_m=item.get("lengthM"),
                    width_m=item.get("widthM"),
                    draft_m=item.get("draftM"),
                )
            )
        return records


def segment_positions(segment: TrackSegment) -> list[TimedPosition]:
    coordinates = [point for line in segment.lines for point in line]
    if not coordinates:
        return []
    if len(coordinates) == 1 or segment.end <= segment.start:
        longitude, latitude = coordinates[0]
        return [TimedPosition(segment.start, longitude, latitude)]
    cumulative = [0.0]
    for left, right in zip(coordinates, coordinates[1:]):
        cumulative.append(cumulative[-1] + haversine_nm(left[1], left[0], right[1], right[0]))
    total_distance = cumulative[-1]
    duration = (segment.end - segment.start).total_seconds()
    positions = []
    for index, (longitude, latitude) in enumerate(coordinates):
        fraction = cumulative[index] / total_distance if total_distance > 0 else index / (len(coordinates) - 1)
        positions.append(
            TimedPosition(
                timestamp=segment.start + (segment.end - segment.start) * fraction,
                longitude=longitude,
                latitude=latitude,
            )
        )
    return positions


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_nm = 3440.065
    latitude1 = math.radians(lat1)
    latitude2 = math.radians(lat2)
    delta_latitude = math.radians(lat2 - lat1)
    delta_longitude = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_latitude / 2) ** 2
        + math.cos(latitude1) * math.cos(latitude2) * math.sin(delta_longitude / 2) ** 2
    )
    return radius_nm * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0, 1 - value)))


def bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    latitude1 = math.radians(lat1)
    latitude2 = math.radians(lat2)
    delta_longitude = math.radians(lon2 - lon1)
    y = math.sin(delta_longitude) * math.cos(latitude2)
    x = math.cos(latitude1) * math.sin(latitude2) - math.sin(latitude1) * math.cos(latitude2) * math.cos(delta_longitude)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _table_overlaps_period(table_name: str, year: int, from_date: date, to_date: date) -> bool:
    match = re.search(r"_(\d{2})$", table_name)
    if not match:
        return True
    month = int(match.group(1))
    first_month = from_date.month if year == from_date.year else 1
    last_month = to_date.month if year == to_date.year else 12
    return first_month <= month <= last_month


def _parse_datetime(raw: str) -> datetime:
    value = str(raw).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _decode_gpkg_multiline(blob: bytes) -> tuple[tuple[tuple[float, float], ...], ...]:
    if len(blob) < 8 or blob[:2] != b"GP":
        return ()
    flags = blob[3]
    envelope_code = (flags >> 1) & 0b111
    envelope_values = {0: 0, 1: 4, 2: 6, 3: 6, 4: 8}.get(envelope_code, 0)
    offset = 8 + envelope_values * 8
    geometry, _ = _read_wkb(blob, offset)
    if geometry[0] == "MultiLineString":
        return tuple(tuple(line) for line in geometry[1])
    if geometry[0] == "LineString":
        return (tuple(geometry[1]),)
    return ()


def _read_wkb(blob: bytes, offset: int):
    byte_order = blob[offset]
    endian = "<" if byte_order == 1 else ">"
    geometry_type = struct.unpack_from(endian + "I", blob, offset + 1)[0] & 0xFF
    cursor = offset + 5
    if geometry_type == 2:
        point_count = struct.unpack_from(endian + "I", blob, cursor)[0]
        cursor += 4
        points = []
        for _ in range(point_count):
            longitude, latitude = struct.unpack_from(endian + "dd", blob, cursor)
            cursor += 16
            points.append((longitude, latitude))
        return ("LineString", points), cursor
    if geometry_type == 5:
        line_count = struct.unpack_from(endian + "I", blob, cursor)[0]
        cursor += 4
        lines = []
        for _ in range(line_count):
            line, cursor = _read_wkb(blob, cursor)
            if line[0] == "LineString":
                lines.append(line[1])
        return ("MultiLineString", lines), cursor
    raise ValueError(f"Unsupported GeoPackage geometry type {geometry_type}")
