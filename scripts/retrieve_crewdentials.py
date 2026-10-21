"""Read known development crew profiles; preserve all fields and download files.

Usage: python scripts/retrieve_crewdentials.py [--profile "Name=profile-id"]
Defaults to the two profile IDs supplied by James. No writes to Crewdentials.
Requires httpx; optional pymupdf extracts text from PDFs.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import html
import json
import mimetypes
from pathlib import Path
import re

import httpx

ROOT = Path(__file__).resolve().parents[1]
KNOWN = {"Sam Jones": "01a1445b-3696-7470-90a5-93a29a28e6cd",
         "Freya Smith": "01a1445f-010f-7724-9aca-ba417003f334"}


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "unnamed"


def retrieve(profiles):
    collection = json.loads((ROOT / "Crewdentials Crew Documents API.postman_collection.json").read_text(encoding="utf-8-sig"))
    config = {v["key"]: v["value"] for v in collection["variable"]}
    if config["BASE_URL"] != "https://crewdentials-api-dev.onrender.com/api":
        raise SystemExit("Expected the supplied development endpoint.")
    now = datetime.now(timezone.utc)
    out = ROOT / "data/crew/provider-retrievals" / now.strftime("%Y%m%dT%H%M%S%fZ")
    out.mkdir(parents=True)
    report = {"retrievedAtUtc": now.isoformat(), "environment": "development", "profiles": [], "errors": []}
    rows, sections = [], []
    with httpx.Client(timeout=90, follow_redirects=True) as client:
        for name, profile_id in profiles.items():
            folder = out / slug(name)
            folder.mkdir()
            r = client.get(config["BASE_URL"] + "/v1/getCrewDocs/" + profile_id,
                           headers={"Authorization": "Bearer " + config["API_KEY"]})
            if r.status_code != 200:
                save(folder / "error.json", {"statusCode": r.status_code, "body": r.text})
                report["errors"].append({"profile": name, "statusCode": r.status_code})
                continue
            data = r.json()
            save(folder / "response.json", data)
            if data.get("crewProfileId") != profile_id:
                raise ValueError("Response profile ID does not match request")
            entry = {"name": name, "crewId": data.get("crewId"), "crewProfileId": profile_id,
                     "documentCount": len(data.get("documents", [])), "files": []}
            section = [f"<h2>{html.escape(name)}</h2><p>Profile: {html.escape(profile_id)}</p>",
                       f'<p><a href="{slug(name)}/response.json">Complete API response (JSON)</a></p>']
            for doc in data.get("documents", []):
                title = doc.get("name") or "Unnamed document"
                expiry = doc.get("expiryDate")
                date_status = "Not supplied / no expiry" if not expiry else ("Expired" if expiry[:10] < now.date().isoformat() else "In date")
                statuses = [v.get("status") for v in doc.get("verifications", [])]
                rows.append({"crewName": name, "crewProfileId": profile_id, "documentId": doc["id"],
                             "name": title, "reference": doc.get("documentRef"), "issueDate": doc.get("issueDate"),
                             "expiryDate": expiry, "dateStatus": date_status, "completed": doc.get("completed"),
                             "verificationStatuses": "; ".join(str(s) for s in statuses) or "No verification recorded"})
                section.append(f"<h3>{html.escape(title)}</h3><p>{html.escape(date_status)}; verification: {html.escape(', '.join(str(s) for s in statuses) or 'None recorded')}</p><ul>")
                for field in ("imageUrls", "originalFileUrls"):
                    for index, url in enumerate(doc.get(field, []), 1):
                        # Signed storage requests must not receive the API key.
                        try:
                            response = client.get(url)
                            response.raise_for_status()
                            mime = response.headers.get("content-type", "").split(";")[0]
                            ext = ".pdf" if response.content.startswith(b"%PDF") else mimetypes.guess_extension(mime) or ".bin"
                            filename = f"{doc['id']}-{field}-{index}{ext}"
                            target = folder / filename
                            target.write_bytes(response.content)
                            entry["files"].append({"documentId": doc["id"], "field": field,
                                                   "path": str(target.relative_to(out)), "bytes": len(response.content),
                                                   "sha256": hashlib.sha256(response.content).hexdigest()})
                            link = target.relative_to(out).as_posix()
                            section.append(f'<li><a href="{html.escape(link)}">{field} {index}</a></li>')
                            if ext == ".pdf":
                                try:
                                    import pymupdf
                                    with pymupdf.open(target) as pdf:
                                        text = "\n".join(page.get_text() for page in pdf)
                                    target.with_suffix(".txt").write_text(text, encoding="utf-8")
                                except ImportError:
                                    pass
                        except httpx.HTTPError as exc:
                            report["errors"].append({"profile": name, "documentId": doc["id"], "field": field,
                                                     "index": index, "errorType": type(exc).__name__})
                section.append("</ul>")
                # Keep every provider field visible, without embedding temporary signed URLs in the report.
                details = {k: v for k, v in doc.items() if k not in ("imageUrls", "originalFileUrls")}
                section.append("<details><summary>All document fields and verification records</summary><pre>" + html.escape(json.dumps(details, indent=2)) + "</pre></details>")
            report["profiles"].append(entry)
            sections.append("\n".join(section))
            print(name, len(data.get("documents", [])), "documents;", len(entry["files"]), "files downloaded", flush=True)
    save(out / "retrieval-report.json", report)
    if rows:
        with (out / "documents.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    (out / "index.html").write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Crewdentials development evidence</title><style>body{font:16px system-ui;max-width:1000px;margin:40px auto;padding:0 24px}pre{white-space:pre-wrap;background:#f3f4f6;padding:16px}h2{border-top:2px solid #ccc;padding-top:24px}h3{margin-bottom:8px}</style><h1>Crewdentials development evidence</h1><p>Retrieved ' + html.escape(now.isoformat()) + '. Date validity and verification are shown separately. Null dates do not establish that a certificate never expires.</p><p><a href="documents.csv">Document summary CSV</a> | <a href="retrieval-report.json">Download manifest</a></p>' + '\n'.join(sections) + '</html>', encoding="utf-8")
    print("Saved:", out)
    print("Errors:", len(report["errors"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append", help="Name=crewProfileId (repeatable)")
    args = parser.parse_args()
    profiles = dict(item.split("=", 1) for item in args.profile) if args.profile else KNOWN
    retrieve(profiles)
