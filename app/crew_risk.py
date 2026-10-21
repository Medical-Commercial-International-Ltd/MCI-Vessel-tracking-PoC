"""Versioned POC evidence-gap metric, not a statutory manning assessment.

Each required evidence slot takes its least problematic matching document. A
document takes its worst verification/date/review penalty. Slot penalties are
weighted; the vessel takes its highest individual score to avoid dilution.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json

from app.crewdentials import CrewUnavailable
from app.models import CrewMemberRisk, CrewRiskAssessment, UnderwritingAssessment, CrewEvidenceCheck, CrewEvidenceIndicator
from app.scoring import risk_band

SAFETY = [
    ("Personal survival", {"PERSONAL_SURVIVAL_TECHNIQUES"}, 1),
    ("Fire safety", {"FIRE_PREVENTION_AND_FIRE_FIGHTING"}, 1),
    ("First aid", {"ELEMENTARY_FIRST_AID"}, 1),
    ("Personal safety", {"PERSONAL_SAFETY_AND_SOCIAL_RESPONSIBILITIES"}, 1),
    ("Medical fitness", {"MEDICAL_FITNESS_CERTIFICATE_ENG1"}, 2),
]
COMPETENCE = {
    "Captain": {"MASTER_UNLIMITED"},
    "Chief officer": {"OFFICER_OF_THE_WATCH_OOW_UNLIMITED", "MASTER_UNLIMITED"},
    "Engineer": {"CHIEF_ENGINEER_UNLIMITED", "ENGINEER_OFFICER_OF_THE_WATCH"},
}
STATUS_PENALTIES = {"VERIFIED_MANUAL": 0, "VERIFIED_INSTANT": 0, "REJECTED": 100,
                    "PENDING_MANUAL": 50, "PENDING_INSTANT": 50, "PENDING": 50,
                    "REVIEWED": 40, "CHECKED": 40, "QUERIES": 75, "REFERRED": 75}


def parse_date(value):
    try:
        return date.fromisoformat(value[:10]) if isinstance(value, str) and value else None
    except ValueError:
        return None


def document_penalty(certificate, today, assignment_end):
    findings = []
    statuses = certificate.get("statuses", [])
    # Multiple/conflicting results are retained; rejection is never hidden by a success.
    verification = max((STATUS_PENALTIES.get(status, 60) for status in statuses), default=60)
    if verification:
        findings.append("verification " + (", ".join(str(s) for s in statuses) or "not recorded"))
    penalty = verification
    referral = verification >= 75
    if not certificate.get("completed"):
        penalty = max(penalty, 40)
        findings.append("document details await review")
    expiry = parse_date(certificate.get("expiry"))
    issue = parse_date(certificate.get("issue"))
    if not expiry:
        penalty = max(penalty, 25)
        findings.append("expiry missing or invalid; non-expiring status unconfirmed")
    elif expiry < today:
        penalty, referral = 100, True
        findings.append(f"expired {expiry.isoformat()}")
    elif expiry < assignment_end:
        penalty, referral = max(penalty, 75), True
        findings.append(f"expires before assignment ends: {expiry.isoformat()}")
    elif expiry <= today + timedelta(days=90):
        penalty = max(penalty, 35)
        findings.append(f"expires within 90 days: {expiry.isoformat()}")
    if not issue:
        penalty = max(penalty, 15)
        findings.append("issue date missing or invalid")
    elif issue > today or (expiry and issue > expiry):
        penalty, referral = 100, True
        findings.append("issue date is in the future or after expiry")
    return penalty, referral, findings


def indicator(status, label, detail=""):
    return CrewEvidenceIndicator(status=status, label=label, detail=detail)


def evidence_check(label, certificate, today, assignment_end, *, unavailable=False):
    """Describe source evidence independently of the numeric gap score."""
    if unavailable:
        return CrewEvidenceCheck(label=label, document=indicator("unknown", "Unknown", "Refresh evidence to assess this requirement."),
                                 verification=indicator("unknown", "Unknown"), validity=indicator("unknown", "Unknown"))
    if certificate is None:
        return CrewEvidenceCheck(label=label, document=indicator("fail", "Not present", "No matching certificate was supplied."),
                                 verification=indicator("unknown", "No document"), validity=indicator("unknown", "No document"))
    statuses = certificate.get("statuses", [])
    worst = max((STATUS_PENALTIES.get(status, 60) for status in statuses), default=60)
    detail = "Provider: " + (", ".join(str(s) for s in statuses) or "no verification recorded")
    if "REJECTED" in statuses:
        verification = indicator("fail", "Rejected", detail)
    elif statuses and worst == 0:
        verification = indicator("pass", "Verified", detail)
        if not certificate.get("completed"):
            verification = indicator("warning", "Review due", detail + "; document details await review")
    elif any(status in {"REFERRED", "QUERIES"} for status in statuses):
        verification = indicator("warning", "Referred", detail)
    elif statuses and worst == 50:
        verification = indicator("warning", "Pending", detail)
    elif statuses and worst == 40:
        verification = indicator("warning", "Checked only", detail + "; verification not established")
    elif not statuses:
        verification = indicator("warning", "Not verified" if certificate.get("completed") else "Awaiting review", detail)
    else:
        verification = indicator("warning", "Needs review", detail)
    expiry = parse_date(certificate.get("expiry"))
    issue = parse_date(certificate.get("issue"))
    if issue and (issue > today or (expiry and issue > expiry)):
        validity = indicator("fail", "Invalid dates", "Issue date is in the future or after expiry.")
    elif expiry and expiry < today:
        validity = indicator("fail", "Expired", "Expired " + expiry.strftime("%d %b %Y"))
    elif not expiry:
        validity = indicator("warning", "Expiry unknown", "No valid expiry date supplied; non-expiring status is unconfirmed.")
    elif expiry < assignment_end:
        validity = indicator("warning", "Expires on duty", "Expires " + expiry.strftime("%d %b %Y") + ", before the assignment ends.")
    elif expiry <= today + timedelta(days=90):
        validity = indicator("warning", "Expiring soon", "Expires " + expiry.strftime("%d %b %Y"))
    elif not issue:
        validity = indicator("warning", "Issue unknown", "No valid issue date supplied. Expiry: " + expiry.strftime("%d %b %Y"))
    else:
        validity = indicator("pass", "In date", "Expires " + expiry.strftime("%d %b %Y"))
    return CrewEvidenceCheck(label=label, document=indicator("pass", "Present", certificate.get("name", label)),
                             verification=verification, validity=validity)


def assess_member(assignment, person, today):
    member = CrewMemberRisk(person_id=assignment["person_id"], name=assignment["name"], role=assignment["role"],
                            start_date=assignment["start_date"], end_date=assignment["end_date"],
                            is_test_data=bool(assignment["is_demo"]))
    slots = list(SAFETY)
    if member.role in COMPETENCE:
        slots.append(("Role competency", COMPETENCE[member.role], 3))
    if not person:
        member.findings.append("Profile evidence unavailable; risk cannot be assessed.")
        member.checks = [evidence_check(label, None, today, member.end_date, unavailable=True) for label, _, _ in slots]
        return member, True
    member.is_test_data = member.is_test_data or person.get("is_demo", True)
    member.experience_supplied = bool(person.get("experience"))
    if person.get("retrieved_at"):
        member.evidence_retrieved_at = datetime.fromisoformat(person["retrieved_at"])
    if person.get("stale") or person.get("refresh_error"):
        member.experience_supplied = None
        member.findings.append("Evidence is stale or the last refresh failed; refresh required.")
        member.checks = [evidence_check(label, None, today, member.end_date, unavailable=True) for label, _, _ in slots]
        return member, True
    if member.role not in COMPETENCE:
        member.findings.append("Specialist role competency is outside this POC rule set.")
    weighted = total_weight = 0
    referral = False
    for label, types, weight in slots:
        candidates = [doc for doc in person["certificates"] if doc.get("type") in types]
        if not candidates:
            penalty, critical, reasons = 100, True, ["required evidence missing"]
            selected = None
        else:
            selected = min(candidates, key=lambda doc: document_penalty(doc, today, member.end_date)[0])
            penalty, critical, reasons = document_penalty(selected, today, member.end_date)
        member.checks.append(evidence_check(label, selected, today, member.end_date))
        member.components[label] = penalty
        weighted += penalty * weight
        total_weight += weight
        referral = referral or critical
        member.findings.extend(f"{label}: {reason}." for reason in reasons)
    member.score = round(weighted / total_weight)
    if not person.get("experience"):
        member.findings.append("CV and experience not supplied; experience is not scored.")
    return member, referral


def assess_crew(assignments, provider, today=None):
    today = today or datetime.now(timezone.utc).date()
    result = CrewRiskAssessment(assessed_on=today)
    inputs = {"model": result.model_version, "date": today.isoformat(), "assignments": assignments, "evidence": []}
    active = [row for row in assignments if date.fromisoformat(row["start_date"]) <= today <= date.fromisoformat(row["end_date"])]
    result.findings = ["Current crew evidence is assessed separately from the historical cyclone period.",
                       "POC requirements are provisional; flag, tonnage, vessel-specific endorsements and complete manning levels require review."]
    critical = False
    for row in active:
        try:
            person = provider.get(row["person_id"])
        except CrewUnavailable:
            person = None
        member, referral = assess_member(row, person, today)
        result.members.append(member)
        critical = critical or referral
        inputs["evidence"].append(person)
    result.is_test_data = any(member.is_test_data for member in result.members)
    if not active:
        result.findings.append("No current crew assignments. Add and review a roster before assessing crew risk.")
    elif any(member.score is None for member in result.members):
        result.findings.append("Some assigned profiles have unavailable or stale evidence. Combined assessment is incomplete.")
    else:
        result.score = max(member.score for member in result.members)
        result.band = risk_band(result.score)
        result.status = "ASSESSED"
    captain_missing = not any(row["role"] == "Captain" for row in active)
    if active and captain_missing:
        result.findings.append("No current Captain assignment; roster review required.")
    result.underwriter_referral = result.score is None or critical or captain_missing or result.score >= 60
    # Signed file URLs rotate independently of certificate evidence and are excluded.
    for person in inputs["evidence"]:
        if person:
            person.pop("raw", None)
    result.evidence_hash = hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()
    return result


def combine_risk(analysis, crew):
    result = UnderwritingAssessment(exposure_score=analysis.risk.score, crew=crew,
                                    is_test_data=analysis.is_synthetic or crew.is_test_data)
    if crew.score is not None:
        # Adds at most 25% of the remaining headroom; crew cannot reduce exposure.
        result.crew_adjustment = round((100 - analysis.risk.score) * 0.25 * crew.score / 100)
        result.score = min(100, analysis.risk.score + result.crew_adjustment)
        result.band = risk_band(result.score)
    result.underwriter_referral = (analysis.risk.underwriter_referral or crew.underwriter_referral
                                   or result.score is None or result.score >= 60)
    material = {"model": result.model_version, "exposureHash": analysis.audit.calculation_hash,
                "exposureScore": analysis.risk.score, "crewHash": crew.evidence_hash,
                "combinedScore": result.score}
    result.calculation_hash = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
    return result
