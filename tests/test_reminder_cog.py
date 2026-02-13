"""ReminderCog テスト"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cogs.reminder import ReminderCog
from src.database.models import Database
from src.database.repository import NotificationRepository


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.default_channel_id = 123456789
    bot.wait_until_ready = AsyncMock()

    mock_channel = AsyncMock()
    mock_channel.send = AsyncMock()
    bot.get_channel = MagicMock(return_value=mock_channel)
    bot.fetch_channel = AsyncMock(return_value=mock_channel)
    return bot


@pytest.fixture
def cog(mock_bot, repo):
    return ReminderCog(mock_bot, repo)


class TestCheckScheduled:
    @pytest.mark.asyncio
    async def test_sends_pending_notification(self, cog, repo, mock_bot):
        past = (datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S")
        repo.create(message="送信テスト", scheduled_at=past)

        await cog.check_scheduled()

        channel = mock_bot.get_channel(123456789)
        channel.send.assert_called_once()

        pending = repo.get_all_pending()
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_does_not_send_future(self, cog, repo, mock_bot):
        future = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
        repo.create(message="未来の通知", scheduled_at=future)

        await cog.check_scheduled()

        channel = mock_bot.get_channel(123456789)
        channel.send.assert_not_called()

        pending = repo.get_all_pending()
        assert len(pending) == 1

    @pytest.mark.asyncio
    async def test_marks_failed_on_error(self, cog, repo, mock_bot):
        past = (datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S")
        repo.create(message="エラーテスト", scheduled_at=past)

        channel = mock_bot.get_channel(123456789)
        channel.send = AsyncMock(side_effect=Exception("送信エラー"))

        await cog.check_scheduled()

        pending = repo.get_all_pending()
        assert len(pending) == 0
