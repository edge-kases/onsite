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

# 5. Seed: release v1.0.0
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
