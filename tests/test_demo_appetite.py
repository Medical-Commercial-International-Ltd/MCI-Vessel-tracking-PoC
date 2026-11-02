import random
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.crew_risk import assess_crew, combine_risk
from app.demo_appetite import assess_appetite, worked_examples
from app.demo_cases import local_cases
from app.demo_crew import generate_roster, RosterProvider
from app.main import create_app
from app.scoring import aggregate_risk


def assessment(score=29, scenario='clear', confidence='MEDIUM', movement=None):
    snapshot = generate_roster(random.Random(7), scenario=scenario)
    crew = assess_crew(snapshot['assignments'], RosterProvider(snapshot))
    risk = aggregate_risk([score], confidence=confidence, preserve_worst=True)
    risk.model_version = 'TC-EXPOSURE-v0.5'
    analysis = SimpleNamespace(risk=risk, is_synthetic=True,
        data_quality=SimpleNamespace(identity_confidence='HIGH'),
        audit=SimpleNamespace(calculation_hash='test'),
        statistics=SimpleNamespace(named_storm_encounters=1),
        storm_response=SimpleNamespace(windows=[SimpleNamespace(kind=movement)] if movement else []))
    analysis.underwriting = combine_risk(analysis, crew)
    return analysis


@pytest.mark.parametrize('score,outcome', [(59, 'OFFER'), (60, 'REFER'), (79, 'REFER'), (80, 'DECLINE')])
def test_appetite_boundaries_do_not_change_scores(score, outcome):
    analysis = assessment(score)
    before = analysis.underwriting.model_dump()
    assert assess_appetite(analysis)['outcome'] == outcome
    assert analysis.underwriting.model_dump() == before
    assert analysis.risk.score == score


@pytest.mark.parametrize('scenario,outcome', [('clear', 'OFFER'), ('expiring', 'OFFER'),
    ('missing', 'REFER'), ('pending', 'REFER'), ('expired', 'DECLINE')])
def test_missing_evidence_is_distinct_from_known_expiry(scenario, outcome):
    assert assess_appetite(assessment(scenario=scenario))['outcome'] == outcome


def test_weak_tracking_and_stationarity_never_establish_weather_decline():
    assert assess_appetite(assessment(0, confidence='LOW'))['outcome'] == 'REFER'
    assert assess_appetite(assessment(91, confidence='INSUFFICIENT'))['outcome'] == 'REFER'
    assert assess_appetite(assessment(91, movement='STATIONARY_APPROACH'))['outcome'] == 'REFER'
    assert assess_appetite(assessment(54, movement='MOVED_TOWARDS'))['outcome'] == 'REFER'


def test_confirmed_crew_blocker_still_applies_when_weather_unknown():
    assert assess_appetite(assessment(scenario='expired', confidence='LOW'))['outcome'] == 'DECLINE'
    analysis = assessment(scenario='expired')
    for member in analysis.underwriting.crew.members:
        member.score = None
    analysis.underwriting.crew.score = None
    assert assess_appetite(analysis)['outcome'] == 'REFER'


def test_unverified_expiry_and_old_models_require_review():
    analysis = assessment(scenario='expired')
    for member in analysis.underwriting.crew.members:
        for check in member.checks:
            check.verification.status = 'warning'
            check.verification.label = 'Pending'
    assert assess_appetite(analysis)['outcome'] == 'REFER'
    analysis = assessment(90)
    analysis.risk.model_version = 'TC-EXPOSURE-v0.3'
    assert assess_appetite(analysis)['outcome'] == 'REFER'
    analysis = assessment()
    analysis.data_quality.identity_confidence = 'LOW'
    assert assess_appetite(analysis)['outcome'] == 'REFER'


def test_repeatable_examples_have_two_offers_two_declines_and_a_referral():
    first, second = worked_examples(), worked_examples()
    assert [(x['combined'], x['policy']['outcome']) for x in first] == [
        (29, 'OFFER'), (36, 'OFFER'), (86, 'DECLINE'), (63, 'DECLINE'), (54, 'REFER')]
    assert [(x['combined'], x['policy']) for x in first] == [(x['combined'], x['policy']) for x in second]


@pytest.mark.parametrize('environment,expected', [('development', 200), ('production', 404)])
def test_case_page_login_and_development_boundary(tmp_path, environment, expected):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path, app_env=environment,
        analysis_provider='demo', demo_seed_count=0, session_secret='a-local-test-session-secret',
        admin_email='demo@example.test', admin_password='TestPassword123!'))
    with TestClient(app, base_url='https://testserver') as client:
        assert client.get('/demo-cases', follow_redirects=False).status_code == 303
        page = client.get('/login')
        token = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
        client.post('/login', data=dict(email='demo@example.test', password='TestPassword123!', csrf=token))
        page = client.get('/demo-cases')
        assert page.status_code == expected
        if expected == 200:
            assert 'Bounty' in page.text and 'El Faro' in page.text
            assert page.text.count('class="demo-notice"') == 1
            assert 'Bounty remains an investigation reference' in page.text
            assert 'Do not offer terms' in page.text


def test_case_library_does_not_substitute_different_period_or_legacy_score():
    from datetime import date, datetime, timezone
    def saved(start, version):
        return SimpleNamespace(is_synthetic=False, status='completed', vessel=SimpleNamespace(mmsi=['368001090']),
            input=SimpleNamespace(period=SimpleNamespace(from_date=start, to_date=date(2023, 10, 3)), storm_proximity_nm=70),
            risk=SimpleNamespace(model_version=version), created_at=datetime.now(timezone.utc), analysis_id='analysis_test')
    wrong = saved(date(2023, 1, 1), 'TC-EXPOSURE-v0.5')
    old = saved(date(2023, 10, 3), 'TC-EXPOSURE-v0.3')
    assert next(x for x in local_cases([wrong, old]) if x['mmsi'] == '368001090')['analysis'] is None
    correct = saved(date(2023, 10, 3), 'TC-EXPOSURE-v0.5')
    assert next(x for x in local_cases([wrong, correct]) if x['mmsi'] == '368001090')['analysis'] is correct
