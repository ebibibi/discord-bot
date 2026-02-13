"""Todoist期限切れ30分チェックループ"""

import json
import subprocess
from datetime import datetime

from discord.ext import commands, tasks

from ..utils.embeds import build_watchdog_embed
from ..utils.logger import get_logger

logger = get_logger(__name__)

TODOIST_SH = "/home/ebi/.claude/skills/todoist/scripts/todoist.sh"


class WatchdogCog(commands.Cog):
    """Todoist期限切れ監視"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._notified_today: set[str] = set()
        self._last_reset_date: str = ""

    async def cog_load(self) -> None:
        self.check_overdue.start()
        logger.info("WatchdogCog loaded, overdue check loop started")

    async def cog_unload(self) -> None:
        self.check_overdue.cancel()

    def _reset_daily(self) -> None:
        """日付が変わったら通知済みセットをリセットする。"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._last_reset_date != today:
            self._notified_today.clear()
            self._last_reset_date = today

    def _is_active_hours(self) -> bool:
        """8:00-23:00 JSTの間だけ動く。"""
        hour = datetime.now().hour
        return 8 <= hour < 23

    def _fetch_overdue_tasks(self) -> list[dict]:
        """todoist.shで期限切れタスクを取得する。"""
        try:
            result = subprocess.run(
                [TODOIST_SH, "tasks", "--filter", "(overdue)"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.error(f"todoist.sh失敗: {result.stderr}")
                return []

            tasks = json.loads(result.stdout)
            if isinstance(tasks, list):
                return tasks
            return []
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"Todoist取得エラー: {e}")
            return []

    @tasks.loop(minutes=30)
    async def check_overdue(self) -> None:
        """30分ごとにTodoist期限切れをチェックする。"""
        if not self._is_active_hours():
            return

        self._reset_daily()

        overdue_tasks = self._fetch_overdue_tasks()
        if not overdue_tasks:
            return

        # 未通知のタスクだけフィルタ
        new_tasks = []
        for task in overdue_tasks:
            task_id = task.get("id", "")
            if task_id and task_id not in self._notified_today:
                new_tasks.append(task)
                self._notified_today.add(task_id)

        if not new_tasks:
            return

        channel_id = self.bot.default_channel_id
        if not channel_id:
            logger.warning("デフォルトチャンネルIDが未設定")
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception as e:
                logger.error(f"チャンネル取得失敗: {e}")
                return

        embed = build_watchdog_embed(new_tasks)
        await channel.send(embed=embed)
        logger.info(f"Watchdog通知送信: {len(new_tasks)}件")

    @check_overdue.before_loop
    async def before_check_overdue(self) -> None:
        await self.bot.wait_until_ready()
