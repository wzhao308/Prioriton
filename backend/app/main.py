import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.browser_login import PROFILE_ROOT
from app.config import get_settings
from app.db import engine, init_db
from app.demo import reset_demo
from app.file_permissions import restrict_to_current_user
from app.models import Course, Integration
from app.routers import (
    analytics,
    courses,
    integrations,
    recommendations,
    reminders,
    settings as settings_router,
    study_sessions,
    sync,
    tasks,
)
from app.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("prioriton.main")

app = FastAPI(title="Prioriton", version="0.1.0")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serving the built frontend from this same process (backend/Dockerfile.demo,
# the public demo's single-container deploy) puts API routes and frontend
# page routes on one origin - and several share a literal path (GET
# /courses, /settings, /recommendations are both real API endpoints AND
# React Router pages). The VPS deploy and local dev never hit this: they
# split frontend/API across subdomains or dev-server ports, so routes are
# never prefixed there and stay exactly as originally built/tested. Only
# when a frontend build is actually baked into this image do routes move
# under /api - see backend/Dockerfile.demo's VITE_API_BASE=/api.
FRONTEND_DIST_DIR = Path(__file__).resolve().parent.parent / "frontend_dist"
_api_prefix = "/api" if FRONTEND_DIST_DIR.is_dir() else ""

# Assignment sync (Canvas/Gradescope/PrairieLearn) and reminders quietly power
# the Home page and Analytics/Recommendations in the background - see
# app.sync_service. courses/tasks are the same underlying data, exposed for
# the Study Timer's course picker and Home's assignment widget.
app.include_router(integrations.router, prefix=_api_prefix)
app.include_router(courses.router, prefix=_api_prefix)
app.include_router(tasks.router, prefix=_api_prefix)
app.include_router(sync.router, prefix=_api_prefix)
app.include_router(reminders.router, prefix=_api_prefix)
app.include_router(settings_router.router, prefix=_api_prefix)
# Prioriton-specific features.
app.include_router(study_sessions.router, prefix=_api_prefix)
app.include_router(analytics.router, prefix=_api_prefix)
app.include_router(recommendations.router, prefix=_api_prefix)


def _recover_stranded_logins() -> None:
    """If the backend restarted mid-way through an interactive login (its
    background thread is gone with it), the DB would otherwise show
    "connecting" forever with no thread left to ever resolve it."""
    with Session(engine) as session:
        stranded = session.exec(select(Integration).where(Integration.status == "connecting")).all()
        for integration in stranded:
            integration.status = "error"
            integration.last_error = "Login was interrupted (server restarted). Reconnect to try again."
            session.add(integration)
        if stranded:
            session.commit()


def _harden_file_permissions() -> None:
    """Best-effort: restrict the database, .env, and browser-profile
    directory to the current OS user - see app.file_permissions. The Fernet
    key (see app.security) is what actually protects the sensitive fields
    inside these; this just narrows who can read the files at all."""
    db_path = Path(get_settings().db_path)
    restrict_to_current_user(db_path, db_path.parent / ".env", PROFILE_ROOT)


def _seed_demo_if_empty() -> None:
    """First-deploy-only: a fresh demo instance shouldn't sit empty until the
    first scheduled reset fires - see app.scheduler's demo-reset job for the
    recurring version of this same call."""
    if not settings.demo_mode:
        return
    with Session(engine) as session:
        if session.exec(select(Course)).first() is None:
            reset_demo(session)
            logger.info("Demo mode: seeded initial sample data (no existing courses found).")


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    _recover_stranded_logins()
    _harden_file_permissions()
    _seed_demo_if_empty()
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown() -> None:
    stop_scheduler()


def health():
    return {"status": "ok", "demo_mode": settings.demo_mode}


# Always unprefixed at plain /health, even in demo mode - both Dockerfiles'
# HEALTHCHECK hit this exact path directly. Also registered under the API
# prefix (a no-op duplicate when there is none) so the frontend's health
# check - which, like every other request, goes through the same
# `${VITE_API_BASE}${path}` pattern - resolves correctly in every deploy
# shape without a special case. See api.getHealth in the frontend client.
app.get("/health")(health)
if _api_prefix:
    app.get(f"{_api_prefix}/health")(health)


# Serves the built frontend when it's baked into this same image (see
# FRONTEND_DIST_DIR/_api_prefix above). Registered last, after every API
# router, so a real (now /api-prefixed) API path always matches first;
# anything else falls through to here and either serves the matching static
# asset or index.html, letting react-router handle client-side routes like
# /study-timer on a hard refresh.
if FRONTEND_DIST_DIR.is_dir():

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        candidate = FRONTEND_DIST_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST_DIR / "index.html")
