from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db import get_session
from app.models import Integration
from app.schemas import IntegrationRead, SyncResult
from app.sync_service import run_sync

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/run", response_model=SyncResult)
def sync_now(session: Session = Depends(get_session)):
    return run_sync(session)


@router.get("/status", response_model=list[IntegrationRead])
def sync_status(session: Session = Depends(get_session)):
    return session.exec(select(Integration)).all()
