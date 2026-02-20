#!/bin/bash
# EbiBot pre-start script — runs as ExecStartPre before bot process.
# Ensures EbiBot code and ccdb dependency are always at latest.
set -e
cd /home/ebi/discord-bot

UV=/home/ebi/.local/bin/uv

# ── Webhook helper ──
DISCORD_WEBHOOK_URL=""
if [ -f .env ]; then
    DISCORD_WEBHOOK_URL=$(grep -E '^DISCORD_WEBHOOK_URL=' .env | cut -d'=' -f2- | tr -d '"' || true)
fi
send_webhook() {
    local message="$1"
    if [ -n "$DISCORD_WEBHOOK_URL" ]; then
        local escaped
        escaped=$(printf '%s' "$message" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')
        curl -s -o /dev/null -X POST "$DISCORD_WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -d "{\"content\": $escaped}" || echo "[pre-start] WARNING: webhook failed" >&2
    fi
}

# ── Step 1: Pull latest EbiBot code ──
# Stash any local changes (e.g. uv.lock modified by previous pre-start)
# so git pull never fails on unstaged changes.
echo "[pre-start] Pulling latest EbiBot code..." >&2
set +e
STASHED=0
if ! git diff --quiet 2>/dev/null; then
    git stash push -m "pre-start auto-stash" --include-untracked 2>&1
    STASHED=1
fi
git pull --ff-only origin master 2>&1
PULL_EXIT=$?
if [ $STASHED -eq 1 ]; then
    git stash drop 2>&1 || true
fi
set -e

if [ $PULL_EXIT -ne 0 ]; then
    echo "[pre-start] WARNING: git pull failed (exit $PULL_EXIT), continuing with current code" >&2
fi

# ── Step 2: Update ccdb to latest git HEAD ──
echo "[pre-start] Upgrading ccdb to latest..." >&2
$UV lock --upgrade-package claude-code-discord-bridge 2>&1
$UV sync 2>&1

# Record what was installed
CCDB_COMMIT=$(.venv/bin/python -c "
import importlib.metadata, json
d = json.loads(importlib.metadata.distribution('claude-code-discord-bridge').read_text('direct_url.json'))
print(d.get('vcs_info',{}).get('commit_id','unknown')[:7])
" 2>/dev/null || echo "unknown")
echo "[pre-start] ccdb installed: ${CCDB_COMMIT}" >&2

# ── Step 3: Commit uv.lock if changed ──
# This prevents "unstaged changes" on next restart and keeps the repo clean.
if ! git diff --quiet uv.lock 2>/dev/null; then
    echo "[pre-start] Committing uv.lock update (ccdb -> ${CCDB_COMMIT})..." >&2
    git add uv.lock
    git commit -m "chore(auto): update ccdb to ${CCDB_COMMIT}" --no-verify 2>&1
    git push origin master 2>&1 || echo "[pre-start] WARNING: git push failed, will retry next restart" >&2
fi

# ── Step 4: Validate imports ──
echo "[pre-start] Validating imports..." >&2
set +e
IMPORT_ERROR=$(.venv/bin/python -c "from src.main import main" 2>&1)
IMPORT_EXIT=$?
set -e

if [ $IMPORT_EXIT -ne 0 ]; then
    echo "[pre-start] ERROR: Import validation failed:" >&2
    echo "$IMPORT_ERROR" >&2
    send_webhook "⚠️ **EbiBot pre-start failed**: Import error after update.\n\`\`\`\n${IMPORT_ERROR}\n\`\`\`\nAttempting rollback..."

    echo "[pre-start] Rolling back..." >&2
    git revert --no-edit HEAD 2>&1 || git checkout HEAD~1 2>&1
    $UV sync 2>&1

    set +e
    ROLLBACK_ERROR=$(.venv/bin/python -c "from src.main import main" 2>&1)
    ROLLBACK_EXIT=$?
    set -e

    if [ $ROLLBACK_EXIT -ne 0 ]; then
        echo "[pre-start] FATAL: Import still fails after rollback" >&2
        send_webhook "🔴 **EbiBot rollback also failed**.\n\`\`\`\n${ROLLBACK_ERROR}\n\`\`\`\nManual intervention required."
        exit 1
    fi

    send_webhook "✅ **EbiBot rollback succeeded**: running on $(git rev-parse --short HEAD)."
fi

# ── Step 5: Cleanup stale ccdb worktrees ──
if [ -x /home/ebi/claude-code-discord-bridge/scripts/cleanup_worktrees.sh ]; then
    /home/ebi/claude-code-discord-bridge/scripts/cleanup_worktrees.sh 2>&1 || true
fi

# ── Step 6: Sanity check — no editable/pth installs of ccdb ──
PTH_FILE=".venv/lib/python3.10/site-packages/_claude_code_discord_bridge.pth"
if [ -f "$PTH_FILE" ]; then
    echo "[pre-start] WARNING: Removing stale editable install of ccdb" >&2
    rm -f "$PTH_FILE"
    rm -rf .venv/lib/python3.10/site-packages/claude_code_discord_bridge-*.dist-info
    $UV sync --reinstall-package claude-code-discord-bridge 2>&1
fi

echo "[pre-start] All checks passed. Starting bot (ccdb=${CCDB_COMMIT})." >&2
