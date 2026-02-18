# Discord Bot (EbiBot)

胡田さん専用の Discord Bot。Push通知・監視・Claude Code チャットを1プロセスで提供する。

## claude-code-discord-bridge との関係（重要）

```
claude-code-discord-bridge (OSS framework)     EbiBot (personal instance)
github.com/ebibibi/claude-code-discord-bridge  /home/ebi/discord-bot/
  PyPIパッケージとして             pyproject.toml の dependencies に
  インストール                     git+https://... で宣言
           |                                |
           | uv add / uv sync              |
           +------>  import claude_discord  |
```

- **claude-code-discord-bridge** = 汎用フレームワーク（公開リポ）。`claude_discord` パッケージとしてインストール
- **EbiBot** = 個人インスタンス（プライベートリポ）。claude-code-discord-bridgeをパッケージ依存 + 独自Cog（reminder, watchdog）
- **アップデート**: `uv lock --upgrade-package claude-code-discord-bridge && uv sync`
- **機能追加の判断基準**: 汎用的 → claude-code-discord-bridgeに。個人ワークフロー固有 → EbiBotに
- **新機能を追加するとき、bridge側に汎化できないか常に考えること**。bridge側に同等機能があるならそちらを使う
- **bridge由来の汎用Cog**: `WebhookTriggerCog`（Webhook→Claude実行）、`AutoUpgradeCog`（自動更新）、`ApiServer`（REST API）
- **1つのBotトークン、1つのプロセス**で全Cogが動く。別プロセスで同じトークンを使わない

## アーキテクチャ

- **discord.py v2** + **aiohttp REST API** が同一asyncioループで動作
- DB: SQLite (`data/bot.db`) — 通知用。Claude Chatセッションは別DB (`data/sessions.db`)
- Cogパターンで機能分離
- パッケージ管理: **uv** (`pyproject.toml` + `uv.lock`)

## Cog一覧

| Cog | 元リポ | 役割 |
|-----|--------|------|
| `reminder.py` | EbiBot独自 | /remind スラッシュコマンド + 時刻指定送信 |
| `watchdog.py` | EbiBot独自 | Todoist期限切れ30分監視 |
| `claude_chat.py` | EbiBot独自（bridgeのクラスをimport） | Discord → Claude Code CLI チャット |
| `docs_sync.py` | **プロンプト定義のみ**（bridge WebhookTriggerCog使用） | GitHub → ドキュメント同期 |
| `auto_upgrade.py` | **設定定義のみ**（bridge AutoUpgradeCog使用） | パッケージ自動更新 + 再起動 |
| `api/server.py` | **bridge ApiServer を re-export** | REST API（通知・スケジュール） |

## ディレクトリ構成

```
src/
  main.py          # エントリーポイント
  bot.py           # EbiBot クラス
  cogs/            # 機能モジュール（reminder, watchdog, claude_chat）
  api/             # REST API（aiohttp, localhost:8099）
  database/        # SQLite DB & Repository（通知 + Claude session）
  utils/           # Embed, Logger
tests/             # pytest
pyproject.toml     # uv依存管理（claude-code-discord-bridge = git+GitHub）
uv.lock            # ロックファイル
```

## 開発ルール

- `uv run python -m src.main` で起動
- テスト: `uv run pytest tests/ -v --cov=src`
- 設定は `.env` から読み込み（python-dotenv）
- REST APIは `127.0.0.1:8099` のみバインド（外部非公開）
- **claude-code-discord-bridge由来のコードを変更したい場合**: まずclaude-code-discord-bridgeリポで変更・push → EbiBotで `uv lock --upgrade-package claude-code-discord-bridge && uv sync`

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

## .env 設定

```
DISCORD_BOT_TOKEN=        # Botトークン
DISCORD_CHANNEL_ID=       # Push通知用チャンネルID
CLAUDE_CHANNEL_ID=        # Claude Chat用チャンネルID（同一チャンネルでもOK）
CLAUDE_COMMAND=claude     # Claude Code CLIパス
CLAUDE_MODEL=sonnet       # デフォルトモデル
CLAUDE_PERMISSION_MODE=acceptEdits
CLAUDE_WORKING_DIR=/home/ebi
MAX_CONCURRENT_SESSIONS=3
SESSION_TIMEOUT_SECONDS=300
API_HOST=127.0.0.1
API_PORT=8099
```
