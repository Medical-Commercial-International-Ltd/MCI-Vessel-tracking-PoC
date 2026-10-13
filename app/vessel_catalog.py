"""Read the distinct MMSIs in cached NOAA files without changing source data."""
from functools import lru_cache
from pathlib import Path
import re
import sqlite3


def exposure_rankings(rows, limit=50):
    """Rank assessed MMSIs; break equal scores consistently by name and MMSI."""
    eligible = [row for row in rows if row.get("analysis") is not None]
    highest = sorted(eligible, key=lambda row: (-row["analysis"].risk.score, row["name"].casefold(), row["mmsi"]))[:limit]
    lowest = sorted(eligible, key=lambda row: (row["analysis"].risk.score, row["name"].casefold(), row["mmsi"]))[:limit]
    return highest, lowest


def cached_vessels(cache_dir: Path):
    files = tuple((str(path.resolve()), path.stat().st_mtime_ns, path.stat().st_size)
                  for path in sorted((cache_dir / "tracks").glob("AISVesselTracks*.gpkg")))
    return _read_vessels(files)


@lru_cache(maxsize=2)
def _read_vessels(files):
    vessels = {}
    for filename, _, _ in files:
        match = re.search(r"(20\d{2})", Path(filename).stem)
        if not match:
            continue
        year = int(match.group(1))
        with sqlite3.connect(f"file:{Path(filename).as_posix()}?mode=ro", uri=True) as connection:
            tables = connection.execute("SELECT table_name FROM gpkg_contents WHERE data_type='features'").fetchall()
            for (table,) in tables:
                quoted = table.replace('"', '""')
                for (value,) in connection.execute(f'SELECT DISTINCT MMSI FROM "{quoted}"'):
                    mmsi = str(value)
                    if re.fullmatch(r"\d{9}", mmsi):
                        vessels.setdefault(mmsi, set()).add(year)
    return tuple((mmsi, tuple(sorted(years))) for mmsi, years in sorted(vessels.items()))
