"""Curated NOAA assessments with an explicitly fictional, stable crew overlay."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import random

from app.demo_crew import generate_roster
from app.models import AnalysisInput, DatePeriod, SourceReference
from app.real_services import RealAnalysisService
from app.repositories import FileAnalysisRepository

CASES = {
    'shelter': dict(name='AZULITA', mmsi='368001090', storm='Philippe',
        observation_date='2023-10-03', movement_kind='MOVED_AWAY',
        movement='Recorded movement increased separation',
        context='AIS-reported sailing craft; length and IMO not established in these broadcasts.',
        caveat='Favourable movement is supported. Sparse tracking and unconfirmed identity still require review before terms.',
        crew='Sample overlay: current CVs and clear certificate checks. Not the actual crew.'),
    'approach': dict(name='A1A', mmsi='368281860', storm='Philippe',
        observation_date='2023-10-03', movement_kind='MOVED_TOWARDS',
        movement='Recorded approach; earlier movement away also observed',
        context='AIS-reported 18 m sailing craft; a small-craft reference, not a verified superyacht.',
        caveat='Mixed response: review passage and shelter context. The demonstration decline is driven by the sample crew blockers.',
        crew='Sample overlay: missing CVs and expired critical certificates. Not the actual crew.'),
}
VERSION = 'NOAA-YACHT-SHOWCASE-v2'

from app.fictional_yachts import CASES as FICTIONAL_CASES, is_fictional_case
ALL_CASES = {**FICTIONAL_CASES, **CASES}


class PresentationAnalysisRepository(FileAnalysisRepository):
    """Separate curated copies from portfolio counts and reject old invented cases."""
    def __init__(self, root):
        super().__init__(root)
        self.presentations = FileAnalysisRepository(root.parent / 'demo')

    @staticmethod
    def is_presentation(analysis_id):
        return analysis_id in {'analysis_presentation_' + key for key in ALL_CASES}

    def get_analysis(self, tenant_id, analysis_id):
        if self.is_presentation(analysis_id):
            analysis = self.presentations.get_analysis(tenant_id, analysis_id)
            return analysis if is_recorded_case(analysis) or is_fictional_case(analysis) else None
        return super().get_analysis(tenant_id, analysis_id)

    def list_analyses(self, tenant_id):
        return [item for item in super().list_analyses(tenant_id) if not item.presentation_case]

    def save_analysis(self, analysis):
        if self.is_presentation(analysis.analysis_id):
            return self.presentations.save_analysis(analysis)
        return super().save_analysis(analysis)

    def save_encounter(self, encounter):
        if self.is_presentation(encounter.analysis_id):
            return self.presentations.save_encounter(encounter)
        return super().save_encounter(encounter)

    def list_encounters(self, tenant_id, analysis_id):
        if self.is_presentation(analysis_id):
            analysis = self.get_analysis(tenant_id, analysis_id)
            if not analysis:
                return []
            # Stable IDs can outlive an earlier case version. Only referenced
            # encounters belong to the current recorded calculation.
            return [event for event in self.presentations.list_encounters(tenant_id, analysis_id)
                    if event.id in analysis.encounter_ids]
        return super().list_encounters(tenant_id, analysis_id)


def is_recorded_case(analysis):
    return bool(analysis and not analysis.is_synthetic and analysis.presentation_case in CASES
        and CASES[analysis.presentation_case]['mmsi'] in analysis.vessel.mmsi
        and any(source.dataset == VERSION for source in analysis.sources))


class _CalculationOutput:
    """Capture service output before saving it under a stable presentation ID."""
    def __init__(self, root):
        self.root = root
        self.encounters = []

    def save_analysis(self, analysis):
        pass

    def save_encounter(self, encounter):
        self.encounters.append(encounter)


def build_case(key, repository, cache_dir):
    case = CASES[key]
    broadcast = repository.root.parent / 'broadcasts' / (case['mmsi'] + '.json')
    if not broadcast.exists():
        raise ValueError('Original NOAA AIS observations have not been imported for this case.')
    metadata = json.loads(broadcast.read_text(encoding='utf-8'))
    expected_url = 'https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2023/AIS_2023_10_03.zip'
    if metadata.get('sources', {}).get(case['observation_date']) != expected_url:
        raise ValueError('The case requires provenance from the original NOAA daily AIS archive.')
    output = _CalculationOutput(repository.root)
    analysis = RealAnalysisService(output, cache_dir).analyse(AnalysisInput(
        identifier_type='MMSI', identifier=case['mmsi'], storm_proximity_nm=70,
        period=DatePeriod(from_date=date(2023, 1, 1), to_date=date(2025, 12, 31))),
        'NOAA broker demonstration')
    if not any(w.kind == case['movement_kind'] for w in analysis.storm_response.windows):
        raise ValueError('The supplied NOAA observations do not support the expected movement comparison.')
    # Preserve the service's scores, confidence, identity and statistics exactly.
    analysis.id = analysis.analysis_id = 'analysis_presentation_' + key
    analysis.presentation_case = key
    for encounter in output.encounters:
        encounter.analysis_id = analysis.analysis_id
    if not any(source.url == expected_url for source in analysis.sources):
        analysis.sources.append(SourceReference(provider='NOAA MarineCadastre',
            dataset='Original daily AIS archive, 3 October 2023', url=expected_url,
            retrieved_at=datetime.fromtimestamp(broadcast.stat().st_mtime, timezone.utc)))
    sources_file = cache_dir / 'storms' / 'sources.json'
    urls = json.loads(sources_file.read_text(encoding='utf-8')) if sources_file.exists() else {}
    for basin in ('atlantic', 'pacific'):
        path = cache_dir / 'storms' / f'hurdat2-{basin}.txt'
        if path.exists():
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            analysis.sources.append(SourceReference(provider='NOAA National Hurricane Center',
                dataset=f'HURDAT2 {basin} best-track input',
                url=urls.get(basin, 'https://www.nhc.noaa.gov/data/#hurdat'), sha256=digest,
                retrieved_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)))
    analysis.sources.append(SourceReference(provider='MCI presentation preparation', dataset=VERSION,
        retrieved_at=datetime.now(timezone.utc)))
    return analysis, output.encounters


def ensure_cases(repository, cache_dir, *, force=False):
    from app.fictional_yachts import build_case as build_fictional_case
    for key in FICTIONAL_CASES:
        analysis, encounters = build_fictional_case(key)
        for encounter in encounters:
            repository.save_encounter(encounter)
        repository.save_analysis(analysis)
    errors = {}
    for key in CASES:
        existing = repository.get_analysis('mci', 'analysis_presentation_' + key)
        if not force and is_recorded_case(existing):
            continue
        try:
            analysis, encounters = build_case(key, repository, cache_dir)
        except ValueError as exc:
            errors[key] = str(exc)
            continue
        for encounter in encounters:
            repository.save_encounter(encounter)
        repository.save_analysis(analysis)
    return errors


def case_roster(key):
    """Fixed sample crew, never a claim about the real yacht's people or documents."""
    if key in FICTIONAL_CASES:
        from app.fictional_yachts import case_roster as fictional_roster
        return fictional_roster(key)
    if key not in CASES:
        raise ValueError('Unknown NOAA presentation case')
    snapshot = generate_roster(random.Random(17), scenario='clear')
    today = datetime.now(timezone.utc).date()
    people = {}
    for index, assignment in enumerate(snapshot['assignments']):
        person = snapshot['people'][assignment['person_id']]
        person_id = f'fictional-{key}-{index}'
        person.update(id=person_id, summary='Fictional crew overlay for a recorded NOAA assessment.',
            cv_updated_on=(today - timedelta(days=14)).isoformat() if key == 'shelter' else None)
        if key == 'approach':
            person.update(experience=[], summary='No current CV supplied in this fictional crew overlay.')
            for cert in person['certificates']:
                if cert['type'] == 'MEDICAL_FITNESS_CERTIFICATE_ENG1' or cert is person['certificates'][-1]:
                    cert['expiry'] = (today - timedelta(days=30)).isoformat()
        assignment['person_id'] = person_id
        person['retrieved_at'] = today.isoformat() + 'T00:00:00+00:00'
        assignment['reviewed_at'] = person['retrieved_at']
        for cert_index, certificate in enumerate(person['certificates']):
            certificate.update(id=f'{person_id}-cert-{cert_index}',
                               reference=f'FICTIONAL-{key}-{index}-{cert_index}')
        people[person_id] = person
    snapshot['people'] = people
    return snapshot

