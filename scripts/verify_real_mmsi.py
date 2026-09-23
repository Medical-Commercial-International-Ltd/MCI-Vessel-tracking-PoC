from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path


CACHE_DIR = Path(r"C:\MCI-AIS-Cache")
REGISTRY_PATH = CACHE_DIR / "vessels" / "registry.json"
TRACK_DIR = CACHE_DIR / "tracks"


def main() -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["vessels"]
    identifiers = [int(vessel["mmsi"]) for vessel in registry]
    counts: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    first_seen: dict[int, str] = {}
    last_seen: dict[int, str] = {}
    placeholders = ",".join("?" for _ in identifiers)
    years: list[int] = []

    for path in sorted(TRACK_DIR.glob("AISVesselTracks*.gpkg")):
        match = re.search(r"(20\d{2})", path.stem)
        if not match:
            continue
        year = int(match.group(1))
        years.append(year)
        print(f"Scanning {year} vessel tracks...", flush=True)
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=60)
        try:
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT table_name FROM gpkg_contents WHERE data_type = 'features'"
                )
            ]
            for table_name in tables:
                quoted = table_name.replace('"', '""')
                query = (
                    f'SELECT MMSI, COUNT(*), MIN(TrackStartTime), MAX(TrackEndTime) '
                    f'FROM "{quoted}" WHERE MMSI IN ({placeholders}) GROUP BY MMSI'
                )
                for mmsi, count, start, end in connection.execute(query, identifiers):
                    key = int(mmsi)
                    counts[key][year] += int(count)
                    if start and (key not in first_seen or start < first_seen[key]):
                        first_seen[key] = start
                    if end and (key not in last_seen or end > last_seen[key]):
                        last_seen[key] = end
        finally:
            connection.close()

    print("\t".join(["MMSI", "Vessel", *(f"{year} segments" for year in years), "First track", "Last track"]))
    for vessel in registry:
        mmsi = int(vessel["mmsi"])
        print("\t".join([
            str(mmsi),
            vessel["name"],
            *(str(counts[mmsi][year]) for year in years),
            first_seen.get(mmsi, "NONE"),
            last_seen.get(mmsi, "NONE"),
        ]))


if __name__ == "__main__":
    main()
