# Local application data

The application creates Cosmos-compatible JSON documents below this directory at runtime.

- `analyses/` contains one immutable directory per vessel assessment.
- `users/` contains localhost-only password hashes.
- `jobs/` is reserved for NOAA processing job state.
- `broadcasts/368208000.json` contains imported El Faro NOAA AIS and NTSB VDR
  observations, with source kinds, URLs, download hashes and timestamp-validation
  notes. The two sources are identified separately in assessments.

Generated content is ignored by source control. Large NOAA archives must not be stored here because this workspace is synchronised by OneDrive. Configure `AIS_CACHE_DIR`, for example `C:/MCI-AIS-Cache`.

