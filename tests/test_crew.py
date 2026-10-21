import re
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.crew import CrewUnavailable, evidence_findings
from app.main import create_app


def csrf(response):
    return re.search(r'name="csrf" value="([^"]+)"', response.text)[1]


@pytest.fixture
def crew_client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data", analysis_provider="demo", crew_provider="demo", demo_seed_count=2,
                              admin_email="tester@example.test", admin_password="TestPassword123!"))
    with TestClient(app) as client:
        login = client.get("/login")
        client.post("/login", data={"email": "tester@example.test", "password": "TestPassword123!", "csrf": csrf(login)})
        analyses = app.state.repository.list_analyses("mci")
        yield client, app, analyses


def lookup(client, analysis, email="maya.patel@example.test", first="Maya", last="Patel"):
    base = f"/crew/{analysis.analysis_id}"
    page = client.get(base)
    return client.post(base + "/lookup", data={"csrf": csrf(page), "first_name": first, "last_name": last, "email": email})


def test_lookup_candidates_profiles_and_missing_evidence(crew_client):
    client, app, analyses = crew_client
    base = f"/crew/{analyses[0].analysis_id}"
    assert "Crew demonstration" in client.get(base).text
    result = lookup(client, analyses[0])
    assert result.status_code == 200
    assert "1 candidate found" in result.text
    profile = client.get(base + "?person=demo-maya")
    assert profile.status_code == 200
    assert "VERIFIED_MANUAL" in profile.text
    assert "expires within 90 days" in profile.text
    assert "not been independently verified" in profile.text
    result = lookup(client, analyses[0], "alex.morgan@example.test", "Alex", "Morgan")
    assert "2 candidates found" in result.text
    assert "name differs from your search" in result.text
    assert "verification rejected" in client.get(base + "?person=demo-alex-1").text
    missing = client.get(base + "?person=demo-alex-2")
    assert "No qualification evidence supplied" in missing.text
    assert "No CV experience supplied" in missing.text
    result = lookup(client, analyses[0], "nobody@example.test")
    assert result.status_code == 200
    assert "No accessible crew record found" in result.text
    assert client.get(base + "?person=demo-alex-1").status_code == 403


def test_assignment_review_validation_upsert_history_and_remove(crew_client):
    client, app, analyses = crew_client
    analysis = analyses[0]
    base = f"/crew/{analysis.analysis_id}"
    lookup(client, analysis)
    profile = client.get(base + "?person=demo-maya")
    start = datetime.now(timezone.utc).date()
    data = {"csrf": csrf(profile), "person_id": "demo-maya", "role": "Captain",
            "start_date": start.isoformat(), "end_date": (start + timedelta(days=120)).isoformat()}
    assert client.post(base + "/assign", data=data).status_code == 422
    data["confirmed"] = "yes"
    invalid = {**data, "end_date": (start - timedelta(days=1)).isoformat()}
    assert client.post(base + "/assign", data=invalid).status_code == 422
    for role in ["Captain", "Chief officer"]:
        data["role"] = role
        result = client.post(base + "/assign", data=data)
        assert result.status_code == 200
        assert "Demonstration assignment saved" in result.text
        assert "expires before the assignment ends" in result.text
    store = app.state.crew_repository
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT count(*) FROM assignments").fetchone()[0] == 1
        assert connection.execute("SELECT role FROM assignments").fetchone()[0] == "Chief officer"
        assert connection.execute("SELECT count(*) FROM assignment_audit").fetchone()[0] == 2
    # Reloading an assessment of the same vessel retains the assignment.
    copy = analysis.model_copy(deep=True)
    copy.analysis_id = "analysis_crew_repeat"
    copy.id = copy.analysis_id
    app.state.repository.save_analysis(copy)
    repeated = client.get(f"/crew/{copy.analysis_id}")
    assert "Maya Patel" in repeated.text
    result = client.post(base + "/remove", data={"csrf": csrf(result), "person_id": "demo-maya"})
    assert result.status_code == 200
    assert "No crew assignments recorded" in result.text
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT count(*) FROM assignment_audit WHERE action='remove'").fetchone()[0] == 1


def test_crew_access_csrf_and_vessel_isolation(crew_client):
    client, app, analyses = crew_client
    base = f"/crew/{analyses[0].analysis_id}"
    assert client.get(base + "?person=demo-maya").status_code == 403
    assert client.post(base + "/lookup", data={"csrf": "wrong"}).status_code == 400
    assert client.post(base + "/assign", data={"csrf": "wrong"}).status_code == 400
    assert client.post(base + "/remove", data={"csrf": "wrong"}).status_code == 400
    lookup(client, analyses[0])
    other = f"/crew/{analyses[1].analysis_id}"
    assert client.get(other + "?person=demo-maya").status_code == 403
    assert client.get("/crew/does-not-exist").status_code == 404
    client.cookies.clear()
    assert client.get(base, follow_redirects=False).status_code == 303
    assert client.post(base + "/lookup", data={}).status_code == 401


def test_lookup_error_validation_and_failed_refresh(crew_client):
    client, app, analyses = crew_client
    result = lookup(client, analyses[0], "not-an-email")
    assert result.status_code == 422
    result = lookup(client, analyses[0], "unavailable@example.test")
    assert result.status_code == 503
    assert "provider is unavailable" in result.text
    assert "No accessible crew record found" not in result.text
    lookup(client, analyses[0])
    class FailedProvider:
        def get(self, person_id):
            raise CrewUnavailable("Provider could not refresh this evidence.")
    app.state.crew_provider = FailedProvider()
    result = client.get(f"/crew/{analyses[0].analysis_id}?person=demo-maya")
    assert result.status_code == 503
    assert "could not refresh" in result.text


def test_lookup_access_expires_and_readonly_roles_are_rejected(crew_client, monkeypatch):
    client, app, analyses = crew_client
    lookup(client, analyses[0])
    monkeypatch.setattr("app.crew.time", lambda: 99999999999)
    assert client.get(f"/crew/{analyses[0].analysis_id}?person=demo-maya").status_code == 403
    monkeypatch.setattr(app.state.users, "authenticate", lambda *args: {
        "email": "viewer@example.test", "displayName": "Viewer", "role": "exposure"})
    page = client.get("/dashboard")
    client.post("/login", data={"csrf": csrf(page), "email": "viewer@example.test", "password": "unused"})
    assert client.get(f"/crew/{analyses[0].analysis_id}").status_code == 403


def test_unconnected_mode_does_not_return_demo_people(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, analysis_provider="demo", crew_provider="unavailable", demo_seed_count=1,
                              admin_email="tester@example.test", admin_password="TestPassword123!"))
    with TestClient(app) as client:
        page = client.get("/login")
        client.post("/login", data={"csrf": csrf(page), "email": "tester@example.test", "password": "TestPassword123!"})
        analysis = app.state.repository.list_analyses("mci")[0]
        result = lookup(client, analysis)
        assert result.status_code == 503
        assert "Live crew lookup is not connected" in result.text
        assert "1 candidate found" not in result.text


def test_unknown_expiry_is_not_treated_as_nonexpiring():
    findings = evidence_findings({"certificates": [{"name": "Test", "expiry": None, "verification": None, "completed": False}], "experience": []})
    assert any("expiry is unknown" in item for item in findings)
