#!/usr/bin/env bash
# ── setup-git-hook.sh — Install post-merge hook for auto-deploy on git pull ───
#
# Run this ONCE on your server after cloning the repo:
#   bash scripts/setup-git-hook.sh
#
# After that, every time you run "git pull", Docker will automatically
# rebuild and restart the containers.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

HOOK_FILE=".git/hooks/post-merge"

cat > "$HOOK_FILE" << 'HOOK'
#!/usr/bin/env bash
# Auto-deploy after git pull
set -euo pipefail

REPO_DIR="$(git rev-parse --show-toplevel)"
cd "$REPO_DIR"

echo ""
echo "══════════════════════════════════════════"
echo "  Stock Market Analyzer — Auto-Deploy"
echo "══════════════════════════════════════════"
echo ""
echo "▶ Rebuilding and restarting containers..."
docker compose up --build -d
echo ""
echo "  ✓ Done! App running at http://localhost"
echo "══════════════════════════════════════════"
echo ""
HOOK

chmod +x "$HOOK_FILE"

echo ""
echo "✓ Git post-merge hook installed."
echo ""
echo "  Every 'git pull' will now automatically rebuild"
echo "  and restart your Docker containers."
echo ""
echo "  To test manually, run:  bash deploy.sh"
echo ""
