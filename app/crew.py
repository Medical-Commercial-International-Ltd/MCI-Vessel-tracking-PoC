"""Crew review, explicit vessel assignments and evidence risk integration."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol
import re
import sqlite3
from time import time
from urllib.parse import urlencode

from fastapi import Form, HTTPException, Request
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from app.security import valid_csrf
from app.crewdentials import CrewUnavailable, CrewdentialsProvider
from app.crew_risk import assess_crew, combine_risk, parse_date


class CrewProvider(Protocol):
    def search(self, first_name: str, last_name: str, email: str) -> list[dict]: ...
    def get(self, person_id: str) -> dict | None: ...


class DemoCrewProvider:
    def __init__(self):
        today = datetime.now(timezone.utc).date()
        self.people = {
            "demo-maya": {
                "id": "demo-maya", "first_name": "Maya", "last_name": "Patel",
                "email": "maya.patel@example.test", "summary": "Captain and deck operations experience on motor yachts.",
                "experience": ["Captain, 42 m motor yacht — 2022–2025", "Chief officer, 35 m motor yacht — 2019–2022"],
                "certificates": [
                    {"name": "Certificate of competency", "reference": "DEMO-COC-01", "verification": "VERIFIED_MANUAL", "completed": True,
                     "expiry": (today + timedelta(days=365)).isoformat(), "limits": "Up to 3,000 GT; flag recognition not supplied"},
                    {"name": "Basic safety training", "reference": "DEMO-BST-01", "verification": "VERIFIED_INSTANT", "completed": True,
                     "expiry": (today + timedelta(days=45)).isoformat(), "limits": "Operating limits not supplied"},
                ],
            },
            "demo-alex-1": {
                "id": "demo-alex-1", "first_name": "Alex", "last_name": "Morgan",
                "email": "alex.morgan@example.test", "summary": "Deck officer experience supplied in a sample CV.",
                "experience": ["Deck officer, 38 m motor yacht — 2021–2024"],
                "certificates": [
                    {"name": "Basic safety training", "reference": "DEMO-BST-02", "verification": "REJECTED", "completed": True,
                     "expiry": (today - timedelta(days=30)).isoformat(), "limits": "Operating limits not supplied"},
                    {"name": "Certificate awaiting review", "reference": None, "verification": None, "completed": False,
                     "expiry": None, "limits": "Unknown"},
                ],
            },
            "demo-alex-2": {
                "id": "demo-alex-2", "first_name": "Alexander", "last_name": "Morgan",
                "email": "alex.morgan@example.test", "summary": None, "experience": [], "certificates": [],
            },
        }

    def search(self, first_name, last_name, email):
        if email.casefold() == "unavailable@example.test":
            raise CrewUnavailable("The demonstration provider is unavailable. Try another sample or retry.")
        return [dict(id=p["id"], first_name=p["first_name"], last_name=p["last_name"], email=p["email"],
                     name_consistent=(p["first_name"].casefold() == first_name.casefold()
                                      and p["last_name"].casefold() == last_name.casefold()))
                for p in self.people.values() if p["email"].casefold() == email.casefold()]

    def get(self, person_id):
        return self.people.get(person_id)


class UnavailableCrewProvider:
    def search(self, first_name, last_name, email):
        raise CrewUnavailable("Live crew lookup is not connected yet. Please try again once it is available.")

    def get(self, person_id):
        raise CrewUnavailable("Live crew lookup is not connected yet.")


class CrewRepository:
    """Local transactional assignment store with an append-only change history."""
    def __init__(self, path: Path):
        self.path = path

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("""CREATE TABLE IF NOT EXISTS assignments (
            vessel_key TEXT NOT NULL, person_id TEXT NOT NULL, name TEXT NOT NULL,
            role TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
            reviewer TEXT NOT NULL, reviewed_at TEXT NOT NULL, is_demo INTEGER NOT NULL,
            PRIMARY KEY (vessel_key, person_id))""")
        connection.execute("""CREATE TABLE IF NOT EXISTS assignment_audit (
            vessel_key TEXT, person_id TEXT, action TEXT, role TEXT, start_date TEXT,
            end_date TEXT, reviewer TEXT, reviewed_at TEXT, is_demo INTEGER)""")
        connection.execute("CREATE TABLE IF NOT EXISTS vessel_aliases (identifier TEXT PRIMARY KEY, vessel_key TEXT NOT NULL)")
        return connection

    @contextmanager
    def connect(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def list(self, vessel_key):
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM assignments WHERE vessel_key = ? ORDER BY name", (vessel_key,))]

    def key(self, analysis):
        canonical = vessel_key(analysis)
        aliases = {f"mci:MMSI:{mmsi}" for mmsi in analysis.vessel.mmsi}
        aliases.add(f"mci:{analysis.input.identifier_type}:{analysis.input.identifier}")
        aliases.add(canonical)
        with self.connect() as connection:
            if not analysis.vessel.imo:
                for alias in sorted(aliases):
                    existing = connection.execute("SELECT vessel_key FROM vessel_aliases WHERE identifier=?", (alias,)).fetchone()
                    if existing:
                        canonical = existing["vessel_key"]
                        break
            for alias in aliases:
                # Promote prior MMSI-only links when the vessel's IMO becomes known.
                # Never import another IMO's links if an MMSI has been reused.
                if alias != canonical and alias.startswith("mci:MMSI:"):
                    rows = connection.execute("SELECT * FROM assignments WHERE vessel_key=?", (alias,)).fetchall()
                    for row in rows:
                        connection.execute("INSERT OR IGNORE INTO assignments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                           (canonical, *(row[k] for k in ("person_id", "name", "role", "start_date", "end_date", "reviewer", "reviewed_at", "is_demo"))))
                    connection.execute("DELETE FROM assignments WHERE vessel_key=?", (alias,))
                connection.execute("INSERT INTO vessel_aliases VALUES (?, ?) ON CONFLICT(identifier) DO UPDATE SET vessel_key=excluded.vessel_key", (alias, canonical))
        return canonical

    def save(self, vessel_key, person, role, start, end, reviewer):
        values = (vessel_key, person["id"], f'{person["first_name"]} {person["last_name"]}',
                  role, start.isoformat(), end.isoformat(), reviewer, datetime.now(timezone.utc).isoformat(), int(person.get("is_demo", True)))
        with self.connect() as connection:
            connection.execute("""INSERT INTO assignments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(vessel_key, person_id) DO UPDATE SET role=excluded.role,
                start_date=excluded.start_date, end_date=excluded.end_date,
                reviewer=excluded.reviewer, reviewed_at=excluded.reviewed_at, is_demo=excluded.is_demo""", values)
            connection.execute("INSERT INTO assignment_audit VALUES (?, ?, 'save', ?, ?, ?, ?, ?, ?)",
                               (values[0], values[1], *values[3:]))

    def remove(self, vessel_key, person_id, reviewer):
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM assignments WHERE vessel_key=? AND person_id=?",
                                     (vessel_key, person_id)).fetchone()
            if row:
                connection.execute("INSERT INTO assignment_audit VALUES (?, ?, 'remove', ?, ?, ?, ?, ?, ?)",
                                   (vessel_key, person_id, row["role"], row["start_date"], row["end_date"],
                                    reviewer, datetime.now(timezone.utc).isoformat(), row["is_demo"]))
                connection.execute("DELETE FROM assignments WHERE vessel_key=? AND person_id=?", (vessel_key, person_id))


def vessel_key(analysis):
    # The existing localhost application has one tenant, MCI.
    if analysis.vessel.imo:
        return f"mci:IMO:{analysis.vessel.imo}"
    if analysis.vessel.mmsi:
        return f"mci:MMSI:{analysis.vessel.mmsi[0]}"
    return f"mci:{analysis.input.identifier_type}:{analysis.input.identifier}"


def evidence_findings(person, end_date=None):
    today = datetime.now(timezone.utc).date()
    findings = ["Flag recognition and role-specific requirements have not been checked."]
    for certificate in person["certificates"]:
        name = certificate["name"]
        expiry = parse_date(certificate["expiry"])
        if "REJECTED" in (certificate["verification"] or ""):
            findings.append(f"{name}: verification rejected; review the underlying evidence.")
        elif not certificate["verification"]:
            findings.append(f"{name}: no verification evidence supplied.")
        if not certificate["completed"]:
            findings.append(f"{name}: document details are awaiting review.")
        if expiry and expiry < today:
            findings.append(f"{name}: expired on {expiry.isoformat()}.")
        elif expiry and end_date and expiry < date.fromisoformat(end_date):
            findings.append(f"{name}: expires before the assignment ends ({expiry.isoformat()}).")
        elif expiry and expiry <= today + timedelta(days=90):
            findings.append(f"{name}: expires within 90 days ({expiry.isoformat()}).")
        if not expiry:
            findings.append(f"{name}: expiry is unknown; a non-expiring qualification is not established.")
    if not person["certificates"]:
        findings.append("No qualification evidence supplied.")
    if not person["experience"]:
        findings.append("No CV experience supplied.")
    return findings


def install_crew_routes(app, settings, analyses, templates, page_context):
    provider = (CrewdentialsProvider(settings) if settings.crew_provider == "crewdentials" else
                DemoCrewProvider() if settings.crew_provider == "demo" else UnavailableCrewProvider())
    store = CrewRepository(settings.data_dir / "crew" / "assignments.sqlite")
    app.state.crew_provider = provider
    app.state.crew_repository = store

    def enrich(analysis, *, persist=True):
        crew = assess_crew(store.list(store.key(analysis)), app.state.crew_provider)
        underwriting = combine_risk(analysis, crew)
        changed = analysis.underwriting != underwriting
        analysis.underwriting = underwriting
        analysis.schema_version = "1.1"
        if persist and changed:
            analyses.save_analysis(analysis)
        return analysis

    app.state.enrich_crew_risk = enrich

    def update_vessel(analysis):
        # Recompute every saved assessment for this vessel after a link/evidence change.
        for other in analyses.list_analyses("mci"):
            if store.key(other) == store.key(analysis):
                enrich(other)

    def context(request, analysis_id):
        user = request.session.get("user")
        if not user:
            raise HTTPException(401, "Sign in to access crew evidence")
        if user.get("role") not in {"underwriter", "admin"}:
            raise HTTPException(403, "Crew evidence requires underwriting access")
        try:
            analysis = analyses.get_analysis("mci", analysis_id)
        except ValueError:
            analysis = None
        if not analysis:
            raise HTTPException(404, "Vessel assessment not found")
        return user, analysis

    def allowed(request, analysis, person_id):
        lookup = request.session.get("crew_lookup", {})
        recent = (lookup.get("analysis") == analysis.analysis_id
                  and 0 <= time() - lookup.get("at", 0) < 900
                  and person_id in lookup.get("ids", []))
        linked = any(row["person_id"] == person_id for row in store.list(store.key(analysis)))
        if not (recent or linked):
            raise HTTPException(403, "Search for and select this person again")

    def render(request, analysis, *, candidates=None, searched=False, person=None, values=None, error=None, status=200, saved=False):
        enrich(analysis)
        assignments = store.list(store.key(analysis))
        assignment = next((a for a in assignments if person and a["person_id"] == person["id"]), None)
        return templates.TemplateResponse(request=request, name="crew.html", status_code=status,
            context=page_context(request, analysis=analysis, crewDemo=settings.crew_provider == "demo",
                crewConnected=settings.crew_provider == "crewdentials",
                connectedProfiles=provider.directory() if isinstance(provider, CrewdentialsProvider) else [],
                candidates=candidates or [], searched=searched, person=person, assignments=assignments,
                assignment=assignment, findings=evidence_findings(person, assignment["end_date"] if assignment else None) if person else [],
                values=values or {}, error=error, saved=saved, today=datetime.now(timezone.utc).date().isoformat()))

    @app.post("/crew/{analysis_id}/select")
    async def crew_select(request: Request, analysis_id: str, csrf: str = Form(""), person_id: str = Form("")):
        _, analysis = context(request, analysis_id)
        if not valid_csrf(request.session, csrf):
            raise HTTPException(400, "Your session expired. Reload and try again.")
        if not isinstance(provider, CrewdentialsProvider) or not any(p["id"] == person_id for p in provider.directory()):
            raise HTTPException(404, "Connected profile not found")
        request.session["crew_lookup"] = {"analysis": analysis_id, "ids": [person_id], "at": time()}
        return RedirectResponse(f"/crew/{analysis_id}?" + urlencode({"person": person_id}), status_code=303)

    @app.post("/crew/{analysis_id}/refresh")
    async def crew_refresh(request: Request, analysis_id: str, csrf: str = Form(""), person_id: str = Form("")):
        _, analysis = context(request, analysis_id)
        if not valid_csrf(request.session, csrf):
            raise HTTPException(400, "Your session expired. Reload and try again.")
        allowed(request, analysis, person_id)
        if not isinstance(provider, CrewdentialsProvider):
            raise HTTPException(400, "Provider refresh is unavailable")
        try:
            profile = await run_in_threadpool(provider.refresh, person_id)
        except CrewUnavailable as exc:
            update_vessel(analysis)
            try:
                previous = provider.get(person_id)
            except CrewUnavailable:
                previous = None
            return render(request, analysis, person=previous, error=str(exc), status=503)
        update_vessel(analysis)
        return render(request, analysis, person=profile)

    @app.get("/crew/{analysis_id}/evidence/{person_id}")
    async def crew_evidence(request: Request, analysis_id: str, person_id: str):
        _, analysis = context(request, analysis_id)
        allowed(request, analysis, person_id)
        person = app.state.crew_provider.get(person_id)
        if not person or not person.get("raw"):
            raise HTTPException(404, "Provider evidence not available")
        return JSONResponse(person["raw"], headers={"Cache-Control": "no-store"})

    @app.get("/crew/{analysis_id}/source/{person_id}/{document_id}")
    async def crew_source(request: Request, analysis_id: str, person_id: str, document_id: str):
        _, analysis = context(request, analysis_id)
        allowed(request, analysis, person_id)
        if not isinstance(provider, CrewdentialsProvider):
            raise HTTPException(404, "Source file unavailable")
        source = provider.document_path(person_id, document_id)
        if not source:
            raise HTTPException(404, "Source file not downloaded locally")
        return FileResponse(source, filename=source.name, headers={"Cache-Control": "no-store"})

    @app.get("/crew/{analysis_id}")
    async def crew_page(request: Request, analysis_id: str, person: str = "", saved: bool = False):
        if not request.session.get("user"):
            return RedirectResponse("/login", status_code=303)
        _, analysis = context(request, analysis_id)
        profile = None
        if person:
            allowed(request, analysis, person)
            try:
                profile = app.state.crew_provider.get(person)
            except CrewUnavailable as exc:
                return render(request, analysis, error=str(exc), status=503)
            if not profile:
                raise HTTPException(404, "Crew profile not found")
        return render(request, analysis, person=profile, saved=saved)

    @app.post("/crew/{analysis_id}/lookup")
    async def crew_lookup(request: Request, analysis_id: str, csrf: str = Form(""),
                          first_name: str = Form(""), last_name: str = Form(""), email: str = Form("")):
        _, analysis = context(request, analysis_id)
        if not valid_csrf(request.session, csrf):
            raise HTTPException(400, "Your session expired. Reload and try again.")
        values = dict(first_name=first_name.strip(), last_name=last_name.strip(), email=email.strip())
        request.session.pop("crew_lookup", None)
        if (not values["first_name"] or not values["last_name"]
                or len(values["first_name"]) > 80 or len(values["last_name"]) > 80
                or len(values["email"]) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", values["email"])):
            return render(request, analysis, values=values, error="Enter a first name, surname and valid email address.", status=422)
        try:
            candidates = app.state.crew_provider.search(**values)
        except CrewUnavailable as exc:
            return render(request, analysis, values=values, error=str(exc), status=503)
        request.session["crew_lookup"] = {"analysis": analysis_id, "ids": [p["id"] for p in candidates], "at": time()}
        return render(request, analysis, values=values, candidates=candidates, searched=True)

    @app.post("/crew/{analysis_id}/assign")
    async def crew_assign(request: Request, analysis_id: str, csrf: str = Form(""), person_id: str = Form(""),
                          role: str = Form(""), start_date: str = Form(""), end_date: str = Form(""), confirmed: str = Form("")):
        user, analysis = context(request, analysis_id)
        if not valid_csrf(request.session, csrf):
            raise HTTPException(400, "Your session expired. Reload and try again.")
        allowed(request, analysis, person_id)
        try:
            person = app.state.crew_provider.get(person_id)
        except CrewUnavailable as exc:
            return render(request, analysis, error=str(exc), status=503)
        if not person:
            raise HTTPException(404, "Crew profile not found")
        try:
            start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
            if end < start or role not in {"Captain", "Chief officer", "Engineer", "Deck crew", "Interior crew", "Other"} or confirmed != "yes":
                raise ValueError()
        except ValueError:
            return render(request, analysis, person=person,
                          values=dict(role=role, start_date=start_date, end_date=end_date),
                          error="Choose a role and valid assignment dates, and confirm the person and vessel link.", status=422)
        store.save(store.key(analysis), person, role, start, end, user["email"])
        update_vessel(analysis)
        return RedirectResponse(f"/crew/{analysis_id}?" + urlencode({"person": person_id, "saved": "true"}), status_code=303)

    @app.post("/crew/{analysis_id}/remove")
    async def crew_remove(request: Request, analysis_id: str, csrf: str = Form(""), person_id: str = Form("")):
        user, analysis = context(request, analysis_id)
        if not valid_csrf(request.session, csrf):
            raise HTTPException(400, "Your session expired. Reload and try again.")
        store.remove(store.key(analysis), person_id, user["email"])
        update_vessel(analysis)
        return RedirectResponse(f"/crew/{analysis_id}", status_code=303)
