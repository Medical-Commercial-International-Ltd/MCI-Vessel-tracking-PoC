from datetime import datetime, timedelta, timezone

from app.ais_data import TimedPosition
from app.hurdat import HurdatPoint, HurdatStorm
from app.storm_behaviour import assess_behaviour
from app.real_services import RealAnalysisService

START = datetime(2025, 8, 1, tzinfo=timezone.utc)


def position(hour, lon, lat=0):
    return TimedPosition(START + timedelta(hours=hour), lon, lat)


def storm(points):
    return HurdatStorm(storm_id="AL012025", name="TEST", basin="AL", points=tuple(
        HurdatPoint(START + timedelta(hours=h), lat, lon, "TS", 50,
                    (50,)*4, (20,)*4, (0,)*4) for h, lon, lat in points))


def test_stationary_approach_adds_risk_but_receding_storm_does_not():
    intervals = [(position(0, 0), position(2, 0))]
    approaching = assess_behaviour(intervals, storm([(0, 2, 0), (2, 1, 0)]), 200)
    receding = assess_behaviour(intervals, storm([(0, 1, 0), (2, 2, 0)]), 200)
    assert approaching.stationary_hours == approaching.stationary_worsening_hours == 2
    assert approaching.adjustment == 10
    assert receding.stationary_hours == 2
    assert receding.adjustment == 0


def test_distance_threshold_and_missing_intervals_do_not_invent_behaviour():
    weather = storm([(0, 2, 0), (12, 1, 0)])
    for intervals, threshold in [([], 200), ([(position(0, 0), position(12, 0))], 200),
                                 ([(position(0, 0), position(2, 0))], 25)]:
        result = assess_behaviour(intervals, weather, threshold)
        assert result.status == "INSUFFICIENT"
        assert result.adjustment == result.stationary_hours == 0


def test_course_change_requires_improvement_over_continuing_course():
    weather = storm([(0, 3, 0), (2, 3, 0)])
    left, turn, right = position(0, 0), position(1, 1), position(2, 0)
    result = assess_behaviour([(left, turn), (turn, right)], weather, 200)
    assert result.avoidance_manoeuvres == 1
    assert result.adjustment == -5
    continuing = assess_behaviour([(left, turn), (turn, position(2, 2))], weather, 200)
    assert continuing.avoidance_manoeuvres == 0
    disconnected = assess_behaviour([(left, turn), (position(1.1, 1), right)], weather, 200)
    assert disconnected.avoidance_manoeuvres == 0


def test_derived_geometry_cannot_apply_a_behaviour_adjustment():
    positions = [position(0, 0), position(2, 0)]
    service = object.__new__(RealAnalysisService)
    encounter = service._match_encounters("test", positions, [storm([(0, 2, 0), (2, 1, 0)])], 200)[0]
    risk = encounter.risk
    assert risk.behaviour.adjustment == 0
    assert risk.behaviour.status == 'INSUFFICIENT'
    assert risk.event_score == min(100, risk.proximity_points + risk.intensity_points + risk.wind_field_points + risk.duration_points)


def test_stationary_penalty_is_capped_and_does_not_apply_to_moving_vessel():
    weather = storm([(0, 3, 0), (6, 1, 0)])
    result = assess_behaviour([(position(0, 0), position(6, 0))], weather, 200)
    assert result.adjustment == 20
    moving = assess_behaviour([(position(0, 0), position(6, -1))], weather, 200)
    assert moving.stationary_hours == 0
    assert moving.adjustment == 0
