"""Auto Upgrade — bridge の AutoUpgradeCog を使った自動パッケージ更新。

フロー:
1. bridge リポに push → GitHub Actions → Discord webhook "🔄 ebibot-upgrade"
2. AutoUpgradeCog が受信 → uv lock --upgrade-package && uv sync を実行
3. systemctl restart discord-bot で自分自身を再起動

このファイルは設定定義のみ。実行ロジックは claude_discord.cogs.auto_upgrade に委譲。
"""

from __future__ import annotations

from claude_discord.cogs.auto_upgrade import UpgradeConfig

_UV = "/home/ebi/.local/bin/uv"

EBIBOT_UPGRADE_CONFIG = UpgradeConfig(
    package_name="claude-code-discord-bridge",
    trigger_prefix="🔄 ebibot-upgrade",
    working_dir="/home/ebi/discord-bot",
    upgrade_command=[_UV, "lock", "--upgrade-package", "claude-code-discord-bridge"],
    sync_command=[_UV, "sync"],
    restart_command=["/usr/bin/sudo", "/usr/bin/systemctl", "restart", "discord-bot.service"],
    upgrade_approval=True,
    restart_approval=True,
    slash_command_enabled=True,
)
