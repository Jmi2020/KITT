"""Safety policy definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from common.db.models import HazardLevel


@dataclass
class HazardPolicy:
    name: str
    requires_dual_confirm: bool
    requires_presence: bool
    allowed_roles: List[str]
    hazard_level: HazardLevel


DEFAULT_POLICIES: Dict[str, HazardPolicy] = {
    "unlock": HazardPolicy(
        name="unlock",
        requires_dual_confirm=True,
        requires_presence=True,
        allowed_roles=["safety", "admin"],
        hazard_level=HazardLevel.high,
    ),
    "power_enable": HazardPolicy(
        name="power_enable",
        requires_dual_confirm=True,
        requires_presence=True,
        allowed_roles=["safety", "operator"],
        hazard_level=HazardLevel.high,
    ),
    "unlock_light": HazardPolicy(
        name="unlock_light",
        requires_dual_confirm=False,
        requires_presence=True,
        allowed_roles=["operator", "engineer", "safety"],
        hazard_level=HazardLevel.medium,
    ),
}


def get_policy(intent: str) -> HazardPolicy | None:
    return DEFAULT_POLICIES.get(intent)
