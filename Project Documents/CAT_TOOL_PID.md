# The CAT Tool — Project Initiation Document

**Status:** Draft for scope and duration agreement  
**Date:** 2 October 2026  
**Initial business focus:** Underwriting intelligence for yachts of 30 metres and above **and cargo/logistics risks**  
**Business owner:** Lead Underwriter — name to be confirmed  
**Project sponsor:** To be confirmed  
**Project lead:** To be confirmed  
**PID purpose:** Agree the project scope, duration, delivery stages, ownership and success measures  
**Planned start date:** 12 October 2026  
**Planned delivery date:** 4 December 2026  
**Underwriter training and readiness:** 7–18 December 2026  
**Target business date:** Ready to support risks incepting on or after 1 January 2027  
**Planned duration:** 8 weeks (40 working days)  
**Delivery split:** 6 weeks development (30 working days), followed by 2 weeks user acceptance testing (10 working days)

## 1. Purpose and intended outcome

The CAT Tool will help underwriters assess and monitor **both specialist-yacht and cargo/logistics risks** using information that is difficult and time-consuming to assemble manually. The initial scope includes yachts of 30 metres and above and cargo risks involving the shipment, carrying vessel, voyage, ports, storage or transshipment. Other insurance classes may be considered later, but yachts and cargo have equal standing in the agreed project scope.

Today, a proposal form provides only a snapshot. For a yacht, the CAT Tool will add evidence about how and where it has operated, the conditions encountered, connected people and organisations, and available compliance or casualty information. For cargo, it will add evidence about the goods, value, carrying vessel, journey legs, ports, storage and transshipment, weather, geographic exposure, accumulation and relevant security or compliance concerns.

The service is intended to support professional judgement, not replace it. It will not automatically accept, decline, bind or price a risk. It will present:

- a concise, explainable risk summary;
- favourable evidence as well as concerns;
- the source and age of the information;
- confidence and data-coverage limitations;
- comparisons with relevant peer yachts, carrying vessels or journeys where a defensible comparison is available;
- clear gaps where reliable information could not be obtained; and
- access to all supporting data used or retrieved, subject to licence and privacy restrictions.

The summary will be the first view so that it is quick to use. Underwriters will be able to expand the evidence, view maps and timelines, and export the supporting information. This avoids both extremes: an unexplained score and an unmanageable screen containing hundreds of observations.

### The intended user journey

1. The underwriter enters the yacht, vessel/fleet or cargo-shipment details and requests a risk summary.
2. The CAT Tool identifies the yacht or carrying vessel, represents the cargo journey where applicable, gathers the available intelligence, performs the agreed checks and presents the summary with its supporting evidence.
3. The underwriter reviews the information, records their judgement and can correct the inputs or regenerate the assessment.
4. If the quote has been sent to the broker and no response has been received, the underwriter can select **Monitor**.
5. If the quote is accepted and the risk is bound, the underwriter can select **Bound Monitor**.

`Monitor` means the risk is still at quote stage. The tool watches for material changes that may affect the quotation, but every notification will state that cover is not confirmed. It stops if the quote is declined, withdrawn, expires or is closed.

`Bound Monitor` means cover has been manually confirmed. The tool can issue coverage-aware alerts only between the confirmed inception and expiry dates. It stops when cover expires or is cancelled. A case can move from `Monitor` to `Bound Monitor` without losing its earlier assessment or monitoring history.

IRIS/Websure remains the policy administration system. There will be no API, file or event integration with it. The underwriter will manually record the quote outcome and, for `Bound Monitor`, confirm the policy reference, insured dates, covered yacht, fleet or cargo interest, insured value and relevant monitoring information.

## 2. What the project will deliver

### Included in the initial yacht and cargo service

The service will bring together the following areas where suitable data and usage rights are available:

| Area | What the underwriter will see |
|---|---|
| Yacht and vessel | Identity, age, size, build, flag, class, ownership, management, refits and material information gaps for the yacht or cargo-carrying vessel. |
| Cargo and journey | Cargo type, value/limit, sensitivity, carrying vessel, journey legs, ports, storage, transshipment, dates and known gaps in the movement. |
| Movement and behaviour | Historical Automatic Identification System (AIS) routes for the yacht or carrying vessel, distance travelled, time underway, speeds, night operation, anchoring, port visits, route changes and visible AIS gaps. |
| Weather and ocean | Historical and forecast wind, storms, waves, swell, currents and other relevant conditions matched to the yacht or cargo journey by position and time. |
| Hurricanes and cyclones | Encounters, closest approach, storm intensity and seasonal exposure affecting the yacht, carrying vessel, port, storage location or planned route. |
| Navigation | Shallow-water and close-coastal operation, estimated depth, grounding indicators, anchoring patterns and proximity to potential safe harbour. Global bathymetry will be treated as underwriting context, not navigation-grade information. |
| Captain and crew | For specialist yachts, relevant qualifications, limitations, endorsements, medical validity and experience, with access restricted appropriately. Captain information will be maintained separately from the yacht. |
| Document Intake integration | The CAT Tool integrates with a separate MCI-wide Document Intake application. Brokers and yacht managing agents can send crew CVs and qualification certificates to its shared mailbox; CAT receives controlled document references and statuses, supplies the yacht-case and crew-member context, and requests approved provider hand-off without owning mailbox processing or document storage. |
| Geography and accumulation | Ports, marinas, shipyards, storage/transshipment locations, cruising and cargo routes, high-risk areas, and concentration of insured values where reliable information exists. |
| Ownership and compliance | Owners, managers, operators, previous vessel names, sanctions indicators and material ownership or flag changes for human review. A possible match will never be presented as a confirmed breach. |
| Casualties, claims and maintenance | Available casualty, incident, detention, survey, refit and permitted claims information for the yacht or carrying vessel. Casualties and insurance claims will remain clearly distinguished. No search result will be described as proof of a claims-free history. |
| Peer comparison | Factual comparison with similar yachts, carrying vessels or journeys, showing the cohort, observation period and data coverage. |

The current preferred approach is to use a licensed global and historical AIS service, with Spire Maritime identified by the underwriting requirements as the leading option for evaluation. NOAA, ECMWF, Copernicus Marine, GEBCO and appropriate official or licensed vessel, cargo/journey, port, hydrographic, certification, casualty, geopolitical and sanctions sources will also be assessed. Naming a source in this document is not a purchasing decision. Each source must pass coverage, quality, licence, retention, security and cost checks before use.

The insurer's own claims and exposure history may later be used to test whether the selected indicators are genuinely associated with loss. This is a calibration exercise, not permission to introduce an automatic underwriting or pricing model.

### Monitoring and response

For both monitoring modes, the tool may identify new or changed weather, route, location, ownership, sanctions, casualty or behavioural information. Alerts will be grouped into manageable cases, assigned to an owner and recorded through acknowledgement, investigation, referral and closure.

Only `Bound Monitor` cases can be treated as insured exposure. They may support insured-period weather or area-entry alerts, accumulation views, event response, and draft notices or broker communications. Any notice of cancellation, additional premium, sanctions decision or other material action will require an authorised person to review and approve it.

### Not included

The project will not deliver:

- integration with IRIS/Websure;
- automatic acceptance, decline, binding or sanctions clearance;
- automatic notices of cancellation or automatic additional premiums;
- an unexplained artificial-intelligence or “black box” score;
- an actuarially validated pricing model at launch;
- a guarantee that AIS or other third-party information is complete;
- navigation advice or a substitute for official charts; or
- rollout to insurance classes beyond the agreed specialist-yacht and cargo/logistics scope.

## 3. Delivery, success and dependencies

The eight-week delivery will run from **12 October to 4 December 2026**, a total of **40 working days**. Development will run for **6 weeks (30 working days), from 12 October to 20 November**. User acceptance testing (UAT) will run for **2 weeks (10 working days), from 23 November to 4 December**. Underwriter training, operational handover and readiness checks will then take place from **7 to 18 December**, leaving time before the Christmas holiday period and the target business date. The service must be ready to support risks incepting on or after **1 January 2027**.

| Phase | Main outcome | Duration | Business review point |
|---|---|---|---|
| 1. Development | Confirm the minimum yacht and cargo inputs, risk indicators, trusted sources and data rights. Build the end-to-end yacht/fleet and cargo-shipment service, including explainable summaries, maps, supporting evidence, saved decisions, and the `Monitor` / `Bound Monitor` lifecycle and alerting. | 12 October–20 November 2026; 6 weeks (30 working days) | The project team confirms that the agreed scope is ready for business testing. |
| 2. User acceptance testing | Yacht and cargo underwriters test representative cases and both monitoring modes. The team records and fixes agreed defects, retests the service and prepares it for handover. | 23 November–4 December 2026; 2 weeks (10 working days) | The business owner confirms whether the agreed acceptance criteria have been met and the service is ready for training and operational handover. |

Underwriter training and operational readiness will run from **7 to 18 December 2026**. The remaining period before 1 January provides a holiday and launch contingency buffer. Operational monitoring, feedback and longer-term learning begin after launch and are not additional development phases within the eight-week delivery timetable.

### What success will look like

The initial service will be considered successful when:

- an underwriter can enter a yacht or cargo risk and obtain an understandable risk summary without assembling the same evidence manually;
- crew documents received through the separate Document Intake application become traceable references on the yacht case without manual saving from Outlook or copying bytes into CAT, and no document is disclosed to a vendor without scan, assignment and approval evidence;
- all evidence used in the summary can be traced to its source and observation period;
- missing, stale or limited data is clearly shown rather than interpreted as a favourable result;
- the underwriter can inspect and export all supporting information permitted for display;
- `Monitor` alerts are clearly identified as quote-stage and never counted as insured exposure;
- `Bound Monitor` alerts occur only for manually confirmed covered interests and insured dates;
- a move from `Monitor` to `Bound Monitor` preserves the full history;
- alert duplication and noise are controlled well enough for underwriters to use the service; and
- pilot underwriters confirm that the service improves the speed, consistency or evidence available for decisions.

Specific targets for time saved, response time, alert volume and adoption will be agreed during development and validated through UAT using representative cases. They should not be invented before the relevant data and workflow have been tested.

### Main dependencies

Delivery depends on recruiting and onboarding a suitable software engineering resource in time to start development on **12 October 2026**. Recruitment, contractual or employment checks, equipment, system access, security induction and technical handover must therefore be completed before the development start date. Progress also depends on access to representative yacht and cargo cases, involvement from both underwriting groups, agreement on alert ownership, approval to use captain/crew, cargo and sanctions information, licences that permit the selected data to be stored and displayed, and an available separate Document Intake application with an agreed owner, Exchange mailbox, security-approved API/event contract, crew-document retention and provider hand-off method. Production cost and timing depend heavily on the volume and price of historical AIS, weather, cargo/journey and other commercial data.

## 4. Ownership, risks and agreement

### Simple governance

| Role | Responsibility |
|---|---|
| Project sponsor | Owns the business case, funding decisions and final scope. |
| Lead Underwriter / business owner | Owns the underwriting requirements, priorities, risk indicators and acceptance of the service. |
| Project lead | Coordinates delivery, decisions, dependencies, reporting and supplier activity. |
| Underwriter working group | Tests representative cases and confirms whether outputs and alerts are useful. |
| Compliance, data protection and security | Approve the handling of sanctions, ownership, captain/crew, licensed and confidential information. |
| Technology and data owners | Deliver and operate the service, data controls, monitoring, audit and recovery arrangements. |

Names, meeting frequency and decision limits will be agreed in this PID. A short monthly sponsor update and a regular working session with underwriters are expected during delivery.

### Principal risks and controls

| Risk | How it will be controlled |
|---|---|
| Data is incomplete, delayed or geographically limited | Display freshness and coverage, use more than one source where justified, and show a data gap rather than a favourable conclusion. |
| Supplier licences restrict storage or display | Complete a rights and retention review before onboarding each source; do not use data until permitted. |
| Users place too much confidence in a score | Make results explainable, show evidence and uncertainty, and keep the underwriting decision with the authorised underwriter. |
| Manual cover details become stale | Record who confirmed them and when, issue reconciliation reminders, and stop or flag monitoring when dates or status are overdue. |
| Alerts create excessive noise | Agree materiality thresholds with underwriters, group repeat events into cases and tune rules during the pilot. |
| Captain, crew or sanctions information is mishandled | Collect only what is necessary, restrict access, record the purpose and retention period, and involve compliance/data protection before use. |
| Malicious, misdirected or incorrectly assigned email attachment is opened or disclosed | Keep extraction and storage in the separate Document Intake application; quarantine and scan every attachment; validate file type; require human business-context assignment and disclosure approval; expose only authorised references to CAT; record provider receipt; and operate exception, recall and deletion procedures. |
| Costs rise because of historical data volumes | Prove value on representative yacht and cargo cases, agree retention needs and benchmark supplier costs before scaling. |
| The software engineering resource is not recruited and onboarded by 12 October 2026 | Assign clear recruitment and onboarding owners and dates; prepare equipment, access and technical handover in advance; escalate slippage immediately because it puts the 4 December delivery and 1 January business dates at risk. |

### Items to agree in this PID

The project group is asked to agree:

1. confirm **both 30m+ yachts and cargo/logistics risks** as the initial business focus;
2. confirm the user journey and the distinction between `Monitor` and `Bound Monitor`;
3. confirm that IRIS/Websure will not be integrated and that policy status will be maintained manually;
4. confirm the **12 October–4 December 2026** delivery schedule, the **7–18 December** training and readiness window, and readiness for risks incepting from **1 January 2027**;
5. nominate the project sponsor, business owner and project lead, and agree the governance rhythm; and
6. confirm the success measures, dependencies and data or supplier decisions that sit within the agreed scope.
7. confirm Document Intake as a separate MCI-wide application, nominate its product owner, and decide whether MCI will build it in Azure or assess TCG/OCTO as the delivery product.

### PID agreement record

| Decision | Name | Role | Date | Comments |
|---|---|---|---|---|
| Agree / Agree with changes / Not agreed |  | Project Sponsor |  |  |
| Agreed |  | Lead Underwriter |  |  |
| Agreed |  | Compliance / Data Protection |  |  |
| Agreed |  | Technology / Security |  |  |

