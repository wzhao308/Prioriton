import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app import browser_login, security
from app.adapters.canvas import CanvasAdapter
from app.adapters.gradescope import LOGIN_URL as GRADESCOPE_LOGIN_URL
from app.adapters.gradescope import is_logged_in as gradescope_is_logged_in
from app.adapters.prairielearn import LOGIN_URL as PRAIRIELEARN_LOGIN_URL
from app.adapters.prairielearn import is_logged_in as prairielearn_is_logged_in
from app.config import get_settings
from app.db import engine, get_session
from app.models import Integration
from app.schemas import ConnectCanvasRequest, IntegrationRead
from app.sync_service import run_sync

logger = logging.getLogger("prioriton.integrations")

router = APIRouter(prefix="/integrations", tags=["integrations"])

# Platform types whose credential is really a local browser-profile directory
# path (populated by an interactive login), not a token - see browser_login.py.
BROWSER_LOGIN_TYPES = {"gradescope", "prairielearn"}


def _reject_in_demo_mode() -> None:
    """Connecting a real account on a shared public demo would mean a
    stranger's real Canvas token or Gradescope/PrairieLearn session landing
    on an instance anyone can reach - see app.config.Settings.demo_mode."""
    if get_settings().demo_mode:
        raise HTTPException(
            status_code=403,
            detail="This is a public demo with sample data - connecting a real account is disabled here.",
        )


@router.get("", response_model=list[IntegrationRead])
def list_integrations(session: Session = Depends(get_session)):
    return session.exec(select(Integration)).all()


@router.post("/canvas", response_model=IntegrationRead)
def connect_canvas(body: ConnectCanvasRequest, session: Session = Depends(get_session)):
    _reject_in_demo_mode()
    adapter = CanvasAdapter(base_url=body.base_url, token=body.token)
    try:
        adapter.test_connection()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        adapter.close()

    integration = session.exec(select(Integration).where(Integration.type == "canvas")).first()
    if integration is None:
        integration = Integration(type="canvas")

    integration.base_url = body.base_url.rstrip("/")
    integration.encrypted_credentials = security.encrypt(body.token)
    integration.status = "connected"
    integration.last_error = None
    session.add(integration)
    session.commit()
    session.refresh(integration)

    # Populate courses/tasks right away so onboarding feels immediate.
    run_sync(session)
    session.refresh(integration)
    return integration


def _start_browser_login(platform: str, login_url: str, success_check, session: Session) -> Integration:
    """Shared by every platform whose credential is a browser profile
    (Gradescope, PrairieLearn) - creates/reuses the Integration row, kicks off
    the interactive login, and runs a sync immediately on success. Platform-
    specific only in which URL/success-check it's given.
    """
    if browser_login.is_login_running(platform):
        raise HTTPException(status_code=409, detail=f"A {platform} login is already in progress.")

    integration = session.exec(select(Integration).where(Integration.type == platform)).first()
    if integration is None:
        integration = Integration(type=platform, encrypted_credentials="")

    profile_path = str(browser_login.profile_dir(platform))
    integration.encrypted_credentials = security.encrypt(profile_path)
    integration.status = "connecting"
    integration.last_error = None
    session.add(integration)
    session.commit()
    session.refresh(integration)
    integration_id = integration.id

    def on_result(ok: bool, error: str | None) -> None:
        with Session(engine) as bg_session:
            integ = bg_session.get(Integration, integration_id)
            if integ is None:
                return
            if ok:
                integ.status = "connected"
                integ.last_error = None
                bg_session.add(integ)
                bg_session.commit()
                # Populate courses/tasks right away, same as Canvas's connect flow -
                # by now browser_login has already saved the authenticated cookie
                # jar for the next adapter open to pick up.
                try:
                    run_sync(bg_session)
                except Exception:  # noqa: BLE001 - a failed first sync shouldn't hide the successful login
                    logger.exception("Post-login sync failed for %s", platform)
            else:
                integ.status = "error"
                integ.last_error = error
                bg_session.add(integ)
                bg_session.commit()

    logger.info("Starting interactive %s login (integration id=%s)", platform, integration_id)
    browser_login.start_interactive_login(platform, login_url, success_check, on_result)
    return integration


@router.post("/gradescope/start-login", response_model=IntegrationRead)
def start_gradescope_login(session: Session = Depends(get_session)):
    _reject_in_demo_mode()
    return _start_browser_login("gradescope", GRADESCOPE_LOGIN_URL, gradescope_is_logged_in, session)


@router.post("/prairielearn/start-login", response_model=IntegrationRead)
def start_prairielearn_login(session: Session = Depends(get_session)):
    _reject_in_demo_mode()
    return _start_browser_login("prairielearn", PRAIRIELEARN_LOGIN_URL, prairielearn_is_logged_in, session)


@router.delete("/{integration_id}", status_code=204)
def disconnect_integration(integration_id: int, session: Session = Depends(get_session)):
    integration = session.get(Integration, integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    if integration.type in BROWSER_LOGIN_TYPES:
        browser_login.delete_profile(integration.type)
        browser_login.delete_cookies(integration.type)
    session.delete(integration)
    session.commit()
