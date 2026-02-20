#!/bin/bash
set -e
cd /home/ebi/discord-bot

# Load webhook URL from .env (optional - notifications skipped if not set)
DISCORD_WEBHOOK_URL=""
if [ -f .env ]; then
    DISCORD_WEBHOOK_URL=$(grep -E '^DISCORD_WEBHOOK_URL=' .env | cut -d'=' -f2- | tr -d '"' || true)
fi

send_webhook() {
    local message="$1"
    if [ -n "$DISCORD_WEBHOOK_URL" ]; then
        # Escape special JSON characters
        local escaped
        escaped=$(printf '%s' "$message" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')
        curl -s -o /dev/null -X POST "$DISCORD_WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -d "{\"content\": $escaped}" || echo "[pre-start] WARNING: Failed to send webhook notification" >&2
    else
        echo "[pre-start] No DISCORD_WEBHOOK_URL configured, skipping notification" >&2
    fi
}

# Pull latest EbiBot code
git pull --ff-only origin master 2>&1 || echo "git pull skipped (not on master or conflict)"

# Update ccdb package to latest
/home/ebi/.local/bin/uv lock --upgrade-package claude-code-discord-bridge 2>&1
/home/ebi/.local/bin/uv sync 2>&1

# ── Import validation ──
# Temporarily disable set -e so we can handle import failure ourselves
set +e
IMPORT_ERROR=$(.venv/bin/python -c "from src.main import main" 2>&1)
IMPORT_EXIT=$?
set -e

if [ $IMPORT_EXIT -ne 0 ]; then
    echo "[pre-start] ERROR: Import validation failed after update:" >&2
    echo "$IMPORT_ERROR" >&2

    send_webhook "⚠️ **EbiBot pre-start failed**: Import error after update.\n\`\`\`\n${IMPORT_ERROR}\n\`\`\`\nAttempting rollback to previous commit..."

    # Rollback to previous commit
    echo "[pre-start] Rolling back to HEAD~1..." >&2
    git checkout HEAD~1 2>&1

    # Re-sync dependencies for the rolled-back code
    /home/ebi/.local/bin/uv sync 2>&1

    # Test import again
    set +e
    ROLLBACK_ERROR=$(.venv/bin/python -c "from src.main import main" 2>&1)
    ROLLBACK_EXIT=$?
    set -e

    if [ $ROLLBACK_EXIT -ne 0 ]; then
        echo "[pre-start] FATAL: Import still fails after rollback:" >&2
        echo "$ROLLBACK_ERROR" >&2

        send_webhook "🔴 **EbiBot rollback also failed**: Import error persists after reverting to previous commit.\n\`\`\`\n${ROLLBACK_ERROR}\n\`\`\`\nManual intervention required."

        exit 1
    fi

    echo "[pre-start] Rollback successful. Bot will start on previous commit." >&2
    send_webhook "✅ **EbiBot rollback succeeded**: Bot will start on previous commit ($(git rev-parse --short HEAD))."
fi

# ── ccdb worktree cleanup ──
if [ -x /home/ebi/claude-code-discord-bridge/scripts/cleanup_worktrees.sh ]; then
    /home/ebi/claude-code-discord-bridge/scripts/cleanup_worktrees.sh 2>&1 || true
fi

echo "[pre-start] All checks passed. Starting bot." >&2
