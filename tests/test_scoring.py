from app.scoring import EncounterInputs, aggregate_risk, risk_band, score_encounter


def test_severe_close_encounter_scores_higher_than_distant_storm():
    close = score_encounter(
        EncounterInputs(
            distance_nm=18,
            maximum_wind_kt=140,
            strongest_wind_field="64KT",
            duration_hours=26,
        )
    )
    distant = score_encounter(
        EncounterInputs(
            distance_nm=180,
            maximum_wind_kt=40,
            strongest_wind_field="OUTSIDE 34KT",
            duration_hours=2,
        )
    )
    assert close.event_score == 100
    assert distant.event_score < close.event_score


def test_aggregate_score_is_explainable_and_bounded():
    result = aggregate_risk([82, 60, 41, 24], "HIGH")
    assert 0 <= result.score <= 100
    assert result.components.worst_encounter == 82
    assert result.components.top_three_average == 61
    assert result.band in {"ELEVATED", "HIGH"}


def test_risk_band_boundaries():
    assert risk_band(19) == "LOW"
    assert risk_band(20) == "MODERATE"
    assert risk_band(40) == "ELEVATED"
    assert risk_band(60) == "HIGH"
    assert risk_band(80) == "SEVERE"


def test_current_aggregation_cannot_dilute_an_event_or_remove_its_referral():
    for events in ([70], [70, 1], [70, 1, 1], [70, 40, 20, 1]):
        result = aggregate_risk(events, 'HIGH', preserve_worst=True)
        assert result.score >= 70
        assert result.underwriter_referral


def test_current_aggregation_is_monotonic_when_adding_any_event():
    for events in ([], [30], [100], [40, 20], [70, 10, 5], [20] * 15):
        previous = aggregate_risk(events, preserve_worst=True).score
        for extra in range(101):
            result = aggregate_risk([*events, extra], preserve_worst=True)
            assert max(previous, extra) <= result.score <= 100

