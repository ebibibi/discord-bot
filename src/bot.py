"""EbiBot クラス（commands.Bot継承）"""

import discord
from discord.ext import commands

from claude_discord.concurrency import SessionRegistry

from .utils.embeds import build_startup_embed
from .utils.logger import get_logger

logger = get_logger(__name__)


class EbiBot(commands.Bot):
    """Discord Bot本体"""

    def __init__(self, default_channel_id: int | None = None):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
        )
        self.default_channel_id = default_channel_id
        # Alias for bridge compatibility (ClaudeDiscordBot uses channel_id)
        self.channel_id = default_channel_id
        self.session_registry = SessionRegistry()

    async def setup_hook(self) -> None:
        """Cogのロードとスラッシュコマンドの同期。"""
        # Cogは main.py 側で追加済み
        await self.tree.sync()
        logger.info("スラッシュコマンドを同期しました")

    async def on_ready(self) -> None:
        logger.info(f"ログイン完了: {self.user} (ID: {self.user.id})")

        if self.default_channel_id:
            try:
                channel = self.get_channel(self.default_channel_id)
                if not channel:
                    channel = await self.fetch_channel(self.default_channel_id)
                embed = build_startup_embed()
                await channel.send(embed=embed)
                logger.info("起動通知を送信しました")
            except Exception as e:
                logger.error(f"起動通知送信失敗: {e}")
