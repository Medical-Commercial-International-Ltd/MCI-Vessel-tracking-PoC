import json
from pathlib import Path


def demo_yachts():
    """Explicit user-supplied identities; NOAA tracks remain the movement source."""
    path = Path(__file__).parent / "data" / "demo-yachts.json"
    return json.loads(path.read_text(encoding="utf-8"))["vessels"]


def storm_demo_vessels():
    path = Path(__file__).parent / 'data' / 'storm-demo-vessels.json'
    return json.loads(path.read_text(encoding='utf-8'))['vessels']


def storm_demo_case(identifier_type, identifier):
    if not identifier:
        return None
    key = 'mmsi' if identifier_type.upper() == 'MMSI' else 'imo'
    return next((v for v in storm_demo_vessels() if v.get(key) == identifier), None)
