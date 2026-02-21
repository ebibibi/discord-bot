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
- **1つのBotトークン、1つのプロセス**で全Cogが動く。別プロセスで同じトークンを使わない

### 絶対ルール: ccdb のコンポーネントを複製するな

**ccdb に存在する Cog・クラス・関数を EbiBot 側にコピーして独自版を作ることは禁止。**

- ccdb の Cog はそのまま `from claude_discord.xxx import XxxCog` して使う
- EbiBot 独自の Cog が許されるのは **ccdb に存在しない機能** のみ（reminder, watchdog）
- ccdb の Cog をカスタマイズしたい場合は **ccdb 側にパラメータ/フックを追加** する。EbiBot 側でラップやコピーをしない
- EbiBot の `src/cogs/` に置いてよいのは: (1) EbiBot固有の Cog、(2) ccdb の Cog に渡す **設定定義のみ** のファイル（`auto_upgrade.py`, `docs_sync.py` のように）
- **なぜ**: ccdb に機能追加したとき、EbiBot 側に独自コピーがあるとそこだけ古いまま残る。2026-02-19 に concurrency awareness が動かなかった原因がこれ

### ccdb 側の設計責務

EbiBot のような消費者が **パッケージ更新だけで新機能を受け取れる** ように設計する:
- デフォルトで有効になるべき機能は、消費者側の配線なしで動くようにする（auto-discovery パターン等）
- Cog のコンストラクタに新パラメータを足すときは `= None` デフォルトで後方互換を保つ
- 消費者にコード変更を要求する設計は失敗。設計を見直す

## アーキテクチャ

- **discord.py v2** + **aiohttp REST API** が同一asyncioループで動作
- DB: SQLite (`data/bot.db`) — 通知用。Claude Chatセッションは別DB (`data/sessions.db`)
- Cogパターンで機能分離
- パッケージ管理: **uv** (`pyproject.toml` + `uv.lock`)

## Cog一覧

| Cog | 種別 | 役割 |
|-----|------|------|
| `reminder.py` | EbiBot独自 | /remind スラッシュコマンド + 時刻指定送信 |
| `watchdog.py` | EbiBot独自 | Todoist期限切れ30分監視 |
| `docs_sync.py` | **設定定義のみ** → ccdb `WebhookTriggerCog` | GitHub → ドキュメント同期 |
| `auto_upgrade.py` | **設定定義のみ** → ccdb `AutoUpgradeCog` | パッケージ自動更新 + 再起動 |
| `api/server.py` | **ccdb `ApiServer` を re-export** | REST API（通知・スケジュール） |

ccdb から直接使用（main.py で import）:
- `ClaudeChatCog` — Discord → Claude Code CLI チャット
- `SkillCommandCog` — /skill スラッシュコマンド
- `SessionManageCog` — セッション管理

## ディレクトリ構成

```
src/
  main.py          # エントリーポイント
  bot.py           # EbiBot クラス
  cogs/            # EbiBot独自Cog + ccdbへの設定定義のみ
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

## 🚨 Botの再起動・デプロイ手順（必ず守れ）

`sudo systemctl restart discord-bot` は **全Claude Cog・全セッション**に影響する破壊的操作。

**再起動前の必須チェック:**
1. **AI ラウンジを読む** → `curl -s "$CCDB_API_URL/api/lounge" | python3 -c "import json,sys; msgs=json.load(sys.stdin); [print(f'[{m[\"posted_at\"][11:16]}] {m[\"label\"]}: {m[\"message\"]}') for m in msgs.get('messages',[])]"`
2. 直近10分以内のメッセージに「作業中」「進行中」のセッションがないか確認
3. 作業中セッションがあれば待つ。なければラウンジに「これからBot再起動します」と予告
4. 再起動実行 → 完了後にラウンジへ報告

**再起動コマンド:**
```bash
sudo systemctl restart discord-bot
sudo systemctl status discord-bot  # 起動確認
```

**AI Loungeを読むコマンド（ショートカット）:**
```bash
curl -s "$CCDB_API_URL/api/lounge" | python3 -m json.tool
```

## REST API

| メソッド | パス | 用途 |
|----------|------|------|
| POST | `/api/notify` | 即時送信 |
| POST | `/api/schedule` | 時刻指定送信 |
| GET | `/api/scheduled` | 未送信一覧 |
| DELETE | `/api/scheduled/{id}` | キャンセル |
| GET | `/api/health` | ヘルスチェック |

## 定期タスク一覧（重要）

EbiBotには**2種類の定期タスク**がある。混同しないこと。

### 種別1: コード埋め込みループ（変更はデプロイ必要）

| Cog | ファイル | 間隔 | 動作条件 |
|-----|---------|------|---------|
| `ReminderCog.check_scheduled` | `src/cogs/reminder.py` | 30秒 | 常時 |
| `WatchdogCog.check_overdue` | `src/cogs/watchdog.py` | 30分 | 8:00〜23:00のみ |

- **ReminderCog**: `/remind` コマンドで登録した通知をDB (`data/bot.db`) からチェックして送信
- **WatchdogCog**: Todoistの期限切れタスクを `todoist.sh (overdue)` で取得してDiscord通知。1タスク/日の上限あり

### 種別2: SchedulerCog（SQLite管理・動的追加可能）

ccdb の `SchedulerCog` が 30秒マスターループで `data/tasks.db` を監視し、期限のきたタスクを自動実行。

**現在登録中のタスク:**

| ID | 名前 | 間隔 | 内容 |
|----|------|------|------|
| 1 | `genai-assessment-workitem-triage` | 15分 | Azure DevOps GenAI-Assessment のWorkItemをトリアージ/自動実装 |

**タスクの確認・操作:**
```bash
# 一覧確認
sqlite3 /home/ebi/discord-bot/data/tasks.db "SELECT id, name, interval_seconds, datetime(next_run_at, 'unixepoch', 'localtime') as next_run FROM scheduled_tasks;"

# REST API経由で追加（Bot起動中のみ）
curl -s http://127.0.0.1:8099/api/tasks

# 直接DB操作（Bot停止中でも可）
sqlite3 /home/ebi/discord-bot/data/tasks.db "UPDATE scheduled_tasks SET interval_seconds=1800 WHERE id=1;"
```

> **注意**: タスクのプロンプトは `src/cogs/` 内に定義があるものもある。`genai-assessment-workitem-triage` のプロンプトはDB直書き（`data/tasks.db` の `prompt` カラムが唯一の真実の源）。

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
