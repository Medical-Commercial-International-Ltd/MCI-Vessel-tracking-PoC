"""Prepare and import fictional crew into the supplied development workflow.

Optional preparation dependencies: pymupdf, pillow. HTTP dependency: httpx.
Local results and temporary file hosting stay under ignored data/crew/.
Never rerun an uncertain POST: inspect the saved response first.
"""
from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/crew/provider-tests"


def save(path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def prepare():
    import pymupdf
    from PIL import Image

    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "manifest.json"
    if manifest_path.exists():
        raise SystemExit("Manifest already exists; preserving existing crew and files.")
    token = secrets.token_urlsafe(24)
    files = OUT / "public" / token
    files.mkdir(parents=True)
    profiles = []
    samples = []
    for source, target in [("COC OOW demo.pdf", "provider-oow.pdf"),
                           ("Crewdentials issued STCW.pdf", "provider-stcw.pdf")]:
        shutil.copyfile(ROOT / "docs" / source, files / target)
        samples.append({"key": target[:-4], "file": target, "field": "originalFileUrls"})
    profiles.append({"key": "provider-samples", "displayName": "MCI TEST Taylor Brooks - provider samples",
                     "scenario": "Original provider PDFs; automatic document extraction", "documents": samples})
    scenarios = [
        ("current-pdf", "MCI TEST Morgan Reed", "Current dated PDF certificates", [
            ("oow", "Officer of the Watch 'OOW' (Unlimited)", "OFFICER_OF_THE_WATCH_OOW_UNLIMITED", "2025-06-20", "2030-06-20", "pdf"),
            ("survival", "Personal Survival Techniques", "PERSONAL_SURVIVAL_TECHNIQUES", "2025-05-30", "2030-05-30", "pdf")]),
        ("expired-png", "MCI TEST Casey Ellis", "Expired PNG certificate", [
            ("fire", "Fire Prevention & Fire Fighting", "FIRE_PREVENTION_AND_FIRE_FIGHTING", "2020-01-15", "2025-01-15", "png")]),
        ("no-expiry-jpeg", "MCI TEST Riley Quinn", "JPEG certificate with no expiry date", [
            ("first-aid", "Elementary First Aid", "ELEMENTARY_FIRST_AID", "2025-05-30", None, "jpg")]),
        ("mixed-dates", "MCI TEST Jordan Blake", "Mixed formats; approaching expiry and missing dates", [
            ("medical", "Medical Fitness Certificate", "MEDICAL_FITNESS_CERTIFICATE_ENG1", "2024-11-15", "2026-11-15", "pdf"),
            ("safety", "Personal Safety and Social Responsibilities", "PERSONAL_SAFETY_AND_SOCIAL_RESPONSIBILITIES", None, None, "png")]),
    ]
    for key, name, scenario, certificates in scenarios:
        documents = []
        for short, title, cert_type, issue, expiry, extension in certificates:
            reference = f"MCI-TEST-{key}-{short}".upper()
            filename = f"{key}-{short}.{extension}"
            doc = pymupdf.open()
            page = doc.new_page(width=595, height=842)
            page.draw_rect(pymupdf.Rect(30, 30, 565, 812), color=(0.6, 0.1, 0.1))
            lines = ["TEST DOCUMENT - NOT VALID", "FICTIONAL CREW - INTEGRATION TEST ONLY", "",
                     "MCI Synthetic Maritime Training Centre", "", title, "", f"Holder: {name}",
                     f"Reference: {reference}", f"Issue date: {issue or 'Not supplied'}",
                     f"Expiry date: {expiry or 'Not supplied / no expiry'}", "",
                     "This is a synthetic certificate for software testing.",
                     "It grants no qualification, competency or medical clearance.",
                     "No real authority has issued or endorsed this document.", "",
                     "Verification status is assigned by Crewdentials,",
                     "independently of the dates shown on this test document."]
            page.insert_textbox(pymupdf.Rect(50, 65, 545, 780), "\n".join(lines), fontsize=12)
            if extension == "pdf":
                doc.save(files / filename)
            else:
                pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                img.save(files / filename)
            doc.close()
            documents.append({"key": short, "file": filename,
                              "field": "originalFileUrls" if extension == "pdf" else "imageUrls",
                              "name": title, "categoryId": "CERTIFICATE", "certificateTypeId": cert_type,
                              "documentRef": reference, "issueDate": issue, "expiryDate": expiry})
        profiles.append({"key": key, "displayName": name, "scenario": scenario, "documents": documents})
    save(manifest_path, {"asOfDate": "2026-10-21", "filePathToken": token, "profiles": profiles})
    print(f"Prepared {len(profiles)} fictional profiles and {sum(len(p['documents']) for p in profiles)} documents.")


def upload(base_url):
    import httpx

    collection = json.loads((ROOT / "Crewdentials Crew Documents API.postman_collection.json").read_text(encoding="utf-8-sig"))
    variables = {item["key"]: item["value"] for item in collection["variable"]}
    if variables["BASE_URL"] != "https://crewdentials-api-dev.onrender.com/api":
        raise SystemExit("Refusing to seed an unrecognised environment.")
    manifest = json.loads((OUT / "manifest.json").read_text())
    with httpx.Client(timeout=120) as client:
        for profile in manifest["profiles"]:
            result_path = OUT / (profile["key"] + "-created.json")
            attempt_path = OUT / (profile["key"] + "-attempt.json")
            if result_path.exists():
                result = json.loads(result_path.read_text())
                if not result.get("crewProfileId"):
                    raise SystemExit(f"Inspect saved response: {result_path}")
            else:
                if attempt_path.exists():
                    raise SystemExit(f"Previous attempt needs reconciliation before retry: {attempt_path}")
                documents = []
                for document in profile["documents"]:
                    url = base_url.rstrip("/") + "/" + manifest["filePathToken"] + "/" + document["file"]
                    response = client.get(url)
                    response.raise_for_status()
                    if response.content != (OUT / "public" / manifest["filePathToken"] / document["file"]).read_bytes():
                        raise SystemExit("Public file content mismatch")
                    payload = {k: v for k, v in document.items() if k not in ("file", "field")}
                    payload[document["field"]] = [url]
                    documents.append(payload)
                payload = {"displayName": profile["displayName"], "workflowId": variables["WORKFLOW_ID"], "documents": documents}
                save(attempt_path, {"displayName": profile["displayName"], "documentKeys": [d["key"] for d in documents]})
                response = client.post(variables["BASE_URL"] + "/v1/insertCrewDocs", json=payload,
                                       headers={"Authorization": "Bearer " + variables["API_KEY"]})
                try:
                    result = response.json()
                except ValueError:
                    result = {"statusCode": response.status_code, "body": response.text}
                save(result_path, result)
                print(profile["key"], "POST", response.status_code, flush=True)
                response.raise_for_status()
                if not result.get("crewProfileId"):
                    raise SystemExit("Creation returned no crewProfileId; inspect response")
            response = client.get(variables["BASE_URL"] + "/v1/getCrewDocs/" + result["crewProfileId"],
                                  headers={"Authorization": "Bearer " + variables["API_KEY"]})
            response.raise_for_status()
            retrieved = response.json()
            save(OUT / (profile["key"] + "-retrieval.json"), retrieved)
            expected = {d["documentId"] for d in result.get("documents", [])}
            actual = {d["id"] for d in retrieved.get("documents", [])}
            if len(expected) != len(profile["documents"]) or not expected.issubset(actual):
                raise SystemExit("Created/retrieved document IDs do not match expected files")
            print(profile["key"], result["crewProfileId"], "GET 200", len(actual), "documents", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "serve", "upload"])
    parser.add_argument("--base-url")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--output-dir", type=Path, help="Isolated manifest and file directory for another test batch")
    args = parser.parse_args()
    if args.output_dir:
        OUT = args.output_dir.resolve()
    if args.action == "prepare":
        prepare()
    elif args.action == "serve":
        class FilesOnly(SimpleHTTPRequestHandler):
            def list_directory(self, path):
                self.send_error(404)
                return None

            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(FilesOnly, directory=str(OUT / "public")))
        print("Serving only prepared test documents on loopback", flush=True)
        server.serve_forever()
    elif not args.base_url or not args.base_url.startswith("https://"):
        parser.error("upload requires --base-url https://...")
    else:
        upload(args.base_url)
