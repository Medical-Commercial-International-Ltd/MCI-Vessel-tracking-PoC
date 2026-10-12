from datetime import datetime, timedelta, timezone

import pytest

from app.ais_data import TrackSegment, TimedPosition, clip_segment, segment_positions, haversine_nm
from app.exposure import movement_statistics, sampled_intervals, storm_coverage_gaps, track_intervals, union_hours
from app.hurdat import HurdatPoint, HurdatStorm, _parse_radii
from app.real_services import RealAnalysisService, _wind_field
from app.scoring import aggregate_risk


START = datetime(2025, 8, 1, tzinfo=timezone.utc)


def position(hours, longitude=0, latitude=0):
    return TimedPosition(START + timedelta(hours=hours), longitude, latitude)


def segment(start=0, end=6, lines=(((0, 0), (6, 0)),)):
    return TrackSegment(START + timedelta(hours=start), START + timedelta(hours=end), lines,
                        'Cargo', 70, None, None, None)


def storm(name='ERIN', radii=(90, 90, 90, 90)):
    return HurdatStorm(name, name, 'AL', tuple(
        HurdatPoint(START + timedelta(hours=hours), 0, 0, 'TS', 40,
                    radii, (0, 0, 0, 0), (0, 0, 0, 0)) for hours in (0, 6)))


def test_date_clipping_preserves_position_and_speed():
    clipped = clip_segment(segment(), START + timedelta(hours=2), START + timedelta(hours=4))
    positions = segment_positions(clipped)
    assert positions[0].longitude == pytest.approx(2)
    assert positions[-1].longitude == pytest.approx(4)
    assert positions[0].timestamp == START + timedelta(hours=2)
    distance, average, maximum = movement_statistics(track_intervals([clipped]))
    assert distance == pytest.approx(120.1, abs=0.1)
    assert average == maximum == pytest.approx(60.0, abs=0.1)


def test_disconnected_lines_do_not_invent_distance():
    track = segment(lines=(((0, 0), (1, 0)), ((100, 0), (101, 0))))
    intervals = track_intervals([track])
    assert len(intervals) == 2
    distance, average, maximum = movement_statistics(intervals)
    assert distance == pytest.approx(120.1, abs=0.1)
    assert average == maximum == pytest.approx(20.0, abs=0.1)


def test_overlapping_tracks_do_not_double_distance_or_time():
    tracks = [segment(0, 4, (((0, 0), (4, 0)),)), segment(2, 6, (((2, 0), (6, 0)),))]
    intervals = track_intervals(tracks)
    assert union_hours([(left.timestamp, right.timestamp) for left, right in intervals]) == 6
    assert movement_statistics(intervals)[0] == pytest.approx(360.2, abs=0.1)


def test_stationary_position_has_track_duration_without_motion():
    intervals = track_intervals([segment(lines=(((0, 0),),))])
    assert movement_statistics(intervals) == (0, 0, 0)
    assert union_hours([(left.timestamp, right.timestamp) for left, right in intervals]) == 6


def test_time_thresholds_and_simultaneous_storms():
    service = object.__new__(RealAnalysisService)
    positions = [position(0), position(6)]
    totals = {}
    encounters = service._match_encounters('test', positions, [storm(), storm('BARRY')], 200, totals=totals)
    assert len(encounters) == 2
    assert all(event.exposure.duration_within_200_nm_hours == 6 for event in encounters)
    assert all(event.exposure.duration_within_34_kt_wind_field_hours == 6 for event in encounters)
    assert union_hours(totals['exposure']) == 6
    assert union_hours(totals['wind']) == 6


def test_gap_and_exit_are_not_counted_as_continuous_exposure():
    service = object.__new__(RealAnalysisService)
    # One hour inside the radius, a separate four-hour gap, then another hour.
    points = [position(0), position(1), position(5), position(6)]
    intervals = [(points[0], points[1]), (points[2], points[3])]
    result = service._match_encounters('test', points, [storm()], 200, intervals=intervals)
    assert result[0].exposure.duration_within_200_nm_hours == 2
    # A vessel leaves and returns: do not connect the two inside hits.
    points = [position(0), position(3, 10), position(6)]
    result = service._match_encounters('test', points, [storm()], 60)
    assert result[0].exposure.duration_within_200_nm_hours == pytest.approx(0.6, abs=0.1)


def test_proximity_setting_changes_exposure_and_unidentified_storm_is_excluded():
    service = object.__new__(RealAnalysisService)
    points = [position(0, 2), position(6, 2)]
    assert service._match_encounters('test', points, [storm()], 100) == []
    assert len(service._match_encounters('test', points, [storm()], 200)) == 1
    assert service._match_encounters('test', points, [storm('UNNAMED')], 200) == []


def test_long_vertex_gap_not_interpolated_for_exposure():
    assert list(sampled_intervals([(position(0), position(7))])) == []


def test_missing_radii_remain_unknown_and_quadrants_are_correct():
    assert _parse_radii(['-999', '0', '90', 'bad'], 0) == (-1, 0, 90, -1)
    point = storm(radii=(-1, 20, 30, 40)).at(START)
    assert _wind_field(position(0, 0.1, 0.1), point, 10) == 'UNKNOWN'
    assert _wind_field(position(0, 0.1, -0.1), point, 10) == '34KT'
    assert _wind_field(position(0, -0.1, -0.1), point, 25) == '34KT'
    assert _wind_field(position(0, -0.1, 0.1), point, 35) == '34KT'
    assert _wind_field(position(0, -0.1, 0.1), point, 45) == 'OUTSIDE 34KT'


def test_insufficient_coverage_still_refers_zero_encounter_assessment():
    assert aggregate_risk([], 'LOW').underwriter_referral
    assert not aggregate_risk([], 'MEDIUM').underwriter_referral


def test_coverage_gap_counts_actual_storm_windows():
    extended = HurdatStorm('x', 'ERIN', 'AL', (storm().points[0],
        HurdatPoint(START + timedelta(hours=24), 0, 0, 'TS', 40, (90,)*4, (0,)*4, (0,)*4)))
    assert storm_coverage_gaps([(position(0), position(1))], [extended], START, START + timedelta(days=1)) == 1
    assert storm_coverage_gaps([(position(0), position(6))], [storm()], START, START + timedelta(days=1)) == 0


def test_distance_reference_and_dateline():
    assert haversine_nm(0, 0, 0, 1) == pytest.approx(60.04, abs=0.01)
    clipped = clip_segment(segment(lines=(((179, 0), (-179, 0)),)),
                           START + timedelta(hours=3), START + timedelta(hours=6))
    assert abs(segment_positions(clipped)[0].longitude) == 180


def test_peak_classification_belongs_to_its_own_storm():
    service = object.__new__(RealAnalysisService)
    far = HurdatStorm('far', 'FAR', 'AL', tuple(
        HurdatPoint(START + timedelta(hours=h), 50, 50, 'EX', 80, (0,)*4, (0,)*4, (0,)*4)
        for h in (0, 6)))
    events = service._match_encounters('test', [position(0), position(6)], [storm(), far], 200)
    assert len(events) == 1
    assert events[0].storm.classification == 'TS'
    assert events[0].storm.category is None


def test_storm_lifetime_inside_sampling_interval_is_not_missed():
    brief = HurdatStorm('brief', 'BRIEF', 'AL', tuple(
        HurdatPoint(START + timedelta(minutes=m), 0, 0, 'TS', 40, (90,)*4, (0,)*4, (0,)*4)
        for m in (1, 2)))
    service = object.__new__(RealAnalysisService)
    totals = {}
    events = service._match_encounters('test', [position(0), position(6)], [brief], 200, totals=totals)
    assert len(events) == 1
    assert union_hours(totals['exposure']) == pytest.approx(1 / 60)


def test_radii_interpolation_and_exact_source_timestamps():
    cyclone = HurdatStorm('test', 'TEST', 'AL', (
        HurdatPoint(START, 0, 0, 'TS', 40, (0, 40, 40, 40), (0,)*4, (0,)*4),
        HurdatPoint(START + timedelta(hours=6), 0, 0, 'TS', 40, (40, -1, 40, 40), (0,)*4, (0,)*4)))
    assert cyclone.at(START).radii_34 == (0, 40, 40, 40)
    assert cyclone.at(START + timedelta(hours=3)).radii_34 == (20, -1, 40, 40)


def test_source_query_includes_previous_month_segment_and_clips_it(tmp_path):
    import sqlite3
    import struct
    from app.ais_data import MarineCadastreTrackStore
    (tmp_path / 'tracks').mkdir()
    database = sqlite3.connect(tmp_path / 'tracks/AISVesselTracks2025.gpkg')
    database.execute('CREATE TABLE gpkg_contents (table_name TEXT, data_type TEXT)')
    database.execute("INSERT INTO gpkg_contents VALUES ('Atlantic_07', 'features')")
    database.execute('CREATE TABLE Atlantic_07 (MMSI INTEGER, Shape BLOB, TrackStartTime TEXT, '
                     'TrackEndTime TEXT, VesselType INTEGER, Length REAL, Width REAL, Draft REAL, VesselGroup TEXT)')
    blob = b'GP' + bytes([0, 1]) + struct.pack('<I', 4326) + struct.pack('<BII', 1, 2, 2) + struct.pack('<dddd', 0, 0, 2, 0)
    database.execute('INSERT INTO Atlantic_07 VALUES (?,?,?,?,?,?,?,?,?)', (
        354215000, blob, (START - timedelta(hours=1)).isoformat(), (START + timedelta(hours=1)).isoformat(),
        70, 100, 20, 5, 'Cargo'))
    database.commit()
    database.close()
    tracks = MarineCadastreTrackStore(tmp_path).load_segments('354215000', START.date(), START.date())
    assert len(tracks) == 1
    assert tracks[0].start == START
    assert segment_positions(tracks[0])[0].longitude == pytest.approx(1)
    assert tracks[0].distance_nm == pytest.approx(60.04, abs=0.01)


def test_score_duration_uses_unrounded_time():
    service = object.__new__(RealAnalysisService)
    events = service._match_encounters('test', [position(0), position(0.96)], [storm()], 200)
    assert events[0].exposure.duration_within_200_nm_hours == 1.0
    assert events[0].risk.duration_points == 3


def test_full_year_example_score_arithmetic():
    result = aggregate_risk([63, 14], 'LOW')
    assert result.components.worst_encounter == 63
    assert result.components.top_three_average == 38
    assert result.components.recurrence == 19
    assert result.score == 47
    assert result.band == 'ELEVATED'
    assert result.underwriter_referral
