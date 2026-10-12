# NOAA vessel results: 2023?2025

2023 and 2024 official NOAA MarineCadastre track databases downloaded, integrity-checked and indexed alongside existing 2025 tracks. All ten MMSIs were submitted sequentially through the running application for 2023-01-01 to 2025-12-31, using 200 nm storm proximity and the default 75 nm coastal setting (not applied by the real-data provider). All result pages returned HTTP 200.

| Vessel | MMSI | Years with tracks | Observed days | Encounters (2025-only to three years) | Score (2025-only to three years) | Band | Storms within 200 nm | Storm names |
| --- | --- | --- | ---: | --- | --- | --- | ---: | --- |
| SUR LA MER | 319023700 | 2023, 2024, 2025 | 455 | 0 to 1 | 0 to 48 | ELEVATED | 1 | Milton (2024) |
| M3 | 339378000 | 2023, 2024, 2025 | 345 | 0 to 1 | 0 to 53 | ELEVATED | 1 | Milton (2024) |
| NEXT CHAPTER | 319076300 | 2023, 2024, 2025 | 178 | 0 to 0 | 0 to 0 | LOW | 0 | None detected |
| LADY ELANE | 339078000 | 2023, 2024, 2025 | 350 | 0 to 2 | 0 to 47 | ELEVATED | 2 | Lee (2023), Ophelia (2023) |
| MY IMAGINE | 319098900 | 2023, 2024, 2025 | 227 | 0 to 0 | 0 to 0 | LOW | 0 | None detected |
| KOJU | 339000115 | 2024, 2025 | 94 | 0 to 0 | 0 to 0 | LOW | 0 | None detected |
| WHEELS | 367403020 | 2023, 2024, 2025 | 367 | 1 to 1 | 14 to 14 | LOW | 1 | Imelda (2025) |
| FRANKLIE | 319298500 | 2024, 2025 | 75 | 0 to 0 | 0 to 0 | LOW | 0 | None detected |
| JODI ANN | 339857000 | 2023, 2024, 2025 | 237 | 0 to 0 | 0 to 0 | LOW | 0 | None detected |
| 319129400 | 319129400 | 2025 | 72 | 1 to 1 | 35 to 35 | MODERATE | 1 | Imelda (2025) |

## Storm counts by closest-approach distance

Counts are cumulative: a storm within 20 nm also counts in every larger threshold. Each distinct storm is counted once per vessel using its estimated closest approach in available 2023-2025 tracks. Thresholds increase by 25 nm from 20 to 295 nm, retaining the earlier 200 nm column and adding a final 300 nm endpoint. All ten vessels were rerun through the application at 300 nm to identify additional storms. A zero means none detected in available tracks; exposure during gaps remains unknown. The original summary scores remain from the 200 nm analyses.

| Vessel | MMSI | Within 20 nm | Within 45 nm | Within 70 nm | Within 95 nm | Within 120 nm | Within 145 nm | Within 170 nm | Within 195 nm | Within 200 nm | Within 220 nm | Within 245 nm | Within 270 nm | Within 295 nm | Within 300 nm |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SUR LA MER | 319023700 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 2 | 2 | 4 | 4 | 4 |
| M3 | 339378000 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 1 | 1 | 1 | 2 | 2 | 3 | 3 |
| NEXT CHAPTER | 319076300 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 1 | 2 |
| LADY ELANE | 339078000 | 0 | 0 | 0 | 1 | 1 | 1 | 1 | 2 | 2 | 2 | 2 | 3 | 3 | 3 |
| MY IMAGINE | 319098900 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| KOJU | 339000115 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| WHEELS | 367403020 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 2 | 2 | 2 | 3 | 3 |
| FRANKLIE | 319298500 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| JODI ANN | 339857000 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 1 |
| 319129400 | 319129400 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |

Tracks remain intermittent; years with tracks do not imply continuous coverage. All ten analyses report LOW confidence. Names and IMO/MMSI pairings are user-supplied and remain unverified by the local vessel registry. Missing observations cannot establish absence of exposure. Positions are AIS-derived track vertices with interpolated timestamps, not original broadcast-message counts.

## Per-vessel results

### SUR LA MER ? 319023700

[Open saved analysis](http://127.0.0.1:8000/analysis?analysisId=analysis_3c5bb97a13564774aec23f07be698cd7)

| Year | Track segments | First recorded UTC | Last recorded UTC |
|---|---:|---|---|
| 2023 | 86 | 2023-01-16T09:11:50.0Z | 2023-12-30T14:38:07.0Z |
| 2024 | 62 | 2024-04-11T16:45:53.0Z | 2024-11-15T22:30:31.0Z |
| 2025 | 190 | 2025-01-21T03:50:36.0Z | 2025-12-19T17:34:32.0Z |

Statistics: {"aisObservationCount": 28486, "observedDays": 455, "namedStormEncounters": 1, "hoursWithin200Nm": 17.5, "hoursWithin34KtWindField": 10.7, "minimumDistanceNm": 151.2, "distanceTravelledNm": 5361.1, "averageSpeedKt": 0.5, "maximumSpeedKt": 14.0}

- Milton (AL142024): closest approach 151.2 nm at 2024-10-10T05:07:32.506506+00:00; 17.5 hours within 200 nm; 10.7 hours within the reported 34 kt wind field.

Data quality warnings:

- MarineCadastre vessel-track geometry is authoritative AIS-derived data, but timestamps between each segment's endpoints are distance-interpolated.
- MarineCadastre AIS is land-receiver data and may not capture vessel activity beyond normal coastal receiver range.
- Exposure durations and closest approaches are estimates from track interpolation sampled at intervals of at most five minutes. Separate tracks and vertex gaps over six hours are not bridged.
- The coastal-limit parameter is not applied: this cache has no coastline-distance filter. Results use all available vessel tracks in the selected dates.
- Wind-field results use reported radii and are not measured wind at the vessel. Missing radii cannot establish an absence of wind exposure.
- 85 named-storm windows have track coverage gaps exceeding six hours. Exposure during those gaps is unknown.

### M3 ? 339378000

[Open saved analysis](http://127.0.0.1:8000/analysis?analysisId=analysis_95ca4d04d9a94832be2e891e6e056fae)

| Year | Track segments | First recorded UTC | Last recorded UTC |
|---|---:|---|---|
| 2023 | 52 | 2023-01-01T00:02:17.0Z | 2023-09-25T23:49:07.0Z |
| 2024 | 68 | 2024-04-25T12:37:16.0Z | 2024-12-26T23:14:40.0Z |
| 2025 | 114 | 2025-01-06T13:07:26.0Z | 2025-12-25T00:42:47.0Z |

Statistics: {"aisObservationCount": 22976, "observedDays": 345, "namedStormEncounters": 1, "hoursWithin200Nm": 21.2, "hoursWithin34KtWindField": 12.4, "minimumDistanceNm": 113.9, "distanceTravelledNm": 5158.5, "averageSpeedKt": 0.6, "maximumSpeedKt": 16.2}

- Milton (AL142024): closest approach 113.9 nm at 2024-10-10T06:43:34.032763+00:00; 21.2 hours within 200 nm; 12.4 hours within the reported 34 kt wind field.

Data quality warnings:

- MarineCadastre vessel-track geometry is authoritative AIS-derived data, but timestamps between each segment's endpoints are distance-interpolated.
- MarineCadastre AIS is land-receiver data and may not capture vessel activity beyond normal coastal receiver range.
- Exposure durations and closest approaches are estimates from track interpolation sampled at intervals of at most five minutes. Separate tracks and vertex gaps over six hours are not bridged.
- The coastal-limit parameter is not applied: this cache has no coastline-distance filter. Results use all available vessel tracks in the selected dates.
- Wind-field results use reported radii and are not measured wind at the vessel. Missing radii cannot establish an absence of wind exposure.
- 96 named-storm windows have track coverage gaps exceeding six hours. Exposure during those gaps is unknown.

### NEXT CHAPTER ? 319076300

[Open saved analysis](http://127.0.0.1:8000/analysis?analysisId=analysis_7cb864562de84f638f95f7fe4945f70d)

| Year | Track segments | First recorded UTC | Last recorded UTC |
|---|---:|---|---|
| 2023 | 16 | 2023-01-04T06:23:04.0Z | 2023-12-31T23:59:14.0Z |
| 2024 | 113 | 2024-01-06T20:32:53.0Z | 2024-09-10T08:07:03.0Z |
| 2025 | 20 | 2025-05-07T09:41:49.0Z | 2025-10-13T20:22:29.0Z |

Statistics: {"aisObservationCount": 14387, "observedDays": 178, "namedStormEncounters": 0, "hoursWithin200Nm": 0.0, "hoursWithin34KtWindField": 0.0, "minimumDistanceNm": null, "distanceTravelledNm": 2691.9, "averageSpeedKt": 0.8, "maximumSpeedKt": 14.1}


Data quality warnings:

- MarineCadastre vessel-track geometry is authoritative AIS-derived data, but timestamps between each segment's endpoints are distance-interpolated.
- MarineCadastre AIS is land-receiver data and may not capture vessel activity beyond normal coastal receiver range.
- Exposure durations and closest approaches are estimates from track interpolation sampled at intervals of at most five minutes. Separate tracks and vertex gaps over six hours are not bridged.
- The coastal-limit parameter is not applied: this cache has no coastline-distance filter. Results use all available vessel tracks in the selected dates.
- Wind-field results use reported radii and are not measured wind at the vessel. Missing radii cannot establish an absence of wind exposure.
- 96 named-storm windows have track coverage gaps exceeding six hours. Exposure during those gaps is unknown.

### LADY ELANE ? 339078000

[Open saved analysis](http://127.0.0.1:8000/analysis?analysisId=analysis_195c332f289f492c97e47d334a35b638)

| Year | Track segments | First recorded UTC | Last recorded UTC |
|---|---:|---|---|
| 2023 | 155 | 2023-01-01T09:02:12.0Z | 2023-12-28T07:19:30.0Z |
| 2024 | 29 | 2024-01-02T07:45:29.0Z | 2024-12-24T22:47:27.0Z |
| 2025 | 172 | 2025-01-13T08:03:46.0Z | 2025-12-26T02:39:54.0Z |

Statistics: {"aisObservationCount": 21775, "observedDays": 350, "namedStormEncounters": 2, "hoursWithin200Nm": 37.8, "hoursWithin34KtWindField": 16.3, "minimumDistanceNm": 91.3, "distanceTravelledNm": 4190.3, "averageSpeedKt": 0.5, "maximumSpeedKt": 14.5}

- Lee (AL132023): closest approach 194.7 nm at 2023-09-16T11:55:56.283156+00:00; 5.6 hours within 200 nm; 4.5 hours within the reported 34 kt wind field.
- Ophelia (AL162023): closest approach 91.3 nm at 2023-09-24T09:37:33.100307+00:00; 32.2 hours within 200 nm; 11.8 hours within the reported 34 kt wind field.

Data quality warnings:

- MarineCadastre vessel-track geometry is authoritative AIS-derived data, but timestamps between each segment's endpoints are distance-interpolated.
- MarineCadastre AIS is land-receiver data and may not capture vessel activity beyond normal coastal receiver range.
- Exposure durations and closest approaches are estimates from track interpolation sampled at intervals of at most five minutes. Separate tracks and vertex gaps over six hours are not bridged.
- The coastal-limit parameter is not applied: this cache has no coastline-distance filter. Results use all available vessel tracks in the selected dates.
- Wind-field results use reported radii and are not measured wind at the vessel. Missing radii cannot establish an absence of wind exposure.
- 86 named-storm windows have track coverage gaps exceeding six hours. Exposure during those gaps is unknown.

### MY IMAGINE ? 319098900

[Open saved analysis](http://127.0.0.1:8000/analysis?analysisId=analysis_ffec07679d4246c397557c9faa452900)

| Year | Track segments | First recorded UTC | Last recorded UTC |
|---|---:|---|---|
| 2023 | 22 | 2023-01-05T14:38:06.0Z | 2023-12-31T23:59:58.0Z |
| 2024 | 86 | 2024-01-08T16:48:46.0Z | 2024-12-27T03:00:38.0Z |
| 2025 | 59 | 2025-01-13T23:30:06.0Z | 2025-11-30T23:59:36.0Z |

Statistics: {"aisObservationCount": 11331, "observedDays": 227, "namedStormEncounters": 0, "hoursWithin200Nm": 0.0, "hoursWithin34KtWindField": 0.0, "minimumDistanceNm": null, "distanceTravelledNm": 2836.7, "averageSpeedKt": 0.6, "maximumSpeedKt": 18.6}


Data quality warnings:

- MarineCadastre vessel-track geometry is authoritative AIS-derived data, but timestamps between each segment's endpoints are distance-interpolated.
- MarineCadastre AIS is land-receiver data and may not capture vessel activity beyond normal coastal receiver range.
- Exposure durations and closest approaches are estimates from track interpolation sampled at intervals of at most five minutes. Separate tracks and vertex gaps over six hours are not bridged.
- The coastal-limit parameter is not applied: this cache has no coastline-distance filter. Results use all available vessel tracks in the selected dates.
- Wind-field results use reported radii and are not measured wind at the vessel. Missing radii cannot establish an absence of wind exposure.
- 105 named-storm windows have track coverage gaps exceeding six hours. Exposure during those gaps is unknown.

### KOJU ? 339000115

[Open saved analysis](http://127.0.0.1:8000/analysis?analysisId=analysis_3663dd77f0a54cf286fe4637d8ab4bac)

| Year | Track segments | First recorded UTC | Last recorded UTC |
|---|---:|---|---|
| 2023 | 0 | No records | No records |
| 2024 | 66 | 2024-10-02T15:07:34.0Z | 2024-12-08T21:29:19.0Z |
| 2025 | 82 | 2025-02-17T13:00:41.0Z | 2025-12-29T12:00:03.0Z |

Statistics: {"aisObservationCount": 4572, "observedDays": 94, "namedStormEncounters": 0, "hoursWithin200Nm": 0.0, "hoursWithin34KtWindField": 0.0, "minimumDistanceNm": null, "distanceTravelledNm": 996.0, "averageSpeedKt": 0.5, "maximumSpeedKt": 14.9}


Data quality warnings:

- MarineCadastre vessel-track geometry is authoritative AIS-derived data, but timestamps between each segment's endpoints are distance-interpolated.
- MarineCadastre AIS is land-receiver data and may not capture vessel activity beyond normal coastal receiver range.
- Exposure durations and closest approaches are estimates from track interpolation sampled at intervals of at most five minutes. Separate tracks and vertex gaps over six hours are not bridged.
- The coastal-limit parameter is not applied: this cache has no coastline-distance filter. Results use all available vessel tracks in the selected dates.
- Wind-field results use reported radii and are not measured wind at the vessel. Missing radii cannot establish an absence of wind exposure.
- No AIS tracks for this vessel were observed in 2023; this does not prove the vessel was absent.
- 104 named-storm windows have track coverage gaps exceeding six hours. Exposure during those gaps is unknown.

### WHEELS ? 367403020

[Open saved analysis](http://127.0.0.1:8000/analysis?analysisId=analysis_f59e0063718449d99227125af45d1ae9)

| Year | Track segments | First recorded UTC | Last recorded UTC |
|---|---:|---|---|
| 2023 | 69 | 2023-01-01T00:00:00.0Z | 2023-12-31T23:57:19.0Z |
| 2024 | 38 | 2024-01-26T13:33:02.0Z | 2024-12-31T23:58:51.0Z |
| 2025 | 46 | 2025-01-01T00:04:53.0Z | 2025-12-23T05:22:31.0Z |

Statistics: {"aisObservationCount": 17091, "observedDays": 367, "namedStormEncounters": 1, "hoursWithin200Nm": 0.0, "hoursWithin34KtWindField": 0.0, "minimumDistanceNm": 163.0, "distanceTravelledNm": 3653.1, "averageSpeedKt": 0.4, "maximumSpeedKt": 20.0}

- Imelda (AL092025): closest approach 163.0 nm at 2025-09-29T12:46:49.421674+00:00; 0.0 hours within 200 nm; 0.0 hours within the reported 34 kt wind field.

Data quality warnings:

- MarineCadastre vessel-track geometry is authoritative AIS-derived data, but timestamps between each segment's endpoints are distance-interpolated.
- MarineCadastre AIS is land-receiver data and may not capture vessel activity beyond normal coastal receiver range.
- Exposure durations and closest approaches are estimates from track interpolation sampled at intervals of at most five minutes. Separate tracks and vertex gaps over six hours are not bridged.
- The coastal-limit parameter is not applied: this cache has no coastline-distance filter. Results use all available vessel tracks in the selected dates.
- Wind-field results use reported radii and are not measured wind at the vessel. Missing radii cannot establish an absence of wind exposure.
- 106 named-storm windows have track coverage gaps exceeding six hours. Exposure during those gaps is unknown.

### FRANKLIE ? 319298500

[Open saved analysis](http://127.0.0.1:8000/analysis?analysisId=analysis_83d109cc849844ef91b51fff44a483fb)

| Year | Track segments | First recorded UTC | Last recorded UTC |
|---|---:|---|---|
| 2023 | 0 | No records | No records |
| 2024 | 1 | 2024-12-17T15:11:03.0Z | 2024-12-27T02:58:17.0Z |
| 2025 | 8 | 2025-02-06T18:40:17.0Z | 2025-12-31T23:57:32.0Z |

Statistics: {"aisObservationCount": 1233, "observedDays": 75, "namedStormEncounters": 0, "hoursWithin200Nm": 0.0, "hoursWithin34KtWindField": 0.0, "minimumDistanceNm": null, "distanceTravelledNm": 208.9, "averageSpeedKt": 0.1, "maximumSpeedKt": 0.6}


Data quality warnings:

- MarineCadastre vessel-track geometry is authoritative AIS-derived data, but timestamps between each segment's endpoints are distance-interpolated.
- MarineCadastre AIS is land-receiver data and may not capture vessel activity beyond normal coastal receiver range.
- Exposure durations and closest approaches are estimates from track interpolation sampled at intervals of at most five minutes. Separate tracks and vertex gaps over six hours are not bridged.
- The coastal-limit parameter is not applied: this cache has no coastline-distance filter. Results use all available vessel tracks in the selected dates.
- Wind-field results use reported radii and are not measured wind at the vessel. Missing radii cannot establish an absence of wind exposure.
- No AIS tracks for this vessel were observed in 2023; this does not prove the vessel was absent.
- 106 named-storm windows have track coverage gaps exceeding six hours. Exposure during those gaps is unknown.

### JODI ANN ? 339857000

[Open saved analysis](http://127.0.0.1:8000/analysis?analysisId=analysis_18210316d85c4ee7bba79ce94463f3e9)

| Year | Track segments | First recorded UTC | Last recorded UTC |
|---|---:|---|---|
| 2023 | 45 | 2023-01-26T18:22:47.0Z | 2023-12-24T05:47:53.0Z |
| 2024 | 40 | 2024-01-07T18:10:01.0Z | 2024-12-21T12:10:27.0Z |
| 2025 | 75 | 2025-01-27T01:30:38.0Z | 2025-12-21T20:29:14.0Z |

Statistics: {"aisObservationCount": 19396, "observedDays": 237, "namedStormEncounters": 0, "hoursWithin200Nm": 0.0, "hoursWithin34KtWindField": 0.0, "minimumDistanceNm": null, "distanceTravelledNm": 3018.4, "averageSpeedKt": 0.6, "maximumSpeedKt": 12.5}


Data quality warnings:

- MarineCadastre vessel-track geometry is authoritative AIS-derived data, but timestamps between each segment's endpoints are distance-interpolated.
- MarineCadastre AIS is land-receiver data and may not capture vessel activity beyond normal coastal receiver range.
- Exposure durations and closest approaches are estimates from track interpolation sampled at intervals of at most five minutes. Separate tracks and vertex gaps over six hours are not bridged.
- The coastal-limit parameter is not applied: this cache has no coastline-distance filter. Results use all available vessel tracks in the selected dates.
- Wind-field results use reported radii and are not measured wind at the vessel. Missing radii cannot establish an absence of wind exposure.
- 104 named-storm windows have track coverage gaps exceeding six hours. Exposure during those gaps is unknown.

### 319129400 ? 319129400

[Open saved analysis](http://127.0.0.1:8000/analysis?analysisId=analysis_9c762e427ac64e9bbfd7ba6cb35403e3)

| Year | Track segments | First recorded UTC | Last recorded UTC |
|---|---:|---|---|
| 2023 | 0 | No records | No records |
| 2024 | 0 | No records | No records |
| 2025 | 27 | 2025-04-25T08:37:12.0Z | 2025-12-20T22:55:12.0Z |

Statistics: {"aisObservationCount": 2383, "observedDays": 72, "namedStormEncounters": 1, "hoursWithin200Nm": 32.4, "hoursWithin34KtWindField": 0.0, "minimumDistanceNm": 148.7, "distanceTravelledNm": 455.0, "averageSpeedKt": 0.3, "maximumSpeedKt": 13.3}

- Imelda (AL092025): closest approach 148.7 nm at 2025-09-29T17:36:27.832336+00:00; 32.4 hours within 200 nm; 0.0 hours within the reported 34 kt wind field.

Data quality warnings:

- MarineCadastre vessel-track geometry is authoritative AIS-derived data, but timestamps between each segment's endpoints are distance-interpolated.
- MarineCadastre AIS is land-receiver data and may not capture vessel activity beyond normal coastal receiver range.
- Exposure durations and closest approaches are estimates from track interpolation sampled at intervals of at most five minutes. Separate tracks and vertex gaps over six hours are not bridged.
- The coastal-limit parameter is not applied: this cache has no coastline-distance filter. Results use all available vessel tracks in the selected dates.
- Wind-field results use reported radii and are not measured wind at the vessel. Missing radii cannot establish an absence of wind exposure.
- No AIS tracks for this vessel were observed in 2023, 2024; this does not prove the vessel was absent.
- 97 named-storm windows have track coverage gaps exceeding six hours. Exposure during those gaps is unknown.


## Saved 300 nm analyses

These additional application runs use a 300 nm proximity setting. The original summary and per-vessel scores elsewhere in this report remain from the 200 nm runs.

- [SUR LA MER - 319023700](http://127.0.0.1:8000/analysis?analysisId=analysis_c5a6292146054a10819a3a6ff141b814): Arlene (2023): 262.1 nm, Ophelia (2023): 261.3 nm, Debby (2024): 211.6 nm, Milton (2024): 151.2 nm
- [M3 - 339378000](http://127.0.0.1:8000/analysis?analysisId=analysis_59fc161231f647ac80fcb2c79ff02758): Ophelia (2023): 230.8 nm, Beryl (2024): 287.0 nm, Milton (2024): 113.9 nm
- [NEXT CHAPTER - 319076300](http://127.0.0.1:8000/analysis?analysisId=analysis_14b1416f20cf42558c7fd4c79fb8faa6): Beryl (2024): 295.7 nm, Debby (2024): 214.3 nm
- [LADY ELANE - 339078000](http://127.0.0.1:8000/analysis?analysisId=analysis_e3c3762856a94fdc828534013a0c13a3): Lee (2023): 194.7 nm, Ophelia (2023): 91.3 nm, Rafael (2024): 263.9 nm
- [MY IMAGINE - 319098900](http://127.0.0.1:8000/analysis?analysisId=analysis_f9a024d834c646bf968d032f3e6bf58b): None detected
- [KOJU - 339000115](http://127.0.0.1:8000/analysis?analysisId=analysis_814fed1edfeb41d7a0b0a1e322e317cb): None detected
- [WHEELS - 367403020](http://127.0.0.1:8000/analysis?analysisId=analysis_872a7ee831504793bc79e30aa3dfda25): Debby (2024): 209.7 nm, Rafael (2024): 271.0 nm, Imelda (2025): 163.0 nm
- [FRANKLIE - 319298500](http://127.0.0.1:8000/analysis?analysisId=analysis_64e599b6ca5f4dfbbab494effa232435): None detected
- [JODI ANN - 339857000](http://127.0.0.1:8000/analysis?analysisId=analysis_ea64bd3d525a4911a783904608fe3ad5): Rafael (2024): 246.3 nm
- [319129400 - 319129400](http://127.0.0.1:8000/analysis?analysisId=analysis_a0205283983f4dce82d409b2949996c0): Imelda (2025): 148.7 nm
