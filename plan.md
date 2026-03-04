# Enterprise Deployment Control Plane — Implementation Plan

## Architecture

```
                        ┌──────────────────────────┐
                        │    Artifact Registry      │
                        │  (simulated: pre-built    │
                        │   bins in phylod image)   │
                        └────────────┬─────────────┘
                                     │ scanned on startup
                        ┌────────────▼─────────────┐
                        │         phylod            │
                        │  (control plane, k8s svc) │
                        │  ┌─────────────────────┐  │
                        │  │   FastAPI Server     │  │
                        │  │  - /agent/sync       │  │
                        │  │  - /versions binary  │  │
                        │  │  - /admin endpoints  │  │
                        │  └────────┬────────────┘  │
                        │       ┌───▼──────┐        │
                        │       │ Postgres │        │
                        │       └──────────┘        │
                        └──────┬──────────┬─────────┘
                     outbound  │          │  outbound
                     (pull)    │          │  (pull)
              ┌────────────────┘          └────────────────┐
              ▼                                            ▼
┌──────────────────────────┐             ┌──────────────────────────┐
│  Container: phylo-agent  │             │  Container: phylo-agent  │
│  namespace: tenant-acme  │             │  namespace: tenant-globex│
│ ┌──────────────────────┐ │             │ ┌──────────────────────┐ │
│ │ Data Plane (PID 1)   │ │             │ │ Data Plane (PID 1)   │ │
│ │  - polls phylod      │ │             │ │  - polls phylod      │ │
│ │  - reports health    │ │             │ │  - reports health    │ │
│ │  - manages agent proc│ │             │ │  - manages agent proc│ │
│ │         │            │ │             │ │         │            │ │
│ │         ▼            │ │             │ │         ▼            │ │
│ │  Agent (subprocess)  │ │             │ │  Agent (subprocess)  │ │
│ │  :8080 ← customer    │ │             │ │  :8080 ← customer    │ │
│ └──────────────────────┘ │             │ └──────────────────────┘ │
└──────────────────────────┘             └──────────────────────────┘
```

## Decisions & Assumptions

1. **Pull-based**: data plane → phylod only, no inbound to customer env
2. **One container, two processes**: data plane (PID 1, entrypoint) + agent (child process). Ship one artifact to customer, env-agnostic (not K8s-specific)
3. **Auto-upgrade opt-in/out**: per data-plane config via env var, reported to phylod in each sync. When auto_upgrade=false, phylod records status but never instructs upgrade
4. **Rollback**: data plane handles locally using rollback binary on disk; reports failed_version to phylod so it can mark version as globally broken
5. **Broken version**: marked globally broken in phylod on first failure report; no other agents get instructed to upgrade to it (implicit canary)
6. **Image delivery**: assume network access for MVP; agent binaries served by phylod directly
7. **OCI containers**: all components are containers, env-agnostic (no K8s-specific features)
8. **Artifact registry**: simulated for MVP; agent binaries pre-packaged in phylod image under `versions/`; phylod scans dir on startup and registers them in DB as unreleased; admin API marks them released
9. **No auth**: skip mTLS/API keys for MVP
10. **Version ordering**: determined by `released_at` timestamp (not semver parsing); most recently released non-broken version = "latest"
11. **Agent port**: hardcoded 8080 in both agent scripts and data plane; data plane exposes no port (outbound-only)
12. **"upgrade" action can mean downgrade**: if another agent marks a version broken while this agent runs it, phylod instructs switch to an older version. Data plane treats all version switches the same — download, replace, health check. Functionally correct.
13. **Health reporting limitation (MVP)**: data plane reports "healthy" when agent is running, but does NOT report "unhealthy" during crash-loops — it just stops syncing. phylod detects this via stale last_heartbeat.

## Tech Stack

- **phylod**: Python 3.11 + FastAPI + SQLAlchemy (sync) + psycopg2-binary + PostgreSQL
- **data plane**: Python 3.11 + `requests` library
- **agent**: Python 3.11, stdlib only (`http.server`)
- **infra**: Docker, Minikube
- **K8s manifests**: raw YAML (no Helm for MVP)

Note: sync SQLAlchemy (not async) for MVP simplicity. FastAPI handles concurrency via threadpool for sync endpoints.

## Project Structure

```
/
├── phylod/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI app, lifespan (create tables + scan versions)
│   │   ├── config.py             # Settings from env: DATABASE_URL, VERSIONS_DIR
│   │   ├── db.py                 # SQLAlchemy engine + sessionmaker
│   │   ├── models.py             # ORM: Version, Agent
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── sync.py           # POST /api/v1/agent/sync
│   │   │   ├── versions.py       # GET /api/v1/versions/{tag}/binary
│   │   │   └── admin.py          # POST /admin/release, GET /admin/agents, GET /admin/versions
│   │   └── services/
│   │       ├── __init__.py
│   │       └── sync_service.py   # core sync logic (upsert agent, compute desired state)
│   └── versions/                 # pre-packaged agent binaries (copied into image)
│       ├── 1.0.0/agent.py
│       ├── 1.1.0/agent.py
│       └── 1.2.0/agent.py        # crash version
│
├── agent/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── dataplane/
│   │   ├── main.py               # entrypoint, main loop
│   │   ├── config.py             # env-based config
│   │   ├── sync_client.py        # SyncClient: sync(), download_binary()
│   │   └── process_manager.py    # ProcessManager: start(), stop(), health_check(), is_running()
│   └── agent/
│       └── agent.py              # baked-in initial agent (copy of v1.0.0)
│
├── k8s/
│   ├── namespaces.yaml
│   ├── postgres.yaml
│   ├── phylod.yaml
│   ├── tenant-acme.yaml
│   └── tenant-globex.yaml
│
├── scripts/
│   ├── setup.sh
│   ├── demo.sh
│   └── teardown.sh
│
├── plan.md
└── DESIGN.md
```

---

## Component 1: phylod (Control Plane)

### phylod config.py

```python
import os

class Settings:
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "postgresql://phylo:phylo@localhost:5432/phylo")
    VERSIONS_DIR: str = os.environ.get("VERSIONS_DIR", "versions")  # relative to CWD or absolute
```

VERSIONS_DIR defaults to `versions` (relative). In the Docker image, CWD is `/app`, so this resolves to `/app/versions/`.

### DB Schema

```sql
CREATE TABLE versions (
    version_tag   VARCHAR(32) PRIMARY KEY,
    released_at   TIMESTAMP,               -- NULL until released via admin API
    is_broken     BOOLEAN DEFAULT FALSE,
    is_released   BOOLEAN DEFAULT FALSE
);

CREATE TABLE agents (
    agent_id            VARCHAR(64) PRIMARY KEY,
    tenant_id           VARCHAR(64) NOT NULL,
    current_version     VARCHAR(32),
    last_stable_version VARCHAR(32),
    health_status       VARCHAR(16) DEFAULT 'unknown',
    auto_upgrade        BOOLEAN DEFAULT TRUE,
    last_heartbeat      TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW()
);
```

Tables auto-created on startup via `Base.metadata.create_all(engine)`.

### models.py

```python
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
```

### db.py

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .config import Settings

engine = create_engine(Settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### Startup Logic (lifespan in main.py)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Create tables
    Base.metadata.create_all(bind=engine)

    # 2. Scan versions directory, register in DB
    versions_dir = Settings.VERSIONS_DIR
    db = SessionLocal()
    try:
        for entry in os.listdir(versions_dir):
            if os.path.isdir(os.path.join(versions_dir, entry)):
                existing = db.query(Version).filter_by(version_tag=entry).first()
                if not existing:
                    db.add(Version(version_tag=entry, is_released=False, is_broken=False))
        db.commit()
    finally:
        db.close()

    yield

app = FastAPI(lifespan=lifespan)
# Include routers...
```

### API Endpoints

#### `POST /api/v1/agent/sync`

Core endpoint. Data plane calls every SYNC_INTERVAL seconds.

**Request body (Pydantic model):**
```python
class SyncRequest(BaseModel):
    agent_id: str
    tenant_id: str
    current_version: str
    health_status: str          # "healthy" | "unhealthy"
    auto_upgrade: bool
    failed_version: Optional[str] = None
```

**Response body (Pydantic model):**
```python
class SyncResponse(BaseModel):
    action: str                 # "upgrade" | "none"
    target_version: Optional[str] = None
    binary_url: Optional[str] = None
```

**Sync logic (sync_service.py) — step by step:**

```python
from datetime import datetime
from sqlalchemy.orm import Session
from ..models import Agent, Version

def handle_sync(db: Session, req: SyncRequest) -> SyncResponse:

    # 1. Upsert agent record
    agent = db.query(Agent).filter_by(agent_id=req.agent_id).first()
    if agent is None:
        # New agent — INSERT
        agent = Agent(
            agent_id=req.agent_id,
            tenant_id=req.tenant_id,
            current_version=req.current_version,
            last_stable_version=req.current_version,  # first version = stable
            health_status=req.health_status,
            auto_upgrade=req.auto_upgrade,
            last_heartbeat=datetime.utcnow(),
        )
        db.add(agent)
    else:
        # Existing agent — UPDATE
        agent.current_version = req.current_version
        agent.health_status = req.health_status
        agent.auto_upgrade = req.auto_upgrade
        agent.last_heartbeat = datetime.utcnow()

    # 2. Handle failed version report
    if req.failed_version is not None:
        version = db.query(Version).filter_by(version_tag=req.failed_version).first()
        if version:
            version.is_broken = True
        # Agent rolled back; current_version IS the stable version
        agent.last_stable_version = req.current_version

    # 3. Update last_stable if healthy (and NOT reporting failure)
    elif req.health_status == "healthy":
        if agent.last_stable_version != req.current_version:
            agent.last_stable_version = req.current_version

    db.commit()

    # 4. If auto_upgrade disabled → done
    if not req.auto_upgrade:
        return SyncResponse(action="none")

    # 5. Find latest released, non-broken version (by released_at DESC)
    latest = (
        db.query(Version)
        .filter(Version.is_released == True, Version.is_broken == False)
        .order_by(Version.released_at.desc())
        .first()
    )

    # 6. No released version, or same as current → nothing
    if latest is None or latest.version_tag == req.current_version:
        return SyncResponse(action="none")

    # 7. Different version → switch (could be upgrade or downgrade)
    return SyncResponse(
        action="upgrade",
        target_version=latest.version_tag,
        binary_url=f"/api/v1/versions/{latest.version_tag}/binary",
    )
```

#### `GET /api/v1/versions/{version_tag}/binary`

Serves raw agent.py file from phylod filesystem.

```python
from fastapi.responses import FileResponse
import os

@router.get("/api/v1/versions/{version_tag}/binary")
def get_binary(version_tag: str):
    file_path = os.path.join(Settings.VERSIONS_DIR, version_tag, "agent.py")
    if not os.path.exists(file_path):
        raise HTTPException(404, f"Binary not found for version {version_tag}")
    return FileResponse(file_path, filename="agent.py")
```

#### `POST /api/v1/admin/release`

Marks a version as released. Simulates CI pushing a new release.

**Request:**
```python
class ReleaseRequest(BaseModel):
    version_tag: str
```

**Logic:**
```python
@router.post("/api/v1/admin/release")
def release_version(req: ReleaseRequest, db: Session = Depends(get_db)):
    version = db.query(Version).filter_by(version_tag=req.version_tag).first()
    if not version:
        raise HTTPException(404, f"Version {req.version_tag} not found")
    version.is_released = True
    version.released_at = datetime.utcnow()
    db.commit()
    return {"version_tag": version.version_tag, "is_released": True, "released_at": str(version.released_at)}
```

#### `GET /api/v1/admin/agents`

Returns all agents. No pagination for MVP.

```python
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
```

#### `GET /api/v1/admin/versions`

```python
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
```

### phylod Dockerfile

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY versions/ ./versions/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Note: curl installed for health checks and setup.sh seed step via kubectl exec.

### phylod requirements.txt
```
fastapi
uvicorn[standard]
sqlalchemy
psycopg2-binary
```

---

## Component 2: phylo-agent Container (Data Plane + Agent)

### Data Plane Config (env vars)

```
AGENT_ID              (required) — unique identifier, e.g. "acme-agent-01"
TENANT_ID             (required) — tenant identifier, e.g. "tenant-acme"
PHYLOD_URL            (required) — e.g. "http://phylod.phylo-system.svc:8000"
AUTO_UPGRADE          (default: "true") — "true" or "false"
SYNC_INTERVAL         (default: "10") — seconds between polls
HEALTH_CHECK_TIMEOUT  (default: "5") — seconds to wait for /healthz
AGENT_PORT            (default: "8080") — port agent listens on
```

### File paths inside container

```
/app/dataplane/main.py              — entrypoint (CMD runs from this dir)
/app/dataplane/config.py
/app/dataplane/sync_client.py
/app/dataplane/process_manager.py
/app/agent/agent.py                 — current agent binary (initially v1.0.0)
/app/agent/agent_rollback.py        — backup of previous version (created during upgrade)
```

### Data Plane Main Loop (main.py)

```python
import sys
import os
import time
import shutil
import logging

from config import Config
from sync_client import SyncClient
from process_manager import ProcessManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dataplane")

AGENT_SCRIPT = "/app/agent/agent.py"
AGENT_ROLLBACK = "/app/agent/agent_rollback.py"
AGENT_NEW = "/app/agent/agent_new.py"


def main():
    config = Config.from_env()
    client = SyncClient(config.phylod_url)
    pm = ProcessManager()

    # ── INIT: start baked-in agent ──
    logger.info("Starting initial agent...")
    pm.start(AGENT_SCRIPT)

    # Health check with retries (up to 3 attempts, 2s apart)
    healthy = False
    for attempt in range(3):
        time.sleep(2)
        healthy = pm.health_check(config.agent_port, config.health_check_timeout)
        if healthy:
            break
        logger.warning(f"Health check attempt {attempt+1} failed, retrying...")
    if not healthy:
        logger.error("Initial agent failed health check after 3 attempts. Exiting.")
        pm.stop()
        sys.exit(1)

    current_version = pm.get_version(config.agent_port)
    failed_version = None
    logger.info(f"Agent started: version={current_version}")

    # ── RUNNING LOOP ──
    while True:
        time.sleep(config.sync_interval)

        # Runtime crash detection
        if not pm.is_running():
            logger.warning("Agent process died unexpectedly. Restarting...")
            pm.start(AGENT_SCRIPT)
            time.sleep(2)
            if pm.health_check(config.agent_port, config.health_check_timeout):
                current_version = pm.get_version(config.agent_port)
                logger.info(f"Agent restarted successfully: version={current_version}")
            else:
                logger.error("Agent restart failed. Will retry next cycle.")
            continue  # skip sync this cycle, retry next

        # Sync with phylod
        try:
            response = client.sync(
                agent_id=config.agent_id,
                tenant_id=config.tenant_id,
                current_version=current_version,
                health_status="healthy",
                auto_upgrade=config.auto_upgrade,
                failed_version=failed_version,
            )
            failed_version = None  # clear after successful report
        except Exception as e:
            logger.warning(f"Sync failed: {e}. Continuing with current agent.")
            continue

        if response["action"] == "none":
            logger.debug("No action needed.")
            continue

        # ── UPGRADE ──
        target = response["target_version"]
        binary_url = response["binary_url"]
        logger.info(f"Upgrading: {current_version} -> {target}")

        # 1. Download new binary
        try:
            client.download_binary(binary_url, AGENT_NEW)
        except Exception as e:
            logger.error(f"Binary download failed: {e}. Skipping upgrade.")
            continue

        # 2. Stop current agent
        pm.stop(timeout=5)

        # 3. Backup current → rollback
        shutil.copy2(AGENT_SCRIPT, AGENT_ROLLBACK)

        # 4. Replace with new
        shutil.move(AGENT_NEW, AGENT_SCRIPT)

        # 5. Start new agent
        pm.start(AGENT_SCRIPT)
        time.sleep(2)

        # 6. Health check new agent
        if pm.health_check(config.agent_port, config.health_check_timeout):
            current_version = pm.get_version(config.agent_port)
            logger.info(f"Upgrade SUCCESS: now on {current_version}")
        else:
            # ROLLBACK
            logger.error(f"Upgrade FAILED: {target} unhealthy. Rolling back...")
            pm.stop(timeout=5)
            shutil.copy2(AGENT_ROLLBACK, AGENT_SCRIPT)
            pm.start(AGENT_SCRIPT)
            time.sleep(2)

            if pm.health_check(config.agent_port, config.health_check_timeout):
                current_version = pm.get_version(config.agent_port)
                failed_version = target
                logger.info(f"Rollback SUCCESS: back on {current_version}. Will report {target} as failed.")
            else:
                logger.error("CRITICAL: Rollback also failed. Will retry next cycle.")


if __name__ == "__main__":
    main()
```

### ProcessManager (process_manager.py)

```python
import subprocess
import requests as http_requests  # avoid name collision


class ProcessManager:
    def __init__(self):
        self.process = None

    def start(self, script_path: str):
        """Start agent as subprocess. stdout/stderr inherited for container logging."""
        self.process = subprocess.Popen(["python", script_path])

    def stop(self, timeout: int = 5) -> bool:
        """SIGTERM, wait, then SIGKILL if needed."""
        if self.process is None:
            return True
        self.process.terminate()
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process = None
        return True

    def is_running(self) -> bool:
        if self.process is None:
            return False
        return self.process.poll() is None

    def health_check(self, port: int, timeout: int) -> bool:
        """GET /healthz, returns True if 200."""
        try:
            resp = http_requests.get(f"http://localhost:{port}/healthz", timeout=timeout)
            return resp.status_code == 200
        except Exception:
            return False

    def get_version(self, port: int) -> str:
        """Extract version from /healthz response."""
        try:
            resp = http_requests.get(f"http://localhost:{port}/healthz", timeout=3)
            return resp.json().get("version", "unknown")
        except Exception:
            return "unknown"
```

### SyncClient (sync_client.py)

```python
import requests


class SyncClient:
    def __init__(self, phylod_url: str):
        self.base_url = phylod_url.rstrip("/")

    def sync(self, agent_id, tenant_id, current_version, health_status, auto_upgrade, failed_version) -> dict:
        resp = requests.post(
            f"{self.base_url}/api/v1/agent/sync",
            json={
                "agent_id": agent_id,
                "tenant_id": tenant_id,
                "current_version": current_version,
                "health_status": health_status,
                "auto_upgrade": auto_upgrade,
                "failed_version": failed_version,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def download_binary(self, binary_url: str, dest_path: str):
        """binary_url is relative (e.g. /api/v1/versions/1.1.0/binary)."""
        resp = requests.get(f"{self.base_url}{binary_url}", timeout=30)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(resp.content)
```

### Config (config.py)

```python
import os


class Config:
    def __init__(self, agent_id, tenant_id, phylod_url, auto_upgrade, sync_interval, health_check_timeout, agent_port):
        self.agent_id = agent_id
        self.tenant_id = tenant_id
        self.phylod_url = phylod_url
        self.auto_upgrade = auto_upgrade
        self.sync_interval = sync_interval
        self.health_check_timeout = health_check_timeout
        self.agent_port = agent_port

    @classmethod
    def from_env(cls):
        return cls(
            agent_id=os.environ["AGENT_ID"],
            tenant_id=os.environ["TENANT_ID"],
            phylod_url=os.environ["PHYLOD_URL"],
            auto_upgrade=os.environ.get("AUTO_UPGRADE", "true").lower() == "true",
            sync_interval=int(os.environ.get("SYNC_INTERVAL", "10")),
            health_check_timeout=int(os.environ.get("HEALTH_CHECK_TIMEOUT", "5")),
            agent_port=int(os.environ.get("AGENT_PORT", "8080")),
        )
```

### Agent Scripts

All agents use stdlib `http.server`. Port hardcoded to 8080.

**versions/1.0.0/agent.py** (also copied to agent/agent.py as baked-in initial):
```python
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

VERSION = "1.0.0"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self._respond(200, {"version": VERSION, "status": "healthy"})
        elif self.path == "/":
            self._respond(200, {"message": f"Phylo Agent {VERSION} running"})
        else:
            self._respond(404, {"error": "not found"})

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, format, *args):
        pass  # suppress request logging

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8080), Handler)
    print(f"Agent {VERSION} listening on :8080")
    server.serve_forever()
```

**versions/1.1.0/agent.py:**
Identical but `VERSION = "1.1.0"`.

**versions/1.2.0/agent.py (CRASH VERSION):**
```python
import sys
print("Agent 1.2.0 starting... CRASH!")
sys.exit(1)
```
Exits immediately. Data plane health check fails (nothing on :8080). Triggers rollback.

### agent Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY dataplane/ ./dataplane/
COPY agent/ ./agent/
EXPOSE 8080
WORKDIR /app/dataplane
CMD ["python", "main.py"]
```

Note: WORKDIR set to `/app/dataplane` so Python finds local imports (config, sync_client, process_manager). Agent paths in code are all absolute (`/app/agent/agent.py`).

### agent requirements.txt
```
requests
```

---

## K8s / Minikube Setup

### namespaces.yaml
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: phylo-system
---
apiVersion: v1
kind: Namespace
metadata:
  name: tenant-acme
---
apiVersion: v1
kind: Namespace
metadata:
  name: tenant-globex
```

### postgres.yaml (in phylo-system)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: phylo-system
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15
        ports:
        - containerPort: 5432
        env:
        - name: POSTGRES_USER
          value: "phylo"
        - name: POSTGRES_PASSWORD
          value: "phylo"
        - name: POSTGRES_DB
          value: "phylo"
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: phylo-system
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
```

### phylod.yaml (in phylo-system)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: phylod
  namespace: phylo-system
spec:
  replicas: 1
  selector:
    matchLabels:
      app: phylod
  template:
    metadata:
      labels:
        app: phylod
    spec:
      containers:
      - name: phylod
        image: phylod:latest
        imagePullPolicy: Never
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          value: "postgresql://phylo:phylo@postgres.phylo-system.svc:5432/phylo"
---
apiVersion: v1
kind: Service
metadata:
  name: phylod
  namespace: phylo-system
spec:
  selector:
    app: phylod
  ports:
  - port: 8000
    targetPort: 8000
```

### tenant-acme.yaml
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: phylo-agent
  namespace: tenant-acme
spec:
  replicas: 1
  selector:
    matchLabels:
      app: phylo-agent
  template:
    metadata:
      labels:
        app: phylo-agent
    spec:
      containers:
      - name: phylo-agent
        image: phylo-agent:latest
        imagePullPolicy: Never
        ports:
        - containerPort: 8080
        env:
        - name: AGENT_ID
          value: "acme-agent-01"
        - name: TENANT_ID
          value: "tenant-acme"
        - name: PHYLOD_URL
          value: "http://phylod.phylo-system.svc:8000"
        - name: AUTO_UPGRADE
          value: "true"
        - name: SYNC_INTERVAL
          value: "10"
```

### tenant-globex.yaml
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: phylo-agent
  namespace: tenant-globex
spec:
  replicas: 1
  selector:
    matchLabels:
      app: phylo-agent
  template:
    metadata:
      labels:
        app: phylo-agent
    spec:
      containers:
      - name: phylo-agent
        image: phylo-agent:latest
        imagePullPolicy: Never
        ports:
        - containerPort: 8080
        env:
        - name: AGENT_ID
          value: "globex-agent-01"
        - name: TENANT_ID
          value: "tenant-globex"
        - name: PHYLOD_URL
          value: "http://phylod.phylo-system.svc:8000"
        - name: AUTO_UPGRADE
          value: "false"
        - name: SYNC_INTERVAL
          value: "10"
```

---

## Scripts

### setup.sh
```bash
#!/bin/bash
set -e

echo "=== Phylo Deployment Control Plane Setup ==="

# 1. Start minikube if not running
minikube status > /dev/null 2>&1 || minikube start
echo "[1/6] Minikube running"

# 2. Point docker to minikube's daemon
eval $(minikube docker-env)
echo "[2/6] Docker env set to minikube"

# 3. Build images
docker build -t phylod:latest ./phylod/
docker build -t phylo-agent:latest ./agent/
echo "[3/6] Images built"

# 4. Apply K8s manifests (order matters)
kubectl apply -f k8s/namespaces.yaml

kubectl apply -f k8s/postgres.yaml
echo "Waiting for postgres..."
kubectl wait --for=condition=ready pod -l app=postgres -n phylo-system --timeout=60s

kubectl apply -f k8s/phylod.yaml
echo "Waiting for phylod..."
kubectl wait --for=condition=ready pod -l app=phylod -n phylo-system --timeout=60s
echo "[4/6] Control plane deployed"

# 5. Seed: release v1.0.0 (phylod needs a moment to init DB + scan versions)
sleep 3
kubectl exec -n phylo-system deploy/phylod -- \
    curl -sf -X POST http://localhost:8000/api/v1/admin/release \
    -H 'Content-Type: application/json' -d '{"version_tag":"1.0.0"}'
echo ""
echo "[5/6] v1.0.0 released"

# 6. Deploy tenant agents
kubectl apply -f k8s/tenant-acme.yaml
kubectl apply -f k8s/tenant-globex.yaml
echo "[6/6] Tenant agents deployed"

echo ""
echo "=== Setup complete ==="
echo "Port-forward phylod:  kubectl port-forward -n phylo-system svc/phylod 8000:8000"
echo "Then:                 curl http://localhost:8000/api/v1/admin/agents | jq"
```

### teardown.sh
```bash
#!/bin/bash
echo "Deleting namespaces..."
kubectl delete namespace tenant-acme tenant-globex phylo-system --ignore-not-found
echo "Done."
```

---

## Demo Scenario

### Prep
```bash
# Terminal 1: port-forward
kubectl port-forward -n phylo-system svc/phylod 8000:8000

# Terminal 2: watch acme logs
kubectl logs -n tenant-acme -l app=phylo-agent -f

# Terminal 3: run demo commands
PHYLOD=http://localhost:8000
```

### Step 1: Baseline — both agents on v1.0.0 (wait ~20s after setup)
```bash
curl -s $PHYLOD/api/v1/admin/agents | jq
# Expect: acme-agent-01 on 1.0.0 healthy, globex-agent-01 on 1.0.0 healthy

curl -s $PHYLOD/api/v1/admin/versions | jq
# Expect: 1.0.0 released; 1.1.0 and 1.2.0 not released
```

### Step 2: Release v1.1.0 — auto-upgrade kicks in
```bash
curl -s -X POST $PHYLOD/api/v1/admin/release \
    -H 'Content-Type: application/json' -d '{"version_tag":"1.1.0"}' | jq

# Wait ~15s for sync cycle
sleep 15

curl -s $PHYLOD/api/v1/admin/agents | jq
# Expect: acme on 1.1.0 healthy; globex still on 1.0.0 (auto_upgrade=false)
```

### Step 3: Release v1.2.0 (broken) — failure detection + rollback
```bash
curl -s -X POST $PHYLOD/api/v1/admin/release \
    -H 'Content-Type: application/json' -d '{"version_tag":"1.2.0"}' | jq

# Wait ~15s
sleep 15

curl -s $PHYLOD/api/v1/admin/agents | jq
# Expect: acme STILL on 1.1.0 healthy (rolled back)

curl -s $PHYLOD/api/v1/admin/versions | jq
# Expect: 1.2.0 is_broken=true
```

### What the acme agent logs show (Terminal 2):
```
Upgrading: 1.1.0 -> 1.2.0
Agent 1.2.0 starting... CRASH!
Upgrade FAILED: 1.2.0 unhealthy. Rolling back...
Rollback SUCCESS: back on 1.1.0. Will report 1.2.0 as failed.
```

---

## Implementation Phases

### Phase 1: Project scaffolding
- Create full directory structure
- All __init__.py files (phylod/app/, routes/, services/)
- requirements.txt for both phylod and agent
- All 3 agent version scripts (1.0.0, 1.1.0, 1.2.0-crash)
- Copy 1.0.0 agent → agent/agent/agent.py (baked-in)
- **Verify**: `python phylod/versions/1.0.0/agent.py` starts, `curl localhost:8080/healthz` returns version

### Phase 2: phylod core
- config.py, db.py, models.py
- main.py with FastAPI + lifespan (create tables, scan versions)
- **Verify**: start local postgres, run uvicorn, check tables created and versions scanned in DB

### Phase 3: phylod API endpoints
- routes/sync.py + services/sync_service.py (the core sync logic)
- routes/versions.py (binary download)
- routes/admin.py (release, list agents, list versions)
- **Verify**: curl all endpoints against local uvicorn + postgres

### Phase 4: Data plane
- config.py, process_manager.py, sync_client.py, main.py
- Full loop: INIT → RUNNING with upgrade/rollback
- **Verify**: run data plane locally against local phylod, confirm upgrade + rollback flow

### Phase 5: Docker images
- Both Dockerfiles
- Build and basic smoke test
- **Verify**: images build, `docker run` starts each without errors

### Phase 6: K8s manifests + minikube
- All YAML manifests
- setup.sh, teardown.sh
- **Verify**: `./scripts/setup.sh` deploys everything, agents register with phylod

### Phase 7: End-to-end demo
- Run all 3 demo steps
- Fix bugs
- Write demo.sh
- **Verify**: full upgrade → failure → rollback cycle works

### Phase 8: Design doc
- DESIGN.md with architecture, decisions, tradeoffs, future work
- **Verify**: document is clear and complete

---

## Out of Scope (MVP)

- Dashboard/UI
- mTLS / authentication / authorization
- Air-gapped binary delivery
- Canary / percentage-based rollout policies
- Persistent storage for postgres
- Horizontal scaling of phylod
- CI/CD pipeline integration (simulated via admin API)
- Data plane self-upgrade mechanism
- Tenant management API
- Metrics / observability beyond stdout logs
