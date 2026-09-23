from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from app.models import EventRisk, RiskAssessment, RiskComponents


@dataclass(frozen=True)
class EncounterInputs:
    distance_nm: float
    maximum_wind_kt: int
    strongest_wind_field: str
    duration_hours: float


def proximity_points(distance_nm: float) -> int:
    if distance_nm <= 25:
        return 25
    if distance_nm <= 50:
        return 21
    if distance_nm <= 100:
        return 15
    if distance_nm <= 150:
        return 9
    if distance_nm <= 200:
        return 4
    return 0


def intensity_points(maximum_wind_kt: int) -> int:
    if maximum_wind_kt >= 137:
        return 25
    if maximum_wind_kt >= 113:
        return 22
    if maximum_wind_kt >= 96:
        return 19
    if maximum_wind_kt >= 83:
        return 15
    if maximum_wind_kt >= 64:
        return 11
    if maximum_wind_kt >= 34:
        return 7
    return 2


def wind_field_points(strongest_wind_field: str) -> int:
    normalized = strongest_wind_field.upper().replace(" ", "")
    return {
        "64KT": 30,
        "50KT": 23,
        "34KT": 15,
        "OUTSIDE34KT": 5,
        "UNKNOWN": 3,
    }.get(normalized, 3)


def duration_points(duration_hours: float) -> int:
    if duration_hours >= 24:
        return 20
    if duration_hours >= 12:
        return 16
    if duration_hours >= 6:
        return 12
    if duration_hours >= 1:
        return 7
    if duration_hours > 0:
        return 3
    return 0


def score_encounter(values: EncounterInputs) -> EventRisk:
    proximity = proximity_points(values.distance_nm)
    intensity = intensity_points(values.maximum_wind_kt)
    wind_field = wind_field_points(values.strongest_wind_field)
    duration = duration_points(values.duration_hours)
    total = min(100, proximity + intensity + wind_field + duration)
    return EventRisk(
        event_score=total,
        proximity_points=proximity,
        intensity_points=intensity,
        wind_field_points=wind_field,
        duration_points=duration,
    )


def risk_band(score: int) -> str:
    if score >= 80:
        return "SEVERE"
    if score >= 60:
        return "HIGH"
    if score >= 40:
        return "ELEVATED"
    if score >= 20:
        return "MODERATE"
    return "LOW"


def aggregate_risk(
    event_scores: list[int],
    confidence: str = "HIGH",
) -> RiskAssessment:
    if not event_scores:
        return RiskAssessment(
            score=0,
            band="LOW",
            confidence=confidence,
            components=RiskComponents(
                worst_encounter=0,
                top_three_average=0,
                recurrence=0,
            ),
            underwriter_referral=confidence == "INSUFFICIENT",
        )

    ordered = sorted(event_scores, reverse=True)
    worst = ordered[0]
    top_three_average = round(mean(ordered[:3]))
    recurrence = min(100, round(sum(score / 100 for score in ordered) * 25))
    total = round((0.5 * worst) + (0.3 * top_three_average) + (0.2 * recurrence))
    band = risk_band(total)
    return RiskAssessment(
        score=total,
        band=band,
        confidence=confidence,
        components=RiskComponents(
            worst_encounter=worst,
            top_three_average=top_three_average,
            recurrence=recurrence,
        ),
        underwriter_referral=band in {"HIGH", "SEVERE"} or confidence in {"LOW", "INSUFFICIENT"},
    )

