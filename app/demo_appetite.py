"""Demonstration appetite rules, separate from exposure and evidence scores.

These are proposed underwriting preferences, not calibrated loss thresholds or
statutory manning requirements. Only development views opt into this policy.
"""
from types import SimpleNamespace
import random

from app.crew_risk import assess_crew, combine_risk
from app.demo_crew import generate_roster, RosterProvider
from app.scoring import aggregate_risk

VERSION = 'DEMO-APPETITE-v2'


def assess_appetite(analysis):
    combined = analysis.underwriting
    crew = combined.crew if combined else None
    blockers, referrals = [], []
    historical = getattr(analysis, 'historical_case', None)
    if historical and historical.retrospective:
        blockers.append('Historical loss investigation establishes unsafe storm navigation. Do not offer for an equivalent submission with those conditions unresolved. This conclusion uses post-event investigation findings, not a pre-loss prediction.')
    conditions = ['Confirm survey, claims, value, cruising area and storm plan.',
                  'Confirm full manning, relevant experience, certificate limits and flag recognition.']
    kinds = {w.kind for w in analysis.storm_response.windows}
    towards = bool(kinds & {'MOVED_TOWARDS', 'MOVED_TOWARDS_RECEDING', 'CONTINUED_APPROACH'})
    stationary = 'STATIONARY_APPROACH' in kinds
    supported = analysis.risk.confidence in {'HIGH', 'MEDIUM'}
    from app.fictional_yachts import is_fictional_case
    fictional = is_fictional_case(analysis)
    current_model = analysis.risk.model_version == 'TC-EXPOSURE-v0.5' or fictional
    if not current_model:
        referrals.append('Rerun the exposure assessment using the current model.')
    if not supported:
        referrals.append('Tracking evidence is insufficient for an offer recommendation.')
    if analysis.data_quality.identity_confidence != 'HIGH':
        referrals.append('Confirm vessel identity against submission documents.')
    if not crew or not crew.members or crew.score is None:
        referrals.append('Obtain a complete, current crew evidence assessment.')
    if crew and crew.members:
        if not any(m.role == 'Captain' for m in crew.members):
            referrals.append('Confirm the Captain assignment.')
        for member in crew.members:
            if member.score is None:
                continue  # Stale or unavailable evidence cannot establish a blocker.
            for check in member.checks:
                critical = check.label in {'Role competency', 'Medical fitness'}
                rejected = check.verification.label == 'Rejected'
                verified_expiry = check.verification.status == 'pass' and check.validity.label == 'Expired'
                if critical and (rejected or verified_expiry):
                    blockers.append(f'{member.role}: {check.label.lower()} evidence is '
                                    f'{"rejected" if rejected else "expired"}. Provide an acceptable replacement before offering terms.')
                elif check.document.status != 'pass' or check.verification.status != 'pass' or check.validity.status in {'fail', 'unknown'} or check.validity.label in {'Expiry unknown', 'Issue unknown', 'Expires on duty'}:
                    referrals.append(f'{member.role}: resolve {check.label.lower()} evidence before offering terms.')
                elif check.validity.label == 'Expiring soon':
                    conditions.append(f'{member.role}: confirm renewal of {check.label.lower()} before expiry.')
            if not member.checks:
                referrals.append(f'{member.role}: detailed certificate checks are unavailable.')
            if member.experience_supplied is not True:
                referrals.append(f'{member.role}: obtain relevant experience evidence.')
        if crew.underwriter_referral:
            referrals.append('Resolve the crew assessment referral.')
    if analysis.risk.score >= 80 and supported and current_model and not stationary:
        blockers.append('Severe historical exposure (80/100 or above) is outside this demonstration appetite. Review a materially revised cruising and storm plan before reconsidering.')
    elif analysis.risk.score >= 60:
        referrals.append('High or severe weather exposure requires individual underwriting review.')
    if stationary:
        referrals.append('Assess berth or anchorage protection; stationarity alone does not justify a decline.')
    if towards:
        referrals.append('Review movement towards the storm against the passage plan, forecasts and shelter; geometry does not establish unsafe intent.')
    if combined and combined.score is not None and combined.score >= 60:
        referrals.append('The combined indicator is 60/100 or above; review both components.')
    if not analysis.statistics.named_storm_encounters:
        conditions.append('Check tracking gaps and cruising history: no detected storm encounter does not prove absence of exposure.')
    if fictional:
        conditions.insert(0, 'Fictional scenario only: validate all evidence independently for a real submission.')
    outcome = 'DECLINE' if blockers else 'REFER' if referrals else 'OFFER'
    return dict(version=VERSION, outcome=outcome,
                label={'DECLINE': 'Do not offer terms', 'REFER': 'Refer for review',
                       'OFFER': 'Offer terms subject to checks'}[outcome],
                reasons=list(dict.fromkeys(blockers + referrals)) or ['Weather and current crew evidence meet this demonstration appetite.'],
                conditions=list(dict.fromkeys(conditions)),
                uses_fictional_crew=bool(crew and crew.is_test_data))


def worked_examples():
    """Stable fictional scenarios; normal vessel searches still use random crew."""
    result = []
    for name, weather, scenario, movement, description in [
        ('Clear passage', 29, 'clear', None, 'Moderate exposure, complete crew evidence and no observed approach concern.'),
        ('Renewal planned', 34, 'expiring', None, 'Moderate exposure; a competency certificate remains valid throughout the assignment and needs renewal soon.'),
        ('Severe storm approach', 86, 'clear', 'MOVED_TOWARDS', 'Severe exposure supported by adequate tracking; vessel movement also reduced storm separation.'),
        ('Crew certification blocker', 29, 'expired', None, 'Moderate exposure, but an assigned officer has an expired, verified competency certificate.'),
        ('Approach needs explanation', 54, 'clear', 'MOVED_TOWARDS', 'Elevated exposure with movement towards the storm; route and shelter context remain unresolved.'),
    ]:
        snapshot = generate_roster(random.Random(7), scenario=scenario)
        crew = assess_crew(snapshot['assignments'], RosterProvider(snapshot))
        risk = aggregate_risk([weather], confidence='MEDIUM', preserve_worst=True)
        risk.model_version = 'TC-EXPOSURE-v0.5'
        analysis = SimpleNamespace(risk=risk, is_synthetic=True,
            audit=SimpleNamespace(calculation_hash='fictional-worked-example'),
            data_quality=SimpleNamespace(identity_confidence='HIGH'),
            statistics=SimpleNamespace(named_storm_encounters=1),
            storm_response=SimpleNamespace(windows=[SimpleNamespace(kind=movement)] if movement else []))
        analysis.underwriting = combine_risk(analysis, crew)
        result.append(dict(name=name, description=description, weather=weather, crew=crew.score,
                           combined=analysis.underwriting.score, policy=assess_appetite(analysis)))
    return result
