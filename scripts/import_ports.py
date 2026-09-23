"""Refresh the local principal-port lookup from the public BTS/USACE layer."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlopen


SOURCE = (
    "https://services7.arcgis.com/n1YM8pTrFmm7L4hs/arcgis/rest/services/"
    "Principal_Ports/FeatureServer/0/query?where=1%3D1&outFields=OBJECTID%2CPORTNAME"
    "&returnGeometry=true&outSR=4326&f=geojson"
)
TARGET = Path(__file__).resolve().parents[1] / "data" / "lookups" / "us_principal_ports.json"


def rings(geometry):
    if geometry["type"] == "Polygon":
        return geometry["coordinates"][:1]
    if geometry["type"] == "MultiPolygon":
        return [polygon[0] for polygon in geometry["coordinates"]]
    return []


def centroid(geometry):
    # Area-weighted centre of the outer rings; the fallback handles tiny polygons.
    areas = []
    for ring in rings(geometry):
        twice_area = sum(
            left[0] * right[1] - right[0] * left[1]
            for left, right in zip(ring, ring[1:])
        )
        if abs(twice_area) < 1e-12:
            continue
        longitude = sum(
            (left[0] + right[0]) * (left[0] * right[1] - right[0] * left[1])
            for left, right in zip(ring, ring[1:])
        ) / (3 * twice_area)
        latitude = sum(
            (left[1] + right[1]) * (left[0] * right[1] - right[0] * left[1])
            for left, right in zip(ring, ring[1:])
        ) / (3 * twice_area)
        areas.append((abs(twice_area), longitude, latitude))
    if not areas:
        raise ValueError("Port polygon has no usable outer ring")
    total = sum(area for area, _, _ in areas)
    return [
        round(sum(area * lon for area, lon, _ in areas) / total, 6),
        round(sum(area * lat for area, _, lat in areas) / total, 6),
    ]


def main():
    with urlopen(SOURCE, timeout=90) as response:
        payload = json.load(response)
    if len(payload.get("features", [])) < 100:
        raise ValueError("The principal-port source returned too few features")
    ports = sorted(
        (
            {
                "id": str(feature["properties"]["OBJECTID"]),
                "name": feature["properties"]["PORTNAME"].strip(),
                "coordinates": centroid(feature["geometry"]),
            }
            for feature in payload["features"]
            if feature.get("geometry") and feature["properties"].get("PORTNAME")
        ),
        key=lambda port: (port["name"].casefold(), port["id"]),
    )
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        json.dumps({"source": SOURCE, "distanceBasis": "polygon centroid", "ports": ports}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Imported {len(ports)} official port locations to {TARGET}")


if __name__ == "__main__":
    main()
