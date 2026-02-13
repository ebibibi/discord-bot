"""/remind スラッシュコマンド & 30秒送信ループ"""

import re
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

from ..database.repository import NotificationRepository
from ..utils.embeds import build_reminder_embed, build_schedule_confirm_embed
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ReminderCog(commands.Cog):
    """リマインダー機能"""

    def __init__(self, bot: commands.Bot, repo: NotificationRepository):
        self.bot = bot
        self.repo = repo

    async def cog_load(self) -> None:
        self.check_scheduled.start()
        logger.info("ReminderCog loaded, check loop started")

    async def cog_unload(self) -> None:
        self.check_scheduled.cancel()

    @app_commands.command(
        name="remind",
        description="指定時刻にリマインドするよ！",
    )
    @app_commands.describe(
        time="時刻（HH:MM形式）",
        message="リマインドメッセージ",
    )
    async def remind(
        self,
        interaction: discord.Interaction,
        time: str,
        message: str,
    ) -> None:
        # HH:MM バリデーション
        match = re.match(r"^(\d{1,2}):(\d{2})$", time.strip())
        if not match:
            await interaction.response.send_message(
                "時刻は HH:MM 形式で指定してね！（例: 14:30）",
                ephemeral=True,
            )
            return

        hour, minute = int(match.group(1)), int(match.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            await interaction.response.send_message(
                "時刻が範囲外だよ！ 00:00〜23:59 で指定してね。",
                ephemeral=True,
            )
            return

        # 時刻を計算（過去なら翌日）
        now = datetime.now()
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if scheduled <= now:
            scheduled += timedelta(days=1)

        scheduled_str = scheduled.strftime("%Y-%m-%dT%H:%M:%S")

        # DB に登録
        self.repo.create(
            message=message,
            scheduled_at=scheduled_str,
            source="slash_command",
            channel_id=interaction.channel_id,
        )

        embed = build_schedule_confirm_embed(
            message=message,
            scheduled_at=scheduled.strftime("%m/%d %H:%M"),
        )
        await interaction.response.send_message(embed=embed)

    @tasks.loop(seconds=30)
    async def check_scheduled(self) -> None:
        """30秒ごとにpending通知をチェックして送信する。"""
        now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        pending = self.repo.get_pending(before=now_str)

        for notif in pending:
            try:
                channel_id = notif.get("channel_id") or self.bot.default_channel_id
                if not channel_id:
                    logger.warning(f"チャンネルID不明: notif_id={notif['id']}")
                    self.repo.mark_failed(notif["id"], "No channel ID")
                    continue

                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    channel = await self.bot.fetch_channel(int(channel_id))

                embed = build_reminder_embed(
                    message=notif["message"],
                    title=notif.get("title"),
                )
                if notif.get("color"):
                    embed.color = notif["color"]

                await channel.send(embed=embed)
                self.repo.mark_sent(notif["id"])
                logger.info(f"通知送信完了: id={notif['id']}")

            except Exception as e:
                logger.error(f"通知送信失敗: id={notif['id']}, error={e}")
                self.repo.mark_failed(notif["id"], str(e))

    @check_scheduled.before_loop
    async def before_check_scheduled(self) -> None:
        await self.bot.wait_until_ready()
