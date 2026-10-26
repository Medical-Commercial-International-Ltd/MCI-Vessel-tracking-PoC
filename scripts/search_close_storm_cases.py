"""Search every cached named storm against all NOAA pleasure-craft tracks.

Creates a separate indexed research cache; original NOAA files are read-only.
Run: python -m scripts.search_close_storm_cases
"""
from collections import defaultdict
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
import argparse

from app.config import Settings
from app.ais_data import TrackSegment, _decode_gpkg_multiline, _parse_datetime, segment_position_lines, interpolate_position, bearing_degrees
from app.event_lookup import EventLookupService, _storm_windows
from app.storm_behaviour import distance, projected_distance
from app.real_services import _wind_field

CACHE = Path('.test-tmp/close-storm-search/yachts.sqlite')
OUTPUT = Path('data/close-storm-search.json')


def prepare(svc):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(CACHE)
    db.execute('create table if not exists complete (year integer primary key)')
    db.execute('''create table if not exists tracks (id integer primary key, year integer, source_table text,
       source_id integer, mmsi integer, shape blob, start text, end text, vessel_group text, type integer, length real,
       min_lon real, max_lon real, min_lat real, max_lat real)''')
    for year in svc.years:
        if db.execute('select 1 from complete where year=?',(year,)).fetchone():
            continue
        db.execute('delete from tracks where year=?',(year,))
        count = 0
        path = svc.track_dir / f'AISVesselTracks{year}.gpkg'
        with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as source:
            source.execute('pragma cache_size=-65536')
            tables = [r[0] for r in source.execute("select table_name from gpkg_contents where data_type='features'")]
            for table in tables:
                query=f'''select OBJECTID,MMSI,Shape,TrackStartTime,TrackEndTime,VesselGroup,VesselType,Length
                     from "{table}" not indexed where (VesselGroup='Pleasure Craft/Sailing' or VesselType in (36,37))
                     and MMSI between 200000000 and 799999999'''
                batch=[]
                for oid,mmsi,shape,start,end,group,code,length in source.execute(query):
                    lines=_decode_gpkg_multiline(bytes(shape))
                    coords=[p for line in lines for p in line]
                    if not coords:
                        continue
                    xs,ys=zip(*coords)
                    batch.append((year,table,oid,mmsi,shape,start,end,group,code,length,min(xs),max(xs),min(ys),max(ys)))
                    count+=1
                    if len(batch)>=2000:
                        db.executemany('insert into tracks values (null,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',batch)
                        batch=[]
                db.executemany('insert into tracks values (null,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',batch)
                print('indexed',year,table,count,'pleasure-craft segments',flush=True)
        db.execute('insert into complete values (?)',(year,))
        db.commit()
    db.execute('create index if not exists track_dates on tracks (year,start,end)')
    db.commit()
    return db


def sample_line(line, storm):
    cursor=max(line[0].timestamp,storm.start)
    end=min(line[-1].timestamp,storm.end)
    edge=0
    while cursor<=end:
        while edge+1<len(line)-1 and line[edge+1].timestamp<cursor:
            edge+=1
        a,b=line[edge:edge+2]
        if a.timestamp<=cursor<=b.timestamp and b.timestamp-a.timestamp<=timedelta(hours=6):
            yield interpolate_position(a,b,cursor)
        else:
            yield None
        cursor+=timedelta(minutes=15)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--recheck-close',action='store_true')
    args=parser.parse_args()
    prior=json.loads(OUTPUT.read_text()) if args.recheck_close else None
    selected=defaultdict(set)
    if prior:
        for item in prior['encounters']:selected[item['storm_id']].add(item['mmsi'])
    svc=EventLookupService(Settings().ais_cache_dir,Path('none'))
    storms=[s for s in svc.storms() if s.name not in {'UNNAMED','NOT NAMED','UNKNOWN'}]
    db=prepare(svc)
    report={'years':svc.years,'named_storms':len(storms),'radius_nm':70,'minimum_length_filter':None,
            'tracks_indexed':db.execute('select count(*) from tracks').fetchone()[0],
            'limitations':['Derived intermediate timestamps, not original AIS broadcast times.',
                          'Historical tracks cannot establish captain intent or an insurance decline decision.'],
            'storms_completed':[], 'encounters':[], 'patterns':[]}
    for storm in storms:
        if prior and storm.storm_id not in selected:
            report['storms_completed'].append(storm.storm_id)
            continue
        windows=_storm_windows(storm,None,100)
        if not windows:
            continue
        lo,hi=min(w.min_lon for w in windows),max(w.max_lon for w in windows)
        bottom,top=min(w.min_lat for w in windows),max(w.max_lat for w in windows)
        rows=db.execute('''select * from tracks where year=? and start<=? and end>=?
          and min_lon<=? and max_lon>=? and min_lat<=? and max_lat>=?''',
          (storm.start.year,storm.end.isoformat(),storm.start.isoformat(),hi,lo,top,bottom)).fetchall()
        encounters={}
        patterns={}
        for row in rows:
            rid,year,table,oid,mmsi,geom,start,end,group,code,length,*_=row
            if prior and str(mmsi) not in selected[storm.storm_id]:continue
            seg=TrackSegment(_parse_datetime(start),_parse_datetime(end),_decode_gpkg_multiline(bytes(geom)),group,code,length,None,None)
            for line in segment_position_lines(seg):
                if len(line)<2:
                    continue
                samples=list(sample_line(line,storm))
                values=[]
                for p in samples:
                    s=storm.at(p.timestamp) if p else None
                    values.append((p,s,distance(p,s)) if s else None)
                close=[v for v in values if v and v[2]<=70 and v[1].wind_kt>=34 and v[1].status in {'TS','HU','SS'}]
                if not close:
                    continue
                closest=min(close,key=lambda v:v[2])
                meta=dict(mmsi=str(mmsi),length_m=length,storm=storm.name,storm_id=storm.storm_id,
                     source_table=table,source_id=oid,source_start=start,source_end=end)
                item=dict(**meta,distance_nm=round(closest[2],2),time=closest[0].timestamp.isoformat(),
                     position=[closest[0].longitude,closest[0].latitude],storm_wind_kt=closest[1].wind_kt,
                     field=_wind_field(*closest))
                if mmsi not in encounters or item['distance_nm']<encounters[mmsi]['distance_nm']:
                    encounters[mmsi]=item
                for span in (4,8,24,48,96):
                    for i in range(span,len(values)):
                        window=values[i-span:i+1]
                        if any(v is None for v in window):
                            continue
                        a,sa,da=window[0];c,sc,dc=window[-1]
                        if min(v[2] for v in window)>70 or sc.wind_kt<34 or sc.status not in {'TS','HU','SS'}:
                            continue
                        hours=span/4
                        travel=distance(a,c)
                        fixed=distance(a,sc)
                        improvement=dc-fixed
                        kind=None;rank=0
                        if travel/hours<=1 and 50<=da<=70 and da-dc>=5:
                            kind='stationary_approach';rank=da-dc
                        elif travel/hours>2 and 50<=da<=70 and da-dc>=5:
                            b=window[len(window)//2][0]
                            h1=bearing_degrees(a.latitude,a.longitude,b.latitude,b.longitude)
                            h2=bearing_degrees(b.latitude,b.longitude,c.latitude,c.longitude)
                            turn=abs((h2-h1+180)%360-180)
                            if turn<=15:
                                kind='continued_approach';rank=da-dc
                        if 50<=da<=70 and da-fixed>=5 and improvement>=10 and dc>=50:
                            kind='relocation';rank=improvement
                        if kind:
                            event=dict(**meta,kind=kind,start=a.timestamp.isoformat(),end=c.timestamp.isoformat(),
                                distances=[round(da,2),round(dc,2)],fixed_distance=round(fixed,2),improvement=round(improvement,2),
                                speed_kt=round(travel/hours,2),positions=[[p.longitude,p.latitude] for p in (a,c)],
                                field=_wind_field(c,sc,dc),fixed_field=_wind_field(a,sc,fixed),rank=rank)
                            key=(mmsi,kind)
                            if key not in patterns or rank>patterns[key]['rank']:
                                patterns[key]=event
        report['storms_completed'].append(storm.storm_id)
        report['encounters'].extend(encounters.values())
        report['patterns'].extend(patterns.values())
        destination=OUTPUT.with_name('close-storm-recheck.json') if prior else OUTPUT
        destination.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(storm.storm_id,storm.name,'rows',len(rows),'close yachts',len(encounters),'patterns',len(patterns),flush=True)
    destination=OUTPUT.with_name('close-storm-recheck.json') if prior else OUTPUT
    destination.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('COMPLETE',len(report['storms_completed']),'storms',len(report['encounters']),'encounters',len(report['patterns']),'patterns',flush=True)


if __name__=='__main__':
    main()
