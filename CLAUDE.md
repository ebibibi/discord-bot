# Discord Bot (EbiBot)

Claude Code → Discord Push通知Bot。

## アーキテクチャ

- **discord.py v2** + **aiohttp REST API** が同一asyncioループで動作
- DB: SQLite (`data/bot.db`)
- Cogパターンで機能分離: reminder, watchdog

## ディレクトリ構成

```
src/
  main.py          # エントリーポイント
  bot.py           # EbiBot クラス
  cogs/            # 機能モジュール（reminder, watchdog）
  api/             # REST API（aiohttp, localhost:8099）
  database/        # SQLite DB & Repository
  utils/           # Embed, Logger
tests/             # pytest
```

## 開発ルール

- `venv/bin/python -m src.main` で起動
- テスト: `venv/bin/pytest tests/ -v --cov=src`
- 設定は `.env` から読み込み（python-dotenv）
- REST APIは `127.0.0.1:8099` のみバインド（外部非公開）

## REST API

| メソッド | パス | 用途 |
|----------|------|------|
| POST | `/api/notify` | 即時送信 |
| POST | `/api/schedule` | 時刻指定送信 |
| GET | `/api/scheduled` | 未送信一覧 |
| DELETE | `/api/scheduled/{id}` | キャンセル |
| GET | `/api/health` | ヘルスチェック |

## Watchdog

Todoist期限切れを30分おきに監視。`~/.claude/skills/todoist/scripts/todoist.sh` 経由。
