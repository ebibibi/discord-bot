"""aiohttp REST API（127.0.0.1:8099）"""

import json
from datetime import datetime
from typing import Optional

from aiohttp import web

from ..database.repository import NotificationRepository
from ..utils.embeds import build_claude_embed
from ..utils.logger import get_logger

logger = get_logger(__name__)


class APIServer:
    """Bot埋め込みREST APIサーバー"""

    def __init__(
        self,
        repo: NotificationRepository,
        bot,
        host: str = "127.0.0.1",
        port: int = 8099,
    ):
        self.repo = repo
        self.bot = bot
        self.host = host
        self.port = port
        self.app = web.Application()
        self._setup_routes()
        self._runner: Optional[web.AppRunner] = None

    def _setup_routes(self) -> None:
        self.app.router.add_get("/api/health", self.health)
        self.app.router.add_post("/api/notify", self.notify)
        self.app.router.add_post("/api/schedule", self.schedule)
        self.app.router.add_get("/api/scheduled", self.list_scheduled)
        self.app.router.add_delete("/api/scheduled/{id}", self.cancel_scheduled)

    async def start(self) -> None:
        """APIサーバーを起動する。"""
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info(f"REST API起動: http://{self.host}:{self.port}")

    async def stop(self) -> None:
        """APIサーバーを停止する。"""
        if self._runner:
            await self._runner.cleanup()

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "timestamp": datetime.now().isoformat()})

    async def notify(self, request: web.Request) -> web.Response:
        """即時送信"""
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        message = data.get("message")
        if not message:
            return web.json_response({"error": "message is required"}, status=400)

        title = data.get("title")
        color = data.get("color")

        channel_id = self.bot.default_channel_id
        if not channel_id:
            return web.json_response({"error": "No default channel"}, status=500)

        channel = self.bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception as e:
                return web.json_response({"error": str(e)}, status=500)

        embed = build_claude_embed(message=message, title=title, color=color)
        await channel.send(embed=embed)

        return web.json_response({"status": "sent"})

    async def schedule(self, request: web.Request) -> web.Response:
        """時刻指定送信"""
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        message = data.get("message")
        scheduled_at = data.get("scheduled_at")

        if not message:
            return web.json_response({"error": "message is required"}, status=400)
        if not scheduled_at:
            return web.json_response({"error": "scheduled_at is required"}, status=400)

        # ISO 8601からローカル時刻文字列に変換
        try:
            dt = datetime.fromisoformat(scheduled_at)
            scheduled_str = dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return web.json_response(
                {"error": "scheduled_at must be ISO 8601 format"},
                status=400,
            )

        notification_id = self.repo.create(
            message=message,
            scheduled_at=scheduled_str,
            title=data.get("title"),
            color=data.get("color", 0x00BFFF),
            source="api",
        )

        return web.json_response({"status": "scheduled", "id": notification_id})

    async def list_scheduled(self, request: web.Request) -> web.Response:
        """未送信一覧"""
        pending = self.repo.get_all_pending()
        return web.json_response({"notifications": pending})

    async def cancel_scheduled(self, request: web.Request) -> web.Response:
        """キャンセル"""
        try:
            notification_id = int(request.match_info["id"])
        except (ValueError, KeyError):
            return web.json_response({"error": "Invalid ID"}, status=400)

        success = self.repo.cancel(notification_id)
        if success:
            return web.json_response({"status": "cancelled"})
        return web.json_response(
            {"error": "Not found or already processed"},
            status=404,
        )
