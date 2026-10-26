"""Search original, cached NOAA broadcasts for stationary ships near a storm."""
import csv
import json
from collections import defaultdict
from datetime import datetime,timezone,timedelta
from pathlib import Path
import zipfile
import argparse

from app.config import Settings
from app.hurdat import load_hurdat_storms
from app.storm_response import assess_response
from app.repositories import _atomic_json_write


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('date')
    parser.add_argument('storm_id')
    args=parser.parse_args()
    s=Settings()
    storm=next(x for x in load_hurdat_storms([s.ais_cache_dir/'storms/hurdat2-atlantic.txt',s.ais_cache_dir/'storms/hurdat2-pacific.txt'],int(args.date[:4]),int(args.date[:4])) if x.storm_id==args.storm_id)
    day=datetime.fromisoformat(args.date).replace(tzinfo=timezone.utc)
    weather=[p for i in range(25) if (p:=storm.at(day+timedelta(hours=i))) is not None]
    bounds=(min(p.longitude for p in weather)-2,max(p.longitude for p in weather)+2,
            min(p.latitude for p in weather)-2,max(p.latitude for p in weather)+2)
    archive=Path('.test-tmp/close-storm-search')/f'AIS_{args.date.replace("-","_")}.zip'
    groups=defaultdict(list)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not name.lower().endswith('.csv'):continue
            with z.open(name) as f:
                header=next(csv.reader([f.readline().decode('utf-8-sig').strip()]))
                for line in f:
                    bits=line.split(b',',5)
                    try:lat,lon=float(bits[2]),float(bits[3])
                    except (ValueError,IndexError):continue
                    if not (bounds[0]<=lon<=bounds[1] and bounds[2]<=lat<=bounds[3]):continue
                    row=dict(zip(header,next(csv.reader([line.decode('utf-8-sig').strip()]))))
                    if not row['MMSI'].isdigit() or not 200000000<=int(row['MMSI'])<=799999999:continue
                    if row.get('VesselType') in ('0','', '99'):continue
                    groups[row['MMSI']].append(row)
    matches=[]
    for mmsi,rows in groups.items():
        response=assess_response(rows,[storm],[day.date()],70)
        for w in response.windows:
            if w.kind!='STATIONARY_APPROACH':continue
            first=rows[0]
            matches.append({'name':first.get('VesselName'),'mmsi':mmsi,'imo':first.get('IMO'),
                'vessel_type':first.get('VesselType'),'window':w.model_dump(mode='json'),
                'context':'Stationary observation only; port/anchorage/shelter requires review.'})
            target=s.data_dir/'broadcasts'/f'{mmsi}.json'
            data=json.loads(target.read_text()) if target.exists() else {'rows':[],'sourceDates':[],'sources':{}}
            data['rows']=[r for r in data['rows'] if not r['BaseDateTime'].startswith(args.date)]+rows
            data['sourceDates']=sorted(set(data['sourceDates'])|{args.date})
            data['sources'][args.date]=f'https://coast.noaa.gov/htdata/CMSP/AISDataHandler/{args.date[:4]}/AIS_{args.date.replace("-","_")}.zip'
            _atomic_json_write(target,data)
    matches.sort(key=lambda x:x['window']['end_distance_nm'])
    output=Path(f'data/stationary-storm-cases-{args.date}.json')
    output.write_text(json.dumps({'date':args.date,'storm_id':args.storm_id,'ships_checked':len(groups),
        'criteria':'Starts 50-70 nm from storm; 1/2/3/6 hour window; no gap >30 min; every speed 0-1 kt; every position within 1 nm of start; storm separation decreases >=5 nm.',
        'source':f'https://coast.noaa.gov/htdata/CMSP/AISDataHandler/{args.date[:4]}/AIS_{args.date.replace("-","_")}.zip','matches':matches},indent=2),encoding='utf-8')
    print('ships checked',len(groups),'stationary close matches',len(matches),flush=True)
    for x in matches[:15]:print(x['name'],x['mmsi'],x['imo'],x['window']['start_distance_nm'],x['window']['end_distance_nm'],x['window']['start_position'],flush=True)


if __name__=='__main__':main()
