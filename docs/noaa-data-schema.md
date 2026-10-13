# Local NOAA data schema

Inspected 13 October 2026. This describes the files actually cached for this application, rather than every NOAA dataset. No application or source-data changes were made for this inspection.

## Inventory

| Dataset | Local files | Coverage / storage |
|---|---|---|
| AIS vessel tracks | `C:/MCI-AIS-Cache/tracks/AISVesselTracks2023.gpkg`, `AISVesselTracks2024.gpkg`, `AISVesselTracks2025.gpkg` | 2023-2025; SQLite GeoPackages |
| NHC Atlantic best tracks | `C:/MCI-AIS-Cache/storms/hurdat2-atlantic.txt` | 1851-2025; 1,988 storm headers |
| NHC eastern/central North Pacific best tracks | `C:/MCI-AIS-Cache/storms/hurdat2-pacific.txt` | 1949-2025; 1,262 storm headers |
| GOES ABI C13 imagery | Fetched on demand; rendered crop cache under `data/satellite` | Separate imagery source; not a downloaded global archive |

## AIS vessel-track fields

One row describes one track segment, not one vessel and not one original AIS transmission. One MMSI can have many rows in multiple tables and years. All feature tables in these three files share the following declared schema. `OBJECTID` is the primary key; all other listed columns are nullable.

| Field | Declared type | Meaning / units | Application use or opportunity |
|---|---|---|---|
| OBJECTID | INTEGER | Feature ID, unique within its table | Record identity; not a vessel ID. |
| Shape | MULTILINESTRING | AIS-derived track geometry; longitude/latitude coordinates | Routes, distance, geographic intersections; no original timestamp on each vertex. |
| MMSI | MEDIUMINT | AIS radio/transponder identifier | Vessel lookup and grouping; source contains malformed values as well as valid nine-digit MMSIs. |
| TrackStartTime | DATETIME | UTC timestamp of track start | Timing and period filtering. |
| TrackEndTime | DATETIME | UTC timestamp of track end | Timing and period filtering. |
| VesselType | MEDIUMINT | AIS/NOAA vessel-type code | Classification; historical/nonstandard codes need the relevant NOAA mapping. |
| Length | DOUBLE | Vessel length in metres | Dimensions and length filters. |
| Width | DOUBLE | Vessel width/beam in metres | Dimensions. |
| Draft | DOUBLE | Reported/static draft in metres | Draft; not a reliable measure of cargo or displacement. |
| DurationMinutes | MEDIUMINT | Track duration in whole minutes | Present in source; application currently derives duration from endpoint timestamps. |
| VesselGroup | TEXT(25) | NOAA grouped vessel category | Classification and event lookup filters. |

### Tables and geometry

- 2023: one feature table, `AISVesselTracks2023`.
- 2024: one feature table, `AISVesselTracks2024`.
- 2025: 72 feature tables: `Atlantic`, `GreatLakes`, `Guam`, `GulfAmerica`, `Pacific` and `WestCoast`, each suffixed `_01` through `_12` for the month.
- Source geometry is a binary GeoPackage MULTILINESTRING with no Z/elevation or M/time dimension. It can contain multiple separate lines.
- Inspected CRS metadata: 2023/2024 use EPSG:4269 (NAD83); all 2025 feature tables declare EPSG:4326 (WGS84). Both use geographic degree coordinates. Future precision-sensitive spatial processing should honour these source declarations.
- GeoPackage support tables describe contents, coordinate reference systems, geometry columns and spatial indexes. These are technical metadata, not additional vessel attributes.
- The application reconstructs vertex times by distance between track start/end timestamps. Speed estimates and animation positions are derived estimates; original reported SOG/COG are absent.
- NULL means unavailable. Zero/nonpositive dimension values should not automatically be treated as reliable physical measurements. MMSI is stored numerically, so identifier formatting and validation matter.

### Fields absent from these downloaded tracks

There are no vessel-name, IMO, call-sign, flag, owner, insurer, cargo, destination, ETA, navigation-status, reported SOG/speed, reported COG/course or heading columns. Some of these may exist in other AIS products or identity registries, but those products are not contained in these GeoPackages. Names/IMO shown by the application must come from an additional identity source or saved analysis, not these track columns.

## HURDAT2 storm files

Comma-delimited text with a header followed by its stated number of observations. Headers contain storm ID (e.g. `AL142024`), name (e.g. `MILTON`) and observation count. ID encodes basin, sequence number and year. A storm ID, rather than its name alone, identifies an event.

Each observation in the cached files has 21 data fields:

| Position | Field | Meaning / units | Used currently? |
|---:|---|---|---|
| 1 | Date | YYYYMMDD, UTC | Yes |
| 2 | Time | HHMM, UTC | Yes |
| 3 | Record identifier | Special-event flag, including landfall flag L; blank for ordinary records | No |
| 4 | Status | Storm classification, e.g. TD, TS, HU or EX | Yes |
| 5 | Latitude | Degrees with N/S hemisphere suffix | Yes |
| 6 | Longitude | Degrees with E/W hemisphere suffix | Yes |
| 7 | Maximum sustained wind | Knots; storm maximum, not measured vessel wind | Yes |
| 8 | Minimum central pressure | Millibars / hPa | No |
| 9 | 34 kt wind radius NE | Nautical miles from centre in this quadrant | Yes |
| 10 | 34 kt wind radius SE | Nautical miles from centre in this quadrant | Yes |
| 11 | 34 kt wind radius SW | Nautical miles from centre in this quadrant | Yes |
| 12 | 34 kt wind radius NW | Nautical miles from centre in this quadrant | Yes |
| 13 | 50 kt wind radius NE | Nautical miles from centre in this quadrant | Yes |
| 14 | 50 kt wind radius SE | Nautical miles from centre in this quadrant | Yes |
| 15 | 50 kt wind radius SW | Nautical miles from centre in this quadrant | Yes |
| 16 | 50 kt wind radius NW | Nautical miles from centre in this quadrant | Yes |
| 17 | 64 kt wind radius NE | Nautical miles from centre in this quadrant | Yes |
| 18 | 64 kt wind radius SE | Nautical miles from centre in this quadrant | Yes |
| 19 | 64 kt wind radius SW | Nautical miles from centre in this quadrant | Yes |
| 20 | 64 kt wind radius NW | Nautical miles from centre in this quadrant | Yes |
| 21 | Radius of maximum wind | Nautical miles from centre to maximum-wind region; not the same as wind-field radius | No |

Storm status examples: TD tropical depression; TS tropical storm; HU hurricane; EX extratropical cyclone; SD/SS subtropical depression/storm; LO low; WV tropical wave; DB disturbance.

Records are generally six-hourly, with additional special-event times. Missing numeric values are commonly -999; the application treats negative wind radii as unavailable. A zero radius and a missing radius are different. Older storm records can lack fields that are available in modern seasons. The application interpolates storm observations and samples exposure at up to five-minute intervals; those steps are not original five-minute NOAA observations.

## GOES imagery fields consumed by the application

The on-demand source is an ABI C13 cloud/moisture imagery NetCDF file. The raw file is deleted after rendering a map crop; the PNG and acquisition metadata can be cached. The following is the subset the renderer consumes, not an exhaustive schema of every variable in the source product.

| Variable / attribute | Meaning / use |
|---|---|
| `CMI` | Infrared brightness-temperature raster, converted to kelvin using scale/offset |
| `DQF` | Pixel quality flags; current renderer accepts values 0 and 1 |
| `x`, `y` | Satellite fixed-grid scan-angle coordinates |
| `goes_imager_projection` | Satellite height, projection-origin longitude and ellipsoid axes for geolocation |
| `scale_factor`, `add_offset`, `_FillValue` | Decode packed raster/coordinate values and identify missing pixels |
| `time_coverage_start`, `time_coverage_end` | Actual UTC acquisition start/end times |

C13 imagery represents infrared brightness temperature, not surface wind, rain rate, wave height or shipboard weather. Current maps render a fixed 180-330 K grayscale and approximately 2 km source resolution. The 640 x 512 output crop is a display raster, not the native satellite grid.

## Additional information we could expose

| Information | Source and approach | Limitation |
|---|---|---|
| Central-pressure chart at vessel encounters | HURDAT2 pressure, currently ignored by parser | Atmospheric pressure at storm centre, not vessel position |
| Radius of maximum wind / compactness | HURDAT2 field 21 | Missing for many older observations; must label estimates |
| Recorded landfalls and status transitions | HURDAT2 special-event flag and status | Cannot establish vessel impact merely from landfall |
| Storm intensification, movement speed and direction | Derive from successive storm observations | Depends on source interval and available records |
| Vessel year/month coverage and gap timeline | Segment timestamps and geometry | Absence of tracks is not proof of absence |
| Vessel beam, draft and dimension history | Width, Draft and Length per segment | Reported values may be missing, stale or inconsistent |
| Port/coastal visits and route heatmaps | Track geometry plus geographic boundaries | Requires additional port/coastline geometry; arrival times are estimates |
| Time within 34/50/64 kt wind fields | Vessel positions plus storm quadrant radii | Modelled overlap, not measured vessel winds |
| Local cloud-top temperature display | GOES C13 raster | Temperature interpretation needs quality/geolocation handling |

Risk scores, confidence, storm encounter counts, closest-approach distance, vessel journey distance and speed are application outputs. They are not pre-existing columns in NOAA data. Ownership, market value, insured value and actual loss history cannot be established from these datasets.

## References

- [NOAA AIS Vessel Tracks 2025 metadata](https://www.fisheries.noaa.gov/inport/item/79504/full-list)
- [NOAA AIS Vessel Tracks 2024 metadata](https://www.fisheries.noaa.gov/inport/item/75937/full-list)
- [NHC HURDAT2 format, including radius of maximum wind](https://www.nhc.noaa.gov/data/hurdat/hurdat2-format-atl-1851-2021.pdf)

Field names, types, table structure, source CRS and cached date ranges above were verified directly against the local files.
