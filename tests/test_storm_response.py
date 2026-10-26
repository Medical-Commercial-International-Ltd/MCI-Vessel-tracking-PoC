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
    ('368001090',23.48,65.10,77.65),('368281860',12.68,61.30,65.50)])
def test_original_noaa_cases_reproduce_research(tmp_path,mmsi,benefit,start,end):
    rows,dates=BroadcastStore(tmp_path).load(mmsi,DatePeriod(from_date=date(2023,10,3),to_date=date(2023,10,3)))
    result=assess_response(rows,[philippe()],dates)
    window=next(w for w in result.windows if w.kind=='MOVED_AWAY')
    assert window.improvement_nm==benefit
    assert window.start_distance_nm==start
    assert window.end_distance_nm==end
    assert window.improvement_nm==pytest.approx(window.end_distance_nm-window.fixed_distance_nm,abs=.01)
    assert any(w.kind=='CONTINUED_APPROACH' for w in result.windows)==(mmsi=='368281860')


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
