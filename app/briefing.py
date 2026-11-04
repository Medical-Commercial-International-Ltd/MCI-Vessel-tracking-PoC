"""Plain-language assessment summary; no names or personal crew evidence."""
from app.storm_response import RESPONSE_LABELS


def build_briefing(analysis, encounters, *, demo_appetite=False):
    combined = analysis.underwriting
    crew = combined.crew if combined else None
    actions = []
    if analysis.risk.confidence in {"LOW", "INSUFFICIENT"}:
        actions.append("Obtain additional tracking evidence before treating the observed exposure as representative.")
    if not analysis.is_synthetic and analysis.risk.model_version != "TC-EXPOSURE-v0.5":
        actions.append("Rerun this historical assessment to apply the current movement method.")
    if analysis.data_quality.identity_confidence != "HIGH":
        actions.append("Confirm the vessel name, IMO and MMSI against the submission documents.")
    if encounters:
        worst = max(encounters, key=lambda event: event.risk.event_score)
        weather = (f"{len(encounters)} storm encounter{'s' if len(encounters) != 1 else ''} detected. The highest event score is "
                   f"{worst.risk.event_score}/100 for {worst.storm.name}, with a closest approach "
                   f"of {worst.closest_approach.distance_nm:g} nautical miles.")
        if any(event.exposure.strongest_wind_field == 'UNKNOWN' for event in encounters):
            actions.append("Obtain additional wind evidence: missing storm wind radii prevent a complete exposure assessment.")
    else:
        weather = "No storm encounters detected in the available tracks. This does not establish absence of exposure."
    if analysis.risk.underwriter_referral:
        actions.append("Review the weather score and evidence confidence; the exposure component triggers referral.")
    kinds = {window.kind for window in analysis.storm_response.windows}
    if kinds & {'MOVED_TOWARDS', 'MOVED_TOWARDS_RECEDING', 'CONTINUED_APPROACH'}:
        actions.append("Discuss the approach windows with the Captain: establish the route, shelter, forecast information and reasons for the movement.")
    if 'STATIONARY_APPROACH' in kinds:
        actions.append("Confirm the berth or anchorage protection and storm plan for stationary approach windows.")
    if 'MOVED_AWAY_CLOSING' in kinds:
        actions.append("Review whether moving away provided enough clearance: the storm still closed in during an observed window.")
    if not crew or not crew.members:
        crew_summary = "No current crew roster has been assessed. The combined assessment is incomplete."
        actions.append("Confirm the current roster, including the Captain, and obtain current certificate evidence.")
    else:
        unknown = sum(member.score is None for member in crew.members)
        crew_summary = f"{len(crew.members)} current crew assignment{'s' if len(crew.members) != 1 else ''} assessed. "
        if unknown:
            crew_summary += f"{unknown} profiles need refreshed or available evidence; the combined assessment is incomplete."
            actions.append("Refresh unavailable or stale crew evidence before relying on the combined assessment.")
        else:
            crew_summary += f"The roster evidence-gap score is {crew.score}/100; higher means more evidence gaps."
        if not any(member.role == "Captain" for member in crew.members):
            actions.append("Confirm a current Captain assignment.")
        if crew.underwriter_referral:
            actions.append("Resolve the crew evidence findings and record the underwriter's review.")
        if any(member.experience_supplied is not True for member in crew.members):
            actions.append("Obtain and review relevant yacht, route and heavy-weather experience; CV experience is not scored.")
    actions.append("Confirm full manning, certificate limits and flag recognition against this yacht and its intended use.")
    actions.append("Review vessel value, survey and condition, claims, cruising area and the storm preparedness plan before offering terms.")
    movement = [dict(label=RESPONSE_LABELS.get(w.kind, w.kind), window=w,
                     separation_change=round(w.end_distance_nm - w.start_distance_nm, 2),
                     storm_closure=round(w.start_distance_nm - w.fixed_distance_nm, 2))
                for w in analysis.storm_response.windows]
    if movement:
        lead = max(movement, key=lambda item: abs(item['window'].improvement_nm))
        window = lead['window']
        movement_summary = (f"{lead['label']}: {window.start_distance_nm:g} → {window.end_distance_nm:g} nm. "
            f"Vessel movement contributed {window.improvement_nm:+g} nm compared with staying put.")
        away = [item['window'] for item in movement if item['window'].kind in {'MOVED_AWAY', 'MOVED_AWAY_CLOSING'}]
        towards = [item['window'] for item in movement if item['window'].kind in {'MOVED_TOWARDS', 'MOVED_TOWARDS_RECEDING'}]
        if away and towards:
            approach = min(towards, key=lambda w: w.improvement_nm)
            retreat = max(away, key=lambda w: w.improvement_nm)
            movement_summary = (f"Mixed response: an away window contributed {retreat.improvement_nm:+g} nm of separation; "
                f"an approach window contributed {approach.improvement_nm:+g} nm "
                f"({approach.start_distance_nm:g} → {approach.end_distance_nm:g} nm actual separation). Both patterns require context.")
    else:
        movement_summary = "Movement response is unknown or no qualifying pattern was found. No avoidance is established."
    from app.demo_appetite import assess_appetite
    appetite = assess_appetite(analysis) if demo_appetite else None
    headline_reasons = []
    if appetite:
        # Surface independent reasons before repeating the same certificate gap by role.
        for prefix in ('Historical loss', 'Severe historical exposure', 'Tracking evidence'):
            headline_reasons.extend(reason for reason in appetite['reasons'] if reason.startswith(prefix))
        if crew and any(member.experience_supplied is not True for member in crew.members):
            headline_reasons.append('Obtain current CVs and review relevant yacht and heavy-weather experience.')
        headline_reasons = list(dict.fromkeys(headline_reasons + appetite['reasons']))[:3]
    return dict(weather=weather, crew=crew_summary, actions=actions, movement=movement,
                appetite=appetite, headline_reasons=headline_reasons,
                is_test_data=analysis.is_synthetic or bool(combined and combined.is_test_data),
                decision="Evidence incomplete" if not combined or combined.score is None else
                         "Underwriter review required" if combined.underwriter_referral else "Standard underwriting review",
                movement_summary=movement_summary)
