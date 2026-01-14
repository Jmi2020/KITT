from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import Any


class ModeSafety(StrEnum):
    SAFE = auto()
    NEUTRAL = auto()
    DESTRUCTIVE = auto()
    YOLO = auto()


class AgentMode(StrEnum):
    DEFAULT = auto()
    AUTO_APPROVE = auto()
    PLAN = auto()
    ACCEPT_EDITS = auto()
    AUTO_ITERATE = auto()

    @property
    def display_name(self) -> str:
        return MODE_CONFIGS[self].display_name

    @property
    def description(self) -> str:
        return MODE_CONFIGS[self].description

    @property
    def config_overrides(self) -> dict[str, Any]:
        return MODE_CONFIGS[self].config_overrides

    @property
    def auto_approve(self) -> bool:
        return MODE_CONFIGS[self].auto_approve

    @property
    def safety(self) -> ModeSafety:
        return MODE_CONFIGS[self].safety

    @property
    def should_auto_iterate(self) -> bool:
        """Returns True if this mode should automatically continue on incomplete tasks."""
        return self == AgentMode.AUTO_ITERATE

    @classmethod
    def from_string(cls, value: str) -> AgentMode | None:
        try:
            return cls(value.lower())
        except ValueError:
            return None


@dataclass(frozen=True)
class ModeConfig:
    display_name: str
    description: str
    safety: ModeSafety = ModeSafety.NEUTRAL
    auto_approve: bool = False
    config_overrides: dict[str, Any] = field(default_factory=dict)


PLAN_MODE_TOOLS = ["grep", "read_file", "todo"]
ACCEPT_EDITS_TOOLS = ["write_file", "search_replace"]

MODE_CONFIGS: dict[AgentMode, ModeConfig] = {
    AgentMode.DEFAULT: ModeConfig(
        display_name="Default",
        description="Requires approval for tool executions",
        safety=ModeSafety.NEUTRAL,
        auto_approve=False,
    ),
    AgentMode.PLAN: ModeConfig(
        display_name="Plan",
        description="Read-only mode for exploration and planning",
        safety=ModeSafety.SAFE,
        auto_approve=True,
        config_overrides={"enabled_tools": PLAN_MODE_TOOLS},
    ),
    AgentMode.ACCEPT_EDITS: ModeConfig(
        display_name="Accept Edits",
        description="Auto-approves file edits only",
        safety=ModeSafety.DESTRUCTIVE,
        auto_approve=False,
        config_overrides={
            "tools": {
                "write_file": {"permission": "always"},
                "search_replace": {"permission": "always"},
            }
        },
    ),
    AgentMode.AUTO_APPROVE: ModeConfig(
        display_name="Auto Approve",
        description="Auto-approves all tool executions",
        safety=ModeSafety.YOLO,
        auto_approve=True,
    ),
    AgentMode.AUTO_ITERATE: ModeConfig(
        display_name="Auto Iterate",
        description="Auto-approves and loops until todos complete",
        safety=ModeSafety.YOLO,
        auto_approve=True,
    ),
}


def get_mode_order() -> list[AgentMode]:
    return [
        AgentMode.DEFAULT,
        AgentMode.PLAN,
        AgentMode.ACCEPT_EDITS,
        AgentMode.AUTO_APPROVE,
        AgentMode.AUTO_ITERATE,
    ]


def next_mode(current: AgentMode) -> AgentMode:
    order = get_mode_order()
    idx = order.index(current)
    return order[(idx + 1) % len(order)]
