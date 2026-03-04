from datetime import datetime
from sqlalchemy.orm import Session
from ..models import Agent, Version


def handle_sync(db: Session, agent_id: str, tenant_id: str, current_version: str,
                health_status: str, auto_upgrade: bool, failed_version: str | None) -> dict:

    # 1. Upsert agent record
    agent = db.query(Agent).filter_by(agent_id=agent_id).first()
    if agent is None:
        agent = Agent(
            agent_id=agent_id,
            tenant_id=tenant_id,
            current_version=current_version,
            last_stable_version=current_version,
            health_status=health_status,
            auto_upgrade=auto_upgrade,
            last_heartbeat=datetime.utcnow(),
        )
        db.add(agent)
    else:
        agent.current_version = current_version
        agent.health_status = health_status
        agent.auto_upgrade = auto_upgrade
        agent.last_heartbeat = datetime.utcnow()

    # 2. Handle failed version report
    if failed_version is not None:
        version = db.query(Version).filter_by(version_tag=failed_version).first()
        if version:
            version.is_broken = True
        agent.last_stable_version = current_version

    # 3. Update last_stable if healthy (and NOT reporting failure)
    elif health_status == "healthy":
        if agent.last_stable_version != current_version:
            agent.last_stable_version = current_version

    db.commit()

    # 4. If auto_upgrade disabled -> done
    if not auto_upgrade:
        return {"action": "none"}

    # 5. Find latest released, non-broken version (by released_at DESC)
    latest = (
        db.query(Version)
        .filter(Version.is_released == True, Version.is_broken == False)
        .order_by(Version.released_at.desc())
        .first()
    )

    # 6. No released version, or same as current -> nothing
    if latest is None or latest.version_tag == current_version:
        return {"action": "none"}

    # 7. Different version -> switch
    return {
        "action": "upgrade",
        "target_version": latest.version_tag,
        "binary_url": f"/api/v1/versions/{latest.version_tag}/binary",
    }
