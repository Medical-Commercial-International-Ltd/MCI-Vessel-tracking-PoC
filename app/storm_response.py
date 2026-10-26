"""Versioned response checks using actual NOAA broadcasts, not derived times."""
from bisect import bisect_left
from datetime import datetime, timezone, timedelta
import json
import math
from pathlib import Path

from app.ais_data import TimedPosition, haversine_nm, TrackSegment
from app.models import ResponseWindow, StormResponseAssessment
from app.storm_behaviour import distance


def timestamp(row):
    value = datetime.fromisoformat(row['BaseDateTime'])
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def position(row):
    return TimedPosition(timestamp(row), float(row['LON']), float(row['LAT']))


def valid_observation(row):
    try:
        p = position(row)
        return math.isfinite(p.latitude) and math.isfinite(p.longitude) and -90 <= p.latitude <= 90 and -180 <= p.longitude <= 180
    except (ValueError, KeyError, TypeError, OverflowError):
        return False


def speed(row):
    try:
        return float(row.get('SOG'))
    except (ValueError, TypeError):
        return float('nan')


def moving(row):
    try:
        return 2 < float(row['SOG']) < 50 and 0 <= float(row['COG']) < 360
    except (ValueError, KeyError, TypeError):
        return False


class BroadcastStore:
    def __init__(self, root: Path):
        self.root = root

    def load(self, mmsi, period):
        if not str(mmsi).isdigit() or len(str(mmsi)) != 9:
            return [], []
        path = self.root / f'{mmsi}.json'
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
        else:
            demo = Path(__file__).parent / 'data' / 'storm-demo-broadcasts.json'
            data = json.loads(demo.read_text(encoding='utf-8'))['vessels'].get(mmsi)
            if data is None:
                return [], []
        rows = [r for r in data['rows'] if r.get('MMSI') == mmsi
                and valid_observation(r) and period.from_date <= timestamp(r).date() <= period.to_date]
        dates = [datetime.fromisoformat(d).date() for d in data['sourceDates']
                 if period.from_date <= datetime.fromisoformat(d).date() <= period.to_date]
        return rows, dates


def broadcast_lines(rows):
    lines = []
    for p in sorted({timestamp(r): position(r) for r in rows}.values(), key=lambda p:p.timestamp):
        if not lines or p.timestamp-lines[-1][-1].timestamp > timedelta(minutes=30):
            lines.append([])
        lines[-1].append(p)
    return lines


def overlay_segments(segments, rows, dates):
    """Original observations replace estimated geometry on each covered source day."""
    if not dates:
        return segments
    from app.ais_data import clip_segment
    from datetime import time
    ranges = [(datetime.combine(d,time.min,timezone.utc),datetime.combine(d+timedelta(days=1),time.min,timezone.utc)) for d in sorted(set(dates))]
    retained = []
    for segment in segments:
        pieces = [segment]
        for start,end in ranges:
            next_pieces = []
            for piece in pieces:
                if piece.end < start or piece.start >= end:
                    next_pieces.append(piece)
                else:
                    for lo,hi in ((piece.start,start-timedelta(microseconds=1)),(end,piece.end)):
                        if lo < hi:
                            clipped = clip_segment(piece,lo,hi)
                            if clipped:next_pieces.append(clipped)
            pieces=next_pieces
        retained.extend(pieces)
    for line in broadcast_lines(rows):
        if len(line)>=2:
            retained.append(TrackSegment(line[0].timestamp,line[-1].timestamp,
                (tuple((p.longitude,p.latitude) for p in line),),'Original AIS broadcasts',None,None,None,None,
                clipped_positions=(tuple(line),)))
    return sorted(retained,key=lambda s:s.start)


def assess_response(rows, storms, source_dates=(), proximity_nm=200):
    # This is the exact comparison used for the October 2023 research cases.
    from app.real_services import _wind_field
    rows = [r for r in rows if valid_observation(r)]
    result = StormResponseAssessment(observation_count=len(rows), source_dates=sorted(set(source_dates)))
    if not rows:
        result.findings.append('No original AIS broadcasts cached for this vessel and period. Movement response is unknown; derived track timing is not used as proof.')
        return result
    result.status = 'ASSESSED_PARTIAL'
    result.findings.append('Checks run against cached original broadcasts only. Unobserved dates and gaps remain unknown.')
    best = {}
    for storm in storms:
        points = []
        for row in rows:
            p = position(row)
            # Research comparisons use the best track at the nearest preceding minute.
            weather = storm.at(p.timestamp.replace(second=0, microsecond=0))
            if weather is None or weather.wind_kt < 34 or weather.status not in {'HU', 'TS', 'SS'}:
                continue
            d = distance(p, weather)
            if d <= 100:
                points.append((row, p, d))
        points.sort(key=lambda x: x[1].timestamp)
        times = [p.timestamp.timestamp() for _, p, _ in points]
        gaps = [0]
        for i in range(1, len(points)):
            gaps.append(gaps[-1] + int(times[i] - times[i-1] > 1800))
        for i, (row, a, da) in enumerate(points):
            if not 50 <= da <= min(70, proximity_nm):
                continue
            for hours in (1, 2, 3, 6):
                target = times[i] + hours * 3600
                right = bisect_left(times, target)
                indices = [j for j in (right-1, right) if i < j < len(times) and abs(times[j]-target) <= 300]
                if not indices:
                    continue
                j = min(indices, key=lambda j: abs(times[j]-target))
                if gaps[j] - gaps[i]:
                    continue
                end_row, b, db = points[j]
                weather = storm.at(b.timestamp)
                if weather is None:
                    continue
                fixed = distance(a, weather)
                benefit = db - fixed
                field = _wind_field(b, weather, db)
                kind = None
                if moving(row) and da-fixed >= 3 and benefit >= 5 and db > da:
                    kind = 'MOVED_AWAY'
                elif moving(row) and moving(end_row) and da-db >= 5:
                    turn = abs((float(end_row['COG'])-float(row['COG'])+180)%360-180)
                    if turn <= 15 and distance(a,b)/hours > 2:
                        kind = 'CONTINUED_APPROACH'
                else:
                    window = points[i:j+1]
                    # All observations stay within 1 nm and all valid reported speeds <=1 kt.
                    speeds = [speed(r) for r,_,_ in window]
                    if (all(0 <= v <= 1 for v in speeds) and max(distance(a,p) for _,p,_ in window) <= 1
                            and da-db >= 5):
                        kind = 'STATIONARY_APPROACH'
                if not kind:
                    continue
                event = ResponseWindow(kind=kind, storm_id=storm.storm_id, storm_name=storm.name.title(),
                    start=a.timestamp, end=b.timestamp, start_distance_nm=round(da,2), end_distance_nm=round(db,2),
                    fixed_distance_nm=round(fixed,2), improvement_nm=round(benefit,2),
                    start_position=(a.longitude,a.latitude), end_position=(b.longitude,b.latitude), field=field)
                rank = benefit if kind == 'MOVED_AWAY' else da-db
                key = (storm.storm_id,kind)
                if key not in best or rank > best[key][0]:
                    best[key] = (rank,event)
    result.windows = sorted((v[1] for v in best.values()), key=lambda w: (w.start,w.kind))
    if not result.windows:
        result.findings.append('No qualifying movement pattern found in the available original broadcasts; this does not prove absence of exposure or a response.')
    result.findings.append('Stationary proximity does not establish failure to act: harbour protection, anchorage, navigation restrictions and intent require review.')
    return result
