# I/O Control Improvement Plan

## Goals
- Make provider/tool toggles predictable and visible.
- Use a single runtime state (Redis/in-memory) and avoid unnecessary `.env` churn.
- Tie toggles to actual tool availability and restarts with clear impacts.
- Improve observability (logs/UI) and alignment across brain/gateway/executors.

## Quick Wins (phase 1)
- Fix `FeatureStateManager` default env path (use project root) and add “volatile” mode to skip `.env` writes for quick flips.
- Expose tool availability and impacts in `/api/io-control/state`: which tools/providers would be enabled/disabled, and whether restart is required.
- Log allow/deny decisions in `UnifiedPermissionGate` (provider-level) so we can see why calls are blocked.
- Ensure all external provider calls route through `UnifiedPermissionGate` (research_deep, openai/anthropic chat, etc.).

## Structural Cleanups (phase 2)
- Map features → tools explicitly in `feature_registry`/`get_tool_availability` (e.g., `web_search` free, `research_deep` → Perplexity, `openai_chat`, `anthropic_chat`).
- Group features by category (providers, routing, devices, storage); hide or prune unused toggles.
- Make restart scopes actionable: map `RestartScope` to real scripts (`llama` restart, gateway reload, or stack restart) and surface “pending restart” hints in the dashboard.
- Surface health/cost hints inline (missing API keys, estimated cost per call).

## UX/Docs
- Dashboard: show “Current tool availability” and a concise “Impacts” section when toggling.
- Docs: short runbook on how I/O Control interacts with env, budget, and permission gate.

## Rollout Steps
1) Phase 1 code changes (state manager, tool availability in API, logging, gate alignment).
2) Phase 2 mapping and UI refinements.
3) Update tests to assert feature → tool availability and provider blocking/allowing.
