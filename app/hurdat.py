from __future__ import annotations

import csv
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class HurdatPoint:
    timestamp: datetime
    latitude: float
    longitude: float
    status: str
    wind_kt: int
    radii_34: tuple[float, float, float, float]
    radii_50: tuple[float, float, float, float]
    radii_64: tuple[float, float, float, float]


@dataclass(frozen=True)
class InterpolatedStormPoint:
    timestamp: datetime
    latitude: float
    longitude: float
    status: str
    wind_kt: int
    radii_34: tuple[float, float, float, float]
    radii_50: tuple[float, float, float, float]
    radii_64: tuple[float, float, float, float]


@dataclass(frozen=True)
class HurdatStorm:
    storm_id: str
    name: str
    basin: str
    points: tuple[HurdatPoint, ...]

    @property
    def start(self) -> datetime:
        return self.points[0].timestamp

    @property
    def end(self) -> datetime:
        return self.points[-1].timestamp

    def at(self, timestamp: datetime) -> InterpolatedStormPoint | None:
        if timestamp < self.start or timestamp > self.end:
            return None
        times = [point.timestamp for point in self.points]
        right_index = bisect_right(times, timestamp)
        if right_index == 0:
            return _as_interpolated(self.points[0], timestamp)
        if right_index >= len(self.points):
            return _as_interpolated(self.points[-1], timestamp)
        left = self.points[right_index - 1]
        right = self.points[right_index]
        seconds = (right.timestamp - left.timestamp).total_seconds()
        if seconds <= 0 or seconds > 12 * 60 * 60:
            return None
        fraction = (timestamp - left.timestamp).total_seconds() / seconds
        longitude_delta = right.longitude - left.longitude
        if longitude_delta > 180:
            longitude_delta -= 360
        elif longitude_delta < -180:
            longitude_delta += 360
        longitude = left.longitude + longitude_delta * fraction
        if longitude > 180:
            longitude -= 360
        if longitude < -180:
            longitude += 360
        return InterpolatedStormPoint(
            timestamp=timestamp,
            latitude=_lerp(left.latitude, right.latitude, fraction),
            longitude=longitude,
            status=left.status if fraction < 0.5 else right.status,
            wind_kt=round(_lerp(left.wind_kt, right.wind_kt, fraction)),
            radii_34=_interpolate_radii(left.radii_34, right.radii_34, fraction),
            radii_50=_interpolate_radii(left.radii_50, right.radii_50, fraction),
            radii_64=_interpolate_radii(left.radii_64, right.radii_64, fraction),
        )


def load_hurdat_storms(
    paths: list[Path],
    start_year: int,
    end_year: int,
) -> list[HurdatStorm]:
    return list(_load_hurdat_storms(tuple(str(path.resolve()) for path in paths), start_year, end_year))


@lru_cache(maxsize=8)
def _load_hurdat_storms(
    paths: tuple[str, ...],
    start_year: int,
    end_year: int,
) -> tuple[HurdatStorm, ...]:
    storms: list[HurdatStorm] = []
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = iter(csv.reader(handle))
            for row in rows:
                if len(row) < 3:
                    continue
                storm_id = row[0].strip().upper()
                if len(storm_id) < 8 or not storm_id[-4:].isdigit():
                    continue
                year = int(storm_id[-4:])
                try:
                    point_count = int(row[2].strip())
                except ValueError:
                    continue
                name = row[1].strip().upper() or "UNNAMED"
                point_rows = [next(rows, []) for _ in range(point_count)]
                if year < start_year or year > end_year:
                    continue
                points = tuple(point for values in point_rows if (point := _parse_point(values)) is not None)
                if points:
                    storms.append(
                        HurdatStorm(
                            storm_id=storm_id,
                            name=name,
                            basin=storm_id[:2],
                            points=points,
                        )
                    )
    return tuple(sorted(storms, key=lambda storm: storm.start))


def category_for_wind(wind_kt: int) -> int | None:
    if wind_kt < 64:
        return None
    if wind_kt < 83:
        return 1
    if wind_kt < 96:
        return 2
    if wind_kt < 113:
        return 3
    if wind_kt < 137:
        return 4
    return 5


def _parse_point(row: list[str]) -> HurdatPoint | None:
    if len(row) < 8:
        return None
    try:
        timestamp = datetime.strptime(row[0].strip() + row[1].strip().zfill(4), "%Y%m%d%H%M").replace(
            tzinfo=timezone.utc
        )
        latitude = _parse_coordinate(row[4])
        longitude = _parse_coordinate(row[5])
        wind_kt = max(0, int(row[6].strip()))
    except (ValueError, TypeError):
        return None
    return HurdatPoint(
        timestamp=timestamp,
        latitude=latitude,
        longitude=longitude,
        status=row[3].strip().upper() or "XX",
        wind_kt=wind_kt,
        radii_34=_parse_radii(row, 8),
        radii_50=_parse_radii(row, 12),
        radii_64=_parse_radii(row, 16),
    )


def _parse_coordinate(raw: str) -> float:
    value = raw.strip().upper()
    direction = value[-1]
    coordinate = float(value[:-1])
    return -coordinate if direction in {"S", "W"} else coordinate


def _parse_radii(row: list[str], offset: int) -> tuple[float, float, float, float]:
    values: list[float] = []
    for index in range(offset, offset + 4):
        try:
            value = float(row[index].strip())
        except (IndexError, ValueError):
            value = 0
        values.append(max(0, value))
    return tuple(values)  # type: ignore[return-value]


def _lerp(left: float, right: float, fraction: float) -> float:
    return left + (right - left) * fraction


def _interpolate_radii(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
    fraction: float,
) -> tuple[float, float, float, float]:
    values = []
    for left_value, right_value in zip(left, right):
        if left_value > 0 and right_value > 0:
            values.append(_lerp(left_value, right_value, fraction))
        else:
            values.append(left_value if fraction < 0.5 else right_value)
    return tuple(values)  # type: ignore[return-value]


def _as_interpolated(point: HurdatPoint, timestamp: datetime) -> InterpolatedStormPoint:
    return InterpolatedStormPoint(
        timestamp=timestamp,
        latitude=point.latitude,
        longitude=point.longitude,
        status=point.status,
        wind_kt=point.wind_kt,
        radii_34=point.radii_34,
        radii_50=point.radii_50,
        radii_64=point.radii_64,
    )
