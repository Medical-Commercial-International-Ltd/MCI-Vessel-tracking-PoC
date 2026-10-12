"""Time intervals supported by track geometry; no interpolation across separate tracks."""
from datetime import timedelta
import math

from app.ais_data import haversine_nm, interpolate_position, segment_position_lines


def track_intervals(segments):
    edges = sorted(
        ((left, right) for segment in segments for line in segment_position_lines(segment)
         for left, right in zip(line, line[1:]) if right.timestamp > left.timestamp),
        key=lambda edge: (edge[0].timestamp, edge[1].timestamp),
    )
    result = []
    covered_until = None
    for left, right in edges:
        if covered_until is not None and right.timestamp <= covered_until:
            continue
        if covered_until is not None and left.timestamp < covered_until:
            left = interpolate_position(left, right, covered_until)
        result.append((left, right))
        covered_until = right.timestamp
    return result


def movement_statistics(intervals):
    distances = [haversine_nm(left.latitude, left.longitude, right.latitude, right.longitude)
                 for left, right in intervals]
    hours = [(right.timestamp - left.timestamp).total_seconds() / 3600 for left, right in intervals]
    distance, duration = sum(distances), sum(hours)
    return (round(distance, 1), round(distance / duration, 1) if duration else 0,
            round(max((distance / hour for distance, hour in zip(distances, hours)), default=0), 1))


def sampled_intervals(intervals, step_minutes=5):
    for left, right in intervals:
        duration = right.timestamp - left.timestamp
        if duration > timedelta(hours=6):
            continue
        count = max(1, math.ceil(duration.total_seconds() / (step_minutes * 60)))
        for index in range(count):
            start = left.timestamp + duration * (index / count)
            end = left.timestamp + duration * ((index + 1) / count)
            yield (start, end, interpolate_position(left, right, start + (end - start) / 2),
                   interpolate_position(left, right, start), interpolate_position(left, right, end))


def union_hours(intervals):
    """Measure elapsed time once even when multiple storms or tracks overlap."""
    seconds = 0.0
    current_start = current_end = None
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if current_end is None:
            current_start, current_end = start, end
        elif start <= current_end:
            current_end = max(current_end, end)
        else:
            seconds += (current_end - current_start).total_seconds()
            current_start, current_end = start, end
    if current_end is not None:
        seconds += (current_end - current_start).total_seconds()
    return seconds / 3600


def storm_coverage_gaps(intervals, storms, start, end):
    supported = [(left.timestamp, right.timestamp) for left, right in intervals
                 if right.timestamp - left.timestamp <= timedelta(hours=6)]
    count = 0
    for storm in storms:
        if storm.name.upper() in {"UNNAMED", "NOT NAMED", "UNKNOWN"}:
            continue
        window_start, window_end = max(start, storm.start), min(end, storm.end)
        if window_start >= window_end:
            continue
        cursor = window_start
        gaps = []
        for left, right in supported:
            if right <= window_start or left >= window_end:
                continue
            left, right = max(left, window_start), min(right, window_end)
            if left > cursor:
                gaps.append(left - cursor)
            cursor = max(cursor, right)
        gaps.append(window_end - cursor)
        if any(gap > timedelta(hours=6) for gap in gaps):
            count += 1
    return count
