"""Use recorded NOAA AIS and the official Philippe HURDAT2 excerpt as test inputs."""
import json
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.crew_risk import assess_crew, combine_risk
from app.demo_appetite import assess_appetite
from app.demo_crew import RosterProvider
from app.main import create_app
from app.models import AnalysisInput, DatePeriod
from app.presentation_cases import (CASES, VERSION, PresentationAnalysisRepository,
    build_case, case_roster, ensure_cases)
from app.real_services import RealAnalysisService
from app.repositories import FileAnalysisRepository
from app.services import DemoAnalysisService

FIXTURES = Path(__file__).parent / 'fixtures'
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def noaa_inputs(tmp_path):
    cache = tmp_path / 'cache'
    (cache / 'storms').mkdir(parents=True)
    # Exact AL172023 record excerpt from NOAA's 1851-2025 Atlantic HURDAT2.
    (cache / 'storms' / 'hurdat2-atlantic.txt').write_bytes(
        (FIXTURES / 'philippe-2023.hurdat2.txt').read_bytes())
    data = tmp_path / 'data'
    (data / 'broadcasts').mkdir(parents=True)
    original = json.loads((ROOT / 'app/data/storm-demo-broadcasts.json').read_text(encoding='utf-8'))
    for mmsi, value in original['vessels'].items():
        (data / 'broadcasts' / (mmsi + '.json')).write_text(json.dumps(value), encoding='utf-8')
    return data, cache


@pytest.mark.parametrize('key,outcome,kind', [
    ('shelter', 'REFER', 'MOVED_AWAY'), ('approach', 'DECLINE', 'MOVED_TOWARDS')])
def test_real_service_scores_and_confidence_are_preserved(noaa_inputs, key, outcome, kind):
    data, cache = noaa_inputs
    repository = FileAnalysisRepository(data / 'demo')
    analysis, encounters = build_case(key, repository, cache)
    saved = []
    baseline = RealAnalysisService(SimpleNamespace(root=repository.root,
        save_analysis=lambda item: None, save_encounter=saved.append), cache).analyse(
            AnalysisInput(identifier_type='MMSI', identifier=CASES[key]['mmsi'],
                period=DatePeriod(from_date=date(2023, 1, 1), to_date=date(2025, 12, 31)),
                storm_proximity_nm=70), 'test')
    assert not analysis.is_synthetic and analysis.synthetic_notice is None
    assert analysis.vessel == baseline.vessel
    assert analysis.risk == baseline.risk
    assert analysis.data_quality == baseline.data_quality
    assert analysis.statistics == baseline.statistics
    assert analysis.storm_response == baseline.storm_response
    assert [item.risk for item in encounters] == [item.risk for item in saved]
    assert all(item.analysis_id == analysis.analysis_id for item in encounters)
    assert kind in {window.kind for window in analysis.storm_response.windows}
    if key == 'approach':
        assert 'MOVED_AWAY' in {window.kind for window in analysis.storm_response.windows}
    snapshot = case_roster(key)
    crew = assess_crew(snapshot['assignments'], RosterProvider(snapshot))
    analysis.underwriting = combine_risk(analysis, crew)
    assert assess_appetite(analysis)['outcome'] == outcome
    assert snapshot == case_roster(key)
    assert all(member.experience_supplied is (key == 'shelter') for member in crew.members)
    assert any(source.sha256 and source.provider == 'NOAA National Hurricane Center'
               for source in analysis.sources)
    assert any(source.dataset == VERSION for source in analysis.sources)


def login(client):
    page = client.get('/login')
    token = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
    client.post('/login', data=dict(email='demo@example.test', password='test-password', csrf=token))


def test_noaa_broker_journey_and_refresh(noaa_inputs):
    data, cache = noaa_inputs
    app = create_app(Settings(_env_file=None, data_dir=data, ais_cache_dir=cache,
        analysis_provider='real', crew_provider='unavailable', crew_random_demo=False,
        demo_seed_count=0, admin_email='demo@example.test', admin_password='test-password'))
    with TestClient(app) as client:
        assert client.get('/analysis?analysisId=analysis_presentation_shelter',
                          follow_redirects=False).status_code == 303
        login(client)
        listing = client.get('/event-lookup')
        assert listing.status_code == 200
        assert len(listing.context['presentationCases']) == 4
        assert 'Safe Harbour' not in listing.text and 'Storm Approach' not in listing.text
        assert 'Real NOAA vessel observations' in listing.text
        assert 'Mixed response' in listing.text
        assert '18 m sailing craft' in listing.text
        assert app.state.repository.list_analyses('mci') == []
        assert client.get('/dashboard').context['summary']['total'] == 0
        for key in CASES:
            analysis_id = 'analysis_presentation_' + key
            page = client.get('/analysis?analysisId=' + analysis_id)
            assert page.status_code == 200
            assert 'NOAA-backed case with sample crew' in page.text
            assert 'fictional six-hour' not in page.text
            assert page.context['briefing']['appetite']['outcome'] == ('REFER' if key == 'shelter' else 'DECLINE')
            if key == 'approach':
                assert 'Mixed response' in page.context['briefing']['movement_summary']
            payload = json.loads(re.search(r'<script id="map-data" type="application/json">(.*?)</script>',
                                           page.text, re.S)[1])
            event = payload['events'][0]
            assert not event['synthetic'] and event['frames']
            assert event['stormId'] == 'AL172023'
            assert event['satelliteManifestUrl']
            export = client.get(f'/analysis/{analysis_id}/json').json()
            assert not export['isSynthetic'] and export['underwriting']['isTestData']
            assert export['underwriting'] == client.get(f'/analysis/{analysis_id}/json').json()['underwriting']
            members = export['underwriting']['crew']['members']
            for member in members:
                profile = client.get(f"/crew/{analysis_id}?person={member['personId']}")
                assert profile.status_code == 200
                assert 'Fictional crew overlay on a NOAA-backed case' in profile.text
                assert '/assign"' not in profile.text
            briefing = client.get(f'/analysis/{analysis_id}/briefing')
            assert briefing.status_code == 200
            assert 'NOAA-backed assessment with fictional crew overlay' in briefing.text
            assert 'https://www.nhc.noaa.gov/data/#hurdat' in briefing.text
            assert all(member['name'] not in briefing.text for member in members)
        token = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
        refresh_url = '/event-lookup/rerun/analysis_presentation_approach'
        assert client.post(refresh_url, data=dict(csrf='wrong')).status_code == 400
        response = client.post(refresh_url, data=dict(csrf=token), follow_redirects=False)
        assert response.status_code == 303
        assert response.headers['location'].endswith('analysis_presentation_approach')
        assert app.state.repository.list_analyses('mci') == []


def test_missing_noaa_inputs_do_not_fall_back_to_invented_examples(tmp_path):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path, ais_cache_dir=tmp_path/'cache',
        analysis_provider='real', admin_email='demo@example.test', admin_password='test-password'))
    with TestClient(app) as client:
        login(client)
        listing = client.get('/event-lookup')
        assert listing.text.count('NOAA case unavailable') == 2
        assert all(case['analysis'] is None for case in listing.context['presentationCases'] if case['key'] in CASES)
        assert client.get('/analysis?analysisId=analysis_presentation_shelter').status_code == 404
        assert app.state.repository.list_analyses('mci') == []


def test_legacy_invented_case_is_never_served(tmp_path):
    repository = PresentationAnalysisRepository(tmp_path / 'analyses')
    invented = DemoAnalysisService(repository.presentations).analyse(AnalysisInput(
        identifier_type='MMSI', identifier='999000001',
        period=DatePeriod(from_date=date(2025, 9, 1), to_date=date(2025, 9, 1))), 'test')
    invented.id = invented.analysis_id = 'analysis_presentation_shelter'
    invented.presentation_case = 'shelter'
    repository.presentations.save_analysis(invented)
    assert ensure_cases(repository.presentations, tmp_path / 'missing-cache')
    assert repository.get_analysis('mci', invented.analysis_id) is None


def test_replacing_old_case_excludes_stale_synthetic_encounters(noaa_inputs):
    data, cache = noaa_inputs
    repository = PresentationAnalysisRepository(data / 'analyses')
    analysis, encounters = build_case('shelter', repository.presentations, cache)
    stale = encounters[0].model_copy(deep=True)
    stale.id = 'encounter_presentation_shelter'
    stale.storm.id = 'DEMO-STORM'
    stale.storm.name = 'DEMO CYCLONE'
    repository.presentations.save_encounter(stale)
    repository.save_analysis(analysis)
    for event in encounters:
        repository.save_encounter(event)
    loaded = repository.list_encounters('mci', analysis.analysis_id)
    assert len(loaded) == len(encounters)
    assert all(event.storm.id == 'AL172023' for event in loaded)


def test_production_does_not_expose_presentation_cases(tmp_path):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path, app_env='production',
        analysis_provider='demo', demo_seed_count=0, session_secret='test-session-secret',
        admin_email='demo@example.test', admin_password='test-password'))
    with TestClient(app, base_url='https://testserver') as client:
        login(client)
        assert client.get('/analysis?analysisId=analysis_presentation_shelter').status_code == 404
        assert app.state.repository.list_analyses('mci') == []

