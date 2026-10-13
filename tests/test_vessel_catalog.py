import sqlite3
from datetime import date

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import AnalysisInput, DatePeriod
from app.services import DemoAnalysisService
from app.vessel_catalog import cached_vessels
from tests.test_app import _csrf


def test_noaa_shortlists_risk_and_fresh_analysis(tmp_path):
    cache = tmp_path / 'cache'
    (cache / 'tracks').mkdir(parents=True)
    for year in (2023, 2024, 2025):
        with sqlite3.connect(cache / 'tracks' / f'AISVesselTracks{year}.gpkg') as db:
            db.execute('CREATE TABLE gpkg_contents(table_name TEXT, data_type TEXT)')
            db.execute("INSERT INTO gpkg_contents VALUES ('tracks','features')")
            db.execute('CREATE TABLE tracks(MMSI INTEGER, VesselGroup TEXT)')
            db.executemany('INSERT INTO tracks(MMSI) VALUES (?)', [(367000001 + i,) for i in range(51)] + [(367000001,), (0,)])
    catalog = cached_vessels(cache)
    assert len(catalog) == 51
    assert catalog[0] == ('367000001', (2023, 2024, 2025))
    settings = Settings(data_dir=tmp_path / 'data', ais_cache_dir=cache, analysis_provider='real',
                        admin_email='tester@mciuw.com', admin_password='TestPassword123!')
    app = create_app(settings)
    repository = app.state.repository
    demo = DemoAnalysisService(repository)
    source = demo.analyse(AnalysisInput(identifier_type='MMSI', identifier='367000001',
                          period=DatePeriod(from_date=date(2024, 1, 1), to_date=date(2025, 12, 31)),
                          storm_proximity_nm=300), 'tester@mciuw.com')
    source.is_synthetic = False
    source.vessel.name = 'TEST VESSEL'
    repository.save_analysis(source)
    tracks = app.state.analysis_service.tracks
    calls = []

    class AnalysisStub:
        def analyse(self, analysis_input, created_by):
            calls.append(analysis_input)
            fresh = demo.analyse(analysis_input, created_by)
            fresh.is_synthetic = False
            repository.save_analysis(fresh)
            return fresh
    stub = AnalysisStub()
    stub.tracks = tracks
    app.state.analysis_service = stub
    with TestClient(app) as client:
        assert client.post('/event-lookup/analyse/367000002', follow_redirects=False).status_code == 303
        login = client.get('/login')
        client.post('/login', data={'email': 'tester@mciuw.com', 'password': 'TestPassword123!', 'csrf': _csrf(login.text)})
        page = client.get('/event-lookup')
        assert page.status_code == 200
        assert '1 assessed vessels' in page.text
        assert 'Highest exposure - top 50' in page.text
        assert 'Lowest exposure - top 50' in page.text
        assert page.text.count('data-vessel-rerun>') == 12
        assert 'Not assessed' in page.text
        assert '/event-lookup/analyse/367000002' not in page.text
        found = client.get('/event-lookup?vesselQuery=TEST+VESSEL')
        assert found.text.count('data-vessel-rerun>') == 12
        assert f'/event-lookup/rerun/{source.analysis_id}' in found.text
        csrf = _csrf(page.text)
        assert client.post(f'/event-lookup/rerun/{source.analysis_id}', data={'csrf': 'wrong'}).status_code == 400
        run = client.post(f'/event-lookup/rerun/{source.analysis_id}', data={'csrf': csrf}, follow_redirects=False)
        assert run.status_code == 303
        fresh_id = run.headers['location'].split('analysisId=')[1]
        assert fresh_id != source.analysis_id
        assert calls[-1] == source.input
        assert client.get(f'/analysis/{fresh_id}/json').json()['input']['stormProximityNm'] == 300
        first = client.post('/event-lookup/analyse/367000002', data={'csrf': csrf}, follow_redirects=False)
        assert first.status_code == 303
        assert calls[-1].identifier == '367000002'
        assert calls[-1].period.from_date == date(2023, 1, 1)
        assert calls[-1].period.to_date == date(2025, 12, 31)
        assert calls[-1].storm_proximity_nm == 200
        assert client.post('/event-lookup/rerun/missing', data={'csrf': csrf}).status_code == 404
        updated = client.get('/event-lookup?vesselQuery=367000002')
        assert '/event-lookup/rerun/' in updated.text



def test_rankings_cap_each_list_and_exclude_unassessed():
    from types import SimpleNamespace
    from app.vessel_catalog import exposure_rankings
    rows = [{'mmsi': str(367000000 + i), 'name': f'Vessel {i:03}',
             'analysis': SimpleNamespace(risk=SimpleNamespace(score=i))} for i in range(101)]
    rows.append({'mmsi': '999999999', 'name': 'Unassessed', 'analysis': None})
    highest, lowest = exposure_rankings(list(reversed(rows)))
    assert len(highest) == len(lowest) == 50
    assert [r['analysis'].risk.score for r in highest] == list(range(100, 50, -1))
    assert [r['analysis'].risk.score for r in lowest] == list(range(50))
    assert not {r['mmsi'] for r in highest} & {r['mmsi'] for r in lowest}
    tied = [dict(r, analysis=SimpleNamespace(risk=SimpleNamespace(score=0))) for r in rows[:60]]
    h1, l1 = exposure_rankings(tied)
    h2, l2 = exposure_rankings(list(reversed(tied)))
    assert [r['mmsi'] for r in h1] == [r['mmsi'] for r in h2]
    assert [r['mmsi'] for r in l1] == [r['mmsi'] for r in l2]


def test_demo_yacht_identity_resolves_by_mmsi_and_imo(tmp_path):
    from app.ais_data import MarineCadastreTrackStore
    from app.vessel_identity import demo_yachts
    store = MarineCadastreTrackStore(tmp_path)
    assert len(demo_yachts()) == 10
    for yacht in demo_yachts():
        vessel = store.resolve_vessel('MMSI', yacht['mmsi'])
        assert vessel.name == yacht['name']
        assert vessel.imo == yacht['imo']
        assert vessel.identity_source == 'user-supplied'
        assert store.resolve_vessel('IMO', yacht['imo']) == vessel
