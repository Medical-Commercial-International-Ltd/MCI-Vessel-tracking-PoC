import json
from pathlib import Path


def demo_yachts():
    """Explicit user-supplied identities; NOAA tracks remain the movement source."""
    path = Path(__file__).parent / "data" / "demo-yachts.json"
    return json.loads(path.read_text(encoding="utf-8"))["vessels"]
