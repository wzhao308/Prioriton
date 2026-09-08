from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session
from app.demo import simulate_connect
from app.models import Integration
from app.schemas import IntegrationRead, SyncResult
from app.sync_service import run_sync

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/run", response_model=SyncResult)
def sync_now(session: Session = Depends(get_session)):
    if get_settings().demo_mode:
        # A simulated integration's encrypted_credentials isn't a real
        # Fernet-encrypted token/profile path (see app.demo.simulate_connect)
        # - the real sync engine would just fail trying to decrypt it. Re-run
        # the simulation for whatever's currently "connected" instead, which
        # refreshes last_synced_at the same way a real sync would.
        integrations = session.exec(select(Integration)).all()
        for integration in integrations:
            simulate_connect(integration.type, session)
        return SyncResult(
            integrations_synced=len(integrations),
            courses_upserted=0,
            tasks_upserted=0,
            errors=[],
        )
    return run_sync(session)


@router.get("/status", response_model=list[IntegrationRead])
def sync_status(session: Session = Depends(get_session)):
    return session.exec(select(Integration)).all()
