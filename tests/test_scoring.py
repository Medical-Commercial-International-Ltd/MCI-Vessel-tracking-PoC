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

