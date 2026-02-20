"""Architecture test: EbiBot must NOT wire up ccdb zero-config services.

Background
----------
ccdb (claude-code-discord-bridge) follows the Zero-Config Principle:
    "Consumers must get new features by updating the package alone —
    no code changes, no wiring required."
    (See: claude-code-discord-bridge CLAUDE.md § Zero-Config Principle)

ccdb services listed in ZERO_CONFIG_SERVICES auto-initialize themselves
from environment variables. EbiBot should NEVER import or instantiate
them directly — doing so means ccdb's auto-init is broken and the
feature will only work for EbiBot, not for any other consumer.

This test fails fast when someone accidentally adds such wiring, catching
the bug at CI time rather than after the next consumer reports "feature
doesn't work without code changes".

If you are seeing this failure
-------------------------------
1. Remove the import / instantiation of the ccdb service from src/main.py
2. Instead, add the feature's env var to discord-bot/.env  (and .env.example)
3. Verify the feature works by running the bot — ccdb will auto-init

If the ccdb service does NOT yet auto-init from env vars, fix ccdb first:
    _get_xxx() lazy resolver should read the env var and create the service.
    See CoordinationService / _get_coordination() for the reference pattern.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

# ── What EbiBot must never instantiate directly ──────────────────────────────
# These ccdb services self-initialize from env vars.
# Adding new entries here is the ONLY change needed when ccdb gains a new
# zero-config service — no other code in EbiBot should change.
ZERO_CONFIG_SERVICES: dict[str, str] = {
    # class name → the env var that configures it (for error messages)
    "CoordinationService": "COORDINATION_CHANNEL_ID",
    "ThreadStatusDashboard": "THREAD_DASHBOARD_CHANNEL_ID",
    # Add future zero-config ccdb services here, e.g.:
    # "MetricsService": "METRICS_CHANNEL_ID",
}

MAIN_PY = Path(__file__).parent.parent / "src" / "main.py"


def _parse_main() -> ast.Module:
    return ast.parse(MAIN_PY.read_text(), filename=str(MAIN_PY))


def _find_direct_imports(tree: ast.Module) -> list[tuple[str, int]]:
    """Return (class_name, lineno) for zero-config services imported in main.py."""
    hits: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname or alias.name
                if name in ZERO_CONFIG_SERVICES:
                    hits.append((name, node.lineno))
    return hits


def _find_direct_instantiations(tree: ast.Module) -> list[tuple[str, int]]:
    """Return (class_name, lineno) for zero-config services instantiated in main.py."""
    hits: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Handles both `CoordinationService(...)` and `some.CoordinationService(...)`
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name and name in ZERO_CONFIG_SERVICES:
                hits.append((name, node.lineno))
    return hits


def _fmt_error(violations: list[tuple[str, int]], kind: str) -> str:
    lines = [
        f"EbiBot src/main.py has {kind} for ccdb zero-config service(s).",
        "",
        "These services auto-initialize from environment variables.",
        "EbiBot must NOT wire them up — just set the env var in .env.",
        "",
        "Violations found:",
    ]
    for cls, lineno in violations:
        env_var = ZERO_CONFIG_SERVICES[cls]
        lines.append(
            f"  Line {lineno}: {cls!r}  →  set {env_var} in .env instead"
        )
    lines += [
        "",
        "Fix: remove the import/instantiation from src/main.py.",
        "See claude-code-discord-bridge CLAUDE.md § Zero-Config Principle.",
    ]
    return textwrap.dedent("\n".join(lines))


class TestZeroConfigBoundary:
    """EbiBot must not import or instantiate ccdb zero-config services."""

    def test_no_direct_import_of_zero_config_services(self) -> None:
        tree = _parse_main()
        violations = _find_direct_imports(tree)
        assert not violations, _fmt_error(violations, "a direct import")

    def test_no_direct_instantiation_of_zero_config_services(self) -> None:
        tree = _parse_main()
        violations = _find_direct_instantiations(tree)
        assert not violations, _fmt_error(violations, "a direct instantiation")

    def test_zero_config_services_list_is_documented(self) -> None:
        """Sanity check: the list must be non-empty so the tests are meaningful."""
        assert ZERO_CONFIG_SERVICES, (
            "ZERO_CONFIG_SERVICES is empty — the architecture tests protect nothing. "
            "Add at least one ccdb zero-config service class name."
        )
