from datetime import datetime, timezone

from app.ais_data import TrackSegment
from app.event_lookup import LookupWindow, _closest_match, _intersect_windows
from app.hurdat import HurdatPoint, HurdatStorm


def test_combined_search_requires_same_position_near_storm_and_port():
    start = datetime(2025, 8, 1, 0, tzinfo=timezone.utc)
    end = datetime(2025, 8, 1, 6, tzinfo=timezone.utc)
    radii = (0.0, 0.0, 0.0, 0.0)
    storm = HurdatStorm(
        storm_id="AL052025", name="ERIN", basin="AL",
        points=(
            HurdatPoint(start, 25.0, -80.0, "TS", 50, radii, radii, radii),
            HurdatPoint(end, 25.0, -80.0, "TS", 50, radii, radii, radii),
        ),
    )
    segment = TrackSegment(
        start=start, end=end, lines=(((-80.0, 25.0), (-80.0, 25.0)),),
        vessel_group="Pleasure Craft/Sailing", vessel_type_code=37,
        length_m=30, width_m=None, draft_m=None,
    )
    window = LookupWindow(start, end, -82, -78, 23, 27)
    close_port = {"coordinates": [-80.1, 25.0]}
    distant_port = {"coordinates": [-82.0, 25.0]}

    match = _closest_match(segment, window, storm, close_port, 10)
    assert match is not None
    assert match[2] == 0
    assert 0 < match[3] < 10
    assert _closest_match(segment, window, storm, distant_port, 10) is None


def test_storm_and_port_spatial_windows_intersect():
    start = datetime(2025, 8, 1, tzinfo=timezone.utc)
    end = datetime(2025, 8, 2, tzinfo=timezone.utc)
    storm = LookupWindow(start, end, -81, -79, 24, 26)
    port = LookupWindow(start, end, -80.5, -79.5, 24.5, 25.5)
    far_port = LookupWindow(start, end, -75, -74, 24.5, 25.5)

    overlap = _intersect_windows(storm, port)
    assert overlap is not None
    assert overlap.min_lon == -80.5
    assert overlap.max_lat == 25.5
    assert _intersect_windows(storm, far_port) is None
