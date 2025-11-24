# Secrets and I/O Control

## Where to set secrets
- **.env (local, not committed):** place provider keys and tokens here: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `PERPLEXITY_API_KEY`, `ZOO_API_KEY`, `TRIPO_API_KEY`, `BRAVE_SEARCH_API_KEY`, `JINA_API_KEY`, `HOME_ASSISTANT_TOKEN`, etc. `.env` is git-ignored.
- **I/O Control Dashboard:** toggles are persisted in Redis and can override runtime availability; persistence to `.env` depends on the FeatureStateManager settings (volatile vs persisted).
- **.env.example:** contains placeholders only; do not put real keys here.

## Interaction with I/O Control
- Provider toggles map to tool availability:
  - `perplexity_api` → `research_deep`
  - `openai_api` → `openai_chat`
  - `anthropic_api` → `anthropic_chat`
  - Cloud routing/offline mode must allow external calls.
- `/api/io-control/state` returns tool availability, enabled functions, health warnings, restart impacts, and cost hints.
- UnifiedPermissionGate checks I/O Control before external calls; if a provider is disabled or offline mode is on, the call is blocked.

## Restart impacts
- Feature restart scopes map to:
  - `llamacpp`: restarts llama.cpp servers.
  - `service`: targeted service restarts (see feature definitions).
  - `stack`: full Docker stack restart.
- The I/O Control state API surfaces these impacts.

## Model/provider notes
- In **Ollama mode** (`LOCAL_REASONER_PROVIDER=ollama`), llama.cpp F16 settings are unused for the main reasoner but remain for fallback seats (Q4/Q4B/Summary/Vision).
- In **llama.cpp mode**, ensure model paths/ports align with `LLAMACPP_*` envs.

## Safety
- Never commit real keys. Use `.env` locally; rely on I/O Control for runtime toggles.
- If a tool is unavailable, the UI/API will show disabled status and a hint to set the required env key or enable cloud routing.***
