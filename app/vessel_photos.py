from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from threading import Lock
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from app.models import VesselIdentity


COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "MCI-Marine-Risk-POC/0.1 (local vessel photo lookup)"
MAX_IMAGE_BYTES = 5_000_000
ALLOWED_LICENSES = {"CC0", "CC0 1.0"} | {
    f"CC {variant} {version}"
    for variant in ("BY", "BY-SA")
    for version in ("2.0", "2.5", "3.0", "4.0")
}

CURATED_PHOTOS = {
    "245261000": {
        "src": "/static/vessels/245261000.jpg",
        "credit": "Niels Johannes · CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:Spuigracht_(IMO_9202534).jpg",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
    },
    "354215000": {
        "src": "/static/vessels/354215000.jpg",
        "credit": "Balou46 · CC BY-SA 4.0",
        "source": "https://commons.wikimedia.org/wiki/File:US-port-canav-carnival-pride_(recropped).jpg",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
    },
}


def vessel_image(vessel: VesselIdentity) -> dict[str, str]:
    """Return a reviewed local photo, or an explicitly labelled illustration."""
    mmsi = next(iter(vessel.mmsi), "")
    photo = CURATED_PHOTOS.get(mmsi)
    if photo:
        return {**photo, "alt": f"{vessel.name} vessel"}
    return {
        "src": "/static/vessels/vessel-placeholder.svg",
        "credit": "Vessel illustration — verified photograph not yet available",
        "source": "",
        "license_url": "",
        "alt": f"Vessel illustration for {vessel.name}",
    }


class _PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(markup: str) -> str:
    parser = _PlainText()
    parser.feed(markup)
    return " ".join(" ".join(parser.parts).split())


class VesselPhotoCatalog:
    """Find exact-identifier Commons images and cache accepted photos locally."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def image_for(self, vessel: VesselIdentity) -> dict[str, str]:
        fallback = vessel_image(vessel)
        if fallback["source"]:
            return fallback

        mmsi = next(iter(vessel.mmsi), "")
        if not re.fullmatch(r"\d{9}", mmsi):
            return fallback
        imo = (vessel.imo or "").upper().removeprefix("IMO")
        if not re.fullmatch(r"\d{7}", imo):
            imo = ""

        with self._lock:
            cached = self._read_metadata(mmsi)
            if cached and cached.get("status") == "found":
                filename = cached.get("filename", "")
                if re.fullmatch(rf"{mmsi}\.(?:jpg|png|webp)", filename) and (
                    self.cache_dir / filename
                ).is_file():
                    return self._image_metadata(vessel, cached)
            if cached and cached.get("status") in {"missing", "unavailable"}:
                try:
                    checked_at = datetime.fromisoformat(cached["checked_at"])
                    ttl = timedelta(days=7 if cached["status"] == "missing" else 1 / 24)
                    if datetime.now(timezone.utc) - checked_at < ttl:
                        return fallback
                except (KeyError, ValueError, TypeError):
                    pass

            try:
                found = self._find_and_cache(mmsi, imo)
            except (OSError, ValueError, KeyError, TypeError):
                self._write_metadata(mmsi, {"status": "unavailable"})
                return fallback
            if found:
                return self._image_metadata(vessel, found)
            self._write_metadata(mmsi, {"status": "missing"})
            return fallback

    def _find_and_cache(self, mmsi: str, imo: str) -> dict | None:
        titles = self._candidate_titles(mmsi, imo)
        if not titles:
            return None
        pages = self._api_json(
            {
                "action": "query",
                "prop": "imageinfo",
                "iiprop": "url|extmetadata|mime",
                "iiurlwidth": "960",
                "titles": "|".join(titles[:10]),
            }
        ).get("query", {}).get("pages", {})
        by_title = {page.get("title"): page for page in pages.values()}
        for title in titles[:10]:
            page = by_title.get(title, {})
            info = next(iter(page.get("imageinfo", [])), {})
            ext = info.get("extmetadata", {})
            license_name = ext.get("LicenseShortName", {}).get("value", "")
            if license_name not in ALLOWED_LICENSES:
                continue
            mime = info.get("mime", "")
            extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(mime)
            if not extension:
                continue
            source = info.get("descriptionurl", "")
            license_url = ext.get("LicenseUrl", {}).get("value", "")
            photo_url = info.get("thumburl", "")
            if not (
                _allowed_url(source, {"commons.wikimedia.org"})
                and _allowed_url(license_url, {"creativecommons.org"})
                and _allowed_url(photo_url, {"thumb.wikimedia.org", "upload.wikimedia.org"})
            ):
                continue
            author = _plain_text(ext.get("Artist", {}).get("value", ""))
            if not author:
                continue
            data = self._image_bytes(photo_url)
            if not _is_image(data, extension):
                continue
            filename = f"{mmsi}.{extension}"
            target = self.cache_dir / filename
            temp = self.cache_dir / f"{filename}.tmp"
            temp.write_bytes(data)
            temp.replace(target)
            metadata = {
                "status": "found",
                "filename": filename,
                "credit": f"{author} · {license_name}",
                "source": source,
                "license_url": license_url,
            }
            self._write_metadata(mmsi, metadata)
            return metadata
        return None

    def _candidate_titles(self, mmsi: str, imo: str) -> list[str]:
        identifier = imo or mmsi
        label = "IMO" if imo else "MMSI"
        results = self._api_json(
            {
                "action": "query",
                "list": "search",
                "srsearch": f'"{label} {identifier}"',
                "srnamespace": "6",
                "srlimit": "10",
            }
        ).get("query", {}).get("search", [])
        exact = re.compile(rf"\b{label}[\s_-]*{identifier}(?!\d)", re.IGNORECASE)
        titles = [
            item["title"]
            for item in results
            if item.get("ns") == 6 and exact.search(item.get("title", ""))
        ]
        if imo and len(titles) < 5:
            members = self._category_members(f"Category:IMO {imo}")
            for item in members:
                if item.get("ns") == 6:
                    titles.append(item["title"])
            for item in members:
                if item.get("ns") == 14 and len(titles) < 10:
                    titles.extend(
                        member["title"]
                        for member in self._category_members(item["title"])
                        if member.get("ns") == 6
                    )
        return list(dict.fromkeys(titles))[:10]

    def _category_members(self, title: str) -> list[dict]:
        return self._api_json(
            {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": title,
                "cmtype": "file|subcat",
                "cmlimit": "20",
            }
        ).get("query", {}).get("categorymembers", [])

    def _api_json(self, params: dict[str, str]) -> dict:
        url = COMMONS_API + "?" + urlencode({"format": "json", **params})
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def _image_bytes(self, url: str) -> bytes:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=8) as response:
            if not _allowed_url(response.url, {"thumb.wikimedia.org", "upload.wikimedia.org"}):
                raise ValueError("Unexpected image host")
            data = response.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("Image exceeds size limit")
        return data

    def _read_metadata(self, mmsi: str) -> dict | None:
        path = self.cache_dir / f"{mmsi}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write_metadata(self, mmsi: str, metadata: dict) -> None:
        path = self.cache_dir / f"{mmsi}.json"
        temp = self.cache_dir / f"{mmsi}.json.tmp"
        payload = {**metadata, "checked_at": datetime.now(timezone.utc).isoformat()}
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    @staticmethod
    def _image_metadata(vessel: VesselIdentity, metadata: dict) -> dict[str, str]:
        return {
            "src": f"/vessel-photos/{metadata['filename']}",
            "credit": metadata["credit"],
            "source": metadata["source"],
            "license_url": metadata["license_url"],
            "alt": f"{vessel.name} vessel",
        }


def _allowed_url(url: str, hosts: set[str]) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in hosts


def _is_image(data: bytes, extension: str) -> bool:
    return {
        "jpg": data.startswith(b"\xff\xd8\xff"),
        "png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
    }[extension]
