"""Import NOAA coastal AIS and NTSB's published, timestamped VDR positions.

Run fetch_historical_ais first. The NTSB KML's unzoned timestamps use a
12-hour clock for afternoon points. Its explicit 24-hour EDT point labels
are used instead, checked against all 32 WAM records' independent UTC columns.
No speeds, headings, missing positions or voyage legs are fabricated.
"""
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import html
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile

import httpx

from app.config import Settings
from app.repositories import _atomic_json_write


def parse_track(kml, wam_csv):
    root = ET.fromstring(kml)
    raw_wam = wam_csv.replace('\r\r\n', '\n')
    start = raw_wam.index('Date (EDT),Time (EDT)')
    reference = {}
    for row in csv.DictReader(io.StringIO(raw_wam[start:])):
        try:
            when = datetime.strptime(row['Date (UTC)'] + ' ' + row['Time (UTC)'], '%m/%d/%Y %H:%M:%S').replace(tzinfo=timezone.utc)
            reference[when] = (float(row['Longitude']), float(row['Latitude']))
        except (ValueError, TypeError):
            continue
    if len(reference) != 32:
        raise ValueError('Unexpected WAM validation dataset')
    rows, validated = [], set()
    for point in root.findall('.//Placemark'):
        kind = (point.findtext('description') or '').strip()
        if kind not in {'WAM', 'VDR'}:
            continue
        label = re.fullmatch(r'(\d{2}:\d{2}(?::\d{2})?) EDT', point.findtext('name') or '')
        if not label:
            raise ValueError('Missing explicit EDT label')
        day = point.findtext('TimeStamp/when')[:10]
        clock = label[1] if len(label[1]) == 8 else label[1] + ':00'
        local = datetime.fromisoformat(day + 'T' + clock).replace(tzinfo=timezone(timedelta(hours=-4)))
        when = local.astimezone(timezone.utc)
        lon, lat, _ = map(float, point.findtext('Point/coordinates').split(','))
        if kind == 'WAM':
            expected = reference.get(when)
            if expected is None or abs(expected[0] - lon) > .000001 or abs(expected[1] - lat) > .000001:
                raise ValueError('KML time conversion does not match independent WAM UTC data')
            validated.add(when)
        else:
            rows.append(dict(MMSI='368208000', BaseDateTime=when.isoformat(), LAT=str(lat), LON=str(lon),
                             SOG='', COG='', VesselName='EL FARO', IMO='IMO7395351',
                             sourceKind='VDR', motionBasis='recorded_positions'))
    if len(validated) != len(reference) or len(rows) != 313:
        raise ValueError('Incomplete timestamp validation or VDR track')
    return sorted(rows, key=lambda r: r['BaseDateTime'])


def main():
    settings = Settings()
    root = settings.ais_cache_dir / 'historical-cases'
    root.mkdir(parents=True, exist_ok=True)
    references = []
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        page = client.get('https://data.ntsb.gov/Docket?ProjectID=92109')
        page.raise_for_status()
        links = [html.unescape(x) for x in re.findall(r'href="([^"]+)"', page.text)]
        for ident, name, title in [('40447555', 'el-faro-official-track.kmz', 'El Faro electronic data attachment 12: combined track'),
                                   ('40447558', 'el-faro-wam.csv', 'El Faro electronic data attachment 2: WAM UTC validation')]:
            url = next(x for x in links if 'ID=' + ident in x)
            if url.startswith('/'):
                url = 'https://data.ntsb.gov' + url
            target = root / name
            if not target.exists() or target.stat().st_size == 0:
                response = client.get(url)
                response.raise_for_status()
                if not response.content:
                    raise ValueError('Empty NTSB download')
                target.write_bytes(response.content)
            references.append(dict(provider='NTSB', dataset=title, url=url,
                retrievedAt=datetime.fromtimestamp(target.stat().st_mtime, timezone.utc).isoformat(),
                sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    with zipfile.ZipFile(root / 'el-faro-official-track.kmz') as archive:
        kml = archive.read(next(n for n in archive.namelist() if n.endswith('.kml')))
    vdr = parse_track(kml, (root / 'el-faro-wam.csv').read_text(encoding='utf-8-sig'))
    first_vdr = datetime.fromisoformat(vdr[0]['BaseDateTime'])
    ais, inspected = [], {}
    for day in ('2015_09_29', '2015_09_30', '2015_10_01'):
        target = root / f'AIS_{day}.zip'
        count = 0
        with zipfile.ZipFile(target) as archive:
            for name in archive.namelist():
                if not name.lower().endswith('.csv'):
                    continue
                with archive.open(name) as handle:
                    header = next(csv.reader([handle.readline().decode('utf-8-sig').strip()]))
                    for line in handle:
                        if line.split(b',', 1)[0] != b'368208000':
                            continue
                        row = dict(zip(header, next(csv.reader([line.decode('utf-8-sig').strip()]))))
                        count += 1
                        # VDR is the source after its recording begins; do not blend
                        # inconsistent measurements at closely spaced timestamps.
                        if datetime.fromisoformat(row['BaseDateTime']).replace(tzinfo=timezone.utc) < first_vdr:
                            row['sourceKind'] = 'AIS'
                            ais.append(row)
        inspected[day.replace('_', '-')] = count
        manifest = json.loads(target.with_suffix('.source.json').read_text())
        references.append(dict(provider='NOAA MarineCadastre', dataset=f'Original AIS archive {day}',
            url=manifest['url'], sha256=manifest['sha256'],
            retrievedAt=datetime.fromtimestamp(target.stat().st_mtime, timezone.utc).isoformat()))
    rows = ais + vdr
    dates = sorted({r['BaseDateTime'][:10] for r in rows})
    _atomic_json_write(settings.data_dir / 'broadcasts/368208000.json',
        dict(rows=rows, sourceDates=dates, sourceReferences=references,
             inspectedNoaaDates=inspected,
             importMethod='NOAA AIS before first VDR point; NTSB VDR from 2015-09-30T09:36:52Z. Explicit EDT labels converted to UTC and checked against 32 WAM UTC records.'))
    print(json.dumps(dict(imported=len(rows), ais=len(ais), vdr=len(vdr), dates=dates,
                         firstVdr=vdr[0]['BaseDateTime'], lastVdr=vdr[-1]['BaseDateTime'], inspected=inspected)), flush=True)


if __name__ == '__main__':
    main()
