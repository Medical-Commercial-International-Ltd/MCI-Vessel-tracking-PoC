"""NOAA map overlays, centred on each encounter and separate from risk calculations."""
from datetime import datetime, timedelta, timezone
import math

from app.ais_data import MarineCadastreTrackStore, TimedPosition, bearing_degrees, haversine_nm, interpolate_position, segment_position_lines
from app.hurdat import load_hurdat_storms


def destination(longitude, latitude, bearing, distance_nm):
    angular = distance_nm / 3440.065
    lat, lon, angle = map(math.radians, (latitude, longitude, bearing))
    result_lat = math.asin(math.sin(lat) * math.cos(angular) + math.cos(lat) * math.sin(angular) * math.cos(angle))
    result_lon = lon + math.atan2(math.sin(angle) * math.sin(angular) * math.cos(lat),
                                  math.cos(angular) - math.sin(lat) * math.sin(result_lat))
    return [((math.degrees(result_lon) + 180) % 360) - 180, math.degrees(result_lat)]


def wind_sectors(point):
    result = []
    for speed, radii in ((34, point.radii_34), (50, point.radii_50), (64, point.radii_64)):
        for quadrant, radius in enumerate(radii):
            if radius <= 0:
                continue
            center = [point.longitude, point.latitude]
            boundary = [destination(*center, bearing, radius)
                        for bearing in range(quadrant * 90, (quadrant + 1) * 90 + 1, 5)]
            result.append({"speedKt": speed, "quadrant": quadrant, "radiusNm": radius,
                           "coordinates": [center, *boundary, center]})
    return result


def _thin(points, limit=6000):
    if len(points) <= limit:
        return points
    return [points[round(index * (len(points) - 1) / (limit - 1))] for index in range(limit)]


def playback_path(timed_lines, edges, anchor, start, end):
    """A display-only path. Unknown legs are flagged; never extrapolate beyond known anchors."""
    points = {point.timestamp: point for line in timed_lines for point in line}
    for left, right, _ in edges:
        points[left.timestamp] = left
        points[right.timestamp] = right
    points[anchor.timestamp] = anchor
    ordered = sorted(points.values(), key=lambda point: point.timestamp)
    # Retain one anchor outside each window boundary, allowing interpolation to that boundary.
    before = [point for point in ordered if point.timestamp < start]
    after = [point for point in ordered if point.timestamp > end]
    ordered = [*(before[-1:] if before else []),
               *(point for point in ordered if start <= point.timestamp <= end),
               *(after[:1] if after else [])]
    result, gaps = [], []
    for index, point in enumerate(ordered):
        record = {"timestamp": point.timestamp.isoformat(), "coordinates": [point.longitude, point.latitude],
                  "gapToNext": False, "speedKt": None, "headingDeg": None}
        if index + 1 < len(ordered):
            right = ordered[index + 1]
            clipped_start, clipped_end = max(start, point.timestamp), min(end, right.timestamp)
            supported = any(left.timestamp <= clipped_start and edge_end.timestamp >= clipped_end
                            for left, edge_end, _ in edges)
            record["gapToNext"] = not supported
            hours = (right.timestamp - point.timestamp).total_seconds() / 3600
            record["speedKt"] = round(haversine_nm(point.latitude, point.longitude, right.latitude, right.longitude) / hours, 1)
            record["headingDeg"] = round(bearing_degrees(point.latitude, point.longitude, right.latitude, right.longitude), 1)
            if not supported and clipped_start < clipped_end:
                count = max(1, math.ceil((clipped_end - clipped_start).total_seconds() / 300))
                interpolated = [interpolate_position(point, right, clipped_start + (clipped_end - clipped_start) * (step / count))
                                for step in range(count + 1)]
                gaps.append([[position.longitude, position.latitude] for position in interpolated])
        result.append(record)
    return result, gaps


def build_map_data(analysis, encounters, cache_dir):
    events = []
    storms = {}
    if not analysis.is_synthetic:
        storms = {storm.storm_id: storm for storm in load_hurdat_storms(
            [cache_dir / "storms" / f"hurdat2-{basin}.txt" for basin in ("atlantic", "pacific")],
            analysis.input.period.from_date.year - 1, analysis.input.period.to_date.year)}
    store = MarineCadastreTrackStore(cache_dir)
    for encounter in encounters:
        timestamp = encounter.closest_approach.timestamp
        event = {"id": encounter.id, "name": encounter.storm.name, "stormId": encounter.storm.id,
                 "vessel": list(encounter.closest_approach.vessel_position.coordinates),
                 "storm": list(encounter.closest_approach.storm_position.coordinates),
                 "distanceNm": encounter.closest_approach.distance_nm, "timestamp": timestamp.isoformat(),
                 "vesselTracks": [], "vesselSamples": [], "vesselPlaybackPoints": [], "vesselGapTracks": [], "stormTrack": [], "frames": [],
                 "frameStepMinutes": 5, "synthetic": analysis.is_synthetic}
        storm = storms.get(encounter.storm.id)
        if storm is not None:
            start = max(timestamp - timedelta(hours=24), storm.start, datetime.combine(
                analysis.input.period.from_date, datetime.min.time(), timezone.utc))
            end = min(timestamp + timedelta(hours=24), storm.end, datetime.combine(
                analysis.input.period.to_date, datetime.max.time(), timezone.utc))
            segments = store.load_segments(analysis.vessel.mmsi[0], start.date(), end.date())
            timed_lines = [line for segment in segments for line in segment_position_lines(segment)]
            edges = []
            sample_points = []
            for line_index, line in enumerate(timed_lines):
                current = []
                part_index = 0
                sample_points.extend({"timestamp": point.timestamp.isoformat(),
                                      "coordinates": [point.longitude, point.latitude]}
                                     for point in line if start <= point.timestamp <= end)
                for left, right in zip(line, line[1:]):
                    if right.timestamp <= start or left.timestamp >= end or right.timestamp <= left.timestamp:
                        continue
                    if right.timestamp - left.timestamp > timedelta(hours=6):
                        if len(current) > 1:
                            event["vesselTracks"].append(_thin(current))
                        current = []
                        part_index += 1
                        continue
                    left, right = (interpolate_position(left, right, max(left.timestamp, start)),
                                   interpolate_position(left, right, min(right.timestamp, end)))
                    edges.append((left, right, f"{line_index}:{part_index}"))
                    if not current:
                        current.append([left.longitude, left.latitude])
                    current.append([right.longitude, right.latitude])
                if len(current) > 1:
                    event["vesselTracks"].append(_thin(current))
            event["vesselSampleCount"] = len(sample_points)
            event["vesselSamples"] = _thin(sample_points, limit=3000)
            anchor = TimedPosition(timestamp, event["vessel"][0], event["vessel"][1])
            event["vesselPlaybackPoints"], event["vesselGapTracks"] = playback_path(timed_lines, edges, anchor, start, end)
            event["stormTrack"] = [{"coordinates": [point.longitude, point.latitude],
                                     "timestamp": point.timestamp.isoformat(), "windKt": point.wind_kt,
                                     "status": point.status} for point in storm.points]
            times = {timestamp, start, end, *(point.timestamp for point in storm.points if start <= point.timestamp <= end)}
            cursor = start
            while cursor <= end:
                times.add(cursor)
                cursor += timedelta(minutes=5)
            times = sorted(times)
            for frame_time in times:
                point = storm.at(frame_time)
                if point is None:
                    continue
                vessel = None
                path_id = speed = heading = None
                for left, right, edge_id in edges:
                    if left.timestamp <= frame_time <= right.timestamp:
                        position = interpolate_position(left, right, frame_time)
                        vessel = [position.longitude, position.latitude]
                        path_id = edge_id
                        hours = (right.timestamp - left.timestamp).total_seconds() / 3600
                        speed = round(haversine_nm(left.latitude, left.longitude, right.latitude, right.longitude) / hours, 1)
                        heading = round(bearing_degrees(left.latitude, left.longitude, right.latitude, right.longitude), 1)
                        break
                if frame_time == timestamp:
                    vessel = event["vessel"]
                event["frames"].append({"timestamp": frame_time.isoformat(), "storm": [point.longitude, point.latitude],
                                        "vessel": vessel, "windKt": point.wind_kt, "status": point.status,
                                        "vesselPathId": path_id, "vesselSpeedKt": speed, "vesselHeadingDeg": heading,
                                        "distanceNm": round(haversine_nm(vessel[1], vessel[0], point.latitude, point.longitude), 1) if vessel else None,
                                        "windSectors": wind_sectors(point),
                                        "missingRadii": any(radius < 0 for radii in
                                            (point.radii_34, point.radii_50, point.radii_64) for radius in radii)})
        events.append(event)
    return events
