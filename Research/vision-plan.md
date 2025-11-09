# Vision Reference Pipeline Plan

## Objective
Give KITTY a first-class vision workflow: search the web for candidate images (e.g., "Gandalf rubber duck"), verify relevance with a local vision model, present a lightweight gallery to the user, store only the chosen references, and feed those references into future APIs (CAD/Tripo).

## Phases

### Phase 0 – Infrastructure & Assets
- [ ] Install Gemma-3 vision GGUF + matching mmproj under `models/gemma-3-27b-it-GGUF/`.
- [ ] Build latest `llama.cpp` with Gemma support; ensure `llama-server --mmproj` works.
- [ ] Extend `start-llamacpp-dual.sh` + validator to launch `kitty-vision` (done).
- [ ] Ensure CLI timeout + GPU budgets can handle vision inference.

### Phase 1 – Vision MCP Server
- [ ] Add `services/mcp/src/mcp/servers/vision_server.py` with tools:
  - `image_search(q, top_k)` (SearXNG → Brave fallback)
  - `image_filter(q, images[], threshold)` (Gemma vision captions / CLIP-like scoring)
  - `store_selection(session_id, selections[])` (persist to MinIO)
- [ ] Register server in `brain.tools.mcp_client` so ReAct can discover tools.

### Phase 2 – Gateway + CLI integrations
- [ ] Create FastAPI router `services/gateway/src/routers/vision.py` with `/api/vision/search|filter|store`.
- [ ] Expose a CLI command (`kitty-cli vision <query>`) that:
  1. Calls search → filter
  2. Prints a compact gallery (index, thumbnail URL, caption)
  3. Accepts selection indices and calls `store` to persist references
- [ ] Save selection metadata locally (session ID, presigned URLs) for later queries.

### Phase 3 – Downstream consumers
- [ ] Update CAD service (Tripo adapter) to accept `image_refs` array.
- [ ] Teach ReAct agent when to suggest images (e.g., "show me ducks").
- [ ] Optional: React gallery UI using `/api/vision/*` for richer workflows.

## Open Questions / TODO
- CLIP vs Gemma vision: start with Gemma for captions; revisit CLIP scoring if needed.
- MinIO deployment: confirm bucket + credentials in `.env`, verify presigned URL TTL.
- Image search rate limits: ensure SearXNG is configured for image category; add Brave key fallback.
- Storage quota: define retention policy for reference images.

## References
- Research doc: `Research/visionMCP.md`
- Vision model: `/Users/Shared/Coding/models/gemma-3-27b-it-GGUF`
- Related scripts: `ops/scripts/start-llamacpp-dual.sh`, `start-kitty-validated.sh`
