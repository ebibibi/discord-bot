# EbiBot

Personal Discord Bot built with [claude-code-discord-bridge](https://github.com/ebibibi/claude-code-discord-bridge).

This is a real-world example of how to use claude-code-discord-bridge as a package — adding custom Cogs for personal workflows on top of the shared framework.

## What EbiBot Does

| Cog | Source | Purpose |
|-----|--------|---------|
| **Claude Chat** | claude-code-discord-bridge | Full Claude Code CLI access via Discord threads |
| **Skill Command** | claude-code-discord-bridge | `/skill` slash command with autocomplete |
| **Docs Sync** | EbiBot custom | Auto-translate docs on GitHub push via webhook |
| **Reminder** | EbiBot custom | `/remind` command + scheduled notifications |
| **Watchdog** | EbiBot custom | Todoist overdue task alerts every 30 minutes |

## Architecture

```
claude-code-discord-bridge (OSS framework)
  ↓  installed as a Python package
EbiBot (this repo)
  ├── Claude Chat + Skill Command (from framework)
  ├── Reminder, Watchdog, Docs Sync (custom Cogs)
  └── REST API for push notifications (localhost:8099)
```

- **One bot token, one process** — all Cogs run in the same asyncio loop
- **discord.py v2** + **aiohttp** REST API
- **SQLite** for notification scheduling and Claude session persistence
- **uv** for dependency management

## Setup

```bash
git clone https://github.com/ebibibi/discord-bot.git
cd discord-bot

cp .env.example .env
# Edit .env with your tokens and channel IDs

uv sync
uv run python -m src.main
```

## Configuration

| Variable | Description |
|----------|-------------|
| `DISCORD_BOT_TOKEN` | Discord bot token |
| `DISCORD_CHANNEL_ID` | Channel for push notifications |
| `DISCORD_OWNER_ID` | Your Discord user ID (authorization) |
| `CLAUDE_CHANNEL_ID` | Channel for Claude Code chat |
| `CLAUDE_COMMAND` | Path to Claude Code CLI (`claude`) |
| `CLAUDE_MODEL` | Model to use (`sonnet`) |
| `CLAUDE_PERMISSION_MODE` | Permission mode (`acceptEdits`) |
| `CLAUDE_WORKING_DIR` | Working directory for Claude |
| `MAX_CONCURRENT_SESSIONS` | Max parallel Claude sessions (`3`) |
| `SESSION_TIMEOUT_SECONDS` | Session timeout (`300`) |
| `API_HOST` | REST API bind address (`127.0.0.1`) |
| `API_PORT` | REST API port (`8099`) |

## REST API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/notify` | Send immediate notification |
| POST | `/api/schedule` | Schedule a notification |
| GET | `/api/scheduled` | List pending notifications |
| DELETE | `/api/scheduled/{id}` | Cancel a notification |
| GET | `/api/health` | Health check |

## Updating the Framework

When claude-code-discord-bridge gets new features:

```bash
uv lock --upgrade-package claude-code-discord-bridge && uv sync
```

## How to Use This as a Template

Want to build your own Claude Code Discord bot? Here's the pattern:

1. Install the framework: `uv add git+https://github.com/ebibibi/claude-code-discord-bridge.git`
2. Import the Cogs you need: `from claude_discord import ClaudeChatCog, ClaudeRunner`
3. Add your own custom Cogs for your specific workflows
4. See this repo for a working example

## Testing

```bash
uv run pytest tests/ -v --cov=src
```

## License

MIT
