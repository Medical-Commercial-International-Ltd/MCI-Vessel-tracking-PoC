from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote
import re

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates

from app.config import Settings, get_settings
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
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers["Cache-Control"] = "no-store"
        return response

    def page_context(request: Request, **values):
        return {
            "request": request,
            "user": request.session.get("user"),
            "csrfToken": csrf_token(request.session),
            "provider": configuration.analysis_provider,
            **values,
        }

    def require_user(request: Request):
        user = request.session.get("user")
        if not user:
            return None, RedirectResponse("/login", status_code=303)
        return user, None

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
                recent=analyses[:8],
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
        analysis = repository.get_analysis("mci", analysisId) if analysisId else None
        vessel_photo = (
            await run_in_threadpool(photo_catalog.image_for, analysis.vessel)
            if analysis and configuration.analysis_provider == "real" and not analysis.is_synthetic
            else vessel_image(analysis.vessel) if analysis else None
        )
        encounters = repository.list_encounters("mci", analysisId) if analysis else []
        map_data = [
            {
                "name": encounter.storm.name,
                "vessel": list(encounter.closest_approach.vessel_position.coordinates),
                "storm": list(encounter.closest_approach.storm_position.coordinates),
                "distanceNm": encounter.closest_approach.distance_nm,
            }
            for encounter in encounters
        ]
        return templates.TemplateResponse(
            request=request,
            name="analysis.html",
            context=page_context(
                request,
                analysis=analysis,
                vesselImage=vessel_photo,
                encounters=encounters,
                mapData=map_data,
                error=None,
                defaults={
                    "identifierType": "MMSI",
                    "identifier": mmsi if mmsi and mmsi.isdigit() and len(mmsi) == 9 else "",
                    "fromDate": fromDate if fromDate and re.fullmatch(r"\d{4}-\d{2}-\d{2}", fromDate) else f"{earliest_contiguous_year}-01-01",
                    "toDate": toDate if toDate and re.fullmatch(r"\d{4}-\d{2}-\d{2}", toDate) else (f"{max(cached_years)}-12-31" if cached_years else "2025-12-31"),
                    "coastalLimitNm": 75,
                    "stormProximityNm": 200,
                },
            ),
        )

    def lookup_context(request: Request, *, values=None, response=None, error=None):
        service = app.state.event_lookup
        storms = service.storms()
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
            error=error,
        )

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

    return app


app = create_app()
