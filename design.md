# Discord Bot (EbiBot) 設計書

## 目的

Claude Code → Discord への **Push型通知** を実現する常駐Bot。

## アーキテクチャ

```
┌─────────────┐   HTTP POST    ┌──────────────┐   Discord API   ┌─────────┐
│ Claude Code │ ──────────────→│  Discord Bot │ ──────────────→│ Discord │
│ (curl)      │  localhost:8099│  (discord.py)│                │ Server  │
└─────────────┘                │              │                └────┬────┘
                               │  ┌────────┐  │                     │
                  30秒ループ   │  │ SQLite │  │  /remind            │
                  ────────────→│  │ 独自DB │  │←────────────────────┘
                               │  └────────┘  │        胡田さん
                  30分ループ   │              │
                  ────────────→│  Todoist API │
                               │  overdue?    │
                               └──────────────┘
```

## コンポーネント

| コンポーネント | ファイル | 役割 |
|---------------|---------|------|
| EbiBot | `src/bot.py` | discord.py Bot本体 |
| ReminderCog | `src/cogs/reminder.py` | /remindコマンド + 30秒送信ループ |
| WatchdogCog | `src/cogs/watchdog.py` | Todoist期限切れ30分チェック |
| APIServer | `src/api/server.py` | aiohttp REST API (localhost:8099) |
| Database | `src/database/models.py` | SQLiteスキーマ & 接続管理 |
| NotificationRepository | `src/database/repository.py` | 通知CRUD |

## DBスキーマ

`scheduled_notifications` テーブル:
- id, message, title, color, scheduled_at, source, channel_id, status, sent_at, error_message, created_at

## REST API

| メソッド | パス | 用途 |
|----------|------|------|
| POST | `/api/notify` | 即時送信 |
| POST | `/api/schedule` | 時刻指定送信 |
| GET | `/api/scheduled` | 未送信一覧 |
| DELETE | `/api/scheduled/{id}` | キャンセル |
| GET | `/api/health` | ヘルスチェック |

## Watchdog煽りレベル

| 件数 | レベル | タイトル |
|------|--------|---------|
| 1-2 | warn | こら！！期限切れタスクあるよ！！ |
| 3-5 | danger | ちょっと！！サボってない？？ |
| 6+ | critical | 🚨🚨🚨 やばい！！放置しすぎ！！ |

## 設計判断

| 判断 | 選択 | 理由 |
|------|------|------|
| リポジトリ | 独立 | scheduler=定期ジョブ vs Bot=対話型Push通知。関心が別 |
| フレームワーク | discord.py v2 | Python, async, slash commands |
| REST API | aiohttp | discord.pyが内部使用、追加依存なし |
| DB | SQLite | scheduler.dbと完全独立 |
| APIバインド | 127.0.0.1 | ローカル専用＝認証不要 |
| Todoist連携 | todoist.sh | 既存スクリプト再利用 |
