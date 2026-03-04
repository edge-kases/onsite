from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
from ..db import get_db
from ..models import Version, Agent

router = APIRouter()


class ReleaseRequest(BaseModel):
    version_tag: str


@router.post("/api/v1/admin/release")
def release_version(req: ReleaseRequest, db: Session = Depends(get_db)):
    version = db.query(Version).filter_by(version_tag=req.version_tag).first()
    if not version:
        raise HTTPException(404, f"Version {req.version_tag} not found")
    version.is_released = True
    version.released_at = datetime.utcnow()
    db.commit()
    return {"version_tag": version.version_tag, "is_released": True, "released_at": str(version.released_at)}


@router.get("/api/v1/admin/agents")
def list_agents(db: Session = Depends(get_db)):
    agents = db.query(Agent).all()
    return {"agents": [
        {
            "agent_id": a.agent_id,
            "tenant_id": a.tenant_id,
            "current_version": a.current_version,
            "last_stable_version": a.last_stable_version,
            "health_status": a.health_status,
            "auto_upgrade": a.auto_upgrade,
            "last_heartbeat": str(a.last_heartbeat) if a.last_heartbeat else None,
        }
        for a in agents
    ]}


@router.get("/api/v1/admin/versions")
def list_versions(db: Session = Depends(get_db)):
    versions = db.query(Version).all()
    return {"versions": [
        {
            "version_tag": v.version_tag,
            "released_at": str(v.released_at) if v.released_at else None,
            "is_released": v.is_released,
            "is_broken": v.is_broken,
        }
        for v in versions
    ]}
