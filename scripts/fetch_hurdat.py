"""Download the current official NHC Atlantic and Pacific HURDAT2 archives."""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from app.config import get_settings
from app.hurdat import load_hurdat_storms


def main() -> None:
    source = "https://www.nhc.noaa.gov/data/"
    headers = {"User-Agent": "MCI-Marine-Risk-POC/0.1"}
    with urlopen(Request(source, headers=headers), timeout=90) as response:
        page = response.read().decode("utf-8")
    links = re.findall(r'href=["\']([^"\']+)["\']', page, re.I)
    directory = get_settings().ais_cache_dir / "storms"
    directory.mkdir(parents=True, exist_ok=True)
    sources = {}
    for basin, pattern in (
        ("atlantic", r"hurdat2-1851-\d{4}-\d+\.txt$"),
        ("pacific", r"hurdat2-nepac-1949-\d{4}-\d+\.txt$"),
    ):
        matches = [link for link in links if re.search(pattern, link, re.I)]
        if len(set(matches)) != 1:
            raise ValueError(f"Cannot uniquely identify the official {basin} archive")
        url = urljoin(source, matches[0])
        if not url.startswith("https://www.nhc.noaa.gov/"):
            raise ValueError("Unexpected archive source")
        temporary = directory / f"hurdat2-{basin}.download"
        with urlopen(Request(url, headers=headers), timeout=90) as response:
            temporary.write_bytes(response.read())
        storms = load_hurdat_storms([temporary], 2021, 2025)
        if not storms:
            raise ValueError(f"No 2021-2025 storms in {basin} download")
        temporary.replace(directory / f"hurdat2-{basin}.txt")
        sources[basin] = url
        print(f"Downloaded {basin}: {len(storms)} storms in 2021-2025", flush=True)
    (directory / "sources.json").write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
