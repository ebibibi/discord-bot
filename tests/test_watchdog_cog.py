"""WatchdogCog テスト"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cogs.watchdog import WatchdogCog


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.default_channel_id = 123456789
    bot.wait_until_ready = AsyncMock()

    mock_channel = AsyncMock()
    mock_channel.send = AsyncMock()
    bot.get_channel = MagicMock(return_value=mock_channel)
    return bot


@pytest.fixture
def cog(mock_bot):
    return WatchdogCog(mock_bot)


class TestWatchdogCog:
    def test_is_active_hours(self, cog):
        with patch("src.cogs.watchdog.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 10
            mock_dt.now.return_value = mock_now
            assert cog._is_active_hours() is True

    def test_is_not_active_hours(self, cog):
        with patch("src.cogs.watchdog.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 3
            mock_dt.now.return_value = mock_now
            assert cog._is_active_hours() is False

    def test_reset_daily(self, cog):
        cog._notified_today.add("task1")
        cog._last_reset_date = "2026-02-12"

        with patch("src.cogs.watchdog.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "2026-02-13"
            cog._reset_daily()

        assert len(cog._notified_today) == 0

    @patch("src.cogs.watchdog.subprocess.run")
    def test_fetch_overdue_tasks_success(self, mock_run, cog):
        tasks = [{"id": "1", "content": "テスト", "due": "2026-02-12"}]
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(tasks),
        )
        result = cog._fetch_overdue_tasks()
        assert len(result) == 1
        assert result[0]["content"] == "テスト"

    @patch("src.cogs.watchdog.subprocess.run")
    def test_fetch_overdue_tasks_failure(self, mock_run, cog):
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="error",
        )
        result = cog._fetch_overdue_tasks()
        assert result == []

    @pytest.mark.asyncio
    @patch.object(WatchdogCog, "_fetch_overdue_tasks")
    @patch.object(WatchdogCog, "_is_active_hours", return_value=True)
    async def test_check_overdue_sends_notification(
        self, mock_active, mock_fetch, cog, mock_bot
    ):
        mock_fetch.return_value = [
            {"id": "task1", "content": "期限切れ1", "due": "2026-02-12"},
            {"id": "task2", "content": "期限切れ2", "due": "2026-02-11"},
        ]
        cog._last_reset_date = datetime.now().strftime("%Y-%m-%d")

        await cog.check_overdue()

        channel = mock_bot.get_channel(123456789)
        channel.send.assert_called_once()

    @pytest.mark.asyncio
    @patch.object(WatchdogCog, "_fetch_overdue_tasks")
    @patch.object(WatchdogCog, "_is_active_hours", return_value=True)
    async def test_check_overdue_dedup(
        self, mock_active, mock_fetch, cog, mock_bot
    ):
        mock_fetch.return_value = [
            {"id": "task1", "content": "同じタスク", "due": "2026-02-12"},
        ]
        cog._last_reset_date = datetime.now().strftime("%Y-%m-%d")

        # 1回目: 通知される
        await cog.check_overdue()
        channel = mock_bot.get_channel(123456789)
        assert channel.send.call_count == 1

        # 2回目: 重複排除で通知されない
        await cog.check_overdue()
        assert channel.send.call_count == 1

    @pytest.mark.asyncio
    @patch.object(WatchdogCog, "_is_active_hours", return_value=False)
    async def test_check_overdue_inactive_hours(self, mock_active, cog, mock_bot):
        await cog.check_overdue()
        channel = mock_bot.get_channel(123456789)
        channel.send.assert_not_called()
