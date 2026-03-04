from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from ..db import get_db
from ..services.sync_service import handle_sync

router = APIRouter()


class SyncRequest(BaseModel):
    agent_id: str
    tenant_id: str
    current_version: str
    health_status: str
    auto_upgrade: bool
    failed_version: Optional[str] = None


class SyncResponse(BaseModel):
    action: str
    target_version: Optional[str] = None
    binary_url: Optional[str] = None


@router.post("/api/v1/agent/sync", response_model=SyncResponse)
def agent_sync(req: SyncRequest, db: Session = Depends(get_db)):
    result = handle_sync(
        db=db,
        agent_id=req.agent_id,
        tenant_id=req.tenant_id,
        current_version=req.current_version,
        health_status=req.health_status,
        auto_upgrade=req.auto_upgrade,
        failed_version=req.failed_version,
    )
    return SyncResponse(**result)
