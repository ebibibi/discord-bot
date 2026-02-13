"""エントリーポイント — Bot + REST API同一asyncioループ"""

import asyncio
import os
import signal

from dotenv import load_dotenv

from .bot import EbiBot
from .api.server import APIServer
from .cogs.reminder import ReminderCog
from .cogs.watchdog import WatchdogCog
from .database.models import Database
from .database.repository import NotificationRepository
from .utils.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    load_dotenv()

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        logger.error("DISCORD_BOT_TOKEN が設定されていません。.envを確認してください。")
        raise SystemExit(1)

    channel_id_str = os.getenv("DISCORD_CHANNEL_ID", "")
    channel_id = int(channel_id_str) if channel_id_str.isdigit() else None

    api_host = os.getenv("API_HOST", "127.0.0.1")
    api_port = int(os.getenv("API_PORT", "8099"))

    # DB初期化
    db = Database(db_path="data/bot.db")
    db.initialize()
    repo = NotificationRepository(db)

    # Bot作成
    bot = EbiBot(default_channel_id=channel_id)

    # API サーバー
    api_server = APIServer(repo=repo, bot=bot, host=api_host, port=api_port)

    async def start_all() -> None:
        async with bot:
            # Cog追加
            await bot.add_cog(ReminderCog(bot, repo))
            await bot.add_cog(WatchdogCog(bot))

            # REST API起動
            await api_server.start()
            logger.info("全コンポーネント起動完了")

            # Bot起動（ブロッキング）
            await bot.start(token)

    async def shutdown() -> None:
        logger.info("シャットダウン開始...")
        await api_server.stop()
        db.close()
        logger.info("シャットダウン完了")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # シグナルハンドラ
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
