import json
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.crew_risk import assess_crew, combine_risk
from app.demo_appetite import assess_appetite
from app.demo_crew import RosterProvider
from app.fictional_yachts import build_case, case_roster, frames_for
from app.main import create_app


@pytest.mark.parametrize('key,score,outcome', [('aurora', 5, 'OFFER'), ('tempest', 98, 'DECLINE')])
def test_evidence_drives_expected_decision(key, score, outcome):
    analysis, events = build_case(key)
    snapshot = case_roster(key)
    assert snapshot == case_roster(key)
    crew = assess_crew(snapshot['assignments'], RosterProvider(snapshot))
    analysis.underwriting = combine_risk(analysis, crew)
    assert analysis.underwriting.score == score
    assert assess_appetite(analysis)['outcome'] == outcome
    assert analysis.is_synthetic and analysis.synthetic_notice
    assert events[0].risk.event_score == analysis.risk.score
    if key == 'aurora':
        assert crew.score == 0
        assert all(c.document.status == c.verification.status == c.validity.status == 'pass'
                   for m in crew.members for c in m.checks)
        assert all(p['cv_updated_on'] and p['experience'] for p in snapshot['people'].values())
    else:
        assert crew.score == 97
        checks = crew.members[0].checks
        assert any(c.verification.label == 'Rejected' for c in checks)
        assert any(c.validity.label == 'Expired' for c in checks)
        assert any(c.document.label == 'Not present' for c in checks)
        assert any('another person' in f for f in crew.members[0].findings)
        assert analysis.underwriting.crew_adjustment == 4


def test_route_geometry_matches_risk_story():
    away, towards = frames_for('aurora'), frames_for('tempest')
    assert len(away) == len(towards) == 73
    assert [f['storm'] for f in away] == [f['storm'] for f in towards]
    assert all(a['distanceNm'] < b['distanceNm'] for a, b in zip(away, away[1:]))
    assert all(a['distanceNm'] > b['distanceNm'] for a, b in zip(towards, towards[1:]))
    assert all(f['distanceNm'] > 65 for f in away)
    assert towards[0]['distanceNm'] > 65 and towards[-1]['distanceNm'] < 20
    for key, frames in [('aurora', away), ('tempest', towards)]:
        analysis, events = build_case(key)
        assert analysis.storm_response.windows[0].end_distance_nm == frames[-1]['distanceNm']
        assert events[0].closest_approach.distance_nm == min(f['distanceNm'] for f in frames)


def test_dates_renew_with_current_day(monkeypatch):
    import app.fictional_yachts as yachts
    import app.demo_crew as demo_crew
    future = datetime.now(timezone.utc) + timedelta(days=800)
    class FutureDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return future
    monkeypatch.setattr(yachts, 'datetime', FutureDatetime)
    monkeypatch.setattr(demo_crew, 'datetime', FutureDatetime)
    snapshot = case_roster('aurora')
    crew = assess_crew(snapshot['assignments'], RosterProvider(snapshot), today=future.date())
    assert crew.score == 0 and len(crew.members) == 3


@pytest.mark.parametrize('crew_provider', ['unavailable', 'crewdentials'])
def test_complete_demo_journey_without_noaa_cache(tmp_path, crew_provider):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path, ais_cache_dir=tmp_path/'cache',
        analysis_provider='real', crew_provider=crew_provider, crew_random_demo=False,
        admin_email='demo@example.test', admin_password='test-password'))
    with TestClient(app) as client:
        assert client.get('/analysis?analysisId=analysis_presentation_aurora', follow_redirects=False).status_code == 303
        token = re.search(r'name="csrf" value="([^"]+)"', client.get('/login').text)[1]
        client.post('/login', data=dict(email='demo@example.test', password='test-password', csrf=token))
        listing = client.get('/event-lookup')
        assert listing.status_code == 200
        assert 'AURORA HAVEN' in listing.text and 'TEMPEST VALE' in listing.text
        for key, score in [('aurora', 5), ('tempest', 98)]:
            aid = 'analysis_presentation_' + key
            page = client.get('/analysis?analysisId=' + aid)
            assert page.status_code == 200
            assert 'Fictional yacht demonstration' in page.text
            assert 'NOAA-backed case with sample crew' not in page.text
            assert 'Refresh recorded NOAA assessment' not in page.text
            assert page.context['analysis'].underwriting.score == score
            assert client.get(page.context['vesselImage']['src']).status_code == 200
            payload = json.loads(re.search(r'<script id="map-data" type="application/json">(.*?)</script>', page.text, re.S)[1])
            event = payload['events'][0]
            assert event['synthetic'] and len(event['frames']) == 73
            assert event['initialFrameIndex'] == 0 and 'satelliteManifestUrl' not in event
            exported = client.get(f'/analysis/{aid}/json').json()
            assert exported['isSynthetic'] and exported['underwriting']['score'] == score
            for member in exported['underwriting']['crew']['members']:
                profile = client.get(f"/crew/{aid}?person={member['personId']}")
                assert profile.status_code == 200
                assert 'Fictional yacht demonstration' in profile.text
                assert 'Download source document' not in profile.text
                assert 'Source: Crewdentials development workspace' not in profile.text
                assert ('Simulated verification complete' if key == 'aurora' else 'Declared information vs verification evidence') in profile.text
            briefing = client.get(f'/analysis/{aid}/briefing')
            assert briefing.status_code == 200
            assert briefing.context['analysis'].underwriting.score == score
            assert 'Fictional yacht demonstration' in briefing.text
            assert 'NOAA-backed assessment with fictional crew overlay' not in briefing.text
        assert app.state.repository.list_analyses('mci') == []
        assert client.get('/dashboard').context['summary']['total'] == 0


@pytest.mark.parametrize('key', ['aurora', 'tempest'])
def test_production_cannot_serve_fictional_presentations(tmp_path, key):
    app = create_app(Settings(_env_file=None, data_dir=tmp_path, app_env='production',
        analysis_provider='demo', demo_seed_count=0,
        admin_email='demo@example.test', admin_password='test-password'))
    with TestClient(app, base_url='https://testserver') as client:
        token = re.search(r'name="csrf" value="([^"]+)"', client.get('/login').text)[1]
        client.post('/login', data=dict(email='demo@example.test', password='test-password', csrf=token))
        assert client.get('/analysis?analysisId=analysis_presentation_' + key).status_code == 404
