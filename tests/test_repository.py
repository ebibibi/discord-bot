"""NotificationRepository テスト"""

from datetime import datetime, timedelta


class TestNotificationRepository:
    def test_create_and_get_pending(self, repo):
        future = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        row_id = repo.create(message="テスト通知", scheduled_at=future)

        assert row_id is not None
        assert row_id > 0

        pending = repo.get_all_pending()
        assert len(pending) == 1
        assert pending[0]["message"] == "テスト通知"
        assert pending[0]["status"] == "pending"

    def test_get_pending_with_before_filter(self, repo):
        past = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        future = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        repo.create(message="過去の通知", scheduled_at=past)
        repo.create(message="未来の通知", scheduled_at=future)

        pending = repo.get_pending(before=now_str)
        assert len(pending) == 1
        assert pending[0]["message"] == "過去の通知"

    def test_mark_sent(self, repo):
        future = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        row_id = repo.create(message="送信テスト", scheduled_at=future)

        repo.mark_sent(row_id)

        pending = repo.get_all_pending()
        assert len(pending) == 0

    def test_mark_failed(self, repo):
        future = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        row_id = repo.create(message="失敗テスト", scheduled_at=future)

        repo.mark_failed(row_id, "テストエラー")

        pending = repo.get_all_pending()
        assert len(pending) == 0

    def test_cancel(self, repo):
        future = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        row_id = repo.create(message="キャンセルテスト", scheduled_at=future)

        success = repo.cancel(row_id)
        assert success is True

        pending = repo.get_all_pending()
        assert len(pending) == 0

    def test_cancel_already_sent(self, repo):
        future = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        row_id = repo.create(message="送信済みキャンセル", scheduled_at=future)

        repo.mark_sent(row_id)
        success = repo.cancel(row_id)
        assert success is False

    def test_create_with_optional_fields(self, repo):
        future = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        row_id = repo.create(
            message="フルオプション",
            scheduled_at=future,
            title="テストタイトル",
            color=0xFF0000,
            source="slash_command",
            channel_id=123456789,
        )

        pending = repo.get_all_pending()
        assert len(pending) == 1
        assert pending[0]["title"] == "テストタイトル"
        assert pending[0]["color"] == 0xFF0000
        assert pending[0]["source"] == "slash_command"
        assert pending[0]["channel_id"] == 123456789
