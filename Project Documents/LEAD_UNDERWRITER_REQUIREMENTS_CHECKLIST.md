# Marine and Cargo Risk Intelligence — Underwriter Discussion List

**For:** Lead underwriter  
**Purpose:** Agree which capabilities would help the underwriting team most.  
**Status:** Discussion draft. For each item, note **Launch**, **Later** or **Not needed** during the meeting. The detailed [high level design](MARINE_CARGO_HLD.md) remains a separate technical document.

**Current context:** The first use is an initial risk profile for a proposed marine, cargo or specialist yacht risk. IRIS PAS remains the policy system and has no available API for this project. Post-bind monitoring will require a simple way to confirm what is actually covered. A fleet may be assessed or monitored where relevant, but the requirements below also work for an individual vessel or shipment.

## 1. Pre-bind: assess the proposed risk

### Information and evidence

- **Capture the essentials:** Enter the class, vessel or shipment, proposed dates, value, route/territory and broker reference once.
- **Identify the vessel and connected parties:** Resolve IMO, MMSI, name and call sign; show owner, manager and operator relationships with dates and sources. Handle yachts that have no IMO number.
- **Review vessel quality:** Show age, flag, class, inspection/PSC history and material gaps in the available data.
- **Check loss history:** Search the vessel against available international casualty and incident records, and separately against any accessible insurance claims history. Show the matched event, date, source and uncertainty; flag significant or possible matches for review. A blank search result must not be presented as proof of a claims-free vessel.
- **Review movement and route:** Show historical AIS tracks, common routes, last known position and significant coverage gaps.
- **Assess specialist yachts:** Combine location and itinerary with historical/forecast weather and relevant crew complement, qualifications and experience.
- **Receive crew documents:** Integrate with the separate MCI Document Intake application so a broker or yacht managing agent can email CVs and qualification certificates to a shared address and each clean attachment appears as a controlled reference on the correct case and crew member after human confirmation.
- **Assess cargo:** Show cargo type/value, carrying vessel, ports, voyage legs, storage and transshipment where known.
- **Assess war and security exposure:** Highlight proposed routes through listed or otherwise high-risk areas and explain the source and date of the area definition.
- **Screen possible compliance issues:** Surface possible sanctions connections, ownership/flag changes, AIS outages and ship-to-ship activity for human review.
- **Handle multiple vessels if needed:** Accept a simple vessel schedule and show per-vessel exceptions and a combined risk view for a proposed fleet.

### Decision support

- **Produce an explainable risk profile:** Show the main concerns, favourable evidence, confidence, missing data and reasons for any referral, with links back to source records.
- **Show existing concentration:** Where reliable MCI exposure data exists, indicate whether the new risk increases concentration around a vessel, owner, port or area.
- **Prepare a referral summary:** Export a concise evidence pack for compliance, Asta or another reviewer.
- **Record the judgement:** Save the underwriter's decision and reasons alongside the data and rule version used.

**Possible refinements for later:** Compare alternative routes or dates; accept a pasted extract of terms, conditions or exclusions from IRIS and suggest possible conflicts. **Pasting wording is optional** and should not be required to produce the initial risk profile. Any suggested interpretation would need underwriter confirmation.

## 2. Post-bind: monitor written business

### Know what is covered

- **Confirm active cover:** Record the IRIS policy reference, inception/expiry dates, covered vessel or shipment, insured value and responsible underwriter. Use a checked file import if IRIS can provide one.
- **Maintain changes:** Record additions, removals, endorsements and cancellations with effective dates; for a fleet, update the covered vessel list.
- **Flag stale cover information:** Show when manually confirmed cover has not been reconciled with IRIS recently.

### Detect and respond

- **Monitor position and data freshness:** Track covered vessels while making missing or old AIS data obvious.
- **Alert on area entry:** Warn when a covered risk enters or approaches an agreed war, piracy or territorial area during the cover period.
- **Alert on significant weather:** Warn when a covered yacht, vessel or cargo movement may be affected by a forecast or warning.
- **Repeat compliance screening:** Recheck active vessels and connected parties when sanctions lists or ownership relationships change.
- **Watch new casualty reports:** Alert the responsible underwriter when a credible new casualty or incident report matches a vessel confirmed on cover, with the source and match confidence shown.
- **Review unusual behaviour:** Raise selected AIS gaps, unexpected route changes or reported ship-to-ship transfers for investigation.
- **Watch exposure accumulation:** Show concurrent covered vessel count and insured value in a port, marina, weather footprint or conflict area.
- **Respond to major events:** Produce a quick list and map of potentially affected policies and values, with location uncertainty shown.
- **Manage alerts as cases:** Route by severity and owner; record acknowledgement, investigation, referral, closure and out-of-hours escalation.
- **Support controlled action:** Prepare compliance referrals and draft NOC, war additional premium or broker messages for authorised review.
- **Report exposure:** Export current and historical portfolio views for underwriting, exposure management and capacity reporting.

## 3. Additional value from data mining and AI

These are opportunities to test, not proposed automatic underwriting decisions. They need suitable licensed data, evidence links and a trial against real cases.

- **Read submissions faster:** Extract vessel, cargo, crew and value details from broker documents into draft fields. *Benefit: less rekeying and quicker first response.*
- **Find connected risks:** Use relationship analysis to spot shared owners or managers across apparently separate vessels or insureds. *Benefit: better risk selection and accumulation awareness.*
- **Spot unusual patterns:** Compare a vessel's current route, AIS gaps or transfers with its own history and relevant peers. *Benefit: earlier investigation of exceptions.*
- **Find emerging hotspots:** Detect clusters of insured vessels or cargo movements outside existing fixed zones. *Benefit: improved peak exposure awareness.*
- **Prioritise alerts:** Rank cases by likely exposure, proximity, policy relevance and confidence. *Benefit: less alert noise and faster attention to material events.*
- **Run what-if scenarios:** Test a changed storm track, conflict area, route or port closure against the portfolio. *Benefit: faster event response and planning.*
- **Learn from outcomes:** If claims, premium and exposure histories can be linked reliably, test which factors actually correlate with loss. *Benefit: better-informed selection and pricing, subject to actuarial validation.*
- **Draft evidence-backed briefings:** Summarise a risk, referral or incident with citations to the underlying records and timestamps. *Benefit: faster communication without losing traceability.*
- **Compare wording when useful:** Highlight unusual clauses or potential conflicts in an underwriter-supplied extract. *Benefit: quicker review of lengthy wording; this remains an optional aid.*

## 4. Points to settle with the lead underwriter

1. Which **five capabilities** would make the first version worth using?
2. Which classes and territories should be covered first: yachts, cargo, hull/war or another area?
3. What minimum information can an underwriter realistically provide for an initial profile?
4. What information must be captured after bind for an alert to be reliable without an IRIS API?
5. Which post-bind events need immediate attention, and who owns the response out of hours?
6. Which sources are trusted today, and what data is most often missing or slow to obtain?
7. What would count as success: time saved, fewer missed referrals, better selection, clearer accumulation or something else?
8. When you say “international claims list”, is the intended source IUMI's major-claims data, IMO's casualty/incident records, another named list, or more than one? Is the decision a vessel casualty check, a check of actual insurance claims, or both?
9. Which central team will own the separate Document Intake application and its exception queue, what CAT intake reference should senders quote, and who may approve sending personal documents to Crewdentials or another provider?

**Meeting notes / additional requirements:**

________________________________________________________________________________

________________________________________________________________________________

**Lead underwriter:** ____________________  **Date:** __________  **Follow-up owner:** ____________________
