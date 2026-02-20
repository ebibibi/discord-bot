"""エントリーポイント — Bot + REST API + Claude Chat 同一asyncioループ"""

from __future__ import annotations

import asyncio
import os
import signal

from dotenv import load_dotenv

from claude_discord.claude.runner import ClaudeRunner
from claude_discord.cogs.auto_upgrade import AutoUpgradeCog
from claude_discord.cogs.session_manage import SessionManageCog
from claude_discord.cogs.skill_command import SkillCommandCog
from claude_discord.cogs.webhook_trigger import WebhookTriggerCog
from claude_discord.database.models import init_db
from claude_discord.database.notification_repo import NotificationRepository
from claude_discord.database.settings_repo import SettingsRepository
from claude_discord.ext.api_server import ApiServer

from .bot import EbiBot
from .cogs.auto_upgrade import EBIBOT_UPGRADE_CONFIG
from claude_discord.cogs.claude_chat import ClaudeChatCog
from .cogs.docs_sync import DOCS_SYNC_TRIGGERS
from .cogs.reminder import ReminderCog
from .cogs.watchdog import WatchdogCog
from .database.models import Database
from .database.repository import NotificationRepository as EbiBotNotificationRepo
from .utils.logger import get_logger

logger = get_logger(__name__)


async def _init_claude_session_db(db_path: str) -> None:
    """Initialize the Claude session database using bridge's init_db (with migrations)."""
    from pathlib import Path

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    await init_db(db_path)
    logger.info(f"Claude session DB初期化完了: {db_path}")


def main() -> None:
    load_dotenv()

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        logger.error("DISCORD_BOT_TOKEN が設定されていません。.envを確認してください。")
        raise SystemExit(1)

    channel_id_str = os.getenv("DISCORD_CHANNEL_ID", "")
    channel_id = int(channel_id_str) if channel_id_str.isdigit() else None

    claude_channel_id_str = os.getenv("CLAUDE_CHANNEL_ID", "")
    claude_channel_id = int(claude_channel_id_str) if claude_channel_id_str.isdigit() else None

    api_host = os.getenv("API_HOST", "127.0.0.1")
    api_port = int(os.getenv("API_PORT", "8099"))

    # DB初期化（通知用 — EbiBot独自のsyncリポ）
    db = Database(db_path="data/bot.db")
    db.initialize()
    ebibot_repo = EbiBotNotificationRepo(db)

    # Bot作成
    bot = EbiBot(default_channel_id=channel_id)

    # Claude Runner
    claude_runner = None
    if claude_channel_id:
        allowed_tools_str = os.getenv("CLAUDE_ALLOWED_TOOLS", "")
        allowed_tools = [t.strip() for t in allowed_tools_str.split(",") if t.strip()] or None
        claude_runner = ClaudeRunner(
            command=os.getenv("CLAUDE_COMMAND", "claude"),
            model=os.getenv("CLAUDE_MODEL", "sonnet"),
            permission_mode=os.getenv("CLAUDE_PERMISSION_MODE", "acceptEdits"),
            working_dir=os.getenv("CLAUDE_WORKING_DIR", "") or None,
            timeout_seconds=int(os.getenv("SESSION_TIMEOUT_SECONDS", "300")),
            allowed_tools=allowed_tools,
            dangerously_skip_permissions=os.getenv(
                "CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS", "",
            ).lower() in ("1", "true", "yes"),
        )

    # bridge の NotificationRepository（REST API用）
    notification_repo = NotificationRepository("data/notifications.db")

    # bridge の ApiServer（REST API）
    api_server = ApiServer(
        repo=notification_repo,
        bot=bot,
        default_channel_id=channel_id,
        host=api_host,
        port=api_port,
    )

    async def start_all() -> None:
        # 通知DBスキーマ初期化
        await notification_repo.init_db()
        async with bot:
            # EbiBot独自 Cog
            await bot.add_cog(ReminderCog(bot, ebibot_repo))
            await bot.add_cog(WatchdogCog(bot))

            # Claude Chat Cog + 関連
            if claude_channel_id and claude_runner:
                session_db_path = "data/sessions.db"
                await _init_claude_session_db(session_db_path)

                from .database.claude_session_repository import ClaudeSessionRepository
                session_repo = ClaudeSessionRepository(session_db_path)

                owner_id_str = os.getenv("DISCORD_OWNER_ID", "")
                if not owner_id_str.isdigit():
                    logger.error(
                        "DISCORD_OWNER_ID 未設定 — Claude Chat Cogを無効化"
                    )
                else:
                    allowed_user_ids = {int(owner_id_str)}
                    claude_cog = ClaudeChatCog(
                        bot=bot,
                        repo=session_repo,
                        runner=claude_runner,
                        max_concurrent=int(
                            os.getenv("MAX_CONCURRENT_SESSIONS", "3"),
                        ),
                        allowed_user_ids=allowed_user_ids,
                    )
                    await bot.add_cog(claude_cog)
                    logger.info(
                        "Claude Chat Cog追加完了 (channel: %d)",
                        claude_channel_id,
                    )

                    # Session Management Cog
                    settings_repo = SettingsRepository(session_db_path)
                    session_manage_cog = SessionManageCog(
                        bot=bot,
                        repo=session_repo,
                        cli_sessions_path=os.path.expanduser(
                            "~/.claude/projects",
                        ),
                        settings_repo=settings_repo,
                    )
                    await bot.add_cog(session_manage_cog)
                    logger.info("Session Manage Cog追加完了")

                    # Skill Command Cog
                    skill_cog = SkillCommandCog(
                        bot=bot,
                        repo=session_repo,
                        runner=claude_runner,
                        claude_channel_id=claude_channel_id,
                        allowed_user_ids=allowed_user_ids,
                    )
                    await bot.add_cog(skill_cog)
                    logger.info("Skill Command Cog追加完了")

                    # Docs Sync — bridge の WebhookTriggerCog
                    docs_sync_cog = WebhookTriggerCog(
                        bot=bot,
                        runner=claude_runner,
                        triggers=DOCS_SYNC_TRIGGERS,
                        channel_ids={claude_channel_id},
                    )
                    await bot.add_cog(docs_sync_cog)
                    logger.info("Docs Sync Cog追加完了 (WebhookTriggerCog)")

                    # Auto Upgrade — bridge の AutoUpgradeCog
                    # DrainAware protocol で Claude Chat + Webhook Trigger を自動検出
                    auto_upgrade_cog = AutoUpgradeCog(
                        bot=bot,
                        config=EBIBOT_UPGRADE_CONFIG,
                    )
                    await bot.add_cog(auto_upgrade_cog)
                    logger.info("Auto Upgrade Cog追加完了 (AutoUpgradeCog)")
            else:
                logger.warning("CLAUDE_CHANNEL_ID 未設定 — Claude Chat Cog無効")

            # REST API起動
            await api_server.start()
            logger.info("全コンポーネント起動完了")

            # Bot起動（ブロッキング）
            await bot.start(token)

    async def shutdown() -> None:
        logger.info("シャットダウン開始...")
        await api_server.stop()
        if not bot.is_closed():
            await bot.close()
        db.close()
        logger.info("シャットダウン完了")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.ensure_future(shutdown()))

    try:
        loop.run_until_complete(start_all())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        loop.run_until_complete(shutdown())
        loop.close()


if __name__ == "__main__":
    main()
