from datetime import datetime, timezone
import random
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.crew_risk import assess_crew
from app.demo_crew import DemoCrewScenarios, RosterProvider, generate_roster
from app.event_lookup import LookupResponse, LookupResult
from app.main import create_app


def csrf(response):
    return re.search(r'name="csrf" value="([^"]+)"', response.text)[1]


@pytest.fixture
def demo(tmp_path):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path, analysis_provider='demo',
        app_env='development', crew_provider='unavailable', crew_random_demo=True,
        demo_seed_count=1, admin_email='demo@example.test', admin_password='TestPassword123!'))
    with TestClient(app) as client:
        login = client.get('/login')
        client.post('/login', data=dict(email='demo@example.test', password='TestPassword123!', csrf=csrf(login)))
        yield client, app, app.state.repository.list_analyses('mci')[0]


def run(client, mmsi='367000001', reference=''):
    page = client.get('/analysis')
    response = client.post('/analysis', data=dict(identifierType='MMSI', identifier=mmsi,
        fromDate='2025-01-02', toDate='2025-01-02', csrf=csrf(page), crewScenario=reference), follow_redirects=False)
    assert response.status_code == 303
    return response.headers['location'].split('=')[1]


def test_every_assessment_has_stable_fictional_crew_without_changing_saved_evidence(demo, monkeypatch):
    client, app, analysis = demo
    monkeypatch.setattr(app.state.crew_provider, 'get', lambda *args: pytest.fail('Live provider must not be consulted'))
    before = app.state.repository.get_analysis('mci', analysis.analysis_id).model_dump()
    result = client.get('/analysis?analysisId=' + analysis.analysis_id)
    assert result.status_code == 200
    assert 'Crew for this assessment' in result.text
    export = client.get(f'/analysis/{analysis.analysis_id}/json').json()
    risk = export['underwriting']
    assert risk['score'] is not None and risk['isTestData']
    assert len(risk['crew']['members']) == 3
    assert {m['role'] for m in risk['crew']['members']} == {'Captain', 'Chief officer', 'Engineer'}
    assert all(m['isTestData'] and m['score'] is not None for m in risk['crew']['members'])
    repeated = client.get(f'/analysis/{analysis.analysis_id}/json').json()
    assert repeated['underwriting'] == risk
    for member in risk['crew']['members']:
        profile = client.get(f"/crew/{analysis.analysis_id}?person={member['personId']}")
        assert profile.status_code == 200
        assert member['name'] in profile.text
        assert '/assign"' not in profile.text
        assert 'Demo application — includes fictional data for demonstration purposes.' in profile.text
    briefing = client.get(f'/analysis/{analysis.analysis_id}/briefing')
    assert 'Demo application — includes fictional data for demonstration purposes.' in briefing.text
    assert all(m['name'] not in briefing.text for m in risk['crew']['members'])
    assert app.state.repository.get_analysis('mci', analysis.analysis_id).model_dump() == before
    assert not app.state.crew_repository.list('mci:MMSI:' + analysis.vessel.mmsi[0])


def test_new_search_gets_a_new_roster_and_reruns_do_too(demo):
    client, app, _ = demo
    first, second = run(client), run(client)
    first_risk = client.get(f'/analysis/{first}/json').json()['underwriting']
    second_risk = client.get(f'/analysis/{second}/json').json()['underwriting']
    assert {m['personId'] for m in first_risk['crew']['members']}.isdisjoint(
        m['personId'] for m in second_risk['crew']['members'])
    page = client.get('/analysis')
    response = client.post('/event-lookup/rerun/' + first, data=dict(csrf=csrf(page)), follow_redirects=False)
    assert response.status_code == 303
    rerun_id = response.headers['location'].split('=')[1]
    assert client.get(f'/analysis/{rerun_id}/json').json()['underwriting']['score'] is not None


def test_search_results_include_crew_and_carry_them_into_analysis(demo):
    client, app, _ = demo
    app.state.event_lookup = SimpleNamespace(years=[2025], ports=lambda: [], storms=lambda: [],
        vessel_groups=lambda: [], search=lambda **kwargs: LookupResponse(results=[LookupResult(
            mmsi=mmsi, name='Example', vessel_group='Pleasure Craft/Sailing', vessel_type_code=37,
            length_m=30, timestamp=datetime(2025, 1, 2, tzinfo=timezone.utc), distance_nm=10)
            for mmsi in ('367000001', '367000002')], inspected_segments=2, truncated=False))
    page = client.get('/event-lookup')
    assert all(yacht['crew'] for yacht in page.context['demoYachts'])
    results = client.post('/event-lookup', data=dict(csrf=csrf(page), dateValue='2025-01-02', portId='test'))
    assert results.status_code == 200
    previews = results.context['lookupCrew']
    assert len(previews) == 2
    preview = previews['367000001']
    assert all(member['name'] in results.text for member in preview['assignments'])
    prefilled = client.get('/analysis?mmsi=367000001&crewScenario=' + preview['reference'])
    assert f'name="crewScenario" value="{preview["reference"]}"' in prefilled.text
    analysis_id = run(client, reference=preview['reference'])
    members = client.get(f'/analysis/{analysis_id}/json').json()['underwriting']['crew']['members']
    assert {m['personId'] for m in members} == {m['person_id'] for m in preview['assignments']}


def test_random_examples_have_varied_evidence_scores_and_do_not_expire_into_unknown(tmp_path):
    results = []
    for seed in range(25):
        snapshot = generate_roster(random.Random(seed))
        result = assess_crew(snapshot['assignments'], RosterProvider(snapshot))
        assert result.score is not None and result.is_test_data
        results.append(result.score)
    assert 0 in results and 50 in results and 60 in results
    scenarios = DemoCrewScenarios(tmp_path)
    snapshot = scenarios.get('analysis_test')
    assert DemoCrewScenarios(tmp_path).get('analysis_test') == snapshot
    snapshot['generated_on'] = '2000-01-01'
    from app.repositories import _atomic_json_write
    _atomic_json_write(tmp_path / 'analysis_test.json', snapshot)
    assert scenarios.get('analysis_test')['generated_on'] != '2000-01-01'
    assert scenarios.read('../../.env') is None


def test_production_does_not_enable_fictional_rosters(tmp_path):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path, app_env='production', crew_random_demo=True))
    assert app.state.demo_crew_scenarios is None


def test_auto_roster_cannot_be_changed_through_assignment_routes(demo):
    client, app, analysis = demo
    page = client.get('/crew/' + analysis.analysis_id)
    for action in ('assign', 'remove', 'refresh', 'lookup', 'select'):
        response = client.post(f'/crew/{analysis.analysis_id}/{action}', data=dict(csrf=csrf(page)))
        assert response.status_code == 400
