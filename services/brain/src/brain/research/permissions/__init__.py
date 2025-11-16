"""
Unified Permission System for Research Pipeline

Single, clear permission flow:
1. I/O Control: Is provider enabled?
2. Budget: Can we afford it?
3. Runtime Approval: Smart cost-based gating
"""

from .unified_gate import (
    UnifiedPermissionGate,
    PermissionResult,
    ApprovalTier,
)

__all__ = [
    "UnifiedPermissionGate",
    "PermissionResult",
    "ApprovalTier",
]
