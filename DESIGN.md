# Enterprise Deployment Control Plane — Design Document

## Problem

SaaS vendors deploying agents into customer environments need a way to manage versions, push upgrades, detect failures, and automatically roll back — without requiring inbound network access to customer infrastructure.

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
│  ┌──────────────────────┐│             │ ┌──────────────────────┐ │
│  │ Data Plane (PID 1)   ││             │ │ Data Plane (PID 1)   │ │
│  │  - polls phylod      ││             │ │  - polls phylod      │ │
│  │  - reports health    ││             │ │  - reports health    │ │
│  │  - manages agent proc││             │ │  - manages agent proc│ │
│  │         │            ││             │ │         │            │ │
│  │         ▼            ││             │ │         ▼            │ │
│  │  Agent (subprocess)  ││             │ │  Agent (subprocess)  │ │
│  │  :8080 ← customer    ││             │ │  :8080 ← customer    │ │
│  └──────────────────────┘│             │ └──────────────────────┘ │
└──────────────────────────┘             └──────────────────────────┘
```

## Key Design Decisions

### 1. Pull-based Communication

Data plane polls phylod; no inbound connections to customer environments. This works behind any firewall/NAT without special network config.

### 2. One Container, Two Processes

Data plane (PID 1, entrypoint) manages agent (child subprocess). Single artifact to ship. Data plane handles lifecycle: start, health check, upgrade, rollback. Agent is a hot-swappable binary on disk.

### 3. Sync Protocol

Single endpoint `POST /api/v1/agent/sync` handles all communication:
- Agent reports: identity, current version, health, auto_upgrade preference, failed versions
- Server responds: action (`none` or `upgrade`) with target version and binary URL

This keeps the protocol simple and stateless from the client's perspective.

### 4. Version Ordering by Release Timestamp

Not semver. `released_at DESC` determines "latest". Simplifies logic — admin controls rollout order by when they release versions. An "upgrade" action can actually be a downgrade if the current version gets marked broken.

### 5. Implicit Canary via Broken Version Marking

First agent to fail on a version reports it as broken. phylod marks it globally broken, preventing all other agents from being instructed to upgrade to it. No explicit canary policy needed for MVP — natural fleet rollout provides implicit canary behavior since agents sync at different times.

### 6. Local Rollback

Data plane keeps `agent_rollback.py` on disk. On upgrade failure (health check fails), it swaps back immediately without needing to re-download. Reports `failed_version` on next sync so phylod can mark it broken.

### 7. Auto-upgrade Opt-in/out

Per-agent env var. Reported to phylod in every sync. When `auto_upgrade=false`, phylod still tracks the agent but never instructs upgrades. Useful for conservative customers or staging environments.

## Components

### phylod (Control Plane)
- **Stack**: Python 3.11, FastAPI, SQLAlchemy (sync), PostgreSQL
- **Responsibilities**: Version registry, agent tracking, sync logic, binary serving
- **Startup**: Creates DB tables, scans `versions/` directory, registers unscanned versions as unreleased

### Data Plane
- **Stack**: Python 3.11, requests
- **Responsibilities**: Agent lifecycle management, polling phylod, executing upgrades/rollbacks
- **Loop**: Sleep → crash detection → sync → upgrade if instructed → health check → rollback if failed

### Agent
- **Stack**: Python 3.11 stdlib (`http.server`)
- **Exposes**: `/healthz` (version + status), `/` (info)
- **Versions**: 1.0.0 (working), 1.1.0 (working), 1.2.0 (crashes on start)

## API Surface

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/agent/sync` | POST | Data plane sync (heartbeat + instructions) |
| `/api/v1/versions/{tag}/binary` | GET | Download agent binary |
| `/api/v1/admin/release` | POST | Mark version as released |
| `/api/v1/admin/agents` | GET | List all agents |
| `/api/v1/admin/versions` | GET | List all versions |

## Tradeoffs

| Decision | Benefit | Cost |
|---|---|---|
| Pull-based | Works behind any firewall | Higher latency (up to SYNC_INTERVAL) |
| Single sync endpoint | Simple protocol, easy to debug | All logic in one handler |
| No auth (MVP) | Faster development | Not production-ready |
| Sync SQLAlchemy | Simpler code | Lower concurrency ceiling |
| Timestamp ordering | Simple, admin-controlled | No semantic version comparison |
| In-process rollback | Fast, no network needed | Only one rollback depth |

## Failure Modes

| Scenario | Behavior |
|---|---|
| Agent crashes after upgrade | Health check fails → rollback → report failed_version |
| Agent crashes at runtime | Data plane detects via `is_running()` → restart from disk |
| phylod unreachable | Sync fails → warning logged → agent continues running |
| Both upgrade and rollback fail | CRITICAL log → retry next cycle |
| Data plane dies | Container restarts (K8s) → starts baked-in agent |

## Future Work

- **Auth**: mTLS or API keys for agent-to-phylod communication
- **Canary policies**: Percentage-based rollout, staged deployment
- **Air-gapped delivery**: OCI registry or sidecar-based binary delivery
- **Persistent storage**: PostgreSQL PV for production
- **Observability**: Prometheus metrics, structured logging
- **Data plane self-upgrade**: Currently only agent is upgradable
- **Multi-binary agents**: Support agents with multiple files/dependencies
- **Tenant management API**: CRUD for tenants, not just agents
- **Dashboard**: Web UI for version management and fleet visibility

## Running the Demo

```bash
# Setup (requires minikube)
./scripts/setup.sh

# In a separate terminal
kubectl port-forward -n phylo-system svc/phylod 8000:8000

# Run demo
./scripts/demo.sh

# Teardown
./scripts/teardown.sh
```
