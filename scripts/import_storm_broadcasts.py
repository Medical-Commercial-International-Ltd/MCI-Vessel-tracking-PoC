"""Persist original NOAA observations for researched vessels, retaining provenance."""
import csv
from collections import defaultdict
from pathlib import Path
import json
import zipfile
import argparse

from app.config import Settings
from app.repositories import _atomic_json_write


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('dates',nargs='+')
    args=parser.parse_args()
    root=Settings().data_dir/'broadcasts'
    for day in args.dates:
        summary=json.loads(Path(f'data/verified-close-broadcasts-{day}.json').read_text())
        targets={v['mmsi'].encode() for v in summary['vessels']} | {b'368001090', b'368281860'}
        groups=defaultdict(list)
        archive=Path('.test-tmp/close-storm-search')/('AIS_'+day.replace('-','_')+'.zip')
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if not name.lower().endswith('.csv'):continue
                with z.open(name) as f:
                    header=next(csv.reader([f.readline().decode('utf-8-sig').strip()]))
                    for line in f:
                        if line.split(b',',1)[0] in targets:
                            row=dict(zip(header,next(csv.reader([line.decode('utf-8-sig').strip()]))))
                            groups[row['MMSI']].append(row)
        for mmsi,rows in groups.items():
            path=root/f'{mmsi}.json'
            stored=json.loads(path.read_text()) if path.exists() else {'rows':[],'sourceDates':[],'sources':{}}
            stored['rows']=[r for r in stored['rows'] if not r['BaseDateTime'].startswith(day)]+rows
            stored['sourceDates']=sorted(set(stored['sourceDates'])|{day})
            stored['sources'][day]=f'https://coast.noaa.gov/htdata/CMSP/AISDataHandler/{day[:4]}/AIS_{day.replace("-","_")}.zip'
            _atomic_json_write(path,stored)
        print(day,len(groups),'vessels',sum(map(len,groups.values())),'original broadcasts persisted',flush=True)


if __name__=='__main__':main()
