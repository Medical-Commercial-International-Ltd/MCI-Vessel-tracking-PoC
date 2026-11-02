# Yacht application: product, UX and risk review

Reviewed 30 October 2026. Audience: MCI underwriting and product owners.

## Verdict

The application has a credible foundation for an underwriter-led broker demonstration: authoritative historical storm data, explorable vessel tracks, persistent crew assignments, evidence checklists and explainable calculations. The strongest proposition is **a clearer evidence-led underwriting conversation**, with specific questions and actions for the broker.

It is not yet a complete yacht underwriting, pricing or acceptance system. Historical cyclone exposure and crew document gaps are only two parts of the risk. A polished presentation must not imply that hull condition, value, claims, machinery, liability, operational suitability or future weather have been assessed.

This review includes implemented corrections, a printable broker briefing, regression tests and browser checks. It does not establish actuarial validity, regulatory compliance or production security. Existing saved weather assessments have been preserved; rerun an assessment to use the new model.

## What was reviewed

- Login, dashboard, new analysis, vessel discovery, yacht examples, results, encounter playback, crew lookup and assignment, evidence presentation, JSON export and printing.
- Vessel identity resolution, AIS track timing and gaps, storm interpolation, proximity, wind radii, exposure duration, movement classification, aggregation, confidence and referral.
- Crew verification, certificate dates, role requirements, missing or stale evidence, roster aggregation and weather/crew combination.
- Storage, evidence hashes, access restrictions, synthetic labels and the distinction between current crew and historical voyages.

Code references: [scoring](../app/scoring.py), [real analysis](../app/real_services.py), [movement](../app/storm_response.py), [confidence](../app/confidence.py), [crew scoring](../app/crew_risk.py), [routes](../app/main.py), [briefing](../app/briefing.py), [templates](../app/templates/analysis.html).

The local installation had AIS files for **2023, 2024 and 2025**, rather than the five complete years asserted in some older documentation. The dashboard now reads available years from the cache. Available years do not establish complete tracking for an individual yacht.

## Findings and implemented corrections

| Priority | Finding | Result of this review |
|---|---|---|
| Critical | Adding a mild encounter could reduce the weather score and remove referral. A single 70-point event produced 60 overall; adding a 1-point event reduced it to 49. | New real model `TC-EXPOSURE-v0.5` floors aggregate weather risk at the worst event score. Both examples now score 70 and retain referral. Legacy calculations remain unchanged. |
| Critical | Real-data dashboard included hard-coded high-risk and confidence figures and a fictional activity chart. | Headline figures and six calendar months of activity now use actual saved assessments. Empty months show zero. |
| High | Movement checks were restricted to starts 50–70 nm from a storm; endpoint filtering at 100 nm could lose movements leaving the area. | `BROADCAST-RESPONSE-v2` examines starts throughout the selected proximity and retains endpoints beyond it. Scoring eligibility remains a separate, disclosed 50–70 nm rule. |
| High | A decreasing vessel–storm distance could be read as the vessel moving towards the storm, even when the storm was overtaking a vessel moving away. | Vessel contribution and storm closure are calculated separately and both are explained. Towards/away and contradictory overall separation trends have distinct findings. |
| High | Actual distances and stationary comparison used slightly different storm times. | All new comparisons use the exact observation timestamp. Historical fixture values change slightly; the model version identifies this change. |
| High | A lower-level real encounter matcher still applied behaviour adjustments from derived geometry, although the main analysis later replaced them. | Removed that path. Derived timing supports exposure estimates; original broadcasts support behaviour adjustments. |
| High | Any available broadcasts could mark an unrelated encounter as partly assessed. | Supported movement windows are tracked per storm; unrelated or unsupported encounters retain unknown movement status. |
| High | Conflicting simultaneous broadcasts and implausible position jumps could contaminate response evidence. | Conflicting timestamps block crossing windows; adjacent jumps implying at least 50 kt also block windows. Exact duplicate reports do not add movement evidence. |
| High | Main page presented scores before explaining what they mean and what the underwriter should do. | Added an underwriting summary covering weather, response, current crew and explicit next steps. Unknown evidence and no detected exposure are distinguished. |
| High | Printing the working page was cluttered and exposed unnecessary crew detail; existing print CSS hid generic demonstration banners. | Added an authenticated broker briefing with aggregate crew findings, dates, model versions, hashes and a print-visible test-data notice. Individual crew names, IDs and documents are excluded. |
| Medium | Movement findings and map playback were disconnected. | Each movement window has Map start / Map end controls. Times outside the map window are disabled rather than silently clamped. |
| Medium | Dashboard called saved assessments “vessels”, despite repeat runs; copy included stray question marks and misleading source-year claims. | Renamed the count, clarified repeat-assessment averages, corrected visible separators, renamed discovery “Find vessels” and made cache years dynamic. |
| Medium | Broken assessment links could fail or resemble an empty analysis page. | Missing or invalid saved IDs now produce an explanatory 404 page with a route back to new analysis. |
| Medium | Evidence hashing removed `raw` from provider-owned profile objects. | Hashing now excludes raw material in a separate copy, preserving the provider object. |

## Risk calculation: what the score actually measures

### 1. Historical exposure per storm

The basic event score sums four provisional components, then applies any supported movement adjustment and bounds the result to 0–100.

| Component | Current points |
|---|---|
| Closest centre distance | ≤25 nm: 25; ≤50: 21; ≤100: 15; ≤150: 9; ≤200: 4; beyond 200: 0 |
| Maximum storm wind during matched proximity | ≥137 kt: 25; ≥113: 22; ≥96: 19; ≥83: 15; ≥64: 11; ≥34: 7; otherwise: 2 |
| Strongest reported wind field containing vessel | 64 kt: 30; 50 kt: 23; 34 kt: 15; outside 34 kt: 5; unknown: 3 |
| Supported estimated duration inside selected proximity | ≥24 h: 20; ≥12: 16; ≥6: 12; ≥1: 7; positive but <1: 3; zero: 0 |

Durations are estimated using samples no more than five minutes apart on supported track edges. Separate tracks and vertex intervals over six hours are not connected for exposure duration. Overlapping time is counted once in total exposure statistics. A single position can establish proximity but cannot establish elapsed exposure.

The storm's maximum wind is not wind measured aboard the yacht. Reported quadrant radii provide stronger exposure context than distance alone, but do not resolve local shelter, waves, surge or berth protection. NOAA describes HURDAT2 as a **post-storm analysis**, not the forecast available to the Captain at the time. [NOAA HURDAT2 format](https://www.nhc.noaa.gov/data/hurdat/hurdat2-format-nov2019.pdf).

Remaining modelling concerns:

- Closest distance, strongest wind field and maximum intensity may occur at different moments. Their sum is a conservative feature summary, not a reconstruction of one simultaneous loss scenario.
- Thresholds create step changes: moving from just over to just under a boundary changes points abruptly. Weights need sensitivity testing and underwriting sign-off.
- Unknown wind radii receive 3 points versus 5 for known outside-field observations. Missing information must not be interpreted as better evidence. The briefing now requests further wind evidence when the event field is wholly unknown; partial missing radii are not yet quantified separately.
- The selected proximity affects detected events and exposure duration. Scores using different windows or proximity limits are not directly comparable.
- At proximity settings above 200 nm, extra events receive intensity/duration points but zero proximity points. This policy needs an explicit use case.
- Named storms are matched across their recorded lifecycle, including weaker or post-tropical phases. Unnamed systems are omitted. It is not an all-weather hazard model.
- AIS timestamps interpolated along segment geometry remain estimates. A dense track geometry is not equivalent to many original timestamped AIS messages.

### 2. Towards / away: separating two moving objects

For each supported original-broadcast window:

```text
D0 = distance(vessel at start, storm at start)
D1 = distance(vessel at end, storm at end)
F  = distance(vessel at start, storm at end)

Vessel contribution = D1 − F
Storm closure towards starting position = D0 − F
Overall separation change = D1 − D0
                          = vessel contribution − storm closure
```

Positive vessel contribution means the vessel ended further from the storm than if it had stayed at its starting position. Negative means it ended closer. This is a retrospective net geometric comparison. It does not prove continuous heading, intention, receipt of a forecast, or that staying put was navigable or safe.

The current method checks 1, 2, 3 and 6-hour windows, with the nearest endpoint within five minutes. Gaps above 30 minutes, conflicting timestamps and implausible jumps invalidate a window. Start distance must fall within the chosen proximity; endpoints can leave it. Storm observations require tropical/subtropical storm or hurricane status and at least 34 kt intensity.

Moving classifications require valid starting SOG >2 and <50 kt, valid starting COG, valid ending SOG from 0 to <50 kt, average net displacement >2 kt and contribution of at least 5 nm in either direction. A vessel may stop at its destination. Stationarity requires all reported speeds between 0 and 1 kt and every observed position within 1 nm of the start.

| Finding | Interpretation |
|---|---|
| Movement increased separation | Positive vessel contribution and increasing overall separation |
| Moved away; storm still closed in | Positive contribution, but the storm's closure outweighed it |
| Movement reduced separation | Negative vessel contribution and decreasing overall separation |
| Moved towards; storm receded faster | Negative contribution despite increasing overall separation |
| Stationary as storm approached/receded | Supported stationarity with at least 5 nm overall change |
| Separation fell; contribution below threshold | Vessel was underway but its net contribution was less than 5 nm |

One representative example per storm and pattern is retained. Selection prioritises the largest applicable score adjustment, then the strongest geometric example. These examples must not be counted as independent incidents or summed as time spent behaving in a particular way; they can overlap.

**Numeric movement policy retained:** starts 50–70 nm away are eligible. A movement-away window with ≥5 nm benefit, increasing actual separation and ≥3 nm hypothetical storm closure earns −5 event points. Stationary approach adds 5 points per actual hour, capped at +20. Other patterns are descriptive and receive no new automatic penalty. Approaching the centre already affects proximity and wind exposure; a further penalty would require underwriting justification to avoid double counting.

**Important unresolved decision:** a stationary yacht in a protected harbour may be following the safer plan. Likewise, moving further from the centre may not reduce wind, wave or surge exposure. The existing stationary penalty and avoidance credit are research heuristics, not validated measures of seamanship. Require shelter, preparedness and forecast context before using them commercially. The 50–70 nm band is a legacy research constraint, not a physical boundary of risk.

### 3. Aggregating weather risk

For new real assessments:

```text
W = highest adjusted event score
T = rounded mean of the three highest scores, or all if fewer than three
R = min(100, round(0.25 × sum of event scores))

Weather score = max(W, round(0.50 × W + 0.30 × T + 0.20 × R))
```

The new floor prevents additional mild events diluting established exposure. Recurrence can still increase the result when repeated events justify a higher composite. Scores are indicators, not percentages of expected loss. Thresholds remain Low 0–19, Moderate 20–39, Elevated 40–59, High 60–79 and Severe 80–100. High/severe scores and Low/Insufficient tracking confidence trigger weather referral.

Legacy/demo calculations retain their earlier model and formula. New real results can therefore rise relative to a saved older score even when the underlying track has not changed. Compare model versions before comparing numbers.

### 4. Evidence confidence

Confidence is separate from risk: 30% position-volume metric, 40% observed-day coverage and 30% supported tracking-time coverage. With detected encounters, 80% of that base is combined with 20% mean coverage around closest approach. Missing tracking does not reduce exposure into a known-safe state.

High requires at least 90 observed days, at least 50% observed-day coverage, sufficient numerical confidence and no uncached requested years. Medium requires at least 30 days and 10% day coverage. Fewer than 10 positions or three days gives Insufficient. Consequently, a one-day demonstration can have useful supported movement evidence while remaining insufficient to characterise long-term vessel exposure. The UI now makes these two questions easier to distinguish.

Remaining issue: confidence measures data support rather than identity certainty, wind-field completeness or predictive accuracy. A dedicated event-window quality indicator would improve short-event review. Position-volume scoring should eventually distinguish original broadcasts from geometry-derived positions.

### 5. Crew evidence

Current assignments are selected by assignment dates. Each person has four safety evidence slots at weight 1 each, medical fitness at weight 2 and role competency for Captain/Chief officer/Engineer at weight 3.

Each document takes its worst verification/date/review penalty. Missing, expired or rejected evidence scores 100; referral/query or expiry during assignment scores 75; absent/unknown verification 60; pending 50; reviewed/checked or incomplete review 40; expiry within 90 days 35; missing expiry 25; missing issue date 15. Invalid/future/reversed issue dates also require review. Successful verification does not override an expired certificate.

Duplicates use the least problematic matching document. Each person's weighted mean is floored at 60 when critical gaps exist. The roster takes the highest member score, with a minimum of 60 for a missing Captain. No current crew, unavailable evidence or stale/failed refresh leaves the combined score incomplete. These are useful safeguards and remain in place.

The score is an **evidence-gap score**, not a measure of crew ability. CV experience is not scored. Current crew are not attributed to old storms.

Crew gaps before live underwriting:

- Role requirements use a small fixed certificate-type mapping. For example, Captain currently matches `MASTER_UNLIMITED`; this does not implement the different yacht certificates, tonnage/area limits and flag recognition rules. MCA publishes yacht-specific certification requirements and limitations. [MCA yacht deck certification](https://www.gov.uk/guidance/certification-for-deck-officers-on-commercial-and-private-yachts).
- Full manning, watch arrangements, relief cover, yacht experience and route/heavy-weather experience are not established by a Captain assignment or a low document-gap score.
- Crewdentials development access is an allowlisted document workflow, not a verified global crew search or an authoritative vessel roster. Provider-supplied verification labels are retained; the contractual meaning of verification and trust fields requires confirmation.
- Duplicate replacement can remove a slot penalty even when another document is rejected. Record whether this is a legitimate renewal/replacement or a conflicting identity/verification issue.
- The standalone fictional crew lookup uses a less complete document schema than the connected provider fixtures; a displayed sample qualification may not populate all scoring slots. Use the typed connected fixtures for a rehearsed scoring demo and normalise the standalone sample schema in a later change.
- Fictional snapshots can waive freshness only in explicit development mode. They are not a substitute for fresh real evidence.

### 6. Combining crew and weather

```text
H = max(weather, crew)
L = min(weather, crew)
Combined score = min(100, H + round((100 − H) × 0.25 × L / 100))
```

Neither component is diluted. Weather 40 and crew 60 produce 64; weather 60 and crew 0 remain 60. Unknown crew does not silently become zero. Referral propagates from either component and from a combined score of at least 60.

The interaction coefficient is provisional and not calibrated against losses. Historical weather and today's crew are different time bases. The combined score is a submission review aid, not proof that the current crew caused historical exposure or that stronger credentials lower expected claims by a quantified amount.

## Product and UX assessment

| Area | Assessment and next improvement |
|---|---|
| Login | Clear internal-workspace presentation. Before external access: managed identities, MFA, lifecycle and tenant/role administration. The current local-user system is a POC. |
| Dashboard | Counts and charts are now truthful. Still an assessment-history dashboard rather than a deduplicated live portfolio or workflow queue. Next: latest assessment per yacht, outstanding evidence, owner and review state. |
| Find vessels | Clearer navigation name and useful storm/port filtering. Keep source-year and yacht-candidate limitations visible. Do not call AIS pleasure craft a verified high-value yacht. Separate research shortlists from the main commercial demo flow. |
| Analysis form | Familiar identifiers and dates. Next: collapse rerun controls after a result, explain long-running jobs using actual task state, and consistently render malformed-input errors in plain language. Current progress messages are timed, not real backend progress. |
| Results | Summary now leads with evidence and actions. The full technical page is still long, particularly on mobile. Use it for investigation and the briefing for presentation. Next: overview, movement, crew and evidence tabs with persistent context. |
| Map | Strong demonstration feature: vessel, storm, wind radii and playback. Added links from response findings to exact times. Keep interpolation labels visible. Default gap interpolation can visually imply certainty; consider defaulting it off in broker mode. |
| Crew | Document presence, verification and dates are usefully separate. Preserve this distinction. Add a reviewed yacht-specific requirements profile and roster-completeness workflow before claiming operational suitability. |
| Briefing | New aggregate evidence summary, actions, provenance and print/save-PDF. It excludes individual crew detail and retains test labels. This is a discussion document, not a quotation or binder. |
| Accessibility | Browser checks at 1440px and 390px found no page-level horizontal overflow in inspected views. Tables remain scrollable. Status includes text as well as colour. This is not a complete keyboard, screen-reader or WCAG audit. |

## Real-data demonstration checked

Two real original-broadcast cases were recalculated in an isolated review data directory, leaving the working portfolio intact. Both use 3 October 2023, Philippe, and a 70 nm selected proximity.

| Vessel | New weather score | Movement evidence |
|---|---:|---|
| A1A, MMSI 368281860 | 54/100 | Away window: 61.18 → 65.37 nm, stationary comparison 52.82 nm, vessel contribution +12.55 nm. A later/overlapping longer window shows contribution −10.08 nm. Other windows show the storm closing despite positive vessel contribution. |
| AZULITA, MMSI 368001090 | 29/100 | Away window: 65.01 → 77.62 nm, vessel contribution +23.45 nm. Ending outside the 70 nm search radius does not discard the response. |

Both weather assessments correctly retain Insufficient long-term tracking confidence for this one-day period. The review attached a clearly fictional, current Captain fixture to A1A solely to exercise combined scoring, privacy and printing. It does not establish A1A's real crew. AZULITA was checked with no assigned crew, producing an incomplete combined assessment.

The original research used minute-rounded storm times. Updated numerical examples therefore differ slightly and must be identified as v2, rather than advertised as exact reproductions of the old method.

## What remains before live use

| Priority | Required work | Acceptance criterion |
|---|---|---|
| P0 | Underwriting model governance | Named owner approves intended use, weights, floors, thresholds, referral rules and treatment of stationary shelter; loss/sample validation and sensitivity results recorded. No premium or acceptance automation until justified. |
| P0 | Real crew and vessel requirements | Actual roster and current provider evidence; appropriate certificate limits/flag recognition; full manning and experience review recorded. Test records cannot support a live decision. |
| P0 | Broader yacht submission | Vessel value/valuation basis, survey/condition, maintenance, claims, use/charter, cruising/navigation limits and storm preparedness captured and reviewed. |
| P1 | Durable decision record | Reviewer, decision, reasons, conditions, evidence requests, deadlines and immutable assessment/evidence snapshot at decision time. Current view-time crew refresh overwrites the enriched assessment rather than preserving every historical decision basis. |
| P1 | Forecast and shelter context | Time-stamped forecast/advisory known at the time, wind/wave/surge exposure, berth/anchorage protection and feasible routes. Do not turn geometric response labels into judgments of seamanship without this. |
| P1 | Data completeness and quality | Coverage appropriate to intended cruising area, original-broadcast availability, missing-radii metrics, identity confirmation and anomaly review. U.S. coastal data is not global yacht coverage. |
| P1 | Hosting and information security | Production configuration without development defaults; managed access, tenant boundaries, audit, backups, retention and consent/contract controls for crew evidence. Current role checks and CSRF are helpful but not a production assurance exercise. |
| P1 | Reproducibility | Pin source revisions/content hashes, immutable crew evidence and model configuration. Some current source retrieval dates are filesystem modification times; hashes do not yet constitute a complete archived source pack. |
| P2 | Commercial workflow and UX | Broker/submission context, requested terms, assigned underwriter, notes, tasks and conditions; concise portfolio queue; consistent errors; full accessibility and user validation. |

## Recommended broker demonstration

1. Open Find vessels and select a rehearsed yacht; state the historical period and the scope of the data.
2. Start with the underwriting summary: observed exposure, response, current crew and what remains to be confirmed.
3. Show one movement window, use Map start / Map end, and explain the difference between vessel contribution and overall distance. A1A is useful because it illustrates both helpful movement and later approach.
4. Review the crew checklist. Explain that present, verified and in-date are three different questions. Label all fictional records explicitly.
5. Open Broker briefing / print. Use the action list to ask focused questions about experience, shelter, storm planning and the yacht submission.
6. Close on the underwriting service: transparent evidence, specific questions and a documented path to terms. Do not promise a lower premium or acceptance based on this uncalibrated indicator.

## Validation and limitations

- Baseline: 111 Python tests passed before changes.
- Updated suite: 129 Python tests passed, including real movement fixtures, direction/closure separation, proximity exit, stopping at destination, invalid speeds, conflicting reports, stationary cases, aggregation monotonicity, crew integration and briefing privacy/access.
- JavaScript: 13 tests passed for encounter playback, evidence-window navigation, missing data, tile failure and satellite buffering. Corrected a pre-existing missing `getComputedStyle` browser mock in the map test harness.
- Headless Chromium: desktop/mobile dashboard, both real vessel assessments, crew page, vessel discovery, playback, briefing and print/PDF outputs checked. Final browser run and artifacts are recorded in `.test-tmp/ux-risk-review/`.
- No live Crewdentials write/refresh, external publication, production load test or formal penetration test was performed. GOES buffering tests ran; a new live satellite archive fetch was not exercised.
- One existing FastAPI/Starlette test-client deprecation warning remains. It did not fail tests.

This review supports a controlled, honestly labelled demonstration. The outstanding underwriting and operational requirements above remain necessary before treating the application as a complete live yacht risk decision system.

## Underwriting case research and demonstration appetite

Added 30 October 2026 following the request for contrasting offer and decline cases.
The user asked for logically derived rules rather than supplying an existing appetite.

The new development-only **Demo cases** page links to the [NTSB Bounty investigation](https://www.ntsb.gov/investigations/Pages/DCA13LM003.aspx)
and [El Faro investigation](https://www.ntsb.gov/investigations/pages/dca16mm001.aspx).
Bounty is the closest documented match to a decision to sail into a forecast hurricane path;
El Faro supplies a second navigation and management reference and now has an imported
2015 voyage for analysis and replay. Bounty remains a reference because its MMSI was
not found in the NOAA October 2012 zone 18 and 19 archives checked. Neither case
is presented as an actual insurer's declinature. Retrospective findings should not be
represented as facts the system could necessarily have known before the casualty.

Fresh `TC-EXPOSURE-v0.5` assessments were saved for these local cases:

| Vessel / MMSI | Period / proximity | Weather | Confidence | Demonstration purpose |
| --- | --- | --- | --- | --- |
| EL FARO / 368208000 | 29 September–1 October 2015 / 200 nm | 93 | Low | Recorded approach towards Joaquin, with NTSB offshore VDR positions supplementing NOAA coastal AIS. Historical-loss recommendation uses the completed investigation separately from the exposure score. |
| JODI ANN / 339857000 | 2023–2025 / 200 nm | 0 | Medium | Favourable discussion, subject to coverage and crew review; no detected encounters is not proof of no exposure. |
| LADY ELANE / 339078000 | 2023–2025 / 200 nm | 57 | Medium | Elevated exposure below the high referral band; current crew and other submission checks remain relevant. |
| AZULITA / 368001090 | 3 October 2023 / 70 nm | 29 | Insufficient | Original broadcasts show increased separation; insufficient long-term evidence for an offer. |
| A1A / 368281860 | 3 October 2023 / 70 nm | 54 | Insufficient | Mixed movement, including a -10.08 nm vessel contribution to separation; refer for passage and shelter context. |
| SERENITY (AIS name) / 367733210 | 23 September 2023 / 70 nm | 91 | Insufficient | Stationary harbour exposure; requires protection review, not an allegation of navigating into danger. |
| LEGACY (AIS name) / 319920000 | 23 September 2023 / 70 nm | 83 | Insufficient | Stationary anchorage exposure; the same shelter limitation applies. |

The page selects matching period, proximity and model version, rather than silently
substituting an unrelated recent assessment. Local research evidence and assessment IDs
are saved in `data/underwriting-case-research.json`. This reviews the local cache and
previously screened candidates, not an exhaustive global archive.

`DEMO-APPETITE-v2` is a separate recommendation layer. It does not change calculated
weather, crew or combined scores. Its ordered rules are:

For the explicitly archived El Faro loss case, do not offer for an equivalent
submission with the investigation's unsafe navigation conditions unresolved.
This is retrospective, not a pre-loss model prediction, and is applied only when
the selected assessment period includes the casualty date. Other cases use:

1. Do not offer while an assigned member's role-competency or medical-fitness document
   has a verified expiry or provider rejection. Obtain an acceptable replacement and
   review suitability. Missing documents and unverified dates require referral instead.
2. Do not offer for exposure of at least 80 using the current model with medium/high
   tracking confidence, pending consideration of a materially revised cruising and
   storm plan. Stationary-approach cases go to shelter review instead of this rule.
3. Refer for weak tracking, uncertain identity, missing/stale/pending crew evidence,
   approach or stationary windows, high exposure or a combined score of at least 60.
4. Otherwise recommend offering subject to survey, claims, value, cruising, storm-plan,
   full-manning, experience, certificate-limit and flag checks, plus any renewal needs.

Confirmed blockers take precedence over incomplete evidence; they are not erased by
a low score. The 60/80 boundaries reuse the existing high/severe bands as proposed
appetite choices, not actuarial validation. Current fictional crew affects only the
demonstration scenario and does not identify the historical crew. Investigation findings
are explained separately; the app does not automatically extract them or infer misconduct.

Five stable fictional worked examples produce combined scores 29 and 36 (conditional
offers), 86 and 63 (do not offer), and 54 (refer). They assume stated exposure inputs,
adequate tracking and confirmed identity; they are not newly discovered AIS events.
Ordinary searches still randomise fictional crew. Recommendations are calculated for
development views and print briefings, not persisted as binding decisions or added to
the saved risk-model JSON. Production views do not enable this policy.

Validation: all 151 Python tests passed, including 16 new policy/case-library tests.
Browser checks confirmed both viewport sizes, no horizontal overflow at 390 pixels,
one top-of-page demo notice, expected scenario outcomes, an A1A referral and policy
content in the PDF briefing. No browser JavaScript errors were observed. The existing
test-client deprecation warning remains.

### El Faro MMSI integration and import verification

The ordinary MMSI form now recognises curated storm cases and loads their dates
and proximity, while allowing date overrides. El Faro, SERENITY and LEGACY were
added to Demo yachts, bringing the table to 15 vessels. Entering a different MMSI
restores the original dates if the case defaults were not manually changed.

Downloaded NOAA archives for 29/30 September and 1 October 2015 contain 1,232,
529 and zero El Faro records respectively. NOAA reception stops at 15:37:43 UTC
on 30 September. The importer keeps 1,635 NOAA observations before the first VDR
sample, then uses 313 NTSB VDR positions through 11:35:45 UTC on 1 October.
It deliberately does not blend overlapping receivers with the VDR track.

The [NTSB electronic-data docket](https://data.ntsb.gov/Docket?ProjectID=92109)
supplies attachment 12 (combined-track KMZ) and attachment 2 (WAM UTC checks).
The former's unzoned timestamp field uses a 12-hour clock; explicit point labels
are 24-hour EDT. UTC conversion is validated against every one of the 32 WAM
records before importing VDR points. The normalized records retain source kind;
no SOG or COG values are manufactured. Download hashes and source URLs are kept
and included in the analysis source references and calculation input hash.

The actual calculation finds one Joaquin encounter: 18.0 nm minimum separation,
12.9 hours within 200 nm, 7.2 hours within reported tropical-storm wind radii,
and a strongest reported wind field of 64 kt. Its score is 25 proximity + 22
storm intensity + 30 wind field + 16 duration = 93. Movement contributes zero
additional points. The six-hour approach window runs 22:45 UTC on 30 September
to 04:45 UTC on 1 October: separation 198.47 → 91.85 nm; fixed-position end
distance 196.42 nm; vessel contribution -104.57 nm. These are observed-history
calculations against post-analysis HURDAT2, not forecasts known to the Captain.

Four new tests exercise the source time conversion, VDR movement guards,
real-data assessment/map without an annual GeoPackage, historical finding date
scope, MMSI form, fresh portfolio rerun, crew and JSON export. The Python suite
now has 155 passing tests after updating the portfolio's expected size; all 13
JavaScript tests pass. Browser checks verify MMSI-only entry, date autofill and
reset, 93/100 result, three fictional crew, decline recommendation, map-window
navigation, mobile layout, table rerun and printable source-backed briefing.
