"""Optional per-project configuration at `.spark/guard.json`.

A project that never writes this file gets the defaults below. A malformed file is
treated as absent — a guard that refuses to run because its own config has a typo
would be worse than one that runs with defaults.
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_NAME = "guard.json"

# Rule modes: "block" (deny the write), "warn" (allow, explain), "off".
DEFAULT_RULES = {
    "plan-requires-approved-spec": "block",
    "qa-requires-passed-review": "block",
    "release-requires-green-gates": "block",
    "overrides-are-human-only": "block",
}

DEFAULTS = {
    "enabled": True,
    "ledger": True,
    "drift_check": True,
    "trail": True,
    "activity": True,
    "template_check": True,
    "rules": DEFAULT_RULES,
}


class Config:
    def __init__(self, data: dict | None = None):
        merged = dict(DEFAULTS)
        merged["rules"] = dict(DEFAULT_RULES)
        if isinstance(data, dict):
            for key, value in data.items():
                if key == "rules" and isinstance(value, dict):
                    merged["rules"].update(
                        {k: v for k, v in value.items() if v in ("block", "warn", "off")}
                    )
                elif key in DEFAULTS and key != "rules":
                    merged[key] = value
        self._data = merged

    @property
    def enabled(self) -> bool:
        return bool(self._data["enabled"])

    @property
    def ledger(self) -> bool:
        return self.enabled and bool(self._data["ledger"])

    @property
    def drift_check(self) -> bool:
        return self.enabled and bool(self._data["drift_check"])

    @property
    def trail(self) -> bool:
        return self.enabled and bool(self._data["trail"])

    @property
    def activity(self) -> bool:
        return self.enabled and bool(self._data["activity"])

    @property
    def template_check(self) -> bool:
        return self.enabled and bool(self._data["template_check"])

    def rule_mode(self, rule_id: str) -> str:
        if not self.enabled:
            return "off"
        return self._data["rules"].get(rule_id, "off")


def load(root: Path) -> Config:
    """Read `<root>/.spark/guard.json`; fall back to defaults on anything unusual."""
    path = Path(root) / ".spark" / CONFIG_NAME
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return Config()
    try:
        return Config(json.loads(raw))
    except (ValueError, TypeError):
        return Config()
