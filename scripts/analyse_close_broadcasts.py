"""Find actual pleasure-craft broadcasts close to a selected NHC storm."""
import csv
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import zipfile
from bisect import bisect_left
from collections import defaultdict

from app.config import Settings
from app.hurdat import load_hurdat_storms
from app.ais_data import TimedPosition, haversine_nm, bearing_degrees
from app.storm_behaviour import distance
from app.real_services import _wind_field


def main():
    date,storm_id=sys.argv[1:3]
    s=Settings()
    storm=next(x for x in load_hurdat_storms([s.ais_cache_dir/'storms/hurdat2-atlantic.txt'],int(date[:4]),int(date[:4])) if x.storm_id==storm_id)
    bounds=(min(x.longitude for x in storm.points)-2,max(x.longitude for x in storm.points)+2,
            min(x.latitude for x in storm.points)-2,max(x.latitude for x in storm.points)+2)
    cache={};groups=defaultdict(list)
    path=Path('.test-tmp/close-storm-search')/('AIS_'+date.replace('-','_')+'.zip')
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not name.lower().endswith('.csv'):continue
            with z.open(name) as f:
                header=next(csv.reader([f.readline().decode('utf-8-sig').strip()]))
                for line in f:
                    quick=line.split(b',',5)
                    try:lat,lon=float(quick[2]),float(quick[3])
                    except (ValueError,IndexError):continue
                    if not (bounds[0]<=lon<=bounds[1] and bounds[2]<=lat<=bounds[3]):continue
                    row=dict(zip(header,next(csv.reader([line.decode('utf-8-sig').strip()]))))
                    if row.get('VesselType') not in {'36','37','36.0','37.0'}:continue
                    t=datetime.fromisoformat(row['BaseDateTime']).replace(tzinfo=timezone.utc)
                    key=t.replace(second=0,microsecond=0)
                    if key not in cache:cache[key]=storm.at(key)
                    weather=cache[key]
                    if weather is None or weather.wind_kt<34 or weather.status not in {'HU','TS','SS'}:continue
                    d=haversine_nm(lat,lon,weather.latitude,weather.longitude)
                    if d<=100:
                        row.update(distance_nm=round(d,2),field=_wind_field(TimedPosition(t,lon,lat),weather,d))
                        groups[row['MMSI']].append(row)
    result=[]
    for m,points in groups.items():
        points.sort(key=lambda p:p['BaseDateTime'])
        epochs=[datetime.fromisoformat(p['BaseDateTime']).replace(tzinfo=timezone.utc).timestamp() for p in points]
        lookup={id(p):i for i,p in enumerate(points)}
        gaps=[0]
        for i in range(1,len(points)):
            gaps.append(gaps[-1]+int(epochs[i]-epochs[i-1]>1800))
        nearest=min(points,key=lambda p:p['distance_nm'])
        if nearest['distance_nm']>70:continue
        moving=[p for p in points if 50<=p['distance_nm']<=70 and 2<float(p['SOG'])<50 and 0<=float(p['COG'])<360]
        info={'mmsi':m,'name':nearest['VesselName'],'imo':nearest['IMO'],'length':nearest['Length'],
              'closest':nearest,'count':len(points),'moving_in_band':len(moving),'patterns':[]}
        for a in moving:
            ta=datetime.fromisoformat(a['BaseDateTime']).replace(tzinfo=timezone.utc)
            for hours in (1,2,3,6):
                target=ta.timestamp()+hours*3600
                right=bisect_left(epochs,target)
                indices=[j for j in (right-1,right) if 0<=j<len(points) and abs(epochs[j]-target)<=300]
                if not indices:continue
                j=min(indices,key=lambda j:abs(epochs[j]-target))
                b=points[j]
                tb=datetime.fromisoformat(b['BaseDateTime']).replace(tzinfo=timezone.utc)
                if gaps[j]-gaps[lookup[id(a)]]>0:continue
                weather=storm.at(tb)
                if weather is None:continue
                fixed=haversine_nm(float(a['LAT']),float(a['LON']),weather.latitude,weather.longitude)
                improvement=b['distance_nm']-fixed
                if a['distance_nm']-fixed>=3 and improvement>=5 and b['distance_nm']>a['distance_nm']:
                    info['patterns'].append({'kind':'movement_away','start':a,'end':b,'fixed_distance':round(fixed,2),'improvement':round(improvement,2)})
                elif (a['distance_nm']-b['distance_nm']>=5 and 2<float(b['SOG'])<50
                      and 0<=float(b['COG'])<360
                      and haversine_nm(float(a['LAT']),float(a['LON']),float(b['LAT']),float(b['LON']))/hours>2):
                    turn=abs((float(b['COG'])-float(a['COG'])+180)%360-180)
                    if turn<=15:
                        info['patterns'].append({'kind':'continued_approach','start':a,'end':b,'turn':round(turn,1)})
        # Only keep strongest example of each pattern per vessel.
        best={}
        for p in info['patterns']:
            rank=p.get('improvement',p['start']['distance_nm']-p['end']['distance_nm'])
            if p['kind'] not in best or rank>best[p['kind']][0]:best[p['kind']]=(rank,p)
        info['patterns']=[v[1] for v in best.values()]
        result.append(info)
    out=Path(f'data/verified-close-broadcasts-{date}.json')
    out.write_text(json.dumps({'date':date,'storm_id':storm_id,'vessels':result},indent=2),encoding='utf-8')
    for x in sorted(result,key=lambda x:(-len(x['patterns']),x['closest']['distance_nm'])):
        print(x['mmsi'],x['name'],x['imo'],'closest',x['closest']['distance_nm'],'moving band',x['moving_in_band'],'patterns',[(p['kind'],p.get('improvement')) for p in x['patterns']],flush=True)


if __name__=='__main__':main()
