"""Development workspace evidence. Profile discovery is a local allowlist.

Crewdentials supplies no vessel assignment or global person-search contract.
Saved responses retain every provider field; signed file URLs are never rendered.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import UUID

import httpx

from app.repositories import _atomic_json_write


class CrewUnavailable(Exception):
    pass


class CrewdentialsProvider:
    def __init__(self, settings):
        self.settings = settings
        self.root = settings.data_dir / "crew"
        self.directory_path = self.root / "connected-profiles.json"
        self.cache_dir = self.root / "evidence"

    def directory(self):
        try:
            rows = json.loads(self.directory_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return []
        return rows if isinstance(rows, list) else []

    def _entry(self, person_id):
        return next((row for row in self.directory() if row.get("id") == person_id), None)

    def search(self, first_name, last_name, email):
        # Email is deliberately not fabricated for imported development profiles.
        return []

    @staticmethod
    def validate(payload, person_id):
        if not isinstance(payload, dict) or payload.get("crewProfileId") != person_id:
            raise CrewUnavailable("Crewdentials returned an unexpected profile.")
        documents = payload.get("documents")
        if not isinstance(documents, list):
            raise CrewUnavailable("Crewdentials returned invalid documents.")
        for doc in documents:
            if not isinstance(doc, dict) or not isinstance(doc.get("id"), str):
                raise CrewUnavailable("Crewdentials returned an invalid document.")
            if not isinstance(doc.get("verifications"), list) or not all(isinstance(v, dict) for v in doc["verifications"]):
                raise CrewUnavailable("Crewdentials returned invalid verification records.")
            for key in ("name", "certificateTypeId", "issueDate", "expiryDate", "documentRef"):
                if doc.get(key) is not None and not isinstance(doc[key], str):
                    raise CrewUnavailable("Crewdentials returned invalid document fields.")
            if any(v.get("status") is not None and not isinstance(v["status"], str) for v in doc["verifications"]):
                raise CrewUnavailable("Crewdentials returned an invalid verification status.")
        return payload

    def get(self, person_id):
        entry = self._entry(person_id)
        if not entry:
            return None
        try:
            UUID(person_id)
            cached = json.loads((self.cache_dir / f"{person_id}.json").read_text(encoding="utf-8"))
            payload = self.validate(cached["payload"], person_id)
            retrieved_at = datetime.fromisoformat(cached["retrievedAt"])
            if retrieved_at.tzinfo is None:
                raise ValueError()
        except (OSError, ValueError, KeyError, TypeError):
            raise CrewUnavailable("No valid saved evidence is available. Refresh this profile.") from None
        name = entry["name"].split(" ", 1)
        certificates = []
        for doc in payload["documents"]:
            if doc.get("archivedAt"):
                continue
            statuses = [v.get("status") for v in doc["verifications"]]
            certificates.append({"id": doc["id"], "type": doc.get("certificateTypeId"),
                                 "name": doc.get("name") or "Document awaiting classification",
                                 "reference": doc.get("documentRef"), "issue": doc.get("issueDate"),
                                 "expiry": doc.get("expiryDate"), "completed": doc.get("completed") is True,
                                 "verification": ", ".join(str(s) for s in statuses) or None,
                                 "statuses": statuses, "verifications": doc["verifications"],
                                 "limits": "Role limits and flag recognition not supplied"})
        age = (datetime.now(timezone.utc) - retrieved_at).total_seconds() / 3600
        return {"id": person_id, "first_name": name[0], "last_name": name[1] if len(name) > 1 else "",
                "email": None, "summary": None, "experience": [], "certificates": certificates,
                "is_demo": entry.get("isTestData", True), "retrieved_at": retrieved_at.isoformat(),
                "stale": age > self.settings.crew_evidence_max_age_hours or age < 0,
                "refresh_error": cached.get("refreshError"), "raw": payload}

    def refresh(self, person_id):
        if not self._entry(person_id):
            raise CrewUnavailable("This profile is not in the connected workspace directory.")
        UUID(person_id)
        key = self.settings.crewdentials_api_key.get_secret_value()
        if not key:
            raise CrewUnavailable("Crewdentials refresh is not configured. Saved evidence is retained.")
        path = self.cache_dir / f"{person_id}.json"
        try:
            with httpx.Client(timeout=30, follow_redirects=False) as client:
                response = client.get(self.settings.crewdentials_base_url.rstrip("/") + "/v1/getCrewDocs/" + person_id,
                                      headers={"Authorization": "Bearer " + key})
                response.raise_for_status()
                payload = self.validate(response.json(), person_id)
        except (httpx.HTTPError, ValueError, CrewUnavailable):
            if path.exists():
                cached = json.loads(path.read_text(encoding="utf-8"))
                cached["refreshError"] = True
                _atomic_json_write(path, cached)
            raise CrewUnavailable("Crewdentials could not refresh this profile. Previous evidence has been retained and flagged for review.") from None
        _atomic_json_write(path, {"retrievedAt": datetime.now(timezone.utc).isoformat(), "payload": payload})
        return self.get(person_id)

    def document_path(self, person_id, document_id):
        person = self.get(person_id)
        if not person or not any(doc["id"] == document_id for doc in person["certificates"]):
            return None
        candidates = []
        for report in sorted((self.root / "provider-retrievals").glob("*/retrieval-report.json"), reverse=True):
            data = json.loads(report.read_text(encoding="utf-8"))
            for profile in data["profiles"]:
                if profile["crewProfileId"] == person_id:
                    files = sorted(profile["files"], key=lambda f: f["field"] != "originalFileUrls")
                    candidates.extend(report.parent / f["path"] for f in files if f["documentId"] == document_id)
        for seed in sorted(self.root.glob("*-tests")):
            if not (seed / "upload-report.json").exists() or not (seed / "manifest.json").exists():
                continue
            report = json.loads((seed / "upload-report.json").read_text(encoding="utf-8"))
            manifest = json.loads((seed / "manifest.json").read_text(encoding="utf-8"))
            candidates.extend(seed / "public" / manifest["filePathToken"] / row["file"]
                              for row in report["documents"] if row["crewProfileId"] == person_id and row["documentId"] == document_id)
        for path in candidates:
            if path.resolve().is_relative_to(self.root.resolve()) and path.is_file():
                return path
        return None


def import_development_snapshots(data_dir: Path):
    """Register only profiles whose IDs and responses were explicitly saved locally."""
    root = data_dir / "crew"
    directory = {}
    path = root / "connected-profiles.json"
    if path.exists():
        directory = {row["id"]: row for row in json.loads(path.read_text(encoding="utf-8"))}

    def add(name, profile_id, source, retrieved_at):
        payload = json.loads(source.read_text(encoding="utf-8"))
        CrewdentialsProvider.validate(payload, profile_id)
        directory[profile_id] = {"id": profile_id, "name": name, "isTestData": True}
        target = root / "evidence" / f"{profile_id}.json"
        if not target.exists():
            _atomic_json_write(target, {"retrievedAt": retrieved_at, "payload": payload})

    for folder in sorted((root / "provider-retrievals").glob("*"), reverse=True):
        report_path = folder / "retrieval-report.json"
        if not report_path.exists():
            continue
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for profile in report["profiles"]:
            slug = profile["name"].lower().replace(" ", "-")
            add(profile["name"], profile["crewProfileId"], folder / slug / "response.json", report["retrievedAtUtc"])
    for seed in sorted(root.glob("*-tests")):
        if not (seed / "manifest.json").exists():
            continue
        manifest = json.loads((seed / "manifest.json").read_text(encoding="utf-8"))
        for profile in manifest["profiles"]:
            source = seed / (profile["key"] + "-retrieval.json")
            if profile.get("crewProfileId") and source.exists():
                add(profile["displayName"], profile["crewProfileId"], source,
                    datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat())
    _atomic_json_write(path, sorted(directory.values(), key=lambda row: row["name"]))
    return list(directory.values())
