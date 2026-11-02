"""Download selected official NOAA archives outside the workspace.

Run with python -m scripts.fetch_historical_ais. Archives are retained for
reproducible extraction; partial downloads are never treated as complete.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import shutil
import zipfile

import httpx

from app.config import Settings

SOURCES = [
    '2015/AIS_2015_09_29.zip',
    '2015/AIS_2015_09_30.zip',
    '2015/AIS_2015_10_01.zip',
    '2012/10/Zone18_2012_10.gdb.zip',
]


def fetch(relative):
    root = Settings().ais_cache_dir / 'historical-cases'
    root.mkdir(parents=True, exist_ok=True)
    url = 'https://coast.noaa.gov/htdata/CMSP/AISDataHandler/' + relative
    target = root / relative.rsplit('/', 1)[-1]
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        head = client.head(url)
        head.raise_for_status()
        expected = int(head.headers['content-length'])
        if not target.exists():
            if shutil.disk_usage(root).free < expected + 4 * 1024**3:
                raise OSError('Insufficient free space for the historical archive')
            temporary = target.with_suffix(target.suffix + '.download')
            downloaded = 0
            with client.stream('GET', url) as response:
                response.raise_for_status()
                with temporary.open('wb') as output:
                    for chunk in response.iter_bytes(4 * 1024**2):
                        output.write(chunk)
                        downloaded += len(chunk)
                        if downloaded // (128 * 1024**2) != (downloaded - len(chunk)) // (128 * 1024**2):
                            print(f'{target.name}: {downloaded // 1024**2}/{expected // 1024**2} MiB', flush=True)
            if temporary.stat().st_size != expected:
                raise ValueError(f'Incomplete archive: {target.name}')
            temporary.replace(target)
        if target.stat().st_size != expected or not zipfile.is_zipfile(target):
            raise ValueError(f'Invalid archive: {target.name}')
    digest = hashlib.sha256()
    with target.open('rb') as handle:
        while chunk := handle.read(8 * 1024**2):
            digest.update(chunk)
    record = dict(url=url, bytes=expected, sha256=digest.hexdigest())
    target.with_suffix('.source.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(f'Ready: {target.name}', flush=True)
    return record


if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(fetch, SOURCES))
