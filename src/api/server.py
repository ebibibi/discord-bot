"""EbiBot REST API — bridge の ApiServer を使用。

bridge の ApiServer がコアエンドポイント（health, notify, schedule, scheduled, cancel）を提供。
EbiBot固有のエンドポイント（test-claude等）が必要な場合はこのファイルに追加。
"""

from __future__ import annotations

from claude_discord.ext.api_server import ApiServer

# Re-export for backward compatibility
__all__ = ["ApiServer"]
