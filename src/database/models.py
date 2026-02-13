"""SQLiteスキーマ & Databaseクラス"""

import sqlite3
from pathlib import Path
from typing import Optional

from ..utils.logger import get_logger

logger = get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS scheduled_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message TEXT NOT NULL,
    title TEXT,
    color INTEGER DEFAULT 49151,
    scheduled_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'api',
    channel_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    sent_at TEXT,
    error_message TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_notif_status_scheduled
    ON scheduled_notifications(status, scheduled_at);
"""


class Database:
    """SQLiteデータベース管理クラス"""

    def __init__(self, db_path: str = "data/bot.db"):
        self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        """接続を取得（なければ作成）。"""
        if self._connection is not None:
            return self._connection

        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self.db_path, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        logger.info(f"DB接続: {self.db_path}")
        return self._connection

    def initialize(self) -> None:
        """スキーマを初期化する。"""
        conn = self.connect()
        conn.executescript(SCHEMA)
        conn.commit()
        logger.info("DBスキーマ初期化完了")

    def close(self) -> None:
        """接続を閉じる。"""
        if self._connection:
            self._connection.close()
            self._connection = None

    @property
    def connection(self) -> sqlite3.Connection:
        return self.connect()
