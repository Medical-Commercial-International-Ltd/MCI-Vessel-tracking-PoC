"""On-demand imagery provider. NOAA AIS and exposure services do not depend on this module."""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from threading import Lock, Semaphore
import time
from typing import Protocol
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from app.encounter_map import build_map_data


class ImageryUnavailable(Exception):
    pass


class ImageryProvider(Protocol):
    name: str
    def resolve(self, timestamp: datetime, bounds: list[float]) -> dict: ...
    def render(self, scan: dict, bounds: list[float], output: Path) -> dict: ...


def utc(timestamp):
    if timestamp.tzinfo is None:
        raise ImageryUnavailable("Satellite request times must include a UTC offset")
    return timestamp.astimezone(timezone.utc)


def scan_time(value):
    return datetime.strptime(value[:13], "%Y%j%H%M%S").replace(tzinfo=timezone.utc)


class GoesArchiveProvider:
    name = "NOAA GOES archive"

    def __init__(self, python: Path):
        self.python = python.resolve()
        self._catalogues = OrderedDict()
        self._lock = Lock()

    def _catalogue(self, satellite, hour):
        prefix = f"ABI-L2-CMIPF/{hour.year}/{hour.strftime('%j')}/{hour:%H}/"
        key = (satellite, prefix)
        with self._lock:
            cached = self._catalogues.get(key)
        if cached and time.monotonic() - cached[0] < 3600:
            return cached[1]
        url = f"https://noaa-goes{satellite}.s3.amazonaws.com/?" + urlencode({"list-type": "2", "prefix": prefix, "max-keys": 1000})
        with urlopen(Request(url, headers={"User-Agent": "MCI-Vessel-Tracking-PoC/0.1"}), timeout=30) as response:
            root = ET.fromstring(response.read(2_000_000))
        scans = []
        ns = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
        for item in root.findall("s:Contents", ns):
            filename = item.findtext("s:Key", namespaces=ns) or ""
            match = re.search(r"-M\dC13_G\d+_s(\d+)_e(\d+)_c\d+\.nc$", filename)
            if filename.startswith(prefix) and match:
                scans.append({"key": filename, "start": scan_time(match[1]), "end": scan_time(match[2]), "satellite": satellite})
        with self._lock:
            self._catalogues[key] = (time.monotonic(), scans)
            while len(self._catalogues) > 128:
                self._catalogues.popitem(last=False)
        return scans

    def resolve(self, timestamp, bounds):
        timestamp = utc(timestamp)
        longitude = (bounds[0] + bounds[2]) / 2
        satellite = (19 if timestamp.date() >= datetime(2025, 4, 7).date() else 16) if longitude >= -105 else (
            18 if timestamp.date() >= datetime(2023, 1, 10).date() else 17)
        if timestamp.year < 2018 or timestamp > datetime.now(timezone.utc):
            raise ImageryUnavailable("Historical GOES imagery is unavailable for this date")
        hour = timestamp.replace(minute=0, second=0, microsecond=0)
        candidates = self._catalogue(satellite, hour)
        if timestamp.minute < 10:
            candidates = [*candidates, *self._catalogue(satellite, hour - timedelta(hours=1))]
        if timestamp.minute >= 50:
            candidates = [*candidates, *self._catalogue(satellite, hour + timedelta(hours=1))]
        if not candidates:
            raise ImageryUnavailable("No archived GOES scans are available for this time")
        scan = min(candidates, key=lambda item: abs((item["start"] - timestamp).total_seconds()))
        if abs((scan["start"] - timestamp).total_seconds()) > 600:
            raise ImageryUnavailable("No GOES scan lies within ten minutes of the requested time")
        return scan

    def render(self, scan, bounds, output):
        if not self.python.is_file():
            raise ImageryUnavailable("Satellite processing environment is not installed; run scripts/setup_satellite.ps1")
        url = f"https://noaa-goes{scan['satellite']}.s3.amazonaws.com/" + quote(scan["key"], safe="/")
        raw = output.with_suffix(".nc.download")
        temporary = output.with_suffix(".rendering.png")
        try:
            with urlopen(Request(url, headers={"User-Agent": "MCI-Vessel-Tracking-PoC/0.1"}), timeout=60) as response, raw.open("wb") as target:
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 100 * 1024 * 1024:
                        raise ImageryUnavailable("Satellite source file exceeded the download limit")
                    target.write(chunk)
            worker = Path(__file__).resolve().parent.parent / "scripts" / "render_satellite.py"
            result = subprocess.run([str(self.python), str(worker)], input=json.dumps({"input": str(raw), "output": str(temporary),
                "bounds": bounds, "width": 640, "height": 512}), text=True, capture_output=True, timeout=90, check=True)
            metadata = json.loads(result.stdout)
            if not temporary.is_file() or temporary.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
                raise ImageryUnavailable("Satellite renderer did not produce a valid image")
            temporary.replace(output)
            metadata.update(provider=self.name, satellite=f"GOES-{scan['satellite']}", sourceUrl=url)
            return metadata
        finally:
            raw.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)


class SatelliteService:
    def __init__(self, cache_dir: Path, limit_mb: int, provider: ImageryProvider):
        self.cache_dir = cache_dir.resolve()
        self.limit_bytes = limit_mb * 1024 * 1024
        self.provider = provider
        self._workers = Semaphore(2)
        self._locks = [Lock() for _ in range(32)]
        self._manifest_lock = Lock()
        self._cache_lock = Lock()
        self._active = set()
        self._manifests = OrderedDict()

    def manifest(self, analysis, encounter, ais_cache_dir):
        key = (analysis.analysis_id, encounter.id)
        with self._manifest_lock:
            cached = self._manifests.get(key)
        if cached:
            return cached
        if analysis.is_synthetic:
            raise ImageryUnavailable("Historical satellite imagery is available for real assessments only")
        event = build_map_data(analysis, [encounter], ais_cache_dir)[0]
        if not event["frames"]:
            raise ImageryUnavailable("No real storm times are available for satellite imagery")
        points = [frame["storm"] for frame in event["frames"]]
        points.extend(frame["vessel"] for frame in event["frames"] if frame["vessel"])
        longitudes, latitudes = [point[0] for point in points], [point[1] for point in points]
        if max(longitudes) - min(longitudes) > 180:
            raise ImageryUnavailable("Satellite image windows crossing the date line are not supported yet")
        bounds = [max(-179.9, min(longitudes)-4), max(-80, min(latitudes)-4),
                  min(179.9, max(longitudes)+4), min(80, max(latitudes)+4)]
        start, end = utc(datetime.fromisoformat(event["frames"][0]["timestamp"])), utc(datetime.fromisoformat(event["frames"][-1]["timestamp"]))
        cursor = start.replace(minute=start.minute // 10 * 10, second=0, microsecond=0)
        frames = []
        while cursor <= end + timedelta(minutes=10):
            stamp = cursor.isoformat()
            url = f"/api/satellite/{analysis.analysis_id}/{encounter.id}/image?" + urlencode({"time": stamp})
            frames.append({"requestedAt": stamp, "url": url})
            cursor += timedelta(minutes=10)
        manifest = {"provider": self.provider.name, "bounds": bounds, "stepMinutes": 10,
                    "start": start.isoformat(), "end": end.isoformat(), "frames": frames,
                    "description": "C13 infrared, approximately 2 km; cold cloud tops are brighter. Each frame is fetched on demand."}
        with self._manifest_lock:
            self._manifests[key] = manifest
            while len(self._manifests) > 128:
                self._manifests.popitem(last=False)
        return manifest

    def image(self, manifest, timestamp):
        timestamp = utc(timestamp)
        if timestamp < datetime.fromisoformat(manifest["start"]) - timedelta(minutes=10) or timestamp > datetime.fromisoformat(manifest["end"]) + timedelta(minutes=10):
            raise ImageryUnavailable("Requested satellite time is outside this encounter's playback window")
        if timestamp.minute % 10 or timestamp.second or timestamp.microsecond:
            raise ImageryUnavailable("Satellite requests must use the manifest's ten-minute steps")
        request_key = hashlib.sha256(json.dumps([self.provider.name, timestamp.isoformat(), manifest["bounds"]]).encode()).hexdigest()
        output, metadata_file = self.cache_dir / f"{request_key}.png", self.cache_dir / f"{request_key}.json"
        with self._workers, self._locks[int(request_key[:8], 16) % len(self._locks)]:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with self._cache_lock:
                self._active.add(output)
            try:
                with self._cache_lock:
                    if output.is_file() and metadata_file.is_file():
                        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
                        output.touch()
                        return output.read_bytes(), metadata, True
                scan = self.provider.resolve(timestamp, manifest["bounds"])
                metadata = self.provider.render(scan, manifest["bounds"], output)
                metadata["requestedAt"] = timestamp.isoformat()
                with self._cache_lock:
                    temporary = metadata_file.with_suffix(".tmp")
                    temporary.write_text(json.dumps(metadata), encoding="utf-8")
                    temporary.replace(metadata_file)
                    # Bounded crop cache; active requests cannot be evicted.
                    files = sorted(self.cache_dir.glob("*.png"), key=lambda file: file.stat().st_mtime)
                    total = sum(file.stat().st_size for file in files)
                    for file in files:
                        if total <= self.limit_bytes:
                            break
                        if file in self._active:
                            continue
                        total -= file.stat().st_size
                        file.unlink(missing_ok=True)
                        file.with_suffix(".json").unlink(missing_ok=True)
                    return output.read_bytes(), metadata, False
            finally:
                with self._cache_lock:
                    self._active.discard(output)
