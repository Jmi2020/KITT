# API Auto-Approval Fix for Autonomous Workflows

## Problem

The BrainRouter's `PermissionManager` was blocking API escalation to MCP/Frontier tiers during autonomous workflows due to trying to use interactive `input()` prompts in non-interactive contexts (Docker containers, API calls).

### Symptoms
- API requests with `forceTier: "mcp"` still routed to `local` tier
- No errors visible in logs
- Permission requests silently failed with `EOFError` in Docker

### Root Cause
In `services/brain/src/brain/routing/permission.py` lines 127-137:

```python
else:
    # Default: CLI prompt (blocking)
    message = self._format_permission_request(request)
    print(message, end="", flush=True)

    try:
        user_input = input().strip()
    except (EOFError, KeyboardInterrupt):
        print("\nPermission denied (interrupted)")
        return False  # ← Permission denied, falls back to local tier
```

## Solution

Added `API_AUTO_APPROVE` environment variable support to enable auto-approval for autonomous workflows.

### Code Changes

**services/brain/src/brain/routing/permission.py** (line 60):
```python
# Auto-approve can be set via env var for autonomous workflows
self._auto_approve = auto_approve or os.getenv("API_AUTO_APPROVE", "").lower() in ("true", "1", "yes")
```

**.env.example** and **.env**:
```bash
# API Permission Management
# Auto-approve API calls to cloud tier (for autonomous workflows, default: false)
API_AUTO_APPROVE=true
# Override password for manual API approval (default: omega)
API_OVERRIDE_PASSWORD=omega
```

### Testing

With `API_AUTO_APPROVE=true` set in `.env`, autonomous workflows (like KB generation) can now:

1. Request MCP tier escalation with `forceTier: "mcp"`
2. Get auto-approved without interactive prompts
3. Route to Perplexity API for web research
4. Return results without falling back to local tier

### Usage

**For interactive CLI**: Set `API_AUTO_APPROVE=false` to get prompted for approval
**For autonomous scripts**: Set `API_AUTO_APPROVE=true` to auto-approve all requests

Budget enforcement (`BUDGET_PER_TASK_USD`) still applies in both modes.

## Related Files

- `services/brain/src/brain/routing/permission.py` - PermissionManager implementation
- `services/brain/src/brain/routing/router.py` - BrainRouter that uses PermissionManager
- `ops/scripts/generate-kb-content.py` - KB generation script using MCP tier
- `.env` - Environment configuration

## Additional Issues Found

### Issue 2: Agentic Mode Override

**Problem**: `AGENTIC_MODE_ENABLED=true` in `.env` was overriding `useAgent: false` requests via the orchestrator logic: `agentic_mode = use_agent or settings.agentic_mode_enabled`

**Solution**: Changed `.env` to `AGENTIC_MODE_ENABLED=false` to match `.env.example` default

### Issue 3: Wrong Perplexity API Endpoint

**Problem**: `MCPClient` was calling `/query` endpoint, but Perplexity uses OpenAI-compatible `/chat/completions` endpoint, causing 404 errors

**Solution**: Fixed `services/brain/src/brain/routing/cloud_clients.py:23` to use `/chat/completions`

## Autonomous KB Generation Results

With all three issues fixed, autonomous knowledge base generation completed successfully:

**Generated Files** (5 total):
- `knowledge/materials/pla.md` - 3,424 characters with YAML frontmatter (bed_temp, cost_per_kg, density, print_temp, suppliers, sustainability_score)
- `knowledge/materials/petg.md` - 3,063 characters
- `knowledge/materials/abs.md` - 3,189 characters
- `knowledge/techniques/first-layer-adhesion.md` - 2,935 characters
- `knowledge/techniques/stringing-prevention.md` - 2,830 characters

**Content Quality**:
- Structured YAML frontmatter with searchable metadata
- Comprehensive markdown sections (Overview, Properties, Applications, Print Settings, Tips)
- Research citations indicating web sources from Perplexity
- Specific technical data (temperatures, strengths, material properties)

**Workflow Execution**:
1. Script queries brain API with research prompts
2. Brain routes to MCP tier (Perplexity) with `forceTier: "mcp"` and `freshnessRequired: true`
3. API_AUTO_APPROVE=true allows permission without interactive prompts
4. Results parsed and saved with python-frontmatter
5. Exit code 0 - successful completion

## Date
2025-11-07

## Sprint
Sprint 2: Knowledge Base Foundation (001-KITTY roadmap)
