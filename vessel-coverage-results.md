# NOAA vessel coverage and application results

Requested period: 2011-01-01 to 2025-12-31. Coastal setting: 75 nm (not applied by real-data provider); storm proximity: 200 nm. All ten MMSIs submitted sequentially to the running application and result pages returned HTTP 200.

Only AISVesselTracks2025.gpkg is cached. No local AIS data for 2011?2024. First/last dates below bound sparse tracks; they do not indicate continuous coverage. Vessel names/IMO pairs are supplied by the user and are not verified by the local registry. Position counts are AIS-derived track vertices with estimated timestamps, not original broadcast-message counts.

| Vessel | MMSI | First record (2025) | Last record (2025) | Segments | Observed days | Positions | Encounters | Score/band |
|---|---|---|---|---:|---:|---:|---:|---|
| SUR LA MER | 319023700 | 01-21 | 12-19 | 190 | 174 | 11295 | 0 | 0 / LOW |
| M3 | 339378000 | 01-06 | 12-25 | 114 | 98 | 5988 | 0 | 0 / LOW |
| NEXT CHAPTER | 319076300 | 05-07 | 10-13 | 20 | 18 | 2281 | 0 | 0 / LOW |
| LADY ELANE | 339078000 | 01-13 | 12-26 | 172 | 126 | 3247 | 0 | 0 / LOW |
| MY IMAGINE | 319098900 | 01-13 | 11-30 | 59 | 70 | 3361 | 0 | 0 / LOW |
| KOJU | 339000115 | 02-17 | 12-29 | 82 | 71 | 3096 | 0 | 0 / LOW |
| WHEELS | 367403020 | 01-01 | 12-23 | 46 | 122 | 5039 | 1 | 14 / LOW |
| FRANKLIE | 319298500 | 02-06 | 12-31 | 8 | 64 | 1184 | 0 | 0 / LOW |
| JODI ANN | 339857000 | 01-27 | 12-21 | 75 | 108 | 9414 | 0 | 0 / LOW |
| 319129400 | 319129400 | 04-25 | 12-20 | 27 | 72 | 2383 | 1 | 35 / MODERATE |

All results have LOW confidence and underwriter referral enabled. No detected encounter is not proof of no exposure: missing years, offshore activity and track gaps remain unknown.

## Saved application results

- [SUR LA MER ? 319023700](http://127.0.0.1:8000/analysis?analysisId=analysis_fe6ababb40db42c8b252129d3d37c4e6)
- [M3 ? 339378000](http://127.0.0.1:8000/analysis?analysisId=analysis_9a606d53cdfd4df8a0938d2dc98f8da9)
- [NEXT CHAPTER ? 319076300](http://127.0.0.1:8000/analysis?analysisId=analysis_2160e395fea049d2997c6b72dc3ac8d6)
- [LADY ELANE ? 339078000](http://127.0.0.1:8000/analysis?analysisId=analysis_931b5a2fae194c7ba55ba8baedbdfe42)
- [MY IMAGINE ? 319098900](http://127.0.0.1:8000/analysis?analysisId=analysis_df1be8feac5e46f08021cb1fbb6b4f59)
- [KOJU ? 339000115](http://127.0.0.1:8000/analysis?analysisId=analysis_fdb615b51c344000817a7204e5c4080f)
- [WHEELS ? 367403020](http://127.0.0.1:8000/analysis?analysisId=analysis_c9e1090ebe4440e496000ee414ce275f)
  - Imelda: closest approach 163.0 nm; timestamp 2025-09-29T12:46:49.421674Z; exposure {"durationWithin200NmHours": 0.0, "durationWithin34KtWindFieldHours": 0.0, "strongestWindField": "OUTSIDE 34KT", "maximumStormWindKt": 53}.
- [FRANKLIE ? 319298500](http://127.0.0.1:8000/analysis?analysisId=analysis_de25688d5f0746a691efb39d0aea66ef)
- [JODI ANN ? 339857000](http://127.0.0.1:8000/analysis?analysisId=analysis_7c0657f2da2f41bdbc503698b78f5ede)
- [319129400 ? 319129400](http://127.0.0.1:8000/analysis?analysisId=analysis_2c8928c338eb4e87b71488bbbe25c784)
  - Imelda: closest approach 148.7 nm; timestamp 2025-09-29T17:36:27.832336Z; exposure {"durationWithin200NmHours": 32.4, "durationWithin34KtWindFieldHours": 0.0, "strongestWindField": "OUTSIDE 34KT", "maximumStormWindKt": 60}.

## Source coverage

NOAA publishes archives spanning these years, but individual-vessel presence in older remote files has not been verified. This run used only the local 2025 AIS dataset. NOAA describes these as land-based receiver data, generally unavailable in foreign waters or more than 40?50 miles offshore.

- [NOAA AIS FAQ](https://coast.noaa.gov/data/marinecadastre/ais/faq.pdf)
- [NOAA year-by-year point data summary](https://coast.noaa.gov/data/marinecadastre/ais/point-data-summary.pdf)
