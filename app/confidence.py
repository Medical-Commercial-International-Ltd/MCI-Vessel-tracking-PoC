"""Transparent evidence coverage heuristics, independent of exposure scoring."""
from datetime import timedelta
from math import log1p

from app.exposure import union_hours


def assess_confidence(position_count, observed_days, start, end, intervals, encounters, missing_years):
    supported = [(max(start, left.timestamp), min(end, right.timestamp)) for left, right in intervals
                 if right.timestamp - left.timestamp <= timedelta(hours=6)
                 and right.timestamp > start and left.timestamp < end]
    hours = max(0, (end - start).total_seconds() / 3600)
    days = max(1, (end.date() - start.date()).days + 1)
    day_percent = min(100, observed_days / days * 100)
    time_percent = min(100, union_hours(supported) / hours * 100) if hours else 0
    volume = min(100, log1p(position_count) / log1p(50000) * 100)
    encounter_percentages = []
    gap_count = 0
    for encounter in encounters:
        centre = encounter.closest_approach.timestamp
        left, right = max(start, centre - timedelta(hours=24)), min(end, centre + timedelta(hours=24))
        clipped = [(max(left, a), min(right, b)) for a, b in supported if b > left and a < right]
        duration = (right - left).total_seconds() / 3600
        encounter_percentages.append(min(100, union_hours(clipped) / duration * 100) if duration else 0)
        cursor = left
        gaps = []
        for a, b in sorted(clipped):
            if a > cursor:
                gaps.append(a - cursor)
            cursor = max(cursor, b)
        gaps.append(right - cursor)
        gap_count += any(gap > timedelta(hours=6) for gap in gaps)
    encounter_percent = sum(encounter_percentages) / len(encounter_percentages) if encounter_percentages else None
    overall = .30 * volume + .40 * day_percent + .30 * time_percent
    score = round(.80 * overall + .20 * encounter_percent) if encounter_percent is not None else round(overall)
    if position_count < 10 or observed_days < 3:
        rating = 'INSUFFICIENT'
    elif score >= 70 and observed_days >= 90 and day_percent >= 50 and not missing_years:
        rating = 'HIGH'
    elif score >= 40 and observed_days >= 30 and day_percent >= 10:
        rating = 'MEDIUM'
    else:
        rating = 'LOW'
    return dict(rating=rating, confidence_score=score, confidence_model_version='AIS-COVERAGE-v1',
                observed_day_coverage_percent=round(day_percent, 1),
                supported_time_coverage_percent=round(time_percent, 1),
                encounter_coverage_percent=round(encounter_percent, 1) if encounter_percent is not None else None,
                significant_storm_period_gaps=gap_count)
