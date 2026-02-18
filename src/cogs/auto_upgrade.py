"""Auto Upgrade Cog — bridge リポ更新時に自動で EbiBot をアップグレード。

フロー:
1. bridge リポに push → GitHub Actions → Discord webhook "🔄 ebibot-upgrade"
2. この Cog が受信 → uv lock --upgrade-package && uv sync を実行
3. systemctl restart discord-bot で自分自身を再起動

セキュリティ設計:
- webhook_id ありのメッセージのみ受け付ける
- 固定トリガー文字列のみ反応
- 実行するコマンドはハードコード（注入不可）
"""

from __future__ import annotations

import asyncio
import logging
import subprocess

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

TRIGGER_UPGRADE = "🔄 ebibot-upgrade"
EBIBOT_DIR = "/home/ebi/discord-bot"


class AutoUpgradeCog(commands.Cog):
    """Cog that auto-upgrades EbiBot when the bridge package is updated."""

    def __init__(
        self,
        bot: commands.Bot,
        channel_id: int,
    ) -> None:
        self.bot = bot
        self.channel_id = channel_id
        self._lock = asyncio.Lock()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Handle upgrade trigger messages."""
        if not message.webhook_id:
            return
        if message.channel.id != self.channel_id:
            return
        if message.content.strip() != TRIGGER_UPGRADE:
            return

        logger.info("ebibot-upgrade トリガー受信")

        if self._lock.locked():
            await message.reply("⏳ アップグレードは既に実行中です。")
            return

        async with self._lock:
            await self._run_upgrade(message)

    async def _run_upgrade(self, trigger_message: discord.Message) -> None:
        """Run the upgrade process."""
        thread = await trigger_message.create_thread(name="🔄 ebibot-upgrade")
        await thread.send("📦 パッケージ更新を開始します...")

        try:
            # Step 1: uv lock --upgrade-package
            await thread.send("⚙️ `uv lock --upgrade-package claude-code-discord-bridge`")
            proc = await asyncio.create_subprocess_exec(
                "uv", "lock", "--upgrade-package", "claude-code-discord-bridge",
                cwd=EBIBOT_DIR,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
            output = stdout.decode().strip()
            if output:
                await thread.send(f"```\n{output[:1800]}\n```")

            if proc.returncode != 0:
                await thread.send("❌ `uv lock` が失敗しました。")
                await trigger_message.add_reaction("❌")
                return

            # Step 2: uv sync
            await thread.send("⚙️ `uv sync`")
            proc = await asyncio.create_subprocess_exec(
                "uv", "sync",
                cwd=EBIBOT_DIR,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
            output = stdout.decode().strip()
            if output:
                await thread.send(f"```\n{output[:1800]}\n```")

            if proc.returncode != 0:
                await thread.send("❌ `uv sync` が失敗しました。")
                await trigger_message.add_reaction("❌")
                return

            # Step 3: Restart via systemctl
            # All commands are hardcoded — no user input involved
            await thread.send("🔄 再起動します...")
            await trigger_message.add_reaction("✅")
            await asyncio.sleep(1)

            # This kills our own process — the service manager will restart us
            subprocess.Popen(  # noqa: S603 — hardcoded command, no injection risk
                ["sudo", "systemctl", "restart", "discord-bot.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        except asyncio.TimeoutError:
            await thread.send("❌ タイムアウトしました。")
            await trigger_message.add_reaction("❌")
        except Exception:
            logger.exception("ebibot-upgrade エラー")
            await thread.send("❌ アップグレードでエラーが発生しました。")
            await trigger_message.add_reaction("❌")
