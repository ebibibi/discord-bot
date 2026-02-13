"""Embed生成ヘルパー テスト"""

from src.utils.embeds import (
    COLOR_CLAUDE,
    COLOR_REMINDER,
    COLOR_STARTUP,
    COLOR_SUCCESS,
    COLOR_WATCHDOG_CRITICAL,
    COLOR_WATCHDOG_DANGER,
    COLOR_WATCHDOG_WARN,
    build_claude_embed,
    build_reminder_embed,
    build_schedule_confirm_embed,
    build_startup_embed,
    build_watchdog_embed,
    get_watchdog_level,
)


class TestGetWatchdogLevel:
    def test_warn_level(self):
        assert get_watchdog_level(1) == "warn"
        assert get_watchdog_level(2) == "warn"

    def test_danger_level(self):
        assert get_watchdog_level(3) == "danger"
        assert get_watchdog_level(5) == "danger"

    def test_critical_level(self):
        assert get_watchdog_level(6) == "critical"
        assert get_watchdog_level(10) == "critical"


class TestBuildReminderEmbed:
    def test_default_title(self):
        embed = build_reminder_embed("テストメッセージ")
        assert "リマインド" in embed.title
        assert embed.description == "テストメッセージ"
        assert embed.color.value == COLOR_REMINDER

    def test_custom_title(self):
        embed = build_reminder_embed("テスト", title="カスタム")
        assert embed.title == "カスタム"


class TestBuildClaudeEmbed:
    def test_default(self):
        embed = build_claude_embed("通知テスト")
        assert "Claude Code" in embed.title
        assert embed.description == "通知テスト"
        assert embed.color.value == COLOR_CLAUDE

    def test_custom_color(self):
        embed = build_claude_embed("テスト", color=0xFF0000)
        assert embed.color.value == 0xFF0000


class TestBuildStartupEmbed:
    def test_startup(self):
        embed = build_startup_embed()
        assert "起動" in embed.title
        assert embed.color.value == COLOR_STARTUP


class TestBuildWatchdogEmbed:
    def test_few_tasks(self):
        tasks = [
            {"content": "タスク1", "due": "2026-02-12"},
            {"content": "タスク2", "due": "2026-02-11"},
        ]
        embed = build_watchdog_embed(tasks)
        assert "2件" in embed.description
        assert embed.color.value == COLOR_WATCHDOG_WARN

    def test_many_tasks(self):
        tasks = [{"content": f"タスク{i}", "due": "2026-02-10"} for i in range(7)]
        embed = build_watchdog_embed(tasks)
        assert "7件" in embed.description
        assert embed.color.value == COLOR_WATCHDOG_CRITICAL


class TestBuildScheduleConfirmEmbed:
    def test_confirm(self):
        embed = build_schedule_confirm_embed("テスト", "02/13 14:00")
        assert "予約" in embed.title
        assert "14:00" in embed.description
        assert embed.color.value == COLOR_SUCCESS
