# Enterprise Deployment Control Plane

Pull-based system for managing deployments across enterprise customer environments. Agents in customer environments poll the control plane for version updates — no inbound connections required.

## Architecture

```
                        ┌──────────────────────────┐
                        │         phylod            │
                        │    (control plane)        │
                        │  - version registry       │
                        │  - sync protocol          │
                        │  - binary serving         │
                        │  - PostgreSQL state       │
                        └──────┬──────────┬─────────┘
                    outbound   │          │  outbound
                    (pull)     │          │  (pull)
              ┌────────────────┘          └────────────────┐
              ▼                                            ▼
┌──────────────────────────┐             ┌──────────────────────────┐
│  tenant-acme             │             │  tenant-globex           │
│  auto_upgrade=true       │             │  auto_upgrade=false      │
│  ┌──────────────────────┐│             │ ┌──────────────────────┐ │
│  │ Data Plane (PID 1)   ││             │ │ Data Plane (PID 1)   │ │
│  │  polls → phylod      ││             │ │  polls → phylod      │ │
│  │  manages lifecycle   ││             │ │  manages lifecycle   │ │
│  │         │            ││             │ │         │            │ │
│  │  Agent (subprocess)  ││             │ │  Agent (subprocess)  │ │
│  │  :8080               ││             │ │  :8080               │ │
│  └──────────────────────┘│             │ └──────────────────────┘ │
└──────────────────────────┘             └──────────────────────────┘
```

## Quick Start

**Prerequisites:** minikube, docker, kubectl, curl, jq

```bash
# Setup: start minikube, build images, deploy everything
./scripts/setup.sh

# Port-forward (separate terminal)
kubectl port-forward -n phylo-system svc/phylod 8000:8000

# Run the 3-step demo
./scripts/demo.sh

# Teardown
./scripts/teardown.sh
```

## Demo Walkthrough

| Step | What happens | What it demonstrates |
|------|-------------|---------------------|
| 1. Baseline | Both agents on v1.0.0, healthy | Version tracking, heartbeat sync |
| 2. Release v1.1.0 | Acme upgrades, Globex stays | Auto-upgrade opt-in/out |
| 3. Release v1.2.0 (broken) | Acme attempts → crashes → auto-rollback to v1.1.0, version marked broken globally | Failure detection, rollback, implicit canary |

## Assumptions & Decisions

**Assumptions (MVP scope):**
- Simulated infra via minikube in different namespaces(no real cloud resources)
- Agent binaries are single Python files (simulating real artifacts)
- No authentication

**Key decisions:**
- **Pull-based** — agents initiate all connections; works behind any firewall/NAT
- **Two-process model** — data plane (PID 1) manages agent as hot-swappable subprocess in one container
- **Implicit canary** — first agent to fail on a version marks it broken globally, preventing fleet-wide rollout
- **Timestamp ordering** — admin controls rollout order via release time, not semver
- **Local rollback** — one level deep, immediate, no network needed

See [DESIGN.md](DESIGN.md) for detailed rationale, tradeoffs, and failure modes.

## Project Structure

```
phylod/              Control plane (FastAPI + PostgreSQL)
  app/               API server, sync logic, models
  versions/          Pre-packaged agent binaries (1.0.0, 1.1.0, 1.2.0)
agent/               Data plane + baked-in agent
  dataplane/         Polling loop, process manager, sync client
  agent/             Initial agent binary (v1.0.0)
k8s/                 Kubernetes manifests (namespaces, deployments, services)
scripts/             setup.sh, demo.sh, teardown.sh for demo purpose
```

## Deliverables

- **Working Prototype** — this repo, runnable via Quick Start above
- **Design Notes** — [DESIGN.md](DESIGN.md)
- **AI Session Transcripts** — [plan-with-claude.txt](plan-with-claude.txt)
