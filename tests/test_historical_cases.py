from datetime import date
import json
from pathlib import Path
import re
import shutil

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.demo_appetite import assess_appetite
from app.encounter_map import build_map_data
from app.main import create_app, vessel_image
from app.models import AnalysisInput, DatePeriod
from app.real_services import RealAnalysisService
from app.repositories import FileAnalysisRepository
from app.storm_response import assess_response
from scripts.import_el_faro import parse_track
from tests.test_storm_behaviour import storm
from tests.test_storm_response import moving_rows

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture
def historical_cache(tmp_path):
    data, cache = tmp_path / 'data', tmp_path / 'cache'
    (data / 'broadcasts').mkdir(parents=True)
    (cache / 'storms').mkdir(parents=True)
    shutil.copyfile(FIXTURES / 'el-faro-vdr.json', data / 'broadcasts/368208000.json')
    shutil.copyfile(FIXTURES / 'joaquin-hurdat.txt', cache / 'storms/hurdat2-atlantic.txt')
    return data, cache


def request_input(end='2015-10-01'):
    return AnalysisInput(identifier_type='MMSI', identifier='368208000',
                         period=DatePeriod(from_date=date(2015, 9, 29), to_date=date.fromisoformat(end)), storm_proximity_nm=200)


def test_official_kml_clock_is_validated_against_independent_utc_data():
    rows = parse_track((FIXTURES / 'el-faro-ntsb.kml').read_bytes(),
                       (FIXTURES / 'el-faro-wam.csv').read_text(encoding='utf-8-sig'))
    assert len(rows) == 313
    assert rows[0]['BaseDateTime'] == '2015-09-30T09:36:52+00:00'
    assert rows[-1]['BaseDateTime'] == '2015-10-01T11:35:45+00:00'
    assert any(r['BaseDateTime'] == '2015-10-01T00:00:00+00:00' for r in rows)
    # A one-hour UTC error in the independent source must stop the import.
    changed = (FIXTURES / 'el-faro-wam.csv').read_text(encoding='utf-8-sig').replace('23:27:58', '22:27:58')
    with pytest.raises(ValueError, match='does not match'):
        parse_track((FIXTURES / 'el-faro-ntsb.kml').read_bytes(), changed)


def test_real_historical_analysis_and_map_without_an_annual_track_file(historical_cache):
    data, cache = historical_cache
    repo = FileAnalysisRepository(data / 'analyses')
    service = RealAnalysisService(repo, cache)
    analysis = service.analyse(request_input(), 'test')
    assert service.tracks.available_years == []
    assert analysis.vessel.name == 'EL FARO'
    assert analysis.vessel.vessel_type == 'Cargo'
    assert analysis.risk.score == 93
    assert analysis.risk.band == 'SEVERE'
    assert analysis.historical_case.event_date == date(2015, 10, 1)
    assert assess_appetite(analysis)['outcome'] == 'DECLINE'
    assert any(s.provider == 'NTSB' and s.sha256 and s.url for s in analysis.sources)
    assert not any('No cached MarineCadastre vessel tracks are available for 2015' in w for w in analysis.data_quality.warnings)
    towards = next(w for w in analysis.storm_response.windows if w.kind == 'MOVED_TOWARDS')
    assert towards.start_distance_nm == 198.47
    assert towards.end_distance_nm == 91.85
    assert towards.improvement_nm == -104.57
    assert towards.score_adjustment == 0
    events = repo.list_encounters('mci', analysis.analysis_id)
    assert events[0].exposure.strongest_wind_field == '64KT'
    assert events[0].closest_approach.distance_nm == 18.0
    map_data = build_map_data(analysis, events, cache, data / 'broadcasts')
    assert map_data[0]['vesselSamples'] and map_data[0]['frames']
    assert repo.get_analysis('mci', analysis.analysis_id).historical_case == analysis.historical_case
    before_loss = service.analyse(request_input('2015-09-30'), 'test')
    assert before_loss.historical_case is None  # Do not leak post-event findings into pre-loss dates.


def test_position_only_evidence_requires_explicit_provenance_and_never_earns_credit():
    rows = moving_rows(-.2)
    for r in rows:
        r.update(SOG='', COG='', sourceKind='VDR', motionBasis='recorded_positions')
    weather = storm([(0, 1, 0), (1, .9, 0)])
    result = assess_response(rows, [weather])
    assert result.model_version == 'OBSERVATION-RESPONSE-v3'
    assert result.windows[0].kind == 'MOVED_AWAY'
    assert result.windows[0].score_adjustment == 0
    rows[2]['sourceKind'] = 'AIS'
    assert not assess_response(rows, [weather]).windows
    rows[2]['sourceKind'] = 'VDR'
    rows[2]['LON'] = '10'
    assert not assess_response(rows, [weather]).windows


def test_mmsi_form_portfolio_rerun_and_export(historical_cache, monkeypatch):
    data, cache = historical_cache
    app = create_app(Settings(_env_file=None, data_dir=data, ais_cache_dir=cache, analysis_provider='real',
        app_env='development', crew_provider='unavailable', crew_random_demo=True,
        admin_email='demo@example.test', admin_password='TestPassword123!', demo_seed_count=0))
    monkeypatch.setattr(app.state.photo_catalog, 'image_for', vessel_image)
    def csrf(response):
        return re.search(r'name="csrf" value="([^"]+)"', response.text)[1]
    with TestClient(app) as client:
        login = client.get('/login')
        client.post('/login', data=dict(email='demo@example.test', password='TestPassword123!', csrf=csrf(login)))
        page = client.get('/analysis?mmsi=368208000')
        assert page.context['defaults']['fromDate'] == '2015-09-29'
        assert page.context['defaults']['toDate'] == '2015-10-01'
        result = client.post('/analysis', data=dict(identifierType='MMSI', identifier='368208000',
            fromDate='2015-09-29', toDate='2015-10-01', stormProximityNm=200, csrf=csrf(page)), follow_redirects=False)
        assert result.status_code == 303
        result = client.get(result.headers['location'])
        assert result.status_code == 200 and 'Historical loss investigation' in result.text
        analysis = result.context['analysis']
        assert len(analysis.underwriting.crew.members) == 3
        exported = client.get(f'/analysis/{analysis.analysis_id}/json').json()
        assert exported['historicalCase']['retrospective']
        assert exported['risk']['score'] == 93
        portfolio = client.get('/event-lookup')
        row = next(r for r in portfolio.context['demoYachts'] if r['mmsi'] == '368208000')
        assert row['years'] == [2015] and row['analysis'].risk.score == 93
        result = client.post('/event-lookup/analyse/368208000', data=dict(csrf=csrf(portfolio)), follow_redirects=False)
        assert result.status_code == 303
        assert client.get('/analysis?mmsi=368208000&fromDate=2015-09-30&toDate=2015-09-30').context['defaults']['fromDate'] == '2015-09-30'
