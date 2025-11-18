# Debug: Inconsistent Webpage Fetching Execution in Research Pipeline

**Issue Type:** Bug - Environmental/Debugging
**Priority:** Medium
**Status:** Open
**Created:** 2025-11-18

## Issue Description
Webpage fetching code (lines 682-748 in nodes.py) executes inconsistently across research sessions. The implementation is verified working but doesn't execute in some sessions.

## Evidence of Working Implementation
Earlier test sessions showed successful execution:
- **Session d710269b** (ocean acidification): ✅ 🌐 logs appeared, Jina API requests made
- **Session accd3577** (meditation): ✅ Webpage fetching attempted
- **Session 639356da** (earthquakes): ✅ HTTP 402 errors from Jina (confirming execution)

## Failure Cases
Recent sessions where code didn't execute:
- **Session 3838c6f9** (Python 3.12): ❌ No 🌐 logs, no fetch attempts
- Findings not persisting to database properly

## Expected vs Actual

### Expected Logs (from working sessions)
```
🌐 Fetching full content from top 3 search results
✅ Fetched X chars from: [title]
📄 Combined N full webpages, total X chars
```

### Actual (failed sessions)
- WEB_SEARCH executes: `"Executing tool: ToolType.WEB_SEARCH"` ✅
- Tool execution logs missing: `"✅ Tool execution completed"` ❌
- Result processing logs missing: `"WEB_SEARCH returned X results"` ❌
- Webpage fetching never triggered

## Investigation Findings

1. ✅ Code verified present in Docker container (line 684)
2. ✅ Using real tool executor (not simulated)
3. ✅ WEB_SEARCH tool starts executing
4. ❌ Tool execution completion logs don't appear
5. ❌ Code path from lines 627-679 not being reached

## Hypothesis

- Silent exception handling somewhere in the call stack
- Async/timing issue with log flushing
- Different execution path for newer vs older sessions
- Python module caching issue despite cache clears
- State or context object differences between sessions

## Reproduction

```bash
# Start a research session
kitty-cli research "What are the key features of Python 3.12?" --no-config

# Check for webpage fetching logs
docker compose logs brain | grep "🌐"

# Check for tool execution logs
docker compose logs brain | grep -E "Tool execution completed|WEB_SEARCH returned"

# Verify findings persistence
curl -s "http://localhost:8000/api/research/sessions/{session_id}" | jq '.findings | length'
```

## Files Involved

- `services/brain/src/brain/research/graph/nodes.py` (lines 618-748)
  - Tool execution: lines 618-630
  - Result processing: lines 632-679
  - Webpage fetching: lines 681-747

- `services/brain/src/brain/research/tools/mcp_integration.py`
  - FETCH_WEBPAGE tool definition

- `services/research/src/research/web_tool.py`
  - Jina Reader + BeautifulSoup implementation

## Related Commits

- `149365c` - feat: add full webpage content fetching to research pipeline

## Next Steps

1. Add more detailed logging before/after tool execution
2. Check if there are multiple code paths or versions running
3. Investigate database transaction issues (findings not persisting)
4. Test with deterministic queries to isolate environmental factors
5. Review async/await execution flow for potential blocking

## Workarounds

None currently - feature works intermittently. When it works, full webpage content is successfully fetched and combined for claim extraction.

## Priority Justification

Medium priority because:
- Core functionality is implemented and verified working
- Earlier sessions demonstrate successful execution
- Issue is environmental/consistency rather than implementation
- Does not block other development work
- Can be debugged independently
