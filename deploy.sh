#!/usr/bin/env bash
# ── deploy.sh — Pull latest code and rebuild/restart Docker containers ─────────
#
# Usage:
#   bash deploy.sh
#
# This script:
#   1. Pulls the latest code from the current branch
#   2. Rebuilds Docker images (picks up any code or dependency changes)
#   3. Restarts containers with zero-downtime (--build -d)
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

echo ""
echo "══════════════════════════════════════════"
echo "  Stock Market Analyzer — Deploy"
echo "══════════════════════════════════════════"
echo ""

# Ensure .env exists
if [ ! -f ".env" ]; then
  echo "ERROR: .env file not found."
  echo "  Run:  cp .env.example .env  — then fill in your keys."
  exit 1
fi

echo "▶ Pulling latest code..."
git pull

echo ""
echo "▶ Rebuilding and restarting containers..."
docker compose up --build -d

echo ""
echo "══════════════════════════════════════════"
echo "  ✓ Deployed successfully!"
echo ""
echo "  App:       http://localhost"
echo "  API docs:  http://localhost:8090/docs"
echo "══════════════════════════════════════════"
echo ""
