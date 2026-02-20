#!/bin/bash
set -e
cd /home/ebi/discord-bot

# Pull latest EbiBot code
git pull --ff-only origin master 2>&1 || echo "git pull skipped (not on master or conflict)"

# Update ccdb package to latest
/home/ebi/.local/bin/uv lock --upgrade-package claude-code-discord-bridge 2>&1
/home/ebi/.local/bin/uv sync 2>&1
