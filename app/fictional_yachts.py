"""Explicit, deterministic presentation fixtures, isolated from recorded assessments."""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
import hashlib
import json
import random

from app.ais_data import haversine_nm
from app.demo_crew import generate_roster
from app.encounter_map import wind_sectors
from app.models import (AnalysisDocument, AnalysisInput, AnalysisStatistics, AuditRecord,
    ClosestApproach, DataQuality, DatePeriod, EncounterDocument, EncounterExposure,
    EventRisk, Position, ResponseWindow, RiskAssessment, RiskComponents, SourceReference,
    StormDetails, StormResponseAssessment, VesselIdentity)

VERSION = 'FICTIONAL-YACHT-SHOWCASE-v1'
NOTICE = 'Fictional demonstration: yacht, crew, documents, storm, route and weather score are simulated. Not a real underwriting submission.'
CASES = {
    'aurora': dict(name='AURORA HAVEN', mmsi='999000005', storm='Demo Iris',
        movement_kind='MOVED_AWAY', movement='Early diversion away from the storm',
        context='48 m motor yacht · fictional identity',
        caveat='Diverts west into clear water; remains outside the storm-force wind field.',
        crew='Three current CVs, verified sea service and all required certificates in date.',
        image='/static/vessels/aurora-haven.png', synthetic=True),
    'tempest': dict(name='TEMPEST VALE', mmsi='999000098', storm='Demo Iris',
        movement_kind='MOVED_TOWARDS', movement='Continues into the storm core',
        context='52 m motor yacht · fictional identity',
        caveat='Continues east through storm-force winds into the hurricane-force core.',
        crew='Missing CVs, false qualification claims, rejected certificates and expired medicals.',
        image='/static/vessels/tempest-vale.png', synthetic=True),
}


def frames_for(key):
    """Same six-hour storm, opposing yacht routes; all coordinates are invented."""
    start = datetime(2026, 10, 20, 6, tzinfo=timezone.utc)
    frames = []
    for i in range(73):
        t = i / 72
        storm = [-60 + .2 * t, 22.0]
        vessel = [-61.6 + (-1.4 if key == 'aurora' else 1.6) * t, 22.0]
        point = SimpleNamespace(longitude=storm[0], latitude=storm[1],
            radii_34=(65, 65, 65, 65), radii_50=(40, 40, 40, 40), radii_64=(20, 20, 20, 20))
        frames.append(dict(timestamp=(start + timedelta(minutes=5*i)).isoformat(),
            storm=storm, vessel=vessel, windKt=85, status='HU', vesselPathId='fictional-route',
            vesselSpeedKt=round(haversine_nm(22, -61.6, 22, -63 if key == 'aurora' else -60)/6, 1),
            vesselHeadingDeg=270 if key == 'aurora' else 90,
            distanceNm=round(haversine_nm(vessel[1], vessel[0], storm[1], storm[0]), 2),
            windSectors=wind_sectors(point), missingRadii=False))
    return frames


def map_event(key, encounter):
    frames = frames_for(key)
    closest = min(frames, key=lambda f: f['distanceNm'])
    return dict(id=encounter.id, name=CASES[key]['storm'], stormId=encounter.storm.id,
        vessel=closest['vessel'], storm=closest['storm'], distanceNm=closest['distanceNm'],
        timestamp=closest['timestamp'], synthetic=True, frameStepMinutes=5,
        frames=frames, initialFrameIndex=0,
        vesselTracks=[[f['vessel'] for f in frames]], vesselGapTracks=[],
        vesselSamples=[dict(timestamp=f['timestamp'], coordinates=f['vessel']) for f in frames],
        vesselSampleCount=len(frames),
        vesselPlaybackPoints=[dict(timestamp=f['timestamp'], coordinates=f['vessel'],
            gapToNext=False, speedKt=f['vesselSpeedKt'], headingDeg=f['vesselHeadingDeg']) for f in frames],
        stormTrack=[dict(timestamp=f['timestamp'], coordinates=f['storm'], windKt=85, status='HU') for f in frames])


def build_case(key):
    case = CASES[key]
    frames = frames_for(key)
    first, last = frames[0], frames[-1]
    closest = min(frames, key=lambda f: f['distanceNm'])
    weather = 5 if key == 'aurora' else 94
    wind_hours = round(sum((a['distanceNm'] <= 65) + (b['distanceNm'] <= 65)
        for a, b in zip(frames, frames[1:])) / 24, 2)
    now = datetime.now(timezone.utc)
    analysis_id = 'analysis_presentation_' + key
    event = EncounterDocument(id='encounter_fictional_' + key, analysis_id=analysis_id,
        storm=StormDetails(id='DEMO-IRIS-2026', name=case['storm'], classification='HU', category=2),
        closest_approach=ClosestApproach(timestamp=closest['timestamp'], distance_nm=closest['distanceNm'],
            vessel_position=Position(coordinates=closest['vessel']), storm_position=Position(coordinates=closest['storm'])),
        exposure=EncounterExposure(duration_within_200_nm_hours=6,
            duration_within_34_kt_wind_field_hours=wind_hours,
            strongest_wind_field='OUTSIDE 34KT' if key == 'aurora' else '64KT', maximum_storm_wind_kt=85),
        risk=EventRisk(event_score=weather, proximity_points=5 if key == 'aurora' else 35,
            intensity_points=0 if key == 'aurora' else 25,
            wind_field_points=0 if key == 'aurora' else 25, duration_points=0 if key == 'aurora' else 9))
    fixed = round(haversine_nm(22, -61.6, 22, last['storm'][0]), 2)
    digest = hashlib.sha256(json.dumps(dict(version=VERSION, key=key, frames=frames, weather=weather), sort_keys=True).encode()).hexdigest()
    analysis = AnalysisDocument(id=analysis_id, analysis_id=analysis_id, status='completed',
        is_synthetic=True, synthetic_notice=NOTICE, presentation_case=key, created_at=now,
        created_by='MCI fictional yacht demonstration',
        input=AnalysisInput(identifier_type='MMSI', identifier=case['mmsi'],
            period=DatePeriod(from_date=date(2026, 10, 20), to_date=date(2026, 10, 20)), storm_proximity_nm=200),
        vessel=VesselIdentity(name=case['name'], mmsi=[case['mmsi']], vessel_type='Motor yacht (fictional)',
            flag='Demo registry', length_m=48 if key == 'aurora' else 52),
        risk=RiskAssessment(model_version=VERSION, score=weather, band='LOW' if key == 'aurora' else 'SEVERE',
            confidence='HIGH', components=RiskComponents(worst_encounter=weather, top_three_average=weather, recurrence=0),
            underwriter_referral=key == 'tempest'),
        statistics=AnalysisStatistics(ais_observation_count=len(frames), observed_days=1, named_storm_encounters=1,
            hours_within_200_nm=6, hours_within_34_kt_wind_field=wind_hours,
            minimum_distance_nm=closest['distanceNm'], distance_travelled_nm=round(first['vesselSpeedKt']*6, 1),
            average_speed_kt=first['vesselSpeedKt'], maximum_speed_kt=first['vesselSpeedKt']),
        encounter_ids=[event.id], data_quality=DataQuality(rating='HIGH', identity_confidence='HIGH',
            years_covered=[2026], warnings=[NOTICE, 'High confidence is a scenario assumption, not verified AIS coverage.']),
        sources=[SourceReference(provider='MCI fictional demonstration', dataset=VERSION, retrieved_at=now),
            SourceReference(provider='MCI scenario design', dataset='Authored weather scores: 5 / 94. Existing crew and combined scoring rules are applied to simulated evidence.', retrieved_at=now)],
        storm_response=StormResponseAssessment(model_version=VERSION, status='ASSESSED', observation_count=len(frames),
            source_dates=[date(2026, 10, 20)], assessed_storm_ids=[event.storm.id], findings=[NOTICE],
            windows=[ResponseWindow(kind=case['movement_kind'], storm_id=event.storm.id, storm_name=case['storm'],
                start=first['timestamp'], end=last['timestamp'], start_distance_nm=first['distanceNm'],
                end_distance_nm=last['distanceNm'], fixed_distance_nm=fixed,
                improvement_nm=round(last['distanceNm']-fixed, 2), start_position=first['vessel'], end_position=last['vessel'],
                field=event.exposure.strongest_wind_field)]),
        audit=AuditRecord(calculation_started_at=now, calculation_completed_at=now,
            application_version=VERSION, calculation_hash=digest))
    return analysis, [event]


def case_roster(key):
    snapshot = generate_roster(random.Random(51), scenario='clear')
    today = datetime.now(timezone.utc).date()
    people = {}
    for i, assignment in enumerate(snapshot['assignments']):
        person = snapshot['people'][assignment['person_id']]
        person_id = f'fictional-{key}-{i}'
        role = assignment['role']
        person.update(id=person_id, retrieved_at=today.isoformat()+'T00:00:00+00:00',
            cv_updated_on=(today-timedelta(days=10)).isoformat() if key == 'aurora' else None,
            summary='Fictional crew evidence for the yacht demonstration.')
        person['experience'] = [f'{12-i*2} years of documented yacht service as {role.lower()}.',
            'Recent service on 45–60 m motor yachts; Caribbean passage planning and storm-avoidance training.',
            'Employment dates and sea-service references match the submitted CV in this simulated review.'] if key == 'aurora' else []
        person['evidence_notes'] = ['CV, identity and employment references match; no unexplained service gaps.',
            'Role competency, ENG1 and all four basic safety certificates verified and valid beyond the assignment.'] if key == 'aurora' else [
            'Claimed current competency certificate: simulated issuer check rejects the reference as belonging to another person.',
            'Claimed current medical: submitted ENG1 expired 90 days ago.',
            'Claimed 10 years of service: no CV or sea-service references supplied; two declared assignments overlap.',
            'First-aid certificate missing; personal-safety document referred for review.']
        for j, cert in enumerate(person['certificates']):
            cert.update(id=f'{person_id}-cert-{j}', reference=f'DEMO-{key.upper()}-{i}-{j}',
                limits='Simulated review: appropriate to this yacht and assigned role; flag recognition confirmed for the scenario.')
            if key == 'tempest':
                status = 'QUERIES' if j == 3 else 'REJECTED'
                cert.update(statuses=[status], verification=status,
                    limits='Simulated discrepancy: submitted claim does not match issuer evidence.')
                if j == 4:
                    cert.update(expiry=(today-timedelta(days=90)).isoformat(), statuses=['VERIFIED_MANUAL'], verification='VERIFIED_MANUAL')
        if key == 'tempest':
            person['certificates'] = [c for c in person['certificates'] if c['type'] != 'ELEMENTARY_FIRST_AID']
        assignment.update(person_id=person_id, reviewed_at=person['retrieved_at'])
        people[person_id] = person
    snapshot['people'] = people
    return snapshot


def image_for(key):
    case = CASES[key]
    return dict(src=case['image'], alt='AI-generated portrait of fictional yacht '+case['name'],
        credit='AI-generated fictional yacht', source=None, license_url=None)


def is_fictional_case(analysis):
    return bool(analysis and getattr(analysis, 'is_synthetic', False) and getattr(analysis, 'presentation_case', None) in CASES
        and analysis.analysis_id == 'analysis_presentation_' + analysis.presentation_case
        and analysis.vessel.mmsi == [CASES[analysis.presentation_case]['mmsi']]
        and any(s.dataset == VERSION for s in analysis.sources))
