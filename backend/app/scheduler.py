import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session

from app.config import get_settings
from app.db import engine
from app.demo import reset_demo
from app.recommendation_service import maybe_generate_weekly
from app.sync_service import run_sync

logger = logging.getLogger("prioriton.scheduler")

scheduler = BackgroundScheduler()


def _scheduled_sync() -> None:
    with Session(engine) as session:
        try:
            result = run_sync(session)
            logger.info("Background sync complete: %s", result)
        except Exception:  # noqa: BLE001
            logger.exception("Background sync failed")


def _scheduled_recommendation_check() -> None:
    if get_settings().demo_mode:
        # The demo ships with a pre-written recommendation (see app.demo) and
        # never makes a real Anthropic call - a shared public instance
        # reaching its own 7-day eligibility window and silently triggering
        # a real LLM call would be exactly the open-ended cost demo mode
        # exists to avoid.
        return
    with Session(engine) as session:
        try:
            recommendation = maybe_generate_weekly(session)
            if recommendation is not None:
                logger.info("Generated a new weekly recommendation (id=%s)", recommendation.id)
        except Exception:  # noqa: BLE001
            logger.exception("Background recommendation check failed")


def _scheduled_demo_reset() -> None:
    with Session(engine) as session:
        try:
            reset_demo(session)
            logger.info("Demo mode: reset and reseeded sample data.")
        except Exception:  # noqa: BLE001
            logger.exception("Demo reset failed")


def start_scheduler() -> None:
    settings = get_settings()
    if scheduler.running:
        return
    # First run happens after one interval - real integrations are usually
    # connected via the manual "Connect"/"Sync now" flow first anyway, which
    # already syncs immediately on its own.
    scheduler.add_job(
        _scheduled_sync,
        "interval",
        minutes=settings.sync_interval_minutes,
        id="sync_all_integrations",
        replace_existing=True,
    )
    scheduler.add_job(
        _scheduled_recommendation_check,
        "interval",
        hours=settings.recommendation_check_interval_hours,
        id="recommendation_check",
        replace_existing=True,
    )
    if settings.demo_mode:
        scheduler.add_job(
            _scheduled_demo_reset,
            "interval",
            hours=settings.demo_reset_interval_hours,
            id="demo_reset",
            replace_existing=True,
        )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
