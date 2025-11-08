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
<!-- MANUAL ADDITIONS END -->
