"""Claude Code session repository — re-export from bridge framework.

Previously this was a local copy of the session repository logic.
Now it delegates entirely to the bridge's SessionRepository which has
additional features (origin tracking, summary, list_all, get_by_session_id).
"""

from __future__ import annotations

from claude_discord.database.repository import SessionRecord, SessionRepository

# Re-export for backwards compatibility
ClaudeSessionRepository = SessionRepository

__all__ = ["ClaudeSessionRepository", "SessionRecord", "SessionRepository"]
