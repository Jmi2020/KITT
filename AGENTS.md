# KITT Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-11-04

## Active Technologies

- Python 3.11 (services), TypeScript 5.x (PWA), Bash (ops), YAML (compose) + FastAPI, Pydantic, paho-mqtt, SQLAlchemy, Home Assistant API, OctoPrint REST, Perplexity MCP SDK, Zoo CAD SDK, Tripo API, CadQuery/FreeCAD, llama.cpp/MLX runtimes, Whisper.cpp, Piper (001-KITTY)

## Project Structure

```text
src/
tests/
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Python 3.11 (services), TypeScript 5.x (PWA), Bash (ops), YAML (compose): Follow standard conventions

## Recent Changes

- 001-KITTY: Added Python 3.11 (services), TypeScript 5.x (PWA), Bash (ops), YAML (compose) + FastAPI, Pydantic, paho-mqtt, SQLAlchemy, Home Assistant API, OctoPrint REST, Perplexity MCP SDK, Zoo CAD SDK, Tripo API, CadQuery/FreeCAD, llama.cpp/MLX runtimes, Whisper.cpp, Piper

<!-- MANUAL ADDITIONS START -->
- 2025-11-06: **Cornerstone** — All tool-capable queries now flow through the `<user_query>` wrapper produced by `KittySystemPrompt` (`services/brain/src/brain/prompts/unified.py`). This keeps tool instructions intact, locks temperature to 0, and prevents hallucinated tools; see `README.md` (CLI workflow) for operator guidance.
- 2025-11-06: **Autonomy Guardrails** — `/api/autonomy/status` + Prometheus gauges expose daily budget, idle state, and readiness (scheduled vs. exploration) driven by `ResourceManager`. Configure with `AUTONOMOUS_ENABLED`, `AUTONOMOUS_DAILY_BUDGET_USD`, and `AUTONOMOUS_IDLE_THRESHOLD_MINUTES=120`.
- 2025-11-06: **Freshness Heuristics** — Time-sensitive prompts now auto-set `freshness_required`, embed the current UTC timestamp, and instruct the LLM to prefer live tools (`web_search`) for anything after its training cutoff (`services/brain/src/brain/routing/freshness.py`, `KittySystemPrompt`).
- 2025-11-06: **Web Search Cascade** — `web_search` now tries self-hosted SearXNG, then Brave’s free tier, before falling back to DuckDuckGo/Perplexity. Configure `SEARXNG_BASE_URL`, `BRAVE_SEARCH_API_KEY`, and `BRAVE_SEARCH_ENDPOINT`. See README “Web Search Stack” for setup.
- 2025-11-08: **Content Extraction** — `fetch_webpage` calls Jina Reader for full-page Markdown and drops to the local BeautifulSoup parser if the API is unavailable. Configure `JINA_API_KEY` / `JINA_READER_BASE_URL` in `.env`.
<!-- MANUAL ADDITIONS END -->
