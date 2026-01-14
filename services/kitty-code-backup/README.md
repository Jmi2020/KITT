# kitty-code KITTY Customizations Backup

Created: 2026-01-13
Purpose: Preserve KITTY-specific code before vanilla mistral-vibe reset

## Backup Contents

### integrations/
- `mcp_kitty.py` - Auto-discovery of KITTY services (brain, cad, fabrication, memory, discovery)

### core/tools/
- `selector.py` - Category-based tool filtering (search, browser, filesystem, code, memory, cad, fabrication, discovery, security)
- `embeddings.py` - SentenceTransformer embedding manager with disk caching

### cli/textual_ui/widgets/
- `welcome.py` - **GRADIENT CAT LOGO** with animation (Electric Cyan #28E6FF to Hot Pink #FF3CB4)
- `queue_indicator.py` - Shows pending message count during agent processing
- `directory_browser.py` - Interactive /cd command browser
- `no_markup_static.py` - Static widget base class without markup interpretation

### cli/textual_ui/renderers/
- `tool_renderers.py` - Custom rendering for bash, file operations, etc.

### update_notifier/adapters/
- `github_version_update_gateway.py` - Airgap stub (returns None)
- `pypi_version_update_gateway.py` - Airgap stub (returns None)
- `filesystem_update_cache_repository.py` - Cache implementation

## Restoration Order

1. **Priority A**: Airgap stubs, MCP stderr suppression
2. **Priority B**: Queue indicator, Directory browser
3. **Priority C**: Semantic tool selection, KITTY service discovery, Custom renderers

## Recovery

If vanilla reset fails:
```bash
git checkout kitty-code-pre-reset -- services/kitty-code/
```
