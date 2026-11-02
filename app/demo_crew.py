"""Isolated fictional rosters for demonstrations; never writes real assignments."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import random
import re
from threading import RLock
from uuid import uuid4

from app.crew_risk import SAFETY
from app.repositories import _atomic_json_write


NAMES = (
    ('Avery', 'Stone'), ('Rowan', 'Fletcher'), ('Harper', 'Lane'), ('Emery', 'Cole'),
    ('Reese', 'Bennett'), ('Cameron', 'Vale'), ('Skyler', 'Hayes'), ('Parker', 'Miles'),
    ('Finley', 'Shaw'), ('Sage', 'Turner'), ('Logan', 'Pierce'), ('Arden', 'Scott'),
    ('Dakota', 'Wells'), ('Elliot', 'Hart'), ('Morgan', 'Reed'), ('Jamie', 'Brooks'),
)
ROLES = (('Captain', 'MASTER_UNLIMITED'),
         ('Chief officer', 'OFFICER_OF_THE_WATCH_OOW_UNLIMITED'),
         ('Engineer', 'CHIEF_ENGINEER_UNLIMITED'))


def generate_roster(rng=None, *, scenario=None):
    rng = rng or random.SystemRandom()
    now = datetime.now(timezone.utc)
    today = now.date()
    scenarios = ('clear', 'pending', 'expiring', 'missing', 'expired')
    scenario = rng.choice(scenarios) if scenario is None else scenario
    if scenario not in scenarios:
        raise ValueError('Unknown fictional crew scenario')
    affected = rng.randrange(len(ROLES))
    people, assignments = {}, []
    for index, ((role, competency), (first, last)) in enumerate(zip(ROLES, rng.sample(NAMES, len(ROLES)))):
        person_id = 'fictional-' + uuid4().hex
        certificates = []
        for label, certificate_type in [(label, sorted(types)[0]) for label, types, _ in SAFETY] + [('Role competency', competency)]:
            certificates.append(dict(id=uuid4().hex, name=label + ' — fictional example',
                type=certificate_type, reference='FICTIONAL-' + uuid4().hex[:8],
                issue=(today - timedelta(days=365)).isoformat(),
                expiry=(today + timedelta(days=730)).isoformat(), completed=True,
                statuses=['VERIFIED_MANUAL'], verification='VERIFIED_MANUAL',
                limits='Fictional document; role limits and flag recognition are not established.'))
        if index == affected:
            if scenario == 'pending':
                for cert in certificates:
                    cert.update(statuses=['PENDING_MANUAL'], verification='PENDING_MANUAL')
            elif scenario == 'expiring':
                certificates[-1]['expiry'] = (today + timedelta(days=45)).isoformat()
            elif scenario == 'missing':
                certificates = [c for c in certificates if c['type'] != 'MEDICAL_FITNESS_CERTIFICATE_ENG1']
            elif scenario == 'expired':
                certificates[-1]['expiry'] = (today - timedelta(days=30)).isoformat()
        person = dict(id=person_id, first_name=first, last_name=last,
            email=f'{first}.{last}@example.test'.lower(), is_demo=True,
            summary='Fictional yacht crew profile generated for this demonstration.',
            experience=[f'Fictional example: {rng.randint(3, 15)} years in yacht operations as {role.lower()}.'],
            certificates=certificates, retrieved_at=now.isoformat(), stale=False)
        people[person_id] = person
        assignments.append(dict(person_id=person_id, name=f'{first} {last}', role=role,
            start_date=today.isoformat(), end_date=(today + timedelta(days=30)).isoformat(),
            is_demo=1, reviewer='Automatic fictional demonstration', reviewed_at=now.isoformat()))
    return dict(version='RANDOM-CREW-DEMO-v1', generated_on=today.isoformat(),
                scenario=scenario, people=people, assignments=assignments)


class RosterProvider:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def get(self, person_id):
        return deepcopy(self.snapshot['people'].get(person_id))


class DemoCrewScenarios:
    def __init__(self, root):
        self.root = root
        self.lock = RLock()

    def _path(self, key):
        if not re.fullmatch(r'(analysis_|crew_demo_|portfolio_)[A-Za-z0-9_-]+', key):
            raise ValueError('Invalid fictional roster reference')
        return self.root / (key + '.json')

    def read(self, key):
        try:
            snapshot = json.loads(self._path(key).read_text(encoding='utf-8'))
            # Renew daily so demonstration assignments and dates remain useful.
            if snapshot.get('generated_on') == datetime.now(timezone.utc).date().isoformat():
                return snapshot
        except (OSError, ValueError, TypeError):
            pass
        return None

    def get(self, key):
        with self.lock:
            snapshot = self.read(key)
            if snapshot is None:
                snapshot = generate_roster()
                _atomic_json_write(self._path(key), snapshot)
            return snapshot

    def preview(self, mmsi):
        key = 'crew_demo_' + uuid4().hex
        snapshot = generate_roster()
        snapshot['mmsi'] = mmsi
        _atomic_json_write(self._path(key), snapshot)
        return dict(reference=key, assignments=snapshot['assignments'])

    def adopt(self, analysis, reference):
        """Carry search-result crew into the resulting assessment when applicable."""
        if not reference.startswith('crew_demo_'):
            return
        with self.lock:
            snapshot = self.read(reference)
            if snapshot and snapshot.get('mmsi') in analysis.vessel.mmsi:
                _atomic_json_write(self._path(analysis.analysis_id), snapshot)
