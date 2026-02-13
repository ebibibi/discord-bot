"""scheduled_notifications CRUD"""

from datetime import datetime
from typing import Optional

from .models import Database
from ..utils.logger import get_logger

logger = get_logger(__name__)


class NotificationRepository:
    """scheduled_notifications テーブルのCRUD操作"""

    def __init__(self, db: Database):
        self.db = db

    def create(
        self,
        message: str,
        scheduled_at: str,
        *,
        title: Optional[str] = None,
        color: int = 0x00BFFF,
        source: str = "api",
        channel_id: Optional[int] = None,
    ) -> int:
        """通知をスケジュールする。作成されたIDを返す。"""
        conn = self.db.connection
        cursor = conn.execute(
            """
            INSERT INTO scheduled_notifications
                (message, title, color, scheduled_at, source, channel_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message, title, color, scheduled_at, source, channel_id),
        )
        conn.commit()
        row_id = cursor.lastrowid
        logger.info(f"通知スケジュール作成: id={row_id}, at={scheduled_at}")
        return row_id

    def get_pending(self, before: Optional[str] = None) -> list[dict]:
        """pending状態の通知を取得する。beforeを指定すると、その時刻以前のみ。"""
        conn = self.db.connection
        if before:
            rows = conn.execute(
                """
                SELECT * FROM scheduled_notifications
                WHERE status = 'pending' AND scheduled_at <= ?
                ORDER BY scheduled_at
                """,
                (before,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM scheduled_notifications
                WHERE status = 'pending'
                ORDER BY scheduled_at
                """,
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_sent(self, notification_id: int) -> None:
        """送信済みにマークする。"""
        conn = self.db.connection
        conn.execute(
            """
            UPDATE scheduled_notifications
            SET status = 'sent', sent_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (notification_id,),
        )
        conn.commit()

    def mark_failed(self, notification_id: int, error: str) -> None:
        """失敗にマークする。"""
        conn = self.db.connection
        conn.execute(
            """
            UPDATE scheduled_notifications
            SET status = 'failed', error_message = ?
            WHERE id = ?
            """,
            (error, notification_id),
        )
        conn.commit()

    def cancel(self, notification_id: int) -> bool:
        """キャンセルする。成功したらTrue。"""
        conn = self.db.connection
        cursor = conn.execute(
            """
            UPDATE scheduled_notifications
            SET status = 'cancelled'
            WHERE id = ? AND status = 'pending'
            """,
            (notification_id,),
        )
        conn.commit()
        return cursor.rowcount > 0

    def get_all_pending(self) -> list[dict]:
        """全pending通知を取得する（API用）。"""
        return self.get_pending()
