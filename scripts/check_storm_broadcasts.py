"""Verify close-storm candidates against original NOAA daily AIS broadcasts."""
import argparse
import csv
import io
import json
from pathlib import Path
import zipfile
import httpx


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('date')
    args=parser.parse_args()
    folder=Path('.test-tmp/close-storm-search')
    folder.mkdir(parents=True,exist_ok=True)
    name='AIS_'+args.date.replace('-','_')+'.zip'
    path=folder/name
    url='https://coast.noaa.gov/htdata/CMSP/AISDataHandler/'+args.date[:4]+'/'+name
    if not path.exists():
        temporary=path.with_suffix('.part')
        with httpx.stream('GET',url,follow_redirects=True,timeout=60) as response:
            response.raise_for_status()
            with temporary.open('wb') as out:
                for chunk in response.iter_bytes(1024*1024):
                    out.write(chunk)
        temporary.replace(path)
    report=json.loads(Path('data/close-storm-search.json').read_text())
    targets={x['mmsi'].encode() for x in report['encounters']}
    result=[]
    with zipfile.ZipFile(path) as archive:
        for filename in archive.namelist():
            if not filename.lower().endswith('.csv'):
                continue
            with archive.open(filename) as raw:
                header=raw.readline().decode('utf-8-sig').strip()
                fields=next(csv.reader([header]))
                for line in raw:
                    if line.split(b',',1)[0] in targets:
                        result.append(dict(zip(fields,next(csv.reader([line.decode('utf-8-sig').strip()])))))
    output=folder / f'storm-broadcasts-{args.date}.json'
    output.write_text(json.dumps({'url':url,'date':args.date,'rows':result},indent=2),encoding='utf-8')
    print('Saved',len(result),'broadcasts to',output,flush=True)


if __name__=='__main__':
    main()
