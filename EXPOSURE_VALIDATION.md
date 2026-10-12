# Exposure statistics validation

Audit completed 12 October 2026. New real-data assessments use `TC-EXPOSURE-v0.2`.
Older saved assessments are retained and show a notice asking you to rerun them.

## Corrections

- Exposure duration measures elapsed time supported by each track, using midpoint
  integration with steps of at most five minutes. A single position contributes
  zero elapsed time. Separate tracks, separate geometry lines and vertex gaps over
  six hours are not bridged. Leaving and returning to a storm does not count the
  time outside its threshold.
- Overall exposure and wind-field hours are unions of time intervals. Simultaneous
  storms do not double-count elapsed time. Individual encounter durations can sum
  to more than the overall duration when storms overlap.
- Geometry is clipped at the requested UTC dates using the original timestamps.
  A segment stored in a neighbouring month/year remains eligible when its actual
  timestamps overlap the requested period.
- Track distance excludes jumps between disconnected lines and overlapping track
  intervals. Average speed is distance divided by supported track time; maximum
  speed is the largest estimated speed between timed vertices, not measured AIS SOG.
- Named-storm counts exclude unnamed depressions. A named storm's complete recorded
  lifecycle remains eligible, including its disturbance/extratropical stages.
- Missing HURDAT2 wind radii remain unknown. Known quadrant radii interpolate
  linearly in time, including valid zero radii. Wind fields are proximity proxies
  based on reported maximum quadrant extents, not measurements at the vessel.
- Storm classification and category refer to peak intensity during the encounter.
  Scoring uses unrounded duration, and low-confidence zero-encounter results still
  require referral.
- Coverage gaps now count named-storm windows with an uncovered span over six
  hours, including gaps inside cached years. Missing years are separately warned.
- The real-data form no longer offers a coastal-distance control that does nothing.
  There is no coastline-distance dataset/filter in this implementation. It uses
  all cached vessel tracks in the requested dates, and reports this limitation.

## Real NOAA validation

MMSI `354215000`, 1 January–31 December 2025, storm threshold 200 nm:

| Statistic | Application | One-minute reference |
|---|---:|---:|
| Derived track positions | 117,069 | 117,069 |
| Days with derived positions | 224 | 224 |
| Named storms encountered | 2 | 2 |
| Closest approach | 2.3 nm | 2.3 nm |
| Track distance | 39,383.0 nm | 39,383.0 nm |
| Average speed | 13.7 kt | 13.7 kt |
| Maximum estimated track speed | 26.4 kt | 26.4 kt |
| Exposure within threshold | 21.6 h | 21.6 h |
| Time inside reported wind radii and threshold | 0.3 h | 0.3 h |

Encounter scores: Chantal 63, Dexter 14. Aggregate components are worst 63,
top-three average 38 and recurrence 19. Weighted score rounds to **47 (Elevated)**.
Confidence is **Low**, with 32 named-storm windows containing coverage gaps.
These include storms in either source basin; the gap check is conservative and
does not establish that the vessel was geographically exposed during missing data.

The original August assessment reported 1.7 exposure hours. The corrected method
reports 0.9 hours. All other displayed August movement statistics stayed the same.

The reference checker implements separate spherical-distance arithmetic and
one-minute time integration. It shares source parsing, storm interpolation and
track interval preparation with the application; controlled regression tests
separately exercise clipping, overlaps, disconnected lines, thresholds, quadrants,
missing values, exact source timestamps, storm-lifetime boundaries and score maths.
This is computational validation, not independent verification of NOAA's accuracy.

To check any saved real assessment:

```powershell
.\.venv\Scripts\python.exe scripts\verify_exposure_statistics.py ANALYSIS_ID
.\.venv\Scripts\python.exe -m pytest
```

JSON fields containing `200_nm` retain their legacy names for compatibility but
store time within the assessment's configured storm threshold. The UI describes
that threshold. Source timestamps reflect local cache modification times.

## Remaining limitations

Intermediate vessel timestamps and storm parameters are interpolated. Five-minute
integration can miss brief boundary crossings, so durations and closest approaches
remain estimates. Track position counts are not counts of original AIS messages.
Missing observations and missing wind radii cannot prove no exposure. Vessel
dimensions/type are cached metadata; missing identity/flag information remains
unknown. The confidence rules and exposure score are heuristics and have not been
actuarially calibrated. Only 2025 AIS tracks are currently cached on this machine.

Source definitions:

- [NOAA MarineCadastre vessel traffic](https://coast.noaa.gov/digitalcoast/data/vesseltraffic.html)
- [NHC HURDAT2 format, including missing radii](https://www.nhc.noaa.gov/data/hurdat/hurdat2-format-nov2019.pdf)
- [NHC wind-field quadrant definitions](https://www.nhc.noaa.gov/aboutwindfield3.shtml)
