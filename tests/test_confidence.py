from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from app.ais_data import TimedPosition
from app.confidence import assess_confidence

START=datetime(2025,1,1,tzinfo=timezone.utc)
END=START+timedelta(days=365)

def intervals(days):
 return [(TimedPosition(START+timedelta(hours=h),0,0),TimedPosition(START+timedelta(hours=h+1),0,0)) for h in range(days*24)]

def quality(points=50000,days=365,edges=None,events=(),missing=()):
 return assess_confidence(points,days,START,END,intervals(days) if edges is None else edges,events,missing)

def test_sparse_three_days_stays_low_even_with_dense_positions():
 assert quality(50000,3)['rating']=='LOW'
 assert quality(4,1)['rating']=='INSUFFICIENT'

def test_volume_improves_score_without_inventing_coverage():
 small=quality(100,100);large=quality(50000,100)
 assert small['confidence_score']<large['confidence_score']
 assert small['supported_time_coverage_percent']==large['supported_time_coverage_percent']

def test_high_coverage_can_be_high_and_missing_years_prevent_high():
 assert quality()['rating']=='HIGH'
 assert quality(missing=[2024])['rating']=='MEDIUM'

def test_only_detected_encounter_windows_are_assessed():
 event=SimpleNamespace(closest_approach=SimpleNamespace(timestamp=START+timedelta(days=10)))
 covered=quality(days=100,events=[event])
 missing=SimpleNamespace(closest_approach=SimpleNamespace(timestamp=START+timedelta(days=200)))
 gapped=quality(days=100,events=[missing])
 assert covered['encounter_coverage_percent']==100
 assert covered['significant_storm_period_gaps']==0
 assert gapped['encounter_coverage_percent']==0
 assert gapped['significant_storm_period_gaps']==1
 assert gapped['confidence_score']<covered['confidence_score']
 assert quality(days=100)['encounter_coverage_percent'] is None

def test_long_gaps_do_not_count_as_supported_time():
 a=TimedPosition(START,0,0);b=TimedPosition(START+timedelta(hours=7),0,0)
 assert quality(edges=[(a,b)])['supported_time_coverage_percent']==0
