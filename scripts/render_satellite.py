"""Render one GOES ABI C13 image as a cropped Web Mercator PNG.

Run in the isolated satellite environment; reads JSON on stdin and prints metadata.
"""
import json
import sys

import h5py
import numpy as np
from PIL import Image
from pyproj import CRS, Transformer


def unpack(dataset, values):
    return values.astype(np.float64) * scalar(dataset.attrs.get("scale_factor", 1)) + scalar(dataset.attrs.get("add_offset", 0))


def scalar(value):
    return float(np.asarray(value).item())


def render(request):
    west, south, east, north = request["bounds"]
    width, height = request.get("width", 640), request.get("height", 512)
    mercator = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    inverse = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    x_min, y_min = mercator.transform(west, south)
    x_max, y_max = mercator.transform(east, north)
    mx, my = np.meshgrid(np.linspace(x_min, x_max, width), np.linspace(y_max, y_min, height))
    longitude, latitude = inverse.transform(mx, my)
    with h5py.File(request["input"], "r") as data:
        projection = data["goes_imager_projection"].attrs
        satellite_height = scalar(projection["perspective_point_height"])
        crs = CRS.from_proj4(f"+proj=geos +h={satellite_height} +lon_0={scalar(projection['longitude_of_projection_origin'])} "
                           f"+a={scalar(projection['semi_major_axis'])} +b={scalar(projection['semi_minor_axis'])} +sweep=x +units=m")
        project = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        px, py = project.transform(longitude, latitude)
        x = unpack(data["x"], data["x"][:]) * satellite_height
        y = unpack(data["y"], data["y"][:]) * satellite_height
        finite = np.isfinite(px) & np.isfinite(py)
        # Native ABI grid is regular; nearest-neighbour sampling preserves measured values.
        column = np.rint(np.where(finite, (px - x[0]) / (x[1] - x[0]), -1)).astype(np.int64)
        row = np.rint(np.where(finite, (py - y[0]) / (y[1] - y[0]), -1)).astype(np.int64)
        valid = finite & (column >= 0) & (column < len(x)) & (row >= 0) & (row < len(y))
        if not np.any(valid):
            raise ValueError("The requested region is outside this satellite's field of view")
        c0, c1 = int(column[valid].min()), int(column[valid].max()) + 1
        r0, r1 = int(row[valid].min()), int(row[valid].max()) + 1
        cmi = data["CMI"]
        crop = cmi[r0:r1, c0:c1]
        local_row, local_column = np.clip(row - r0, 0, r1-r0-1), np.clip(column - c0, 0, c1-c0-1)
        raw = crop[local_row, local_column]
        valid &= raw != cmi.attrs.get("_FillValue", -1)
        if "DQF" in data:
            quality = data["DQF"][r0:r1, c0:c1][local_row, local_column]
            valid &= quality <= 1
        if not np.any(valid):
            raise ValueError("No usable infrared pixels cover this region")
        temperature = unpack(cmi, raw)
        # Fixed 180–330 K grayscale across frames: cold cloud tops white, warm surfaces dark.
        shade = (np.clip((330 - temperature) / 150, 0, 1) * 255).astype(np.uint8)
        rgba = np.stack((shade, shade, shade, np.where(valid, 255, 0).astype(np.uint8)), axis=-1)
        Image.fromarray(rgba).save(request["output"], format="PNG", optimize=True)
        def attribute(name):
            value = np.asarray(data.attrs[name]).item()
            return value.decode() if isinstance(value, bytes) else str(value)
        return {"acquiredAt": attribute("time_coverage_start"), "acquisitionEnd": attribute("time_coverage_end"),
                "band": "ABI C13 clean infrared", "resolutionKm": 2,
                "rendering": "180–330 K grayscale; cold cloud tops are brighter", "bounds": request["bounds"]}


if __name__ == "__main__":
    print(json.dumps(render(json.load(sys.stdin))))
