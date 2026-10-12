from datetime import datetime, timezone

from app.ais_data import TimedPosition
from app.hurdat import HurdatPoint, HurdatStorm, category_for_wind
from app.real_services import RealAnalysisService


def test_real_encounter_uses_hurdat_storm_identity():
    start = datetime(2025, 8, 1, 0, tzinfo=timezone.utc)
    end = datetime(2025, 8, 1, 6, tzinfo=timezone.utc)
    radii = (90.0, 90.0, 90.0, 90.0)
    storm = HurdatStorm(
        storm_id="AL052025",
        name="ERIN",
        basin="AL",
        points=(
            HurdatPoint(start, 30.0, -75.0, "HU", 80, radii, (50, 50, 50, 50), (20, 20, 20, 20)),
            HurdatPoint(end, 30.5, -74.5, "HU", 85, radii, (50, 50, 50, 50), (20, 20, 20, 20)),
        ),
    )
    positions = [
        TimedPosition(datetime(2025, 8, 1, 3, tzinfo=timezone.utc), -74.8, 30.2),
    ]

    service = object.__new__(RealAnalysisService)
    encounters = service._match_encounters("analysis_test", positions, [storm], 200)

    assert len(encounters) == 1
    assert encounters[0].storm.id == "AL052025"
    assert encounters[0].storm.name == "Erin"
    assert encounters[0].exposure.maximum_storm_wind_kt == 82
    # One position establishes proximity, but cannot establish elapsed exposure.
    assert encounters[0].exposure.duration_within_34_kt_wind_field_hours == 0


def test_saffir_simpson_category_boundaries():
    assert category_for_wind(63) is None
    assert category_for_wind(64) == 1
    assert category_for_wind(83) == 2
    assert category_for_wind(96) == 3
    assert category_for_wind(113) == 4
    assert category_for_wind(137) == 5
