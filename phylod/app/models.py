from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class Version(Base):
    __tablename__ = "versions"
    version_tag = Column(String(32), primary_key=True)
    released_at = Column(DateTime, nullable=True)
    is_broken = Column(Boolean, default=False)
    is_released = Column(Boolean, default=False)


class Agent(Base):
    __tablename__ = "agents"
    agent_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    current_version = Column(String(32))
    last_stable_version = Column(String(32))
    health_status = Column(String(16), default="unknown")
    auto_upgrade = Column(Boolean, default=True)
    last_heartbeat = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
