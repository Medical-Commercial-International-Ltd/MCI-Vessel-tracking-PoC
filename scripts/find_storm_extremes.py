"""Read-only NOAA cache search for contrasting yacht movement candidates."""
import json
import sqlite3
import pickle
import argparse
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from app.config import Settings
from app.ais_data import TrackSegment, _decode_gpkg_multiline, _parse_datetime, segment_position_lines, interpolate_position, haversine_nm, bearing_degrees
from app.event_lookup import EventLookupService, LookupWindow, _storm_windows, _table_overlaps_window
from app.storm_behaviour import distance, projected_distance
from app.real_services import _wind_field


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cached-only',action='store_true')
    parser.add_argument('--radius',type=float,default=200)
    args=parser.parse_args()
    settings = Settings()
    svc = EventLookupService(settings.ais_cache_dir, Path('app/data/ports.json'))
    results = []
    wanted = {'MILTON', 'HELENE', 'IDALIA', 'LEE', 'OPHELIA', 'ERIN'}
    for storm in svc.storms():
        if storm.name not in wanted:
            continue
        windows = _storm_windows(storm, None, 200)
        windows = [LookupWindow(storm.start, storm.end, min(w.min_lon for w in windows),
                   max(w.max_lon for w in windows), min(w.min_lat for w in windows), max(w.max_lat for w in windows))]
        rows = {}
        cache=Path(f'.test-tmp/storm-search/storm-search-{storm.storm_id}.pickle')
        cache.parent.mkdir(parents=True,exist_ok=True)
        if args.cached_only and not cache.exists():
            continue
        if cache.exists():
            rows=pickle.loads(cache.read_bytes())
        for year in svc.years:
            if rows and cache.exists():
                break
            path = svc.track_dir / f'AISVesselTracks{year}.gpkg'
            with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as con:
                tables = [r[0] for r in con.execute("select table_name from gpkg_contents where data_type='features'")]
                for table in tables:
                    for w in windows:
                        if not w.start.year <= year <= w.end.year or not _table_overlaps_window(table,year,w):
                            continue
                        query = f'''select t.OBJECTID,t.MMSI,t.Shape,t.TrackStartTime,t.TrackEndTime,t.VesselGroup,t.VesselType,t.Length
                          from "rtree_{table}_Shape" r cross join "{table}" t on r.id=t.OBJECTID
                          where r.minX<=? and r.maxX>=? and r.minY<=? and r.maxY>=?
                          and t.TrackEndTime>=? and t.TrackStartTime<?
                          and (t.VesselGroup='Pleasure Craft/Sailing' or t.VesselType in (36,37))
                          and t.Length>=24 and t.MMSI between 200000000 and 799999999'''
                        params=(w.max_lon,w.min_lon,w.max_lat,w.min_lat,w.start.strftime('%Y-%m-%dT%H:%M:%S'),w.end.strftime('%Y-%m-%dT%H:%M:%S'))
                        for r in con.execute(query,params):
                            rows[(year,table,r[0])]=r
        cache.write_bytes(pickle.dumps(rows))
        print(storm.name,'segments',len(rows),flush=True)
        best = {}
        for row in rows.values():
            oid,mmsi,geom,start,end,group,code,length = row
            seg=TrackSegment(_parse_datetime(start),_parse_datetime(end),_decode_gpkg_multiline(bytes(geom)),group,code,length,None,None)
            for line in segment_position_lines(seg):
                if len(line)<2:
                    continue
                # Same six-hour support limit as the application's exposure model.
                samples=[]
                cursor=max(line[0].timestamp,storm.start)
                edge=0
                while cursor<=min(line[-1].timestamp,storm.end):
                    while edge+1<len(line)-1 and line[edge+1].timestamp<cursor:
                        edge+=1
                    l,r=line[edge:edge+2]
                    if l.timestamp<=cursor<=r.timestamp and r.timestamp-l.timestamp<=timedelta(hours=6):
                        samples.append(interpolate_position(l,r,cursor))
                    else:
                        samples.append(None)
                    cursor+=timedelta(minutes=15)
                for i in range(8,len(samples)):
                    if any(p is None for p in samples[i-8:i+1]):
                        continue
                    a,b,c=samples[i-8],samples[i-4],samples[i]
                    sa,sb,sc=storm.at(a.timestamp),storm.at(b.timestamp),storm.at(c.timestamp)
                    if not all([sa,sb,sc]):
                        continue
                    da,db,dc=distance(a,sa),distance(b,sb),distance(c,sc)
                    if min(da,db,dc)>args.radius:
                        continue
                    v1,v2=distance(a,b),distance(b,c)
                    h1=bearing_degrees(a.latitude,a.longitude,b.latitude,b.longitude)
                    h2=bearing_degrees(b.latitude,b.longitude,c.latitude,c.longitude)
                    turn=abs((h2-h1+180)%360-180)
                    continued=projected_distance(b,h1,v1,sc)
                    field=_wind_field(c,sc,dc)
                    kind=None
                    if v1>=3 and v2>=3 and da-db>=5 and dc-db>=5 and turn>=30 and dc-continued>=10:
                        kind='avoidance';rank=dc-continued
                    elif v1>=3 and v2>=3 and da-dc>=10 and turn<=15 and field in {'34KT','50KT','64KT'}:
                        kind='continued_approach';rank=300-dc
                    if kind:
                        record=dict(kind=kind,storm=storm.name,storm_id=storm.storm_id,mmsi=str(mmsi),length=length,
                            start=str(a.timestamp),turn_time=str(b.timestamp),end=str(c.timestamp),
                            positions=[[p.longitude,p.latitude] for p in (a,b,c)],distances=[round(x,1) for x in (da,db,dc)],
                            speeds=[round(v1,1),round(v2,1)],turn=round(turn,1),continuation_distance=round(continued,1),
                            improvement=round(dc-continued,1),wind_field=field,storm_wind=sc.wind_kt,rank=rank)
                        key=(kind,mmsi)
                        if key not in best or rank>best[key]['rank']:
                            best[key]=record
                for span in (4,12,24,48,96):
                    for i in range(span,len(samples)):
                        if any(p is None for p in samples[i-span:i+1]):
                            continue
                        a,c=samples[i-span],samples[i]
                        sa,sc=storm.at(a.timestamp),storm.at(c.timestamp)
                        if sa is None or sc is None:
                            continue
                        da,dc=distance(a,sa),distance(c,sc)
                        fixed=distance(a,sc)
                        fixed_field=_wind_field(a,sc,fixed)
                        actual_field=_wind_field(c,sc,dc)
                        if (da<=args.radius and da-fixed>=20 and dc-fixed>=30 and dc>da
                                and sc.wind_kt>=34 and actual_field=='OUTSIDE 34KT'):
                            record=dict(kind='relocation',storm=storm.name,storm_id=storm.storm_id,mmsi=str(mmsi),length=length,
                               start=str(a.timestamp),end=str(c.timestamp),positions=[[p.longitude,p.latitude] for p in (a,c)],
                               distances=[round(da,1),round(dc,1)],fixed_distance=round(fixed,1),fixed_field=fixed_field,
                               wind_field=actual_field,improvement=round(dc-fixed,1),rank=dc-fixed)
                            key=('relocation',mmsi)
                            if key not in best or record['rank']>best[key]['rank']:
                                best[key]=record
        results.extend(best.values())
        Path(f'data/storm-extreme-candidates-{args.radius:g}.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        for kind in ['continued_approach','avoidance','relocation']:
            print(kind,sorted([r for r in best.values() if r['kind']==kind],key=lambda r:-r['rank'])[:6],flush=True)


if __name__=='__main__':
    main()
