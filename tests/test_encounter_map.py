from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.ais_data import TrackSegment, TimedPosition, haversine_nm
from app.encounter_map import build_map_data, playback_path, wind_sectors
from app.hurdat import HurdatPoint, HurdatStorm


def test_wind_overlay_uses_each_reported_quadrant_and_omits_unknown():
    point = HurdatPoint(datetime(2025, 7, 1, tzinfo=timezone.utc), 30, -80, 'TS', 40,
                        (90, 0, -1, 45), (0,)*4, (0,)*4)
    sectors = wind_sectors(point)
    assert len(sectors) == 2
    assert [item['quadrant'] for item in sectors] == [0, 3]
    for sector in sectors:
        assert sector['coordinates'][0] == [-80, 30]
        assert sector['coordinates'][-1] == [-80, 30]
        for longitude, latitude in sector['coordinates'][1:-1]:
            assert haversine_nm(30, -80, latitude, longitude) == pytest.approx(sector['radiusNm'])


def test_map_frames_keep_unknown_vessel_position_in_gap(monkeypatch, tmp_path):
    start = datetime(2025, 7, 1, tzinfo=timezone.utc)
    storm = HurdatStorm('AL032025', 'CHANTAL', 'AL', tuple(
        HurdatPoint(start + timedelta(hours=h), 30, -80, 'TS', 40, (90,)*4, (0,)*4, (0,)*4)
        for h in (0, 6, 12)))
    track = TrackSegment(start, start + timedelta(hours=1), (((-80,30),(-79,30)),),
                         'Passenger', 60, None, None, None)
    monkeypatch.setattr('app.encounter_map.load_hurdat_storms', lambda *args: [storm])
    monkeypatch.setattr('app.encounter_map.MarineCadastreTrackStore.load_segments', lambda *args: [track])
    analysis = SimpleNamespace(is_synthetic=False, vessel=SimpleNamespace(mmsi=['354215000']),
        input=SimpleNamespace(period=SimpleNamespace(from_date=start.date(), to_date=start.date())))
    event = SimpleNamespace(id='encounter_001', storm=SimpleNamespace(id='AL032025', name='Chantal'),
        closest_approach=SimpleNamespace(timestamp=start, distance_nm=1,
            vessel_position=SimpleNamespace(coordinates=(-80,30)),
            storm_position=SimpleNamespace(coordinates=(-80,30))))
    payload = build_map_data(analysis, [event], tmp_path)[0]
    assert len(payload['vesselTracks']) == 1
    assert len(payload['stormTrack']) == 3
    assert payload['frames'][0]['vessel'] == [-80,30]
    assert next(frame for frame in payload['frames'] if frame['timestamp'] == (start + timedelta(hours=6)).isoformat())['vessel'] is None
    assert next(frame for frame in payload['frames'] if frame['timestamp'] == (start + timedelta(hours=12)).isoformat())['vessel'] is None
    five_minutes = payload['frames'][1]
    assert five_minutes['timestamp'] == (start + timedelta(minutes=5)).isoformat()
    assert five_minutes['vessel'][0] == pytest.approx(-80 + 1/12)
    assert five_minutes['vesselSpeedKt'] > 0
    assert five_minutes['vesselHeadingDeg'] is not None
    assert five_minutes['vesselPathId'] is not None
    assert payload['vesselSamples']
    assert payload['frames'][0]['windSectors']


def test_synthetic_map_does_not_load_noaa_data(monkeypatch, tmp_path):
    def forbidden(*args):
        raise AssertionError('Synthetic positions must not be decorated with real tracks')
    monkeypatch.setattr('app.encounter_map.load_hurdat_storms', forbidden)
    analysis = SimpleNamespace(is_synthetic=True)
    start = datetime(2025, 7, 1, tzinfo=timezone.utc)
    event = SimpleNamespace(id='encounter_001', storm=SimpleNamespace(id='AL032025', name='Chantal'),
        closest_approach=SimpleNamespace(timestamp=start, distance_nm=1,
            vessel_position=SimpleNamespace(coordinates=(-80,30)),
            storm_position=SimpleNamespace(coordinates=(-80,30))))
    payload = build_map_data(analysis, [event], tmp_path)[0]
    assert payload['synthetic']
    assert not payload['stormTrack'] and not payload['vesselTracks'] and not payload['frames']


def test_playback_bridges_only_between_known_points_and_labels_gap():
    start = datetime(2025, 7, 1, tzinfo=timezone.utc)
    point = lambda hours, longitude: TimedPosition(start + timedelta(hours=hours), longitude, 30)
    a, b, c, d = point(0, -80), point(1, -79), point(3, -77), point(4, -76)
    edges = [(a, b, 'first'), (c, d, 'second')]
    path, gaps = playback_path([[a,b], [c,d]], edges, b, start, start + timedelta(hours=5))
    assert [item['gapToNext'] for item in path] == [False, True, False, False]
    assert len(gaps) == 1
    assert gaps[0][0] == [-79,30]
    assert gaps[0][-1] == [-77,30]
    assert gaps[0][len(gaps[0]) // 2][0] == pytest.approx(-78)
    assert path[-1]['timestamp'] == d.timestamp.isoformat()  # no projected endpoint at hour five
    assert len(edges) == 2  # source-supported intervals are not extended


def test_playback_retains_known_anchor_before_window_to_interpolate_into_it():
    start = datetime(2025, 7, 1, tzinfo=timezone.utc)
    a = TimedPosition(start - timedelta(hours=1), -80, 30)
    b = TimedPosition(start + timedelta(hours=1), -78, 30)
    path, gaps = playback_path([[a], [b]], [], b, start, start + timedelta(hours=2))
    assert path[0]['timestamp'] == a.timestamp.isoformat()
    assert gaps[0][0][0] == pytest.approx(-79)
    assert gaps[0][-1] == [-78,30]
