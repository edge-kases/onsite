#!/bin/bash
set -e

PHYLOD=http://localhost:8000

echo "=== Demo: Enterprise Deployment Control Plane ==="
echo ""

# Step 1: Baseline
echo "--- Step 1: Baseline (both agents on v1.0.0) ---"
echo "Agents:"
curl -s $PHYLOD/api/v1/admin/agents | jq
echo ""
echo "Versions:"
curl -s $PHYLOD/api/v1/admin/versions | jq
echo ""

read -p "Press Enter to release v1.1.0..."

# Step 2: Release v1.1.0
echo "--- Step 2: Release v1.1.0 (auto-upgrade for acme) ---"
curl -s -X POST $PHYLOD/api/v1/admin/release \
    -H 'Content-Type: application/json' -d '{"version_tag":"1.1.0"}' | jq
echo ""
echo "Waiting 20s for sync cycle..."
sleep 20

echo "Agents after v1.1.0 release:"
curl -s $PHYLOD/api/v1/admin/agents | jq
echo ""

read -p "Press Enter to release v1.2.0 (broken)..."

# Step 3: Release v1.2.0 (broken)
echo "--- Step 3: Release v1.2.0 (broken — triggers rollback) ---"
curl -s -X POST $PHYLOD/api/v1/admin/release \
    -H 'Content-Type: application/json' -d '{"version_tag":"1.2.0"}' | jq
echo ""
echo "Waiting 20s for sync + rollback..."
sleep 20

echo "Agents after v1.2.0 release (should rollback):"
curl -s $PHYLOD/api/v1/admin/agents | jq
echo ""
echo "Versions (1.2.0 should be broken):"
curl -s $PHYLOD/api/v1/admin/versions | jq
echo ""

echo "=== Demo complete ==="
