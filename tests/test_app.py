import re
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app, vessel_image
from app.event_lookup import LookupResponse, LookupResult
from app.models import VesselIdentity


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf" value="([^"]+)"', html)
    assert match
    return match.group(1)


def test_spuigracht_uses_verified_local_photo():
    vessel = VesselIdentity(name="SPUIGRACHT", imo="9202534", mmsi=["245261000"])

    image = vessel_image(vessel)

    assert image["src"] == "/static/vessels/245261000.jpg"
    assert "Niels Johannes" in image["credit"]
    assert "Spuigracht_(IMO_9202534).jpg" in image["source"]


def test_login_dashboard_analysis_and_json_download(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        session_secret="test-secret-with-enough-entropy",
        admin_email="tester@mciuw.com",
        admin_password="TestPassword123!",
        analysis_provider="demo",
        demo_seed_count=8,
    )

    with TestClient(create_app(settings)) as client:
        unauthenticated = client.get("/dashboard", follow_redirects=False)
        assert unauthenticated.status_code == 303
        assert unauthenticated.headers["location"] == "/login"

        login_page = client.get("/login")
        assert login_page.status_code == 200
        login = client.post(
            "/login",
            data={
                "email": "tester@mciuw.com",
                "password": "TestPassword123!",
                "csrf": _csrf(login_page.text),
            },
            follow_redirects=False,
        )
        assert login.status_code == 303
        assert login.headers["location"] == "/dashboard"

        dashboard = client.get("/dashboard")
        assert dashboard.status_code == 200
        assert "Portfolio overview" in dashboard.text

        analysis_page = client.get("/analysis")
        run = client.post(
            "/analysis",
            data={
                "identifierType": "MMSI",
                "identifier": "367000001",
                "fromDate": "2021-01-01",
                "toDate": "2025-12-31",
                "coastalLimitNm": "75",
                "stormProximityNm": "200",
                "csrf": _csrf(analysis_page.text),
            },
            follow_redirects=False,
        )
        assert run.status_code == 303
        result_url = run.headers["location"]
        assert result_url.startswith("/analysis?analysisId=analysis_")

        result = client.get(result_url)
        assert result.status_code == 200
        assert "Tropical Cyclone Exposure Score" in result.text
        analysis_id = result_url.split("=", 1)[1]

        updated_dashboard = client.get("/dashboard")
        assert updated_dashboard.status_code == 200
        assert "MMSI 367000001" in updated_dashboard.text
        assert "Submitted by you" in updated_dashboard.text
        assert "01 Jan 2021" in updated_dashboard.text
        assert "31 Dec 2025" in updated_dashboard.text

        download = client.get(f"/analysis/{analysis_id}/json")
        assert download.status_code == 200
        assert download.json()["analysisId"] == analysis_id
        assert download.json()["input"]["identifier"] == "367000001"


def test_health_is_available_without_login(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", analysis_provider="demo", demo_seed_count=0)
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_real_analysis_form_discloses_unavailable_coastal_filter(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", analysis_provider="real",
                        ais_cache_dir=tmp_path / "cache", admin_email="tester@mciuw.com",
                        admin_password="TestPassword123!")
    with TestClient(create_app(settings)) as client:
        login = client.get("/login")
        client.post("/login", data={"email": "tester@mciuw.com", "password": "TestPassword123!",
                                    "csrf": _csrf(login.text)})
        page = client.get("/analysis")
        assert page.status_code == 200
        assert 'name="coastalLimitNm"' not in page.text
        assert "coastline-distance filter is not available" in page.text
        assert 'name="stormProximityNm"' in page.text


def test_event_lookup_lists_source_options_and_links_mmsi(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        session_secret="test-secret-with-enough-entropy",
        admin_email="tester@mciuw.com",
        admin_password="TestPassword123!",
        analysis_provider="demo",
        demo_seed_count=0,
    )
    app = create_app(settings)
    lookup_calls = []

    class LookupStub:
        years = [2025]

        def ports(self):
            return [{"id": "27", "name": "PortMiami, FL"}]

        def storms(self):
            return [SimpleNamespace(storm_id="AL092022", name="IAN", basin="AL",
                                    start=datetime(2022, 9, 23, tzinfo=timezone.utc))]

        def vessel_groups(self):
            return ["Pleasure Craft/Sailing"]

        def search(self, **kwargs):
            lookup_calls.append(kwargs)
            assert kwargs["port_id"] == "27"
            assert kwargs["yacht_candidates"] is True
            return LookupResponse(
                results=[LookupResult(
                    mmsi="368282410", name="MMSI 368282410",
                    vessel_group="Pleasure Craft/Sailing", vessel_type_code=37,
                    length_m=30.0, timestamp=datetime(2025, 1, 2, 12, tzinfo=timezone.utc),
                    distance_nm=14.9,
                )],
                inspected_segments=3, truncated=False,
            )

    app.state.event_lookup = LookupStub()
    with TestClient(app) as client:
        assert client.get("/event-lookup", follow_redirects=False).status_code == 303
        login_page = client.get("/login")
        client.post("/login", data={
            "email": "tester@mciuw.com", "password": "TestPassword123!",
            "csrf": _csrf(login_page.text),
        })
        page = client.get("/event-lookup")
        assert page.status_code == 200
        assert "PortMiami, FL" in page.text
        assert "IAN" in page.text
        assert 'data-lookup-combo="storm"' in page.text
        assert 'data-lookup-combo="port"' in page.text
        assert 'data-lookup-combo="type"' in page.text
        assert page.text.count('role="combobox"') == 3
        assert 'name="stormId"' in page.text
        assert 'name="portId"' in page.text
        assert '<select name="stormId"' not in page.text
        assert '<select name="portId"' not in page.text
        assert "Pleasure Craft/Sailing" in page.text
        assert client.post("/event-lookup", data={"csrf": "wrong"}).status_code == 400
        result = client.post("/event-lookup", data={
            "csrf": _csrf(page.text), "dateValue": "2025-01-02",
            "portId": "27", "distanceNm": "50", "minLengthM": "24",
            "yachtCandidates": "1",
        })
        assert result.status_code == 200
        assert "MMSI 368282410" in result.text
        assert 'data-lookup-combo="storm"' in result.text
        assert "/analysis?mmsi=368282410" in result.text
        both = client.post("/event-lookup", data={
            "csrf": _csrf(page.text), "dateValue": "2025-01-02",
            "stormId": "AL092022", "portId": "27", "distanceNm": "50",
            "yachtCandidates": "1",
        })
        assert both.status_code == 200
        assert 'name="stormId" value="AL092022"' in both.text
        assert 'name="portId" value="27"' in both.text
        assert lookup_calls[0]["storm_id"] == ""
        assert lookup_calls[1]["storm_id"] == "AL092022"
        prefilled = client.get("/analysis?mmsi=368282410&fromDate=2025-01-02&toDate=2025-01-02")
        assert 'name="identifier" value="368282410"' in prefilled.text
