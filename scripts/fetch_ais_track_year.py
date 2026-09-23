"""Download and verify one official NOAA MarineCadastre AIS track year.

The archive is kept only until its GeoPackage is extracted and validated.
Interrupted downloads retain a .download file and resume with HTTP Range.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from pathlib import Path
from urllib.request import Request, urlopen

import zipfile64.zipfile as zipfile


SOURCE_BASE = "https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais/aistrack"
CACHE_DIR = Path(r"C:\MCI-AIS-Cache\tracks")
CHUNK_BYTES = 8 * 1024 * 1024
GIB = 1024 ** 3


def _validate_gpkg(path: Path) -> None:
    if path.stat().st_size < GIB:
        raise ValueError(f"GeoPackage is unexpectedly small: {path}")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=60)
    try:
        result = connection.execute("PRAGMA quick_check").fetchone()
        if not result or result[0] != "ok":
            raise ValueError(f"GeoPackage integrity check failed: {result}")
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM gpkg_contents WHERE data_type = 'features'"
            )
        ]
        if not tables:
            raise ValueError("GeoPackage contains no feature tables")
        quoted = tables[0].replace('"', '""')
        columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{quoted}")')}
        required = {"MMSI", "Shape", "TrackStartTime", "TrackEndTime", "VesselGroup"}
        if not required <= columns:
            raise ValueError(f"Track table lacks required columns: {required - columns}")
        print(f"Verified {path.name}: {path.stat().st_size / GIB:.2f} GiB, {len(tables)} feature tables", flush=True)
    finally:
        connection.close()


def _ensure_mmsi_index(path: Path) -> None:
    if shutil.disk_usage(CACHE_DIR).free < 8 * GIB:
        raise OSError("At least 8 GiB free space is required to index AIS tracks")
    connection = sqlite3.connect(str(path), timeout=120)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM gpkg_contents WHERE data_type = 'features'"
            )
        ]
        for table in tables:
            index_name = f"mci_{table}_mmsi_idx".replace('"', '""')
            quoted_table = table.replace('"', '""')
            existing = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?",
                (f"mci_{table}_mmsi_idx",),
            ).fetchone()
            if existing:
                continue
            print(f"Indexing MMSI lookups in {path.name}...", flush=True)
            connection.execute(
                f'CREATE INDEX "{index_name}" ON "{quoted_table}" (MMSI)'
            )
            connection.commit()
    finally:
        connection.close()


def _download(url: str, archive: Path) -> None:
    partial = archive.with_name(archive.name + ".download")
    headers = {"User-Agent": "MCI-Marine-Risk-POC/0.1 (official NOAA AIS cache)"}
    with urlopen(Request(url, headers=headers, method="HEAD"), timeout=60) as response:
        expected = int(response.headers["Content-Length"])
    existing = partial.stat().st_size if partial.exists() else 0
    if existing > expected:
        raise ValueError(f"Partial download exceeds source size: {partial}")
    if shutil.disk_usage(CACHE_DIR).free < expected - existing + 20 * GIB:
        raise OSError("Insufficient free disk space for download and extraction")

    request_headers = dict(headers)
    if existing:
        request_headers["Range"] = f"bytes={existing}-"
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=120) as response:
        if existing and response.status != 206:
            raise OSError("Server did not honour the resume range")
        mode = "ab" if existing else "wb"
        with partial.open(mode) as output:
            downloaded = existing
            last_report = existing
            while chunk := response.read(CHUNK_BYTES):
                output.write(chunk)
                downloaded += len(chunk)
                if downloaded - last_report >= 256 * 1024 * 1024:
                    print(f"{archive.name}: {downloaded / GIB:.2f}/{expected / GIB:.2f} GiB", flush=True)
                    last_report = downloaded
    if partial.stat().st_size != expected:
        raise OSError(f"Incomplete download: {partial.stat().st_size} of {expected} bytes")
    partial.replace(archive)
    print(f"Downloaded {archive.name}: {expected / GIB:.2f} GiB", flush=True)


def fetch(year: int, *, index_only: bool = False) -> None:
    if year not in range(2021, 2026):
        raise ValueError("This importer supports the five complete years 2021-2025")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"AISVesselTracks{year}"
    target = CACHE_DIR / f"{stem}.gpkg"
    if index_only:
        if not target.exists():
            raise FileNotFoundError(f"Extract and validate {year} before indexing")
        _ensure_mmsi_index(target)
        print(f"MMSI index ready: {target}", flush=True)
        return
    if target.exists():
        _validate_gpkg(target)
        _ensure_mmsi_index(target)
        print(f"Already available: {target}", flush=True)
        return

    archive = CACHE_DIR / f"{stem}.zip"
    if not archive.exists():
        _download(f"{SOURCE_BASE}/{archive.name}", archive)

    with zipfile.ZipFile(archive) as package:
        candidates = [
            item for item in package.infolist()
            if not item.is_dir() and item.filename.lower().endswith(".gpkg")
        ]
        if len(candidates) != 1:
            raise ValueError(f"Expected one GeoPackage in {archive.name}, found {len(candidates)}")
        member = candidates[0]
        if shutil.disk_usage(CACHE_DIR).free < member.file_size + 2 * GIB:
            raise OSError("Insufficient free disk space to extract GeoPackage")
        partial_target = target.with_name(target.name + ".extracting")
        print(f"Extracting {member.filename}: {member.file_size / GIB:.2f} GiB", flush=True)
        with package.open(member) as source, partial_target.open("wb") as output:
            shutil.copyfileobj(source, output, CHUNK_BYTES)
        if partial_target.stat().st_size != member.file_size:
            raise ValueError("Extracted GeoPackage size does not match archive metadata")

    _validate_gpkg(partial_target)
    partial_target.replace(target)
    archive.unlink()
    _ensure_mmsi_index(target)
    print(f"Ready: {target}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("year", type=int, choices=range(2021, 2026))
    parser.add_argument("--index-only", action="store_true", help="Index an existing validated GeoPackage without downloading")
    arguments = parser.parse_args()
    fetch(arguments.year, index_only=arguments.index_only)
