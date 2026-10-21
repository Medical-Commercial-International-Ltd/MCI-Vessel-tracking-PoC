"""Create and link distinct fictional crew for the ten-yacht demonstration.

Prepare creates marked PDF/PNG/JPEG files and a resumable plan. Upload uses the
existing development-only importer. Verify checks stored bytes before assigning.
Assign preserves user-reviewed links and migrates the earlier demo-maya fixture.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets

import httpx

from app.config import Settings
from app.crew import CrewRepository
from app.crewdentials import CrewdentialsProvider, import_development_snapshots
from app.crew_risk import assess_crew, combine_risk
from app.models import AnalysisInput, DatePeriod, VesselIdentity
from app.repositories import FileAnalysisRepository, _atomic_json_write
from app.vessel_identity import demo_yachts
from scripts import seed_crewdentials

BATCH_NAME = "yacht-portfolio-tests"
CERTIFICATES = [
    ("survival", "Personal Survival Techniques", "PERSONAL_SURVIVAL_TECHNIQUES"),
    ("fire", "Fire Prevention & Fire Fighting", "FIRE_PREVENTION_AND_FIRE_FIGHTING"),
    ("first-aid", "Elementary First Aid", "ELEMENTARY_FIRST_AID"),
    ("safety", "Personal Safety and Social Responsibilities", "PERSONAL_SAFETY_AND_SOCIAL_RESPONSIBILITIES"),
    ("medical", "Medical Fitness Certificate", "MEDICAL_FITNESS_CERTIFICATE_ENG1"),
]
PEOPLE = [
    ("Maya Patel", "MCI TEST Morgan Reed"),
    ("MCI TEST Avery Stone", "MCI TEST Casey Ellis"),
    ("MCI TEST Cameron Vale", "MCI TEST Riley Quinn"),
    ("MCI TEST Harper Lane", "MCI TEST Jordan Blake"),
    ("MCI TEST Elliot Hart", "MCI TEST Taylor Brooks - provider samples"),
    ("MCI TEST Rowan Fletcher", "MCI TEST Finley Shaw"),
    ("MCI TEST Emery Cole", "MCI TEST Logan Pierce"),
    ("MCI TEST Dakota Wells", "MCI TEST Skyler Hayes"),
    ("MCI TEST Reese Bennett", "MCI TEST Arden Scott"),
    ("MCI TEST Parker Miles", "MCI TEST Sage Turner"),
]


def batch_dir(settings):
    return settings.data_dir / "crew" / BATCH_NAME


def write_certificate(target, name, title, reference, issue, expiry):
    import pymupdf
    from PIL import Image

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(pymupdf.Rect(30, 30, 565, 812), color=(0.6, 0.1, 0.1))
    text = "\n".join(["TEST DOCUMENT - NOT VALID", "FICTIONAL CREW - INTEGRATION TEST ONLY", "",
                      "MCI Synthetic Maritime Training Centre", "", title, "", f"Holder: {name}",
                      f"Reference: {reference}", f"Issue date: {issue or 'Not supplied'}",
                      f"Expiry date: {expiry or 'Not supplied'}", "",
                      "Synthetic software test evidence. No real qualification is granted.",
                      "No real authority has issued or endorsed this document.",
                      "Verification status is assigned independently by Crewdentials."])
    remaining = page.insert_textbox(pymupdf.Rect(50, 60, 545, 780), text, fontsize=12)
    if remaining < 0:
        raise ValueError("Test certificate text overflow")
    if target.suffix == ".pdf":
        doc.save(target)
    else:
        pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
        Image.frombytes("RGB", [pix.width, pix.height], pix.samples).save(target)
    doc.close()


def prepare(settings):
    out = batch_dir(settings)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "manifest.json").exists():
        print("Existing batch retained:", out)
        return
    known = {entry["name"]: entry["id"] for entry in CrewdentialsProvider(settings).directory()}
    today = datetime.now(timezone.utc).date()
    token = secrets.token_urlsafe(24)
    public = out / "public" / token
    public.mkdir(parents=True)
    profiles, roster = [], []
    for yacht_index, (yacht, names) in enumerate(zip(demo_yachts(), PEOPLE, strict=True)):
        members = []
        for role, name in zip(["Captain", "Chief officer"], names, strict=True):
            key = name.lower().replace(" ", "-")
            member = {"name": name, "role": role, "key": key}
            if name in known:
                member["crewProfileId"] = known[name]
            else:
                types = CERTIFICATES + [("competency", "Master (Unlimited)" if role == "Captain" else "Officer of the Watch 'OOW' (Unlimited)",
                                        "MASTER_UNLIMITED" if role == "Captain" else "OFFICER_OF_THE_WATCH_OOW_UNLIMITED")]
                documents = []
                for index, (short, title, cert_type) in enumerate(types):
                    ext = ["pdf", "png", "jpg"][index % 3]
                    filename = f"{key}-{short}.{ext}"
                    issue, expiry = "2025-05-30", "2030-05-30"
                    if yacht_index % 4 == 1 and short == "fire":
                        issue, expiry = "2020-01-15", "2025-01-15"
                    elif yacht_index % 4 == 2 and short == "medical":
                        expiry = (today + timedelta(days=45)).isoformat()
                    elif yacht_index % 4 == 3 and short == "safety":
                        issue, expiry = None, None
                    reference = f"MCI-YACHT-TEST-{yacht_index+1:02}-{role[:3].upper()}-{short.upper()}"
                    write_certificate(public / filename, name, title, reference, issue, expiry)
                    documents.append({"key": short, "file": filename, "field": "originalFileUrls" if ext == "pdf" else "imageUrls",
                                      "name": title, "categoryId": "CERTIFICATE", "certificateTypeId": cert_type,
                                      "documentRef": reference, "issueDate": issue, "expiryDate": expiry})
                profiles.append({"key": key, "displayName": name, "scenario": "Fictional " + role + " for " + yacht["name"], "documents": documents})
            members.append(member)
        roster.append({"vessel": yacht, "members": members})
    _atomic_json_write(out / "manifest.json", {"asOfDate": today.isoformat(), "filePathToken": token,
                                              "profiles": profiles, "roster": roster})
    print("Prepared", len(profiles), "new profiles and", sum(len(p["documents"]) for p in profiles), "PDF/PNG/JPEG documents.")


def upload(settings, base_url):
    seed_crewdentials.OUT = batch_dir(settings)
    seed_crewdentials.upload(base_url)
    out = batch_dir(settings)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    for profile in manifest["profiles"]:
        result = json.loads((out / (profile["key"] + "-created.json")).read_text(encoding="utf-8"))
        profile.update({"crewId": result["crewId"], "crewProfileId": result["crewProfileId"]})
    _atomic_json_write(out / "manifest.json", manifest)
    print("Returned crew IDs saved to the batch manifest.")


def verify(settings):
    out = batch_dir(settings)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    rows = []
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for profile in manifest["profiles"]:
            created = json.loads((out / (profile["key"] + "-created.json")).read_text())
            retrieved = json.loads((out / (profile["key"] + "-retrieval.json")).read_text())
            documents = {doc["id"]: doc for doc in retrieved["documents"]}
            by_key = {doc["key"]: doc["documentId"] for doc in created["documents"]}
            for source in profile["documents"]:
                doc = documents[by_key[source["key"]]]
                response = client.get(doc[source["field"]][0])
                response.raise_for_status()
                original = (out / "public" / manifest["filePathToken"] / source["file"]).read_bytes()
                digest = hashlib.sha256(original).hexdigest()
                if hashlib.sha256(response.content).hexdigest() != digest:
                    raise ValueError("Stored document bytes differ from uploaded file")
                rows.append({"crewProfileId": created["crewProfileId"], "documentId": doc["id"], "file": source["file"],
                             "sha256": digest, "storedBytesVerified": True})
            print(profile["displayName"], "all stored documents verified", flush=True)
    _atomic_json_write(out / "upload-report.json", {"environment": "development", "documents": rows})


def yacht_identity(yacht, today):
    # A vessel link needs identity, not a fabricated exposure assessment.
    from types import SimpleNamespace
    return SimpleNamespace(vessel=VesselIdentity(name=yacht["name"], imo=yacht["imo"], mmsi=[yacht["mmsi"]]),
                           input=AnalysisInput(identifier_type="IMO", identifier=yacht["imo"],
                                               period=DatePeriod(from_date=today, to_date=today)))


def assign(settings):
    out = batch_dir(settings)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    if not (out / "upload-report.json").exists():
        raise SystemExit("Verify stored files before assigning crew.")
    import_development_snapshots(settings.data_dir)
    provider = CrewdentialsProvider(settings)
    known = {entry["name"]: entry["id"] for entry in provider.directory()}
    store = CrewRepository(settings.data_dir / "crew/assignments.sqlite")
    today = datetime.now(timezone.utc).date()
    end = today + timedelta(days=180)
    summary = []
    for yacht_row in manifest["roster"]:
        yacht = yacht_row["vessel"]
        vessel_key = store.key(yacht_identity(yacht, today))
        existing = {row["person_id"]: row for row in store.list(vessel_key)}
        for member in yacht_row["members"]:
            profile_id = known[member["name"]]
            # Preserve the user's original review dates for the earlier Maya fixture.
            legacy = existing.get("demo-maya") if member["name"] == "Maya Patel" else None
            if profile_id not in existing:
                start = date.fromisoformat(legacy["start_date"]) if legacy else today
                finish = date.fromisoformat(legacy["end_date"]) if legacy else end
                reviewer = "MCI POC yacht portfolio setup" + ("; migrated reviewed demo-maya link" if legacy else "")
                store.save(vessel_key, provider.get(profile_id), member["role"], start, finish, reviewer)
            if legacy:
                store.remove(vessel_key, "demo-maya", "MCI POC yacht portfolio setup; migrated to provider test profile")
            member["crewProfileId"] = profile_id
        # This checks actual store entries, not only the planned manifest.
        active = [row for row in store.list(vessel_key) if row["start_date"] <= today.isoformat() <= row["end_date"]]
        risk = assess_crew(active, provider)
        summary.append({"vessel": yacht, "members": active, "crewScore": risk.score, "underwriterReferral": risk.underwriter_referral})
        print(yacht["name"], len(active), "current fictional crew; evidence gap score", risk.score)
    repository = FileAnalysisRepository(settings.analyses_dir)
    yacht_imos = {row["vessel"]["imo"] for row in manifest["roster"]}
    yacht_mmsis = {row["vessel"]["mmsi"] for row in manifest["roster"]}
    updated = 0
    for analysis in repository.list_analyses("mci"):
        if analysis.vessel.imo in yacht_imos or yacht_mmsis.intersection(analysis.vessel.mmsi):
            analysis.underwriting = combine_risk(analysis, assess_crew(store.list(store.key(analysis)), provider))
            analysis.schema_version = "1.1"
            repository.save_analysis(analysis)
            updated += 1
    _atomic_json_write(out / "manifest.json", manifest)
    report = {"isTestData": True, "asOfDate": today.isoformat(), "yachts": summary, "assessmentsUpdated": updated}
    _atomic_json_write(settings.data_dir / "crew/yacht-portfolio-rosters.json", report)
    with (settings.data_dir / "crew/yacht-portfolio-rosters.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        columns = ["yacht", "imo", "mmsi", "crewName", "role", "crewProfileId", "from", "to"]
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for yacht in summary:
            for member in yacht["members"]:
                writer.writerow({"yacht": yacht["vessel"]["name"], "imo": yacht["vessel"]["imo"], "mmsi": yacht["vessel"]["mmsi"],
                                 "crewName": member["name"], "role": member["role"], "crewProfileId": member["person_id"],
                                 "from": member["start_date"], "to": member["end_date"]})
    print("Updated saved yacht assessments:", updated)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "upload", "verify", "assign"])
    parser.add_argument("--base-url")
    args = parser.parse_args()
    settings = Settings(crew_provider="crewdentials")
    if args.action == "upload":
        if not args.base_url or not args.base_url.startswith("https://"):
            parser.error("upload requires --base-url https://...")
        upload(settings, args.base_url)
    else:
        {"prepare": prepare, "verify": verify, "assign": assign}[args.action](settings)
