# MCI Marine Risk Intelligence

Localhost proof of concept for assessing a vessel's historical tropical-cyclone exposure in U.S. coastal waters.

For the proposed Azure platform spanning marine, cargo and specialist yachts, see the [Marine and Cargo High Level Design](MARINE_CARGO_HLD.md).

## What is included

- Secure localhost login with Argon2 password hashes and session protection
- Real-data underwriting dashboard backed by cached authoritative datasets
- IMO/MMSI analysis form and explainable `TC-EXPOSURE-v0.1` scoring
- Statistical vessel and encounter breakdowns
- Self-contained interactive encounter map that works without external map services
- Cosmos-compatible, schema-versioned JSON persistence
- Repository abstraction ready for a future Cosmos DB implementation
- Configurable NOAA cache location outside the OneDrive project

The active `real` provider matches NOAA/BOEM/U.S. Coast Guard MarineCadastre AIS vessel tracks against NOAA National Hurricane Center HURDAT2 best tracks. It never generates substitute encounters when source data is absent.

## Event Look up

Open **Event Look up** from the top navigation to discover MMSIs in the cached 2021-2025 AIS tracks. Choose a named NOAA storm, one of 150 U.S. principal ports, or both. The storm, port and vessel-type fields are editable dropdowns: click into a field and type to narrow its choices, then click a suggestion or use the arrow keys and Enter. Storm options include year and NHC storm ID so repeated names are unambiguous. When both storm and port are selected, a vessel must be within the chosen nautical-mile distance of both at the same recorded time. A storm search can leave the date blank to inspect its complete recorded lifetime; a single date is faster. A port-only search requires a date. Results show separate storm and port distances and link directly to **New analysis** with MMSI and date prefilled.

The AIS vessel-type dropdown is read from the local track database. The **Yacht candidates** filter includes AIS pleasure/sailing craft (group or type codes 36/37) with a recorded length of at least 24 m. You can also set another minimum length or turn the preset off. Gross tonnage and vessel value are deliberately not filters: this data does not substantiate them, and length alone cannot establish a £5m-£50m valuation. Missing AIS tracks do not prove that a vessel was absent.

Port names and reference points come from the [U.S. principal ports layer](https://services7.arcgis.com/n1YM8pTrFmm7L4hs/arcgis/rest/services/Principal_Ports/FeatureServer/0), based on USACE port polygons. Distance is measured from the polygon's area-weighted reference point, not its full boundary. To refresh the local port list, run `\.venv\Scripts\python.exe scripts\import_ports.py`. The lookup requires the existing AIS and HURDAT2 cache; it does not fabricate vessels or storm encounters.

## REAL MMSI TEST NUMBERS

Use the following real MMSIs in **New Analysis**. Every number below has been checked directly against the locally cached NOAA MarineCadastre 2021–2025 GeoPackage track files. To assess the full five-year source period, use **2021-01-01 to 2025-12-31**; the individual observed range shows where each vessel actually has records. A five-year source cache does not mean every vessel has five years of observations.

| Real MMSI | Vessel | IMO | Track segments (2021–2025) | Observed track range |
|---|---|---|---:|---|
| `215938000` | PIRANHA | `9088249` | 147 | 2024-06-16 to 2025-07-12 |
| `please copy C:\Users\PeterBurrows\OneDrive - Medical & Commercial International Ltd\Documents\CAT POC Project\Project Documents\MCI Vessel Tracking High Level Design - HLD Aligned.drawio.xml to my downloads directory` | SPUIGRACHT | `9202534` | 2,307 | 2021-02-01 to 2025-12-11 |
| `255806481` | INDEPENDENT QUEST | `9246700` | 2,112 | 2021-02-16 to 2025-12-21 |
| `259023000` | DON PASQUALE | `9138513` | 1,263 | 2023-06-21 to 2025-11-30 |
| `311001653` | DOLE WARI | `9399777` | 2,339 | 2025-02-03 to 2025-12-22 |
| `354215000` | CARNIVAL PRIDE | `9223954` | 7,387 | 2021-01-02 to 2025-12-30 |
| `355029000` | GRAND MARK | `9228306` | 1,969 | 2021-01-06 to 2025-12-17 |
| `355488000` | DELHI HIGHWAY | `9536959` | 2,226 | 2021-07-29 to 2025-12-30 |
| `355708000` | GRAND DOLPHIN | `9279329` | 1,582 | 2021-02-07 to 2025-12-30 |
| `367138490` | ANNA M | `9406403` | 6,908 | 2021-01-01 to 2025-12-31 |
| `367721220` | OCEAN GLORY | `9681833` | 1,602 | 2021-01-06 to 2025-12-09 |
| `367775000` | MAERSK OHIO | `9298698` | 5,899 | 2021-01-01 to 2025-12-24 |
| `368004000` | BRENTON REEF | `9144926` | 7,905 | 2021-01-01 to 2025-12-15 |
| `368400770` | BOYS TOY | — | 665 | 2025-05-23 to 2025-11-24 |
| `431527000` | FRONTIER ACE | `9209271` | 1,918 | 2025-04-23 to 2025-12-31 |
| `440253000` | MORNING MENAD | `9318515` | 4,413 | 2022-06-20 to 2025-09-23 |
| `538009562` | DEL MONTE ROSE | `9849655` | 7,860 | 2021-11-01 to 2025-12-24 |
| `565473000` | MAERSK NORTHAMPTON | `9215919` | 4,411 | 2021-01-01 to 2025-10-11 |
| `636020349` | MARIANNA I | `9162227` | 469 | 2025-03-07 to 2025-10-20 |
| `636022776` | CHIQUITA VOYAGER | `9304978` | 6,650 | 2023-07-07 to 2025-12-31 |

Copyable MMSI list:

```text
215938000, 245261000, 255806481, 259023000, 311001653,
354215000, 355029000, 355488000, 355708000, 367138490,
367721220, 367775000, 368004000, 368400770, 431527000,
440253000, 538009562, 565473000, 636020349, 636022776
```

### Vessel photographs

The analysis page serves verified photos from local files. SPUIGRACHT (`245261000`, IMO `9202534`) uses a [photograph by Niels Johannes](https://commons.wikimedia.org/wiki/File:Spuigracht_(IMO_9202534).jpg), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). CARNIVAL PRIDE (`354215000`) uses a [photograph by Balou46](https://commons.wikimedia.org/wiki/File:US-port-canav-carnival-pride_(recropped).jpg), also licensed CC BY-SA 4.0.

For any other real-data assessment, the first result view searches Wikimedia Commons using the vessel's resolved IMO, or its MMSI if no IMO is known. It accepts only images tied to that exact identifier and carrying an approved Creative Commons licence, then caches the image and attribution under `data/vessel_photos/`. The browser loads the cached local copy on later views, avoiding external image requests. If the source is unavailable or no trustworthy, reusable photograph exists, the page shows the labelled vessel illustration; it never substitutes a photo of a different ship. Unsuccessful matches are retried after seven days, and temporary lookup errors after one hour. The photo lookup does not affect AIS or storm analysis results.

### Legacy demonstration MMSI reference (inactive)

The following 248 MMSIs belong to the original synthetic demonstration portfolio. They are retained for reference but are not valid real-data inputs while the application is in `real` provider mode.

| MMSI | MMSI | MMSI | MMSI | MMSI | MMSI | MMSI | MMSI |
|---|---|---|---|---|---|---|---|
| `200000000` | `200000001` | `200000002` | `200000003` | `200000004` | `200000005` | `200000006` | `200000007` |
| `200000008` | `200000009` | `200000010` | `200000011` | `200000012` | `200000013` | `200000014` | `200000015` |
| `200000016` | `200000017` | `200000018` | `200000019` | `200000020` | `200000021` | `200000022` | `200000023` |
| `200000024` | `200000025` | `200000026` | `200000027` | `200000028` | `200000029` | `200000030` | `200000031` |
| `200000032` | `200000033` | `200000034` | `200000035` | `200000036` | `200000037` | `200000038` | `200000039` |
| `200000040` | `200000041` | `200000042` | `200000043` | `200000044` | `200000045` | `200000046` | `200000047` |
| `200000048` | `200000049` | `200000050` | `200000051` | `200000052` | `200000053` | `200000054` | `200000055` |
| `200000056` | `200000057` | `200000058` | `200000059` | `200000060` | `200000061` | `200000062` | `200000063` |
| `200000064` | `200000065` | `200000066` | `200000067` | `200000068` | `200000069` | `200000070` | `200000071` |
| `200000072` | `200000073` | `200000074` | `200000075` | `200000076` | `200000077` | `200000078` | `200000079` |
| `200000080` | `200000081` | `200000082` | `200000083` | `200000084` | `200000085` | `200000086` | `200000087` |
| `200000088` | `200000089` | `200000090` | `200000091` | `200000092` | `200000093` | `200000094` | `200000095` |
| `200000096` | `200000097` | `200000098` | `200000099` | `200000100` | `200000101` | `200000102` | `200000103` |
| `200000104` | `200000105` | `200000106` | `200000107` | `200000108` | `200000109` | `200000110` | `200000111` |
| `200000112` | `200000113` | `200000114` | `200000115` | `200000116` | `200000117` | `200000118` | `200000119` |
| `200000120` | `200000121` | `200000122` | `200000123` | `200000124` | `200000125` | `200000126` | `200000127` |
| `200000128` | `200000129` | `200000130` | `200000131` | `200000132` | `200000133` | `200000134` | `200000135` |
| `200000136` | `200000137` | `200000138` | `200000139` | `200000140` | `200000141` | `200000142` | `200000143` |
| `200000144` | `200000145` | `200000146` | `200000147` | `200000148` | `200000149` | `200000150` | `200000151` |
| `200000152` | `200000153` | `200000154` | `200000155` | `200000156` | `200000157` | `200000158` | `200000159` |
| `200000160` | `200000161` | `200000162` | `200000163` | `200000164` | `200000165` | `200000166` | `200000167` |
| `200000168` | `200000169` | `200000170` | `200000171` | `200000172` | `200000173` | `200000174` | `200000175` |
| `200000176` | `200000177` | `200000178` | `200000179` | `200000180` | `200000181` | `200000182` | `200000183` |
| `200000184` | `200000185` | `200000186` | `200000187` | `200000188` | `200000189` | `200000190` | `200000191` |
| `200000192` | `200000193` | `200000194` | `200000195` | `200000196` | `200000197` | `200000198` | `200000199` |
| `200000200` | `200000201` | `200000202` | `200000203` | `200000204` | `200000205` | `200000206` | `200000207` |
| `200000208` | `200000209` | `200000210` | `200000211` | `200000212` | `200000213` | `200000214` | `200000215` |
| `200000216` | `200000217` | `200000218` | `200000219` | `200000220` | `200000221` | `200000222` | `200000223` |
| `200000224` | `200000225` | `200000226` | `200000227` | `200000228` | `200000229` | `200000230` | `200000231` |
| `200000232` | `200000233` | `200000234` | `200000235` | `200000236` | `200000237` | `200000238` | `200000239` |
| `200000240` | `200000241` | `200000242` | `200000243` | `200000244` | `200000245` | `200000246` | `200000247` |


The local cache now contains verified AIS track files for all five complete years, 2021–2025. The analysis form defaults to the latest uninterrupted set of cached years. An analysis is rejected when no real AIS tracks exist; the application does not substitute synthetic positions. Individual vessels may have AIS observations in only some cached years. For example, `431527000` (FRONTIER ACE) has verified records in 2025 only; it cannot yield a five-year personal track history from this cache.

### Authoritative sources

- [NOAA NHC HURDAT2 archive](https://www.nhc.noaa.gov/data/) — official post-analysis tropical cyclone positions, intensities and wind radii.
- [NOAA Digital Coast Vessel Traffic](https://coast.noaa.gov/digitalcoast/data/vesseltraffic.html) — U.S. Coast Guard AIS-derived MarineCadastre vessel tracks.
- [NOAA MarineCadastre annual vessel-track archive](https://ocmgeodatastor1.blob.core.windows.net/marinecadastre/ais/aistrack/index-aistrack.html) — the 2021–2025 ZIP files used by the local cache.

The MarineCadastre products contain track geometry with segment start and end times. The application distance-interpolates timestamps for intermediate geometry vertices, records that limitation in every assessment, and never treats missing terrestrial AIS coverage as proof of vessel absence.


## Prerequisites

- Windows 10/11
- Python 3.12 or newer
- At least 100 GB free for downloading and extracting the complete 2021–2025 AIS cache
- Recommended AIS cache: `C:\MCI-AIS-Cache`

## Setup

From PowerShell in the project directory:

```powershell
.\scripts\setup.ps1
.\scripts\run.ps1
```

Alternatively, with Node.js and npm installed, run `npm run dev` after the
one-time setup. This starts the same FastAPI server with automatic reload;
the server serves both the frontend pages and backend routes. No npm
dependencies need to be installed. Keep the terminal open and press Ctrl+C
to stop the server.

Open <http://127.0.0.1:8000>.

### Encounter map

The encounter view uses locally bundled Leaflet 1.9.4 with OpenStreetMap background
tiles. No account, API key, payment method or npm dependency installation is needed.
Use the zoom buttons, drag to pan, choose a storm encounter, toggle vessel/storm
tracks and 34/50/64 kt wind areas, or move the timeline to inspect historical storm
positions. Fit encounter and Full storm track buttons reset the view.

The timeline now provides five-minute steps and smooth Play/Pause playback at
10, 30 or 60 historical minutes per real-time second. Scrubbing pauses playback.
Vessel and storm markers and wind areas move together. Vessel playback follows
the timed track geometry, including straight-line interpolation between known
positions where source data has gaps. These bridges are dashed and labelled as
display-only estimates; they never contribute to exposure scores or statistics.
Uncheck Interpolate gaps to hide these estimates. Positions are not projected
before the first or after the last known point. Missing storm intervals remain
unknown. Coordinates, estimated speed/heading and centre
separation update beside the map. Enable Track samples to inspect timestamped
geometry vertices; a maximum of 3,000 sample markers are shown per encounter,
with the displayed/available count reported. No new original AIS messages are
created by interpolation.

#### On-demand historical GOES imagery

Choose **GOES infrared (10 min, on demand)** under Background for animated historical
satellite imagery. The application requests each image through its own authenticated
API, looks up the nearest archived GOES scan, downloads that single source file,
and prepares a 640 × 512 Web Mercator crop covering the encounter. It never
downloads the whole satellite archive or substitutes today's image for a historical
request. Actual acquisition start/end times are displayed; the scan start must be
within ten minutes of the requested slot.

This is ABI C13 clean infrared imagery, with approximately 2 km source resolution.
The fixed grayscale uses 180–330 K: cold cloud tops are brighter. It works by day
and night and is not a true-colour photograph.

For the installed application, the isolated satellite worker is already configured.
For a new checkout, install Python 3.13 and run:

```powershell
.\scripts\setup_satellite.ps1
# If needed: .\scripts\setup_satellite.ps1 -PythonPath C:\path\to\python.exe
```

The worker's numpy/h5py/Pillow/pyproj dependencies are kept in `.venv-satellite`,
separate from the main application's Python environment. Optional `.env` settings:

```text
SATELLITE_PYTHON=.venv-satellite/Scripts/python.exe
SATELLITE_CACHE_DIR=./data/satellite
SATELLITE_CACHE_LIMIT_MB=512
```

Image crops are cached within that limit; raw downloads are removed after rendering.
The browser buffers the current and next three images, with two requests in flight
and a twelve-image memory cache. Playback waits while the next frame is loading.
Selecting GOES sets playback to 10 historical minutes/second; faster speeds can
require more buffering. Missing images are labelled, and **Retry imagery** retries
failed requests. Leaving the source or encounter cancels browser requests and
prevents stale images from appearing in another encounter.

The `ImageryProvider` interface in `app/satellite.py` isolates source lookup and
rendering so a future imagery API can replace the archive adapter. It has no
dependency on scoring; AIS tracking and storm/exposure calculations remain NOAA
based. Free public source access requires no API key, cloud account or payment.
Internet access is required on the server for first-time frames; cached crops
can be reused without fetching their source again.

Checks:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv-satellite\Scripts\python.exe tests/satellite_renderer_checks.py
node --test tests/encounter-map.test.cjs tests/satellite-playback.test.cjs
```

Vessel tracks show up to 24 hours either side of closest approach within the
assessment dates. Storm tracks show the full NOAA lifecycle. Missing vessel
positions and wind radii remain unknown. Wind polygons represent reported maximum
quadrant extents at the selected time, not a forecast cone or measured shipboard winds.

Background tiles need internet access. If tiles cannot load, the local NOAA overlays
remain interactive and a message identifies the missing background. Tile requests
use HTTPS, visible OpenStreetMap attribution and the browser's normal tile caching.
Only tiles for the visible map are requested; no bulk downloading or prefetching.
The default tile service is intended for light use and has no availability guarantee.
See the [OpenStreetMap tile usage policy](https://operations.osmfoundation.org/policies/tiles/).

An alternative tile service can be configured with `MAP_TILE_URL` and
`MAP_TILE_ATTRIBUTION` in `.env`, then restart `npm run dev`. These settings are
optional; the OpenStreetMap defaults work immediately. Google Maps settings are
no longer used. Leaflet's license is included under `app/static/vendor/leaflet/`.

For an initial real-data test, download the official hurricane records and
one year of AIS tracks before downloading the full cache:

```powershell
.\.venv\Scripts\python.exe scripts\fetch_hurdat.py
.\.venv\Scripts\python.exe scripts\fetch_ais_track_year.py 2025
```

Both downloaders use `AIS_CACHE_DIR` from `.env`. The hurricane downloader
records its official source URLs in `storms/sources.json`. AIS extraction
requires either the `zipfile64` Python package or 7-Zip installed at its
standard Windows location when an archive uses Deflate64 compression.
Keep `ANALYSIS_PROVIDER=real` and select dates within the downloaded year.
MMSI searches work without a vessel registry; IMO searches need a matching
entry in `vessels/registry.json`.

To populate or rebuild the full five-year MarineCadastre vessel-track cache, run this in PowerShell. The importer resumes interrupted downloads, validates each annual GeoPackage, and removes its temporary ZIP only after validation:

```powershell
2021..2025 | ForEach-Object { .\.venv\Scripts\python.exe scripts\fetch_ais_track_year.py $_ }
```

The importer also builds an MMSI lookup index for each year. For a GeoPackage that was already cached before indexing was added, run `fetch_ais_track_year.py YEAR --index-only` to create that index without downloading again.

Login credentials are configured locally in the ignored `.env` file and are not displayed in the application or documentation.

## Configuration

Copy `.env.example` to `.env`. Important settings:

```text
ANALYSIS_PROVIDER=real
DATA_DIR=./data
AIS_CACHE_DIR=C:/MCI-AIS-Cache
AIS_CACHE_LIMIT_GB=100
```

The cache must remain outside OneDrive. Real mode reads any available `tracks/AISVesselTracksYYYY.gpkg` files, the two HURDAT2 text files under `storms/`, and `vessels/registry.json`. The full five-year cache requires one GeoPackage for each year from 2021 through 2025. JSON analysis documents remain under `data/analyses` and are small enough to keep with the local application.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Storage migration

Application services depend on `AnalysisRepository`, not directly on files. The Azure version will replace `FileAnalysisRepository` with a Cosmos DB implementation and place GeoJSON, Parquet and PDF artifacts in Azure Blob Storage.
