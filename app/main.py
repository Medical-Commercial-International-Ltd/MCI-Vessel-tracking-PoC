from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote
import json
import re
import logging
import subprocess

from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates

from app.config import Settings, get_settings
from app.crew import install_crew_routes
from app.encounter_map import build_map_data
from app.event_lookup import EventLookupService
from app.models import AnalysisInput, DatePeriod
from app.repositories import FileAnalysisRepository
from app.real_services import RealAnalysisService
from app.security import LocalUserStore, LoginRateLimiter, csrf_token, valid_csrf
from app.services import (
    DemoAnalysisService,
    dashboard_summary,
    seed_demo_portfolio,
    validate_identifier,
)
from app.vessel_photos import VesselPhotoCatalog, vessel_image
from app.satellite import GoesArchiveProvider, ImageryUnavailable, SatelliteService
from app.vessel_catalog import cached_vessels
from app.vessel_identity import demo_yachts


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def illustrative_activity_months(reference: datetime | None = None) -> list[dict[str, int | str]]:
    """Return chart-only sample activity without creating fake assessments."""
    current = reference or datetime.now(timezone.utc)
    counts = [3, 5, 4, 7, 6, 8]
    months = []
    current_index = current.year * 12 + current.month - 1
    for offset, count in zip(range(5, -1, -1), counts):
        month_index = current_index - offset
        year, zero_based_month = divmod(month_index, 12)
        label = datetime(year, zero_based_month + 1, 1).strftime("%b")
        months.append({"label": label, "count": count})
    return months


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings or get_settings()
    repository = FileAnalysisRepository(configuration.analyses_dir)
    photo_dir = configuration.data_dir / "vessel_photos"
    photo_catalog = VesselPhotoCatalog(photo_dir)
    users = LocalUserStore(configuration.users_file)
    limiter = LoginRateLimiter()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configuration.data_dir.mkdir(parents=True, exist_ok=True)
        users.ensure_admin(configuration.admin_email, configuration.admin_password)
        if configuration.analysis_provider == "demo":
            seed_demo_portfolio(repository, configuration.demo_seed_count)
        yield

    app = FastAPI(
        title=configuration.app_name,
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=configuration.session_secret,
        max_age=8 * 60 * 60,
        same_site="lax",
        https_only=configuration.app_env == "production",
    )
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    app.mount("/vessel-photos", StaticFiles(directory=photo_dir), name="vessel-photos")

    app.state.settings = configuration
    app.state.repository = repository
    app.state.photo_catalog = photo_catalog
    satellite = SatelliteService(configuration.satellite_cache_dir, configuration.satellite_cache_limit_mb,
                                 GoesArchiveProvider(configuration.satellite_python))
    app.state.satellite_service = satellite
    app.state.event_lookup = EventLookupService(
        configuration.ais_cache_dir,
        configuration.data_dir / "lookups" / "us_principal_ports.json",
    )
    if configuration.analysis_provider == "real":
        app.state.analysis_service = RealAnalysisService(repository, configuration.ais_cache_dir)
    else:
        app.state.analysis_service = DemoAnalysisService(repository)
    app.state.users = users
    app.state.login_limiter = limiter

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["Cache-Control"] = "no-store"
        return response

    def page_context(request: Request, **values):
        crew_example = None
        roster_path = configuration.data_dir / "crew" / "test-roster.json"
        if request.session.get("user", {}).get("role") in {"admin", "underwriter"} and roster_path.exists():
            try:
                crew_example = json.loads(roster_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        return {
            "request": request,
            "user": request.session.get("user"),
            "csrfToken": csrf_token(request.session),
            "provider": configuration.analysis_provider,
            "crewExample": crew_example,
            **values,
        }

    def require_user(request: Request):
        user = request.session.get("user")
        if not user:
            return None, RedirectResponse("/login", status_code=303)
        return user, None

    def with_crew(request, analysis):
        if not analysis:
            return None
        if request.session.get("user", {}).get("role") not in {"admin", "underwriter"}:
            return analysis.model_copy(update={"underwriting": None})
        return app.state.enrich_crew_risk(analysis)

    def satellite_context(request, analysis_id, encounter_id):
        if not request.session.get("user"):
            raise HTTPException(401, "Sign in to request satellite imagery")
        try:
            analysis = repository.get_analysis("mci", analysis_id)
            encounters = repository.list_encounters("mci", analysis_id)
        except ValueError:
            raise HTTPException(404, "Assessment not found")
        encounter = next((item for item in encounters if item.id == encounter_id), None)
        if analysis is None or encounter is None:
            raise HTTPException(404, "Storm encounter not found")
        return analysis, encounter

    @app.get("/api/satellite/{analysis_id}/{encounter_id}/manifest")
    async def satellite_manifest(request: Request, analysis_id: str, encounter_id: str):
        analysis, encounter = satellite_context(request, analysis_id, encounter_id)
        try:
            return await run_in_threadpool(satellite.manifest, analysis, encounter, configuration.ais_cache_dir)
        except ImageryUnavailable as exc:
            raise HTTPException(404, str(exc))
        except (OSError, ValueError):
            logging.getLogger(__name__).exception("Satellite manifest failed")
            raise HTTPException(503, "Satellite imagery is temporarily unavailable")

    @app.get("/api/satellite/{analysis_id}/{encounter_id}/image")
    async def satellite_image(request: Request, analysis_id: str, encounter_id: str, time: datetime):
        analysis, encounter = satellite_context(request, analysis_id, encounter_id)
        try:
            manifest = await run_in_threadpool(satellite.manifest, analysis, encounter, configuration.ais_cache_dir)
            image_bytes, metadata, cached = await run_in_threadpool(satellite.image, manifest, time)
        except ImageryUnavailable as exc:
            raise HTTPException(404, str(exc))
        except (OSError, ValueError, subprocess.SubprocessError):
            logging.getLogger(__name__).exception("Satellite frame failed")
            raise HTTPException(503, "Satellite frame could not load; try again shortly", headers={"Retry-After": "10"})
        return Response(image_bytes, media_type="image/png", headers={
            "X-Satellite-Acquired-At": metadata["acquiredAt"], "X-Satellite-Acquisition-End": metadata["acquisitionEnd"],
            "X-Satellite-Name": metadata["satellite"], "X-Satellite-Cache": "hit" if cached else "miss",
        })

    @app.get("/", include_in_schema=False)
    async def root(request: Request):
        target = "/dashboard" if request.session.get("user") else "/login"
        return RedirectResponse(target, status_code=303)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        if request.session.get("user"):
            return RedirectResponse("/dashboard", status_code=303)
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context=page_context(request, error=None, email=""),
        )

    @app.post("/login", response_class=HTMLResponse)
    async def login(
        request: Request,
        email: str = Form(...),
        password: str = Form(...),
        csrf: str = Form(...),
    ):
        if not valid_csrf(request.session, csrf):
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                status_code=400,
                context=page_context(request, error="Your session expired. Please try again.", email=email),
            )
        client = request.client.host if request.client else "local"
        limiter_key = f"{client}:{email.strip().lower()}"
        if not limiter.allowed(limiter_key):
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                status_code=429,
                context=page_context(
                    request,
                    error="Too many sign-in attempts. Please wait ten minutes.",
                    email=email,
                ),
            )
        user = users.authenticate(email, password)
        if not user:
            limiter.failed(limiter_key)
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                status_code=401,
                context=page_context(request, error="Email or password was not recognised.", email=email),
            )
        limiter.clear(limiter_key)
        request.session.clear()
        request.session["user"] = user
        csrf_token(request.session)
        return RedirectResponse("/dashboard", status_code=303)

    @app.post("/logout")
    async def logout(request: Request, csrf: str = Form(...)):
        if not valid_csrf(request.session, csrf):
            return HTMLResponse("Invalid request", status_code=400)
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request):
        _, redirect = require_user(request)
        if redirect:
            return redirect
        analyses = repository.list_analyses("mci")
        if configuration.analysis_provider == "real":
            analyses = [analysis for analysis in analyses if not analysis.is_synthetic]
        else:
            analyses = [analysis for analysis in analyses if analysis.is_synthetic]
        summary = dashboard_summary(analyses)
        if configuration.analysis_provider == "real":
            activity_months = illustrative_activity_months()
            activity_is_illustrative = True
            headline_metrics = {
                "highOrSevere": 2,
                "highConfidencePercent": 80,
                "isIllustrative": True,
            }
        else:
            activity_months = summary["months"][-6:]
            activity_is_illustrative = False
            headline_metrics = {
                "highOrSevere": summary["highOrSevere"],
                "highConfidencePercent": summary["highConfidencePercent"],
                "isIllustrative": False,
            }
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context=page_context(
                request,
                summary=summary,
                recent=[with_crew(request, item) for item in analyses[:8]],
                activityMonths=activity_months,
                activityIsIllustrative=activity_is_illustrative,
                headlineMetrics=headline_metrics,
            ),
        )

    @app.get("/analysis", response_class=HTMLResponse)
    async def analysis_page(
        request: Request,
        analysisId: str | None = None,
        mmsi: str | None = None,
        fromDate: str | None = None,
        toDate: str | None = None,
    ):
        _, redirect = require_user(request)
        if redirect:
            return redirect
        cached_years = (
            app.state.analysis_service.tracks.available_years
            if configuration.analysis_provider == "real"
            else []
        )
        earliest_contiguous_year = max(cached_years) if cached_years else 2021
        while earliest_contiguous_year - 1 in cached_years:
            earliest_contiguous_year -= 1
        analysis = with_crew(request, repository.get_analysis("mci", analysisId)) if analysisId else None
        vessel_photo = (
            await run_in_threadpool(photo_catalog.image_for, analysis.vessel)
            if analysis and configuration.analysis_provider == "real" and not analysis.is_synthetic
            else vessel_image(analysis.vessel) if analysis else None
        )
        encounters = repository.list_encounters("mci", analysisId) if analysis else []
        map_data = await run_in_threadpool(build_map_data, analysis, encounters, configuration.ais_cache_dir) if analysis and encounters else []
        for event in map_data:
            event["satelliteManifestUrl"] = f"/api/satellite/{analysis.analysis_id}/{event['id']}/manifest"
        return templates.TemplateResponse(
            request=request,
            name="analysis.html",
            context=page_context(
                request,
                analysis=analysis,
                vesselImage=vessel_photo,
                encounters=encounters,
                mapData=map_data,
                mapTileUrl=configuration.map_tile_url,
                mapTileAttribution=configuration.map_tile_attribution,
                error=None,
                defaults={
                    "identifierType": analysis.input.identifier_type if analysis else "MMSI",
                    "identifier": analysis.input.identifier if analysis else (mmsi if mmsi and mmsi.isdigit() and len(mmsi) == 9 else ""),
                    "fromDate": analysis.input.period.from_date.isoformat() if analysis else (fromDate if fromDate and re.fullmatch(r"\d{4}-\d{2}-\d{2}", fromDate) else f"{earliest_contiguous_year}-01-01"),
                    "toDate": analysis.input.period.to_date.isoformat() if analysis else (toDate if toDate and re.fullmatch(r"\d{4}-\d{2}-\d{2}", toDate) else (f"{max(cached_years)}-12-31" if cached_years else "2025-12-31")),
                    "coastalLimitNm": analysis.input.coastal_limit_nm if analysis else 75,
                    "stormProximityNm": analysis.input.storm_proximity_nm if analysis else 200,
                },
            ),
        )

    def lookup_context(request: Request, *, values=None, response=None, error=None):
        service = app.state.event_lookup
        storms = service.storms()
        latest_vessels = {}
        for analysis in repository.list_analyses("mci"):
            if analysis.status != "completed" or analysis.is_synthetic != (configuration.analysis_provider == "demo"):
                continue
            for key in analysis.vessel.mmsi or [analysis.input.identifier]:
                previous = latest_vessels.get(key)
                if previous is None or analysis.created_at > previous.created_at:
                    latest_vessels[key] = analysis
        catalog = cached_vessels(configuration.ais_cache_dir) if configuration.analysis_provider == "real" else tuple((mmsi, ()) for mmsi in sorted(latest_vessels))
        catalog_years = dict(catalog)
        yacht_rows = []
        crew_visible = request.session.get("user", {}).get("role") in {"admin", "underwriter"}
        current_day = datetime.now(timezone.utc).date().isoformat()
        for identity in demo_yachts():
            crew = app.state.crew_repository.list(f"mci:IMO:{identity['imo']}") if crew_visible else []
            yacht_rows.append({**identity, "years": catalog_years.get(identity["mmsi"], ()),
                               "analysis": with_crew(request, latest_vessels.get(identity["mmsi"])),
                               "crew": [row for row in crew if row["start_date"] <= current_day <= row["end_date"]]})
        return page_context(
            request,
            ports=service.ports(),
            vesselGroups=service.vessel_groups(),
            storms=sorted(storms, key=lambda storm: (storm.start.year, storm.name, storm.storm_id), reverse=True),
            years=service.years,
            values=values or {
                "date": "", "portId": "", "stormId": "",
                "distanceNm": "100", "vesselGroup": "", "minLengthM": "24",
                "yachtCandidates": True,
            },
            lookupResponse=response,
            demoYachts=yacht_rows,
            error=error,
        )

    @app.post("/event-lookup/analyse/{mmsi}")
    async def analyse_lookup_vessel(request: Request, mmsi: str, csrf: str = Form("")):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        if not valid_csrf(request.session, csrf):
            return HTMLResponse("Invalid request", status_code=400)
        try:
            identifier = validate_identifier("MMSI", mmsi)
            years = app.state.analysis_service.tracks.available_years if configuration.analysis_provider == "real" else [2025]
            if not years:
                raise ValueError("No cached AIS track years are available.")
            earliest = max(years)
            while earliest - 1 in years:
                earliest -= 1
            analysis_input = AnalysisInput(identifier_type="MMSI", identifier=identifier,
                                           period=DatePeriod(from_date=date(earliest, 1, 1), to_date=date(max(years), 12, 31)))
            result = await run_in_threadpool(app.state.analysis_service.analyse, analysis_input, user["email"])
        except ValueError as exc:
            context = await run_in_threadpool(lookup_context, request, error=str(exc))
            return templates.TemplateResponse(request=request, name="event_lookup.html", context=context, status_code=422)
        with_crew(request, result)
        return RedirectResponse(f"/analysis?analysisId={quote(result.analysis_id)}", status_code=303)

    @app.post("/event-lookup/rerun/{analysis_id}")
    async def rerun_lookup_vessel(request: Request, analysis_id: str, csrf: str = Form("")):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        if not valid_csrf(request.session, csrf):
            return HTMLResponse("Invalid request", status_code=400)
        previous = await run_in_threadpool(repository.get_analysis, "mci", analysis_id)
        if previous is None or previous.is_synthetic != (configuration.analysis_provider == "demo"):
            raise HTTPException(status_code=404, detail="Analysis not found")
        try:
            result = await run_in_threadpool(app.state.analysis_service.analyse, previous.input, user["email"])
        except ValueError as exc:
            context = await run_in_threadpool(lookup_context, request, error=str(exc))
            return templates.TemplateResponse(request=request, name="event_lookup.html", context=context, status_code=422)
        with_crew(request, result)
        return RedirectResponse(f"/analysis?analysisId={quote(result.analysis_id)}", status_code=303)

    @app.get("/event-lookup", response_class=HTMLResponse)
    async def event_lookup_page(request: Request):
        _, redirect = require_user(request)
        if redirect:
            return redirect
        context = await run_in_threadpool(lookup_context, request)
        return templates.TemplateResponse(request=request, name="event_lookup.html", context=context)

    @app.post("/event-lookup", response_class=HTMLResponse)
    async def search_event_lookup(
        request: Request,
        dateValue: str = Form(""),
        portId: str = Form(""),
        stormId: str = Form(""),
        distanceNm: str = Form("100"),
        vesselGroup: str = Form(""),
        minLengthM: str = Form(""),
        yachtCandidates: str = Form(""),
        csrf: str = Form(""),
    ):
        _, redirect = require_user(request)
        if redirect:
            return redirect
        if not valid_csrf(request.session, csrf):
            return HTMLResponse("Invalid request", status_code=400)
        values = {
            "date": dateValue, "portId": portId, "stormId": stormId,
            "distanceNm": distanceNm, "vesselGroup": vesselGroup,
            "minLengthM": minLengthM, "yachtCandidates": bool(yachtCandidates),
        }
        try:
            selected_date = date.fromisoformat(dateValue) if dateValue else None
            service = app.state.event_lookup
            if selected_date and selected_date.year not in service.years:
                raise ValueError("Choose a date within the cached AIS years.")
            result = await run_in_threadpool(
                service.search,
                selected_date=selected_date,
                port_id=portId,
                storm_id=stormId,
                radius_nm=float(distanceNm),
                vessel_group=vesselGroup or None,
                min_length_m=float(minLengthM) if minLengthM else None,
                yacht_candidates=bool(yachtCandidates),
            )
            context = await run_in_threadpool(lookup_context, request, values=values, response=result)
            return templates.TemplateResponse(request=request, name="event_lookup.html", context=context)
        except (ValueError, OverflowError) as exc:
            context = await run_in_threadpool(lookup_context, request, values=values, error=str(exc))
            return templates.TemplateResponse(request=request, name="event_lookup.html", context=context, status_code=400)

    @app.post("/analysis", response_class=HTMLResponse)
    async def run_analysis(
        request: Request,
        identifierType: str = Form(...),
        identifier: str = Form(...),
        fromDate: date = Form(...),
        toDate: date = Form(...),
        coastalLimitNm: float = Form(75),
        stormProximityNm: float = Form(200),
        csrf: str = Form(...),
    ):
        user, redirect = require_user(request)
        if redirect:
            return redirect
        defaults = {
            "identifierType": identifierType,
            "identifier": identifier,
            "fromDate": fromDate.isoformat(),
            "toDate": toDate.isoformat(),
            "coastalLimitNm": coastalLimitNm,
            "stormProximityNm": stormProximityNm,
        }
        error = None
        if not valid_csrf(request.session, csrf):
            error = "Your session expired. Please try again."
        try:
            normalized_type = identifierType.strip().upper()
            if normalized_type not in {"IMO", "MMSI"}:
                raise ValueError("Choose IMO or MMSI")
            normalized_identifier = validate_identifier(normalized_type, identifier)
            analysis_input = AnalysisInput(
                identifier_type=normalized_type,
                identifier=normalized_identifier,
                period=DatePeriod(from_date=fromDate, to_date=toDate),
                coastal_limit_nm=coastalLimitNm,
                storm_proximity_nm=stormProximityNm,
            )
        except ValueError as exc:
            error = str(exc)
        except Exception:
            error = "Check the dates and analysis limits, then try again."
        if error:
            return templates.TemplateResponse(
                request=request,
                name="analysis.html",
                status_code=422,
                context=page_context(
                    request,
                    analysis=None,
                    encounters=[],
                    mapData=[],
                    error=error,
                    defaults=defaults,
                ),
            )
        try:
            result = await run_in_threadpool(
                app.state.analysis_service.analyse,
                analysis_input,
                user["email"],
            )
        except ValueError as exc:
            return templates.TemplateResponse(
                request=request,
                name="analysis.html",
                status_code=422,
                context=page_context(
                    request,
                    analysis=None,
                    encounters=[],
                    mapData=[],
                    error=str(exc),
                    defaults=defaults,
                ),
            )
        with_crew(request, result)
        return RedirectResponse(
            f"/analysis?analysisId={quote(result.analysis_id)}",
            status_code=303,
        )

    @app.get("/analysis/{analysis_id}/json", include_in_schema=False)
    async def download_analysis(request: Request, analysis_id: str):
        _, redirect = require_user(request)
        if redirect:
            return redirect
        analysis = repository.get_analysis("mci", analysis_id)
        if not analysis:
            return HTMLResponse("Analysis not found", status_code=404)
        analysis = with_crew(request, analysis)
        payload = analysis.model_dump_json(by_alias=True, indent=2) + "\n"
        return Response(
            content=payload,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{analysis_id}.json"'
            },
        )

    @app.get("/health", include_in_schema=False)
    async def health():
        return {
            "status": "ok",
            "provider": configuration.analysis_provider,
            "cacheLimitGb": configuration.ais_cache_limit_gb,
        }

    install_crew_routes(app, configuration, repository, templates, page_context)
    return app


app = create_app()
