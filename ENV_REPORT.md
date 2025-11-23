# Repository Guidelines: .env Rationalization Report

## Scope
This note highlights the most critical `.env` fields in KITTY, how they are consumed, and practical steps to slim the file while keeping startup scripts and agents healthy.

## Critical Variables (high impact)
- **LLM routing & health:** `LOCAL_REASONER_PROVIDER` (ollama|llamacpp), `OLLAMA_HOST`, `OLLAMA_MODEL`, `LLAMACPP_Q4_PORT/ALIAS/HOST`, `LLAMACPP_F16_*`, `LLAMACPP_VISION_*`, `LLAMACPP_MODELS_DIR`. These drive `start-all.sh` health checks and router selection; missing/incorrect values break startup or routing.
- **Paths & artifacts:** `KITTY_ARTIFACTS_DIR`, model paths (e.g., `LLAMACPP_PRIMARY_MODEL`, `LLAMACPP_CODER_MODEL`, `LLAMACPP_VISION_MODEL/MMPROJ`). Needed for llama.cpp to find weights; safe defaults could live in scripts.
- **Safety/budgeting:** `BUDGET_PER_TASK_USD`, `CONFIDENCE_THRESHOLD`, `API_OVERRIDE_PASSWORD`, `HAZARD_CONFIRMATION_PHRASE`, `VERBOSITY`. Used by Brain safety/routing logic.
- **Service URLs/ports:** `DATABASE_URL`, `RABBITMQ_URL` (+ user/pass), `REDIS_*`, `MINIO_*`, `GRAFANA_*`, `PROMETHEUS_*`, `IMAGE_SERVICE_URL`, `GATEWAY/LOAD_BALANCER` ports. Compose relies on these; changing them without compose updates breaks services.
- **Feature toggles:** `ENABLE_*_COLLECTIVE`, `OFFLINE_MODE`, `LLAMACPP_*_ENABLED`, `LLAMACPP_*_FLASH_ATTN`, `LLAMACPP_*_PARALLEL/BATCH`. Non-critical defaults can be sourced from code instead of `.env`.

## Observations
- The file reads like a runbook with extensive comments and many optional toggles; only a subset is required for a working local stack.
- Start scripts already carry sane defaults for ports/hosts and now fall back to localhost for Ollama pulls; many values can move out of `.env`.
- Multiple redundant sections (e.g., Q4/F16/vision knobs, message queue notes) increase length without changing runtime.

## Slimming Strategies
1) **Create a minimal `.env.example`** with only required variables: user identifiers, `LOCAL_REASONER_PROVIDER`, `OLLAMA_HOST`/`OLLAMA_MODEL`, `LLAMACPP_MODELS_DIR` + key model paths, `DATABASE_URL`, `RABBITMQ_URL` (if queue enabled), `IMAGE_SERVICE_URL`, and safety/budget knobs. Point contributors to full docs for optional tuning.
2) **Move defaults into code/scripts:** Use hardcoded fallbacks in `ops/scripts/*` and Pydantic settings for batch/threads/flash_attn so those lines can be dropped from `.env`.
3) **Group optional features into profiles:** e.g., `env.message-queue`, `env.observability`, `env.vision`. Load selectively (`set -a source env.message-queue`).
4) **Prune verbose comments:** Keep one-line intent per block; relocate long explanations to `docs/agents.md` or a new `docs/env-tuning.md`.
5) **Use anchored variables:** Derive URLs from shared host/port vars to reduce repetition (e.g., `RABBITMQ_URL=amqp://$RABBITMQ_USER:$RABBITMQ_PASSWORD@$RABBITMQ_HOST:$RABBITMQ_PORT/`).
6) **Secret hygiene:** Move real secrets to `.env.local` (gitignored) and keep public defaults in `.env.example`.

## Proposed Minimal Set (safe baseline)
- Identity/safety: `USER_NAME`, `KITTY_USER_NAME`, `KITTY_USER_ID`, `VERBOSITY`, `CONFIDENCE_THRESHOLD`, `BUDGET_PER_TASK_USD`, `HAZARD_CONFIRMATION_PHRASE`, `API_OVERRIDE_PASSWORD`.
- LLM core: `LOCAL_REASONER_PROVIDER`, `OLLAMA_HOST`, `OLLAMA_MODEL`, `LLAMACPP_MODELS_DIR`, `LLAMACPP_Q4_MODEL`, `LLAMACPP_F16_MODEL`, `LLAMACPP_VISION_MODEL`, `LLAMACPP_VISION_MMPROJ`, port/alias trio for Q4/F16/Vision.
- Services: `DATABASE_URL`, `RABBITMQ_URL` (if queue), `IMAGE_SERVICE_URL`, `GATEWAY/LOAD_BALANCER` ports if overridden.
- Optional profiles: observability (`PROMETHEUS/GRAFANA/LOKI/TEMPO`), message queue, vision toggle, offline mode.

Adopting the minimal set + profiles should drop the 650+ line `.env` to ~60–80 required lines, with detailed guidance moved to docs.***
