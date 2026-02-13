"""Discord Embed生成ヘルパー"""

from datetime import datetime
from typing import Optional

import discord

# カラー定数
COLOR_REMINDER = 0x00BFFF     # 水色 — リマインダー
COLOR_CLAUDE = 0x7289DA       # Discord色 — Claude Code通知
COLOR_STARTUP = 0x00BFFF      # 水色 — Bot起動
COLOR_WATCHDOG_WARN = 0xFF6B6B  # オレンジ寄り赤 — 1-2件
COLOR_WATCHDOG_DANGER = 0xFF4444  # 赤 — 3-5件
COLOR_WATCHDOG_CRITICAL = 0xFF0000  # 真っ赤 — 6件以上
COLOR_SUCCESS = 0x00FF00      # 緑

# 煽りテンプレート
WATCHDOG_TEMPLATES = {
    "warn": {
        "title": "こら！！期限切れタスクあるよ！！",
        "color": COLOR_WATCHDOG_WARN,
    },
    "danger": {
        "title": "ちょっと！！サボってない？？",
        "color": COLOR_WATCHDOG_DANGER,
    },
    "critical": {
        "title": "\U0001f6a8\U0001f6a8\U0001f6a8 やばい！！放置しすぎ！！",
        "color": COLOR_WATCHDOG_CRITICAL,
    },
}


def get_watchdog_level(overdue_count: int) -> str:
    """期限切れ件数から煽りレベルを返す。"""
    if overdue_count >= 6:
        return "critical"
    if overdue_count >= 3:
        return "danger"
    return "warn"


def build_reminder_embed(
    message: str,
    title: Optional[str] = None,
) -> discord.Embed:
    """リマインダー通知用Embedを作る。"""
    embed = discord.Embed(
        title=title or "\u23f0 リマインド！",
        description=message,
        color=COLOR_REMINDER,
        timestamp=datetime.now(),
    )
    embed.set_footer(text="EbiBot Reminder")
    return embed


def build_claude_embed(
    message: str,
    title: Optional[str] = None,
    color: Optional[int] = None,
) -> discord.Embed:
    """Claude Code通知用Embedを作る。"""
    embed = discord.Embed(
        title=title or "\U0001f4e2 Claude Codeからのお知らせ",
        description=message,
        color=color or COLOR_CLAUDE,
        timestamp=datetime.now(),
    )
    embed.set_footer(text="EbiBot")
    return embed


def build_startup_embed() -> discord.Embed:
    """Bot起動通知用Embedを作る。"""
    embed = discord.Embed(
        title="\U0001f389 起動したよ～！",
        description="EbiBot が稼働開始しました。\nREST API も準備完了！",
        color=COLOR_STARTUP,
        timestamp=datetime.now(),
    )
    embed.set_footer(text="EbiBot")
    return embed


def build_watchdog_embed(
    overdue_tasks: list[dict],
) -> discord.Embed:
    """Todoist期限切れ煽りEmbedを作る。"""
    count = len(overdue_tasks)
    level = get_watchdog_level(count)
    template = WATCHDOG_TEMPLATES[level]

    task_lines = []
    for task in overdue_tasks[:15]:
        content = task.get("content", "???")
        due = task.get("due", "")
        task_lines.append(f"- **{content}**  (期限: {due})")

    if count > 15:
        task_lines.append(f"...他 {count - 15} 件")

    embed = discord.Embed(
        title=template["title"],
        description=f"期限切れタスクが **{count}件** あるよ！！\n\n"
        + "\n".join(task_lines),
        color=template["color"],
        timestamp=datetime.now(),
    )
    embed.set_footer(text="EbiBot Watchdog")
    return embed


def build_schedule_confirm_embed(
    message: str,
    scheduled_at: str,
) -> discord.Embed:
    """スケジュール登録確認Embedを作る。"""
    embed = discord.Embed(
        title="\u2705 リマインド予約したよ！",
        description=f"**{scheduled_at}** に通知するね。\n\n> {message}",
        color=COLOR_SUCCESS,
        timestamp=datetime.now(),
    )
    embed.set_footer(text="EbiBot Reminder")
    return embed
