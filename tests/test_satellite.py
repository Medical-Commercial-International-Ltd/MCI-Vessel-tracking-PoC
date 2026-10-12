from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app
from app.satellite import GoesArchiveProvider, ImageryUnavailable, SatelliteService, scan_time


STAMP = datetime(2025, 9, 30, 12, tzinfo=timezone.utc)
MANIFEST = {"start": "2025-09-30T00:00:00+00:00", "end": "2025-10-01T00:00:00+00:00", "bounds": [-80,25,-65,38]}


class Provider:
    name = 'Fake image provider'
    def __init__(self): self.calls = 0
    def resolve(self, timestamp, bounds): return {"timestamp": timestamp}
    def render(self, scan, bounds, output):
        self.calls += 1
        time.sleep(0.01)
        output.write_bytes(b'\x89PNG\r\n\x1a\n' + b'x'*32)
        return {"acquiredAt": scan['timestamp'].isoformat(), "acquisitionEnd": (scan['timestamp']+timedelta(minutes=9)).isoformat(),
                "satellite": "GOES-test"}


def test_same_frame_is_cached_and_concurrent_requests_share_one_render(tmp_path):
    provider = Provider()
    service = SatelliteService(tmp_path, 64, provider)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.image(MANIFEST, STAMP), range(2)))
    assert provider.calls == 1
    assert results[0][0] == results[1][0]
    assert sorted(result[2] for result in results) == [False, True]
    assert results[0][1]['acquiredAt'] == STAMP.isoformat()


def test_cache_key_includes_region_and_cache_is_bounded(tmp_path):
    service = SatelliteService(tmp_path, 64, Provider())
    service.limit_bytes = 50
    service.image(MANIFEST, STAMP)
    region = {**MANIFEST, 'bounds': [-81,25,-65,38]}
    service.image(region, STAMP)
    assert service.provider.calls == 2
    assert len(list(tmp_path.glob('*.png'))) == 1
    assert len(list(tmp_path.glob('*.json'))) == 1


@pytest.mark.parametrize('stamp', [datetime(2025,9,30,12), STAMP.replace(minute=1), STAMP-timedelta(days=2)])
def test_invalid_request_time_never_calls_provider(tmp_path, stamp):
    provider = Provider(); service = SatelliteService(tmp_path,64,provider)
    with pytest.raises(ImageryUnavailable): service.image(MANIFEST, stamp)
    assert provider.calls == 0


def test_archive_scan_parsing_and_no_stale_image_substitution(monkeypatch, tmp_path):
    assert scan_time('20252731200204') == STAMP.replace(second=20)
    provider = GoesArchiveProvider(tmp_path/'python.exe')
    satellites = []
    def catalogue(satellite, hour):
        satellites.append(satellite)
        return [{'start': STAMP - timedelta(hours=2), 'end': STAMP-timedelta(minutes=110)}]
    monkeypatch.setattr(provider, '_catalogue', catalogue)
    with pytest.raises(ImageryUnavailable, match='within ten minutes'): provider.resolve(STAMP,MANIFEST['bounds'])
    assert set(satellites) == {19}


def test_manifest_is_on_demand_and_does_not_fetch_source_images(monkeypatch,tmp_path):
    provider = Provider(); service = SatelliteService(tmp_path,64,provider)
    monkeypatch.setattr('app.satellite.build_map_data', lambda *args: [{'frames': [
        {'timestamp':STAMP.isoformat(),'storm':[-75,30],'vessel':[-76,30]},
        {'timestamp':(STAMP+timedelta(hours=1)).isoformat(),'storm':[-74,31],'vessel':None}]}])
    manifest = service.manifest(SimpleNamespace(analysis_id='analysis_test',is_synthetic=False),SimpleNamespace(id='encounter_001'),tmp_path)
    assert manifest['stepMinutes'] == 10
    assert len(manifest['frames']) == 8
    assert provider.calls == 0
    assert manifest['frames'][0]['url'].startswith('/api/satellite/analysis_test/encounter_001/image?')
    assert manifest['bounds'] == [-80,26,-70,35]


def test_satellite_endpoints_require_login(tmp_path):
    settings=Settings(data_dir=tmp_path/'data',analysis_provider='demo',demo_seed_count=0,
                      satellite_cache_dir=tmp_path/'satellite')
    with TestClient(create_app(settings)) as client:
        for path in ['/api/satellite/analysis_test/encounter_001/manifest',
                     '/api/satellite/analysis_test/encounter_001/image?time=2025-09-30T12%3A00%3A00Z']:
            assert client.get(path).status_code == 401


def test_authenticated_image_endpoint_returns_scan_times_and_handles_outage(tmp_path,monkeypatch):
    import re
    settings=Settings(data_dir=tmp_path/'data',analysis_provider='demo',demo_seed_count=0,
                      satellite_cache_dir=tmp_path/'satellite',admin_email='tester@mciuw.com',admin_password='TestPassword123!')
    app=create_app(settings)
    monkeypatch.setattr(app.state.repository,'get_analysis',lambda *args: SimpleNamespace(analysis_id='analysis_test'))
    monkeypatch.setattr(app.state.repository,'list_encounters',lambda *args: [SimpleNamespace(id='encounter_001')])
    service=app.state.satellite_service
    service.provider=Provider()
    monkeypatch.setattr(service,'manifest',lambda *args: MANIFEST)
    with TestClient(app) as client:
        login=client.get('/login')
        token=re.search(r'name="csrf" value="([^"]+)"',login.text).group(1)
        client.post('/login',data={'email':'tester@mciuw.com','password':'TestPassword123!','csrf':token})
        url='/api/satellite/analysis_test/encounter_001/image?time=2025-09-30T12%3A00%3A00Z'
        response=client.get(url)
        assert response.status_code==200 and response.headers['content-type']=='image/png'
        assert response.headers['x-satellite-acquired-at']==STAMP.isoformat()
        assert response.headers['x-satellite-cache']=='miss'
        assert client.get(url).headers['x-satellite-cache']=='hit'
        def outage(*args): raise OSError('network unavailable')
        monkeypatch.setattr(service.provider,'render',outage)
        response=client.get(url.replace('12%3A00','12%3A10'))
        assert response.status_code==503
        assert response.headers['retry-after']=='10'
