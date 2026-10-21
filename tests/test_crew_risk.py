from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
import re

from fastapi.testclient import TestClient
import httpx
import pytest

from app.config import Settings
from app.crew_risk import assess_crew, combine_risk, document_penalty, SAFETY
from app.crewdentials import CrewdentialsProvider, CrewUnavailable
from app.main import create_app
from app.crew import vessel_key

PROFILE_ID = "01a1445b-3696-7470-90a5-93a29a28e6cd"
TODAY = date(2026, 10, 21)


def certificate(**overrides):
    return {"id": "test-document", "name": "Test qualification", "type": "MASTER_UNLIMITED",
            "issue": "2025-01-01", "expiry": "2030-01-01", "completed": True,
            "statuses": ["VERIFIED_MANUAL"], **overrides}


def person():
    docs = [certificate(id=str(i), type=next(iter(types))) for i, (_, types, _) in enumerate(SAFETY)]
    docs.append(certificate())
    return {"id": PROFILE_ID, "is_demo": True, "certificates": docs, "experience": [],
            "retrieved_at": "2026-10-21T10:00:00+00:00", "stale": False}


def assignment(**changes):
    return {"person_id": PROFILE_ID, "name": "Test captain", "role": "Captain",
            "start_date": "2026-01-01", "end_date": "2026-12-31", "is_demo": 1, **changes}


class Provider:
    def __init__(self, people):
        self.people = people

    def get(self, identifier):
        return deepcopy(self.people.get(identifier))


@pytest.mark.parametrize("status,expected", [("VERIFIED_MANUAL", 0), ("VERIFIED_INSTANT", 0),
    ("REJECTED", 100), ("REVIEWED", 40), ("PENDING_MANUAL", 50), ("REFERRED", 75), ("QUERIES", 75),
    ("FUTURE_PROVIDER_STATUS", 60), (None, 60)])
def test_verification_status_penalties(status, expected):
    assert document_penalty(certificate(statuses=[status]), TODAY, date(2026, 12, 31))[0] == expected


def test_dates_and_verification_are_independent_and_conflicts_are_conservative():
    assert document_penalty(certificate(expiry="2026-01-15"), TODAY, TODAY)[:2] == (100, True)
    assert document_penalty(certificate(expiry=None), TODAY, TODAY)[0] == 25
    assert document_penalty(certificate(expiry="garbage"), TODAY, TODAY)[0] == 25
    assert document_penalty(certificate(issue="2031-01-01"), TODAY, TODAY)[:2] == (100, True)
    assert document_penalty(certificate(expiry="2026-11-01"), TODAY, date(2026, 12, 31))[:2] == (75, True)
    assert document_penalty(certificate(expiry="2026-11-01"), TODAY, TODAY)[0] == 35
    assert document_penalty(certificate(statuses=["VERIFIED_MANUAL", "REJECTED"]), TODAY, TODAY)[0] == 100


def test_missing_stale_or_inactive_crew_never_produces_a_low_risk_score():
    for assignments, people in [([], {}), ([assignment()], {}),
                               ([assignment()], {PROFILE_ID: {**person(), "stale": True}}),
                               ([assignment()], {PROFILE_ID: {**person(), "refresh_error": True}}),
                               ([assignment(end_date="2025-01-01")], {PROFILE_ID: person()}),
                               ([assignment(start_date="2027-01-01")], {PROFILE_ID: person()})]:
        result = assess_crew(assignments, Provider(people), TODAY)
        assert result.score is None
        assert result.underwriter_referral


def test_slot_weighting_missing_documents_duplicates_and_roster_dilution():
    good = person()
    clean = assess_crew([assignment()], Provider({PROFILE_ID: good}), TODAY)
    assert clean.score == 0
    assert not clean.underwriter_referral
    missing_medical = deepcopy(good)
    missing_medical["certificates"] = [doc for doc in good["certificates"] if doc["type"] != "MEDICAL_FITNESS_CERTIFICATE_ENG1"]
    result = assess_crew([assignment()], Provider({PROFILE_ID: missing_medical}), TODAY)
    assert result.score == round(200 / 9)
    assert result.underwriter_referral
    rejected = deepcopy(good)
    rejected["certificates"][-1]["statuses"] = ["REJECTED"]
    result = assess_crew([assignment(), assignment(person_id="good")], Provider({PROFILE_ID: rejected, "good": good}), TODAY)
    assert result.score == round(300 / 9)
    assert result.underwriter_referral  # Rejection forces review below numeric threshold.
    rejected["certificates"].append(certificate(id="renewal"))
    assert assess_crew([assignment()], Provider({PROFILE_ID: rejected}), TODAY).score == 0


def test_evidence_hash_changes_when_provider_decision_changes():
    first = person()
    second = deepcopy(first)
    second["certificates"][-1]["statuses"] = ["REJECTED"]
    a = assess_crew([assignment()], Provider({PROFILE_ID: first}), TODAY)
    b = assess_crew([assignment()], Provider({PROFILE_ID: second}), TODAY)
    assert a.evidence_hash != b.evidence_hash


def test_checklist_distinguishes_uploaded_unverified_expired_and_missing_evidence():
    evidence = person()
    evidence["certificates"][0].update(statuses=[], completed=False)
    evidence["certificates"][1]["expiry"] = "2025-01-01"
    evidence["certificates"] = [doc for doc in evidence["certificates"] if doc["type"] != "MEDICAL_FITNESS_CERTIFICATE_ENG1"]
    result = assess_crew([assignment()], Provider({PROFILE_ID: evidence}), TODAY)
    checks = {check.label: check for check in result.members[0].checks}
    uploaded = checks["Personal survival"]
    assert uploaded.document.status == "pass"
    assert uploaded.verification.status == "warning"
    assert uploaded.validity.status == "pass"
    expired = checks["Fire safety"]
    assert expired.document.status == expired.verification.status == "pass"
    assert expired.validity.status == "fail"
    missing = checks["Medical fitness"]
    assert missing.document.status == "fail"
    assert missing.verification.status == missing.validity.status == "unknown"


def test_unavailable_checklist_does_not_claim_documents_or_cv_are_missing():
    result = assess_crew([assignment()], Provider({}), TODAY)
    member = result.members[0]
    assert member.experience_supplied is None
    assert all(check.document.status == check.verification.status == check.validity.status == "unknown" for check in member.checks)


def write_provider_data(root):
    crew = root / "crew"
    (crew / "evidence").mkdir(parents=True)
    (crew / "connected-profiles.json").write_text(json.dumps([{"id": PROFILE_ID, "name": "Sam Jones", "isTestData": True}]))
    documents = []
    for index, cert in enumerate(person()["certificates"]):
        documents.append({"id": str(index), "name": cert["name"], "certificateTypeId": cert["type"],
                          "issueDate": cert["issue"], "expiryDate": cert["expiry"], "completed": True,
                          "verifications": [{"status": "VERIFIED_MANUAL", "trusted": True}],
                          "imageUrls": [], "originalFileUrls": []})
    payload = {"crewId": "crew-1", "crewProfileId": PROFILE_ID, "documents": documents}
    (crew / "evidence" / f"{PROFILE_ID}.json").write_text(json.dumps({"retrievedAt": datetime.now(timezone.utc).isoformat(), "payload": payload}))
    return payload


def csrf(response):
    return re.search(r'name="csrf" value="([^"]+)"', response.text)[1]


@pytest.fixture
def connected(tmp_path):
    write_provider_data(tmp_path)
    settings = Settings(data_dir=tmp_path, analysis_provider="demo", crew_provider="crewdentials", demo_seed_count=1,
                        admin_email="tester@example.test", admin_password="TestPassword123!", crewdentials_api_key="test-key")
    app = create_app(settings)
    with TestClient(app) as client:
        page = client.get("/login")
        client.post("/login", data={"csrf": csrf(page), "email": settings.admin_email, "password": settings.admin_password})
        yield client, app, app.state.repository.list_analyses("mci")[0]


def test_connected_crew_changes_persisted_risk_ui_export_and_repeat_assessment(connected):
    client, app, analysis = connected
    base = f"/crew/{analysis.analysis_id}"
    page = client.get(base)
    assert "Sam Jones" in page.text
    assert client.get(base + f"?person={PROFILE_ID}").status_code == 403
    page = client.post(base + "/select", data={"csrf": csrf(page), "person_id": PROFILE_ID})
    assert page.status_code == 200
    assert "VERIFIED_MANUAL" in page.text
    now = datetime.now(timezone.utc).date()
    page = client.post(base + "/assign", data={"csrf": csrf(page), "person_id": PROFILE_ID, "role": "Captain",
                       "start_date": now.isoformat(), "end_date": (now + timedelta(days=180)).isoformat(), "confirmed": "yes"})
    assert page.status_code == 200
    assert "Sam Jones" in client.get(f"/analysis?analysisId={analysis.analysis_id}").text
    stored = app.state.repository.get_analysis("mci", analysis.analysis_id)
    assert stored.underwriting.crew.score == 0
    assert stored.underwriting.score == analysis.risk.score
    assert stored.underwriting.is_test_data
    assert stored.risk == analysis.risk
    exported = client.get(f"/analysis/{analysis.analysis_id}/json").json()
    assert exported["underwriting"]["crew"]["members"][0]["personId"] == PROFILE_ID
    assert "Vessel + crew" in client.get("/dashboard").text
    repeated = app.state.analysis_service.analyse(analysis.input, "tester@example.test")
    client.get(f"/analysis?analysisId={repeated.analysis_id}")
    assert app.state.repository.get_analysis("mci", repeated.analysis_id).underwriting.crew.members[0].person_id == PROFILE_ID
    page = client.post(base + "/remove", data={"csrf": csrf(page), "person_id": PROFILE_ID})
    assert app.state.repository.get_analysis("mci", repeated.analysis_id).underwriting.score is None
    assert app.state.repository.get_analysis("mci", analysis.analysis_id).underwriting.score is None


def test_connected_routes_csrf_and_allowlist(connected):
    client, app, analysis = connected
    base = f"/crew/{analysis.analysis_id}"
    page = client.get(base)
    assert client.post(base + "/select", data={"csrf": "wrong", "person_id": PROFILE_ID}).status_code == 400
    assert client.post(base + "/select", data={"csrf": csrf(page), "person_id": "unknown"}).status_code == 404
    assert client.get(base + f"/evidence/{PROFILE_ID}").status_code == 403
    assert client.post(base + "/refresh", data={"csrf": "wrong", "person_id": PROFILE_ID}).status_code == 400
    assert client.get(base + f"/source/{PROFILE_ID}/0").status_code == 403


def test_refresh_failure_retains_evidence_and_blocks_combined_score(connected, monkeypatch):
    client, app, analysis = connected
    now = datetime.now(timezone.utc).date()
    provider = app.state.crew_provider
    app.state.crew_repository.save(vessel_key(analysis), provider.get(PROFILE_ID),
                                   "Captain", now, now + timedelta(days=60), "reviewer")
    def fail(*args, **kwargs):
        raise httpx.ConnectError("unavailable")
    monkeypatch.setattr(httpx.Client, "get", fail)
    with pytest.raises(CrewUnavailable):
        provider.refresh(PROFILE_ID)
    assert len(provider.get(PROFILE_ID)["certificates"]) == 6
    result = app.state.enrich_crew_risk(analysis)
    assert result.underwriting.score is None


def test_provider_preserves_unknown_status_and_ignores_archived_documents(tmp_path):
    payload = write_provider_data(tmp_path)
    payload["documents"][0]["verifications"] = [{"status": "FUTURE_STATUS"}]
    payload["documents"][1]["archivedAt"] = "2026-10-01T00:00:00Z"
    cache = tmp_path / "crew/evidence" / f"{PROFILE_ID}.json"
    cache.write_text(json.dumps({"retrievedAt": datetime.now(timezone.utc).isoformat(), "payload": payload}))
    provider = CrewdentialsProvider(Settings(data_dir=tmp_path))
    result = provider.get(PROFILE_ID)
    assert len(result["certificates"]) == 5
    assert result["certificates"][0]["statuses"] == ["FUTURE_STATUS"]
    assert result["raw"] == payload
    assert provider.get("../../.env") is None


@pytest.mark.parametrize("exposure", [0, 19, 40, 79, 100])
def test_combination_is_bounded_and_never_reduces_exposure(connected, exposure):
    _, _, analysis = connected
    analysis.risk.score = exposure
    crew = assess_crew([assignment()], Provider({PROFILE_ID: {**person(), "certificates": []}}), TODAY)
    combined = combine_risk(analysis, crew)
    assert combined.score == exposure + round((100 - exposure) * .25)
    assert exposure <= combined.score <= min(100, exposure + 25)


def test_restricted_user_cannot_read_crew_via_analysis_or_export(connected, monkeypatch):
    client, app, analysis = connected
    now = datetime.now(timezone.utc).date()
    app.state.crew_repository.save(vessel_key(analysis), app.state.crew_provider.get(PROFILE_ID), "Captain", now,
                                   now + timedelta(days=90), "reviewer")
    app.state.enrich_crew_risk(analysis)
    monkeypatch.setattr(app.state.users, "authenticate", lambda *args: {"email": "viewer@example.test", "role": "exposure"})
    page = client.get("/dashboard")
    client.post("/login", data={"csrf": csrf(page), "email": "viewer@example.test", "password": "unused"})
    assert "Sam Jones" not in client.get(f"/analysis?analysisId={analysis.analysis_id}").text
    assert client.get(f"/analysis/{analysis.analysis_id}/json").json()["underwriting"] is None


def test_mmsi_assignment_is_promoted_to_imo_and_not_shared_with_another_imo(connected):
    _, app, analysis = connected
    store = app.state.crew_repository
    analysis = analysis.model_copy(deep=True)
    analysis.vessel.mmsi = ["999111222"]
    analysis.input.identifier_type = "MMSI"
    analysis.input.identifier = "999111222"
    mmsi_only = analysis.model_copy(deep=True)
    mmsi_only.vessel.imo = None
    key = store.key(mmsi_only)
    now = datetime.now(timezone.utc).date()
    store.save(key, app.state.crew_provider.get(PROFILE_ID), "Captain", now, now + timedelta(days=90), "reviewer")
    imo_key = store.key(analysis)
    assert imo_key.startswith("mci:IMO:")
    assert len(store.list(imo_key)) == 1
    assert store.list(key) == []
    assert store.key(mmsi_only) == imo_key
    reused_mmsi = analysis.model_copy(deep=True)
    reused_mmsi.vessel.imo = "9202534" if analysis.vessel.imo != "9202534" else "9319466"
    assert not store.list(store.key(reused_mmsi))


def test_refresh_success_retains_full_response_and_updates_unknown_status(connected, monkeypatch):
    client, app, analysis = connected
    provider = app.state.crew_provider
    raw = deepcopy(provider.get(PROFILE_ID)["raw"])
    raw["documents"][0]["verifications"] = [{"status": "NEW_PROVIDER_STATUS", "trusted": None}]
    calls = []
    def result(_client, url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json=raw, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx.Client, "get", result)
    profile = provider.refresh(PROFILE_ID)
    assert profile["raw"] == raw
    assert profile["certificates"][0]["statuses"] == ["NEW_PROVIDER_STATUS"]
    assert not profile.get("refresh_error")
    assert calls[0][1]["headers"]["Authorization"] == "Bearer test-key"


def test_refresh_http_error_is_visible_and_preserves_previous_source(connected, monkeypatch):
    client, app, analysis = connected
    provider = app.state.crew_provider
    previous = provider.get(PROFILE_ID)["raw"]
    def result(_client, url, **kwargs):
        return httpx.Response(401, json={"error": "unauthorised"}, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx.Client, "get", result)
    with pytest.raises(CrewUnavailable):
        provider.refresh(PROFILE_ID)
    assert provider.get(PROFILE_ID)["raw"] == previous
    assert provider.get(PROFILE_ID)["refresh_error"]
