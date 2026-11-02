from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from app.hurdat import HurdatPoint, HurdatStorm
from app.models import DatePeriod
from app.storm_response import BroadcastStore, assess_response, overlay_segments
from tests.test_storm_behaviour import START, position, storm


def philippe():
    record=json.loads((Path(__file__).parent/'fixtures/philippe-track.json').read_text())
    return HurdatStorm(record['storm_id'],record['name'],record['basin'],tuple(
        HurdatPoint(**{**p,'timestamp':datetime.fromisoformat(p['timestamp'])}) for p in record['points']))


@pytest.mark.parametrize('mmsi,benefit,start,end',[
    ('368001090',23.45,65.01,77.62),('368281860',12.55,61.18,65.37)])
def test_original_noaa_cases_use_simultaneous_timestamps(tmp_path,mmsi,benefit,start,end):
    rows,dates=BroadcastStore(tmp_path).load(mmsi,DatePeriod(from_date=date(2023,10,3),to_date=date(2023,10,3)))
    result=assess_response(rows,[philippe()],dates)
    window=next(w for w in result.windows if w.kind=='MOVED_AWAY')
    assert window.improvement_nm==benefit
    assert window.start_distance_nm==start
    assert window.end_distance_nm==end
    assert window.improvement_nm==pytest.approx(window.end_distance_nm-window.fixed_distance_nm,abs=.01)
    assert window.score_adjustment == -5
    assert any(w.kind=='MOVED_TOWARDS' for w in result.windows)==(mmsi=='368281860')
    assert result.model_version == 'BROADCAST-RESPONSE-v2'


def rows_at_origin(speed='0',missing=False):
    return [{'MMSI':'123456789','BaseDateTime':(START+timedelta(minutes=15*i)).isoformat(),
             'LAT':'0','LON':'0','SOG':speed,'COG':'0'} for i in range(9) if not missing or i in (0,8)]


def test_stationary_approach_requires_supported_positions_and_valid_speeds():
    weather=storm([(0,1,0),(2,.5,0)])
    result=assess_response(rows_at_origin(),[weather],[START.date()])
    assert any(w.kind=='STATIONARY_APPROACH' for w in result.windows)
    for rows in (rows_at_origin('102.3'),rows_at_origin(missing=True),[]):
        assert not assess_response(rows,[weather]).windows
    for bad in ('',None,'not supplied','nan'):
        assert not assess_response(rows_at_origin(bad),[weather]).windows
    assert assess_response([{'LAT':'nan','LON':'0','BaseDateTime':'bad'}],[weather]).status=='INSUFFICIENT'


def test_no_broadcasts_are_unknown_and_period_is_respected(tmp_path):
    store=BroadcastStore(tmp_path)
    rows,dates=store.load('368001090',DatePeriod(from_date=date(2025,1,1),to_date=date(2025,1,1)))
    assert not rows and not dates
    assert assess_response(rows,[philippe()],dates).status=='INSUFFICIENT'
    assert store.load('../../anything',DatePeriod(from_date=date.today(),to_date=date.today()))==([],[])


def test_broadcast_overlay_preserves_actual_timestamps_and_does_not_bridge_gaps():
    rows=rows_at_origin(missing=True)
    assert overlay_segments([],rows,[START.date()])==[]
    rows=rows_at_origin()
    segments=overlay_segments([],rows,[START.date()])
    assert len(segments)==1
    assert segments[0].clipped_positions[0][1].timestamp==START+timedelta(minutes=15)


def moving_rows(end_lon, end_speed='12'):
    rows = rows_at_origin('12')[:5]
    for i, row in enumerate(rows):
        row['LON'] = str(end_lon * i / 4)
        row['COG'] = '90' if end_lon > 0 else '270'
    rows[-1]['SOG'] = end_speed
    return rows


@pytest.mark.parametrize('start_storm,end_storm,end_vessel,kind', [
    (2, 2, -.2, 'MOVED_AWAY'),
    (2, 2, .2, 'MOVED_TOWARDS'),
    (2, 1.5, -.2, 'MOVED_AWAY_CLOSING'),
    (2, 3, .2, 'MOVED_TOWARDS_RECEDING'),
    (.5, .5, -.2, 'MOVED_AWAY'),
    (1.5, 1.5, -.3, 'MOVED_AWAY'),
])
def test_vessel_contribution_is_separate_from_storm_motion(start_storm, end_storm, end_vessel, kind):
    weather = storm([(0, start_storm, 0), (1, end_storm, 0)])
    result = assess_response(moving_rows(end_vessel), [weather], proximity_nm=200)
    assert len(result.windows) == 1
    window = result.windows[0]
    assert window.kind == kind
    assert window.improvement_nm == pytest.approx(window.end_distance_nm - window.fixed_distance_nm, abs=.01)
    assert window.score_adjustment == 0  # Broader detection does not expand score eligibility.


def test_away_window_can_leave_proximity_and_stop_at_destination():
    weather = storm([(0, 1.5, 0), (1, 1.5, 0)])
    result = assess_response(moving_rows(-.3, '0'), [weather], proximity_nm=100)
    assert result.windows[0].kind == 'MOVED_AWAY'
    assert result.windows[0].end_distance_nm > 100
    assert not assess_response(moving_rows(-.3), [weather], proximity_nm=50).windows


@pytest.mark.parametrize('bad_speed', ['102.3', 'nan', '-1', None])
def test_invalid_ending_speed_never_awards_movement_credit(bad_speed):
    weather = storm([(0, 1, 0), (1, .9, 0)])
    assert not assess_response(moving_rows(-.2, bad_speed), [weather]).windows


def test_duplicate_conflicts_and_impossible_jumps_break_windows():
    weather = storm([(0, 2, 0), (1, 2, 0)])
    rows = moving_rows(-.2)
    assert assess_response(rows + [dict(rows[2])], [weather]).windows
    assert not assess_response(rows + [{**rows[2], 'LON': '10'}], [weather]).windows
    rows[2]['LON'] = '10'
    assert not assess_response(rows, [weather]).windows


def test_stationary_detection_outside_scoring_band_is_descriptive():
    weather = storm([(0, 3, 0), (2, 2, 0)])
    result = assess_response(rows_at_origin(), [weather])
    assert result.windows[0].kind == 'STATIONARY_APPROACH'
    assert result.windows[0].score_adjustment == 0
    receding = assess_response(rows_at_origin(), [storm([(0, 2, 0), (2, 3, 0)])])
    assert receding.windows[0].kind == 'STATIONARY_RECEDING'
    assert receding.windows[0].score_adjustment == 0


def test_observations_far_from_storm_do_not_claim_assessed_encounter():
    result = assess_response(rows_at_origin(), [storm([(0, 20, 0), (2, 19, 0)])])
    assert result.status == 'INSUFFICIENT'
    assert not result.assessed_storm_ids
