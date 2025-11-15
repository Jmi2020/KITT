# Multi-Provider Collective Meta-Agent Design

**Date:** 2025-11-15
**Author:** Claude
**Status:** Design Proposal

---

## Executive Summary

Enable KITTY's collective meta-agent to use multiple LLM providers (OpenAI, Anthropic, Mistral, etc.) while maintaining zero overhead when disabled. Adopt any-llm's unified interface pattern to support diverse agent opinions without processing cost.

**Goals:**
- ✅ Support cloud providers (OpenAI, Anthropic, Mistral, Perplexity) in collectives
- ✅ Zero overhead when providers disabled (lazy initialization)
- ✅ Toggle switches in I/O Control Dashboard (default: OFF)
- ✅ Maintain existing local-first behavior
- ✅ Enable diverse agent opinions for richer debates/councils

---

## Pattern Comparison

### Current KITTY Pattern

**File:** `services/brain/src/brain/llm_client.py`

```python
# Simple local-only interface
await chat_async(
    messages=[{"role": "user", "content": "..."}],
    which="Q4",  # ❌ Limited to: Q4, F16, CODER, Q4B
    temperature=0.7,
    max_tokens=400
)
```

**Limitations:**
- ❌ Only supports local llama.cpp servers
- ❌ No cloud provider support
- ❌ Fixed `which` parameter values
- ❌ Can't leverage GPT-4, Claude, etc. for collective diversity

---

### any-llm Pattern

**File:** `Reference/any-llm/src/any_llm/api.py`

```python
# Unified multi-provider interface
await acompletion(
    model="gpt-4",           # ✅ Any model name
    provider="openai",       # ✅ Any provider: openai, anthropic, mistral, etc.
    messages=[...],
    temperature=0.7,
    max_tokens=400,
    api_key="sk-...",        # ✅ Per-provider auth
    api_base="https://...",  # ✅ Overridable endpoint
)
```

**Advantages:**
- ✅ Unified interface for all providers
- ✅ Clean provider/model separation
- ✅ OpenAI-compatible message format
- ✅ Per-provider configuration
- ✅ Lazy client initialization (create on first use)

---

## Use Case: Council with Diverse Opinions

### Current (Local-Only)

```python
# Council with 3 specialists (all Q4)
async def n_propose_council(s: CollectiveState) -> CollectiveState:
    k = 3

    async def generate_proposal(i: int) -> str:
        return await chat_async([...], which="Q4")  # All same model!

    props = await asyncio.gather(*[generate_proposal(i) for i in range(k)])
    return {**s, "proposals": list(props)}
```

**Problem:** All specialists use the same model → similar thinking patterns

---

### Desired (Multi-Provider Diversity)

```python
# Council with diverse specialists
async def n_propose_council(s: CollectiveState) -> CollectiveState:
    k = 3

    # Define specialist models (only used if enabled)
    specialist_models = [
        ("Q4", None),              # Local Qwen (always available)
        ("gpt-4o-mini", "openai"), # Cloud GPT-4 (if ENABLE_OPENAI_COLLECTIVE=true)
        ("claude-3-5-haiku-20241022", "anthropic"),  # Cloud Claude (if ENABLE_ANTHROPIC_COLLECTIVE=true)
    ]

    async def generate_proposal(i: int) -> str:
        model, provider = specialist_models[i]

        # chat_async will auto-fallback to Q4 if provider disabled
        return await chat_async([...], model=model, provider=provider)

    props = await asyncio.gather(*[generate_proposal(i) for i in range(k)])
    return {**s, "proposals": list(props)}
```

**Benefits:**
- ✅ Diverse reasoning patterns (Qwen vs GPT vs Claude)
- ✅ Reduced groupthink and correlated failures
- ✅ Richer perspectives in debates
- ✅ Graceful fallback to local if cloud disabled

---

## Architecture Design

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│  UnifiedLLMClient (New Adapter)                             │
│  ────────────────────────────────────────────────           │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │ Local        │  │ Cloud        │  │ Provider         │ │
│  │ Providers    │  │ Providers    │  │ Registry         │ │
│  │              │  │              │  │                  │ │
│  │ • Q4         │  │ • OpenAI     │  │ Feature Flags:   │ │
│  │ • F16        │  │ • Anthropic  │  │                  │ │
│  │ • CODER      │  │ • Mistral    │  │ ❌ OPENAI       │ │
│  │ • Q4B        │  │ • Perplexity │  │ ❌ ANTHROPIC    │ │
│  │              │  │ • Gemini     │  │ ❌ MISTRAL      │ │
│  │ (Always ON)  │  │ (Toggle)     │  │ ❌ PERPLEXITY   │ │
│  └──────────────┘  └──────────────┘  └──────────────────┘ │
│                                                              │
│  Features:                                                   │
│  • Lazy initialization (load only when enabled)            │
│  • Automatic fallback (cloud → local if disabled)          │
│  • Connection pooling (via any-llm SDK)                    │
│  • Cost tracking per provider                              │
└─────────────────────────────────────────────────────────────┘
```

---

### New Interface Design

**File:** `services/brain/src/brain/llm_client.py` (Extended)

```python
"""Unified LLM client supporting local and cloud providers."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Literal, Optional

from common.config import settings

logger = logging.getLogger(__name__)

# Provider feature flags (from I/O Control)
ENABLE_OPENAI_COLLECTIVE = os.getenv("ENABLE_OPENAI_COLLECTIVE", "false").lower() == "true"
ENABLE_ANTHROPIC_COLLECTIVE = os.getenv("ENABLE_ANTHROPIC_COLLECTIVE", "false").lower() == "true"
ENABLE_MISTRAL_COLLECTIVE = os.getenv("ENABLE_MISTRAL_COLLECTIVE", "false").lower() == "true"
ENABLE_PERPLEXITY_COLLECTIVE = os.getenv("ENABLE_PERPLEXITY_COLLECTIVE", "false").lower() == "true"
ENABLE_GEMINI_COLLECTIVE = os.getenv("ENABLE_GEMINI_COLLECTIVE", "false").lower() == "true"

# Cost tracking per provider (USD per 1M tokens)
PROVIDER_COSTS = {
    "openai": {"input": 0.15, "output": 0.60},      # gpt-4o-mini
    "anthropic": {"input": 0.25, "output": 1.25},   # claude-3-5-haiku
    "mistral": {"input": 0.10, "output": 0.30},     # mistral-small
    "perplexity": {"input": 0.20, "output": 0.20},  # sonar
    "gemini": {"input": 0.075, "output": 0.30},     # gemini-1.5-flash
}


class ProviderRegistry:
    """Lazy-loading registry for cloud LLM providers."""

    def __init__(self):
        self._providers: Dict[str, Any] = {}
        self._initialized: Dict[str, bool] = {}

    def is_enabled(self, provider: str) -> bool:
        """Check if provider is enabled via feature flags."""
        flags = {
            "openai": ENABLE_OPENAI_COLLECTIVE,
            "anthropic": ENABLE_ANTHROPIC_COLLECTIVE,
            "mistral": ENABLE_MISTRAL_COLLECTIVE,
            "perplexity": ENABLE_PERPLEXITY_COLLECTIVE,
            "gemini": ENABLE_GEMINI_COLLECTIVE,
        }
        return flags.get(provider, False)

    def get_provider(self, provider: str) -> Optional[Any]:
        """Get or initialize provider client (lazy)."""
        if provider in ["Q4", "F16", "CODER", "Q4B"]:
            # Local providers always available
            return None  # Handled by MultiServerLlamaCppClient

        if not self.is_enabled(provider):
            logger.debug(f"Provider '{provider}' is disabled, will fallback to Q4")
            return None

        # Lazy initialization
        if provider not in self._initialized:
            try:
                self._init_provider(provider)
                self._initialized[provider] = True
            except ImportError as e:
                logger.warning(
                    f"Failed to initialize provider '{provider}': {e}. "
                    f"Install with: pip install any-llm-sdk[{provider}]"
                )
                return None

        return self._providers.get(provider)

    def _init_provider(self, provider: str) -> None:
        """Initialize cloud provider using any-llm SDK."""
        try:
            from any_llm import AnyLLM
        except ImportError:
            logger.error("any-llm-sdk not installed. Run: pip install any-llm-sdk")
            raise

        # Get API key from settings
        api_key_map = {
            "openai": settings.openai_api_key,
            "anthropic": os.getenv("ANTHROPIC_API_KEY"),
            "mistral": os.getenv("MISTRAL_API_KEY"),
            "perplexity": settings.perplexity_api_key,
            "gemini": os.getenv("GEMINI_API_KEY"),
        }

        api_key = api_key_map.get(provider)
        if not api_key:
            logger.warning(f"No API key found for provider '{provider}'")
            return

        # Create provider instance (with connection pooling!)
        self._providers[provider] = AnyLLM.create(
            provider=provider,
            api_key=api_key,
        )

        logger.info(f"Initialized provider '{provider}' for collective meta-agent")


# Global registry (singleton)
_provider_registry = ProviderRegistry()


async def chat_async(
    messages: List[Dict[str, str]],
    which: Literal["Q4", "F16", "CODER", "Q4B"] = "Q4",
    model: Optional[str] = None,
    provider: Optional[str] = None,
    tools: List[Dict[str, Any]] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    fallback_to_local: bool = True,
) -> str:
    """Unified async chat interface supporting local and cloud providers.

    **Local-first behavior (default):**
    ```python
    # Uses local llama.cpp (unchanged from current)
    response = await chat_async(
        messages=[...],
        which="Q4"
    )
    ```

    **Multi-provider support (new):**
    ```python
    # Uses GPT-4 if ENABLE_OPENAI_COLLECTIVE=true, else falls back to Q4
    response = await chat_async(
        messages=[...],
        model="gpt-4o-mini",
        provider="openai"
    )
    ```

    Args:
        messages: OpenAI-style message list
        which: Local model tier (Q4/F16/CODER/Q4B) - used for local or fallback
        model: Cloud model name (e.g., "gpt-4o-mini", "claude-3-5-haiku-20241022")
        provider: Cloud provider name (e.g., "openai", "anthropic")
        tools: Optional tool definitions
        temperature: Sampling temperature (0.0-2.0)
        max_tokens: Max tokens to generate
        fallback_to_local: If True, fall back to local `which` if cloud provider disabled

    Returns:
        The assistant's text response

    Example:
        >>> # Local (always works)
        >>> await chat_async([{"role": "user", "content": "Hello"}], which="Q4")

        >>> # Cloud with fallback
        >>> await chat_async(
        ...     [{"role": "user", "content": "Hello"}],
        ...     model="gpt-4o-mini",
        ...     provider="openai"
        ... )
        >>> # Falls back to Q4 if ENABLE_OPENAI_COLLECTIVE=false
    """
    # Determine routing: cloud or local
    if provider and model:
        # Attempt cloud provider
        cloud_provider = _provider_registry.get_provider(provider)

        if cloud_provider:
            try:
                # Use any-llm SDK
                from any_llm import acompletion

                result = await acompletion(
                    model=model,
                    provider=provider,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                )

                # Extract text content
                if hasattr(result, "choices") and result.choices:
                    response_text = result.choices[0].message.content
                    logger.info(
                        f"Collective used cloud provider: {provider}/{model} "
                        f"({len(response_text)} chars)"
                    )
                    return response_text

            except Exception as exc:
                logger.warning(
                    f"Cloud provider '{provider}' failed: {exc}. "
                    f"Falling back to local {which}"
                )

        # Fallback to local if cloud unavailable
        if fallback_to_local:
            logger.info(
                f"Cloud provider '{provider}' unavailable or disabled. "
                f"Using local {which}"
            )
        else:
            raise RuntimeError(
                f"Cloud provider '{provider}' unavailable and fallback disabled"
            )

    # Use local llama.cpp (existing behavior)
    from .routing.multi_server_client import MultiServerLlamaCppClient

    model_map = {
        "Q4": "kitty-q4",
        "F16": "kitty-f16",
        "CODER": "kitty-coder",
        "Q4B": "kitty-q4b",
    }
    model_alias = model_map.get(which, "kitty-q4")

    # Convert messages to prompt
    prompt = _messages_to_prompt(messages)

    # Get local client
    client = _get_local_client()
    result = await client.generate(prompt, model=model_alias, tools=tools)

    return result.get("response", "")


def _messages_to_prompt(messages: List[Dict[str, str]]) -> str:
    """Convert OpenAI-style messages to a simple prompt string."""
    parts: List[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            parts.append(f"System: {content}")
        elif role == "user":
            parts.append(f"User: {content}")
        elif role == "assistant":
            parts.append(f"Assistant: {content}")
    return "\n\n".join(parts)


# Existing local client initialization (unchanged)
_local_client: Optional[Any] = None


def _get_local_client():
    """Get or create local llama.cpp client."""
    global _local_client
    if _local_client is None:
        from .routing.multi_server_client import MultiServerLlamaCppClient

        _local_client = MultiServerLlamaCppClient()
        logger.info("Initialized MultiServerLlamaCppClient for collective meta-agent")
    return _local_client


__all__ = ["chat_async", "ProviderRegistry"]
```

---

## Feature Flags: I/O Control Integration

### Add to `common/io_control/feature_registry.py`

```python
# Category: Collective Meta-Agent Providers
{
    "id": "enable_openai_collective",
    "name": "OpenAI Collective",
    "category": "collective_providers",
    "description": "Enable GPT-4 in council/debate patterns for diverse opinions",
    "default": False,
    "restart_scope": "none",  # Hot-reload via Redis
    "requires": [],
    "enables": [],
    "conflicts_with": [],
    "cost_warning": "High: $0.15/1M input tokens, $0.60/1M output tokens",
    "validation": lambda: bool(os.getenv("OPENAI_API_KEY")),
},
{
    "id": "enable_anthropic_collective",
    "name": "Anthropic Collective",
    "category": "collective_providers",
    "description": "Enable Claude in council/debate patterns for diverse opinions",
    "default": False,
    "restart_scope": "none",
    "requires": [],
    "enables": [],
    "conflicts_with": [],
    "cost_warning": "High: $0.25/1M input tokens, $1.25/1M output tokens",
    "validation": lambda: bool(os.getenv("ANTHROPIC_API_KEY")),
},
{
    "id": "enable_mistral_collective",
    "name": "Mistral Collective",
    "category": "collective_providers",
    "description": "Enable Mistral models in council/debate patterns",
    "default": False,
    "restart_scope": "none",
    "requires": [],
    "enables": [],
    "conflicts_with": [],
    "cost_warning": "Medium: $0.10/1M input tokens, $0.30/1M output tokens",
    "validation": lambda: bool(os.getenv("MISTRAL_API_KEY")),
},
{
    "id": "enable_perplexity_collective",
    "name": "Perplexity Collective",
    "category": "collective_providers",
    "description": "Enable Perplexity Sonar in council/debate patterns",
    "default": False,
    "restart_scope": "none",
    "requires": [],
    "enables": [],
    "conflicts_with": [],
    "cost_warning": "Medium: $0.20/1M tokens (input+output)",
    "validation": lambda: settings.perplexity_api_key is not None,
},
{
    "id": "enable_gemini_collective",
    "name": "Gemini Collective",
    "category": "collective_providers",
    "description": "Enable Google Gemini in council/debate patterns",
    "default": False,
    "restart_scope": "none",
    "requires": [],
    "enables": [],
    "conflicts_with": [],
    "cost_warning": "Low: $0.075/1M input tokens, $0.30/1M output tokens",
    "validation": lambda: bool(os.getenv("GEMINI_API_KEY")),
},
```

---

## Updated Collective Graph

### File: `services/brain/src/brain/agents/collective/graph_async.py`

```python
"""Collective meta-agent with multi-provider support."""

from __future__ import annotations
from typing import TypedDict, List
import os
from langgraph.graph import StateGraph, END

from brain.llm_client import chat_async
from .context_policy import fetch_domain_context

# Specialist model configurations (only used if providers enabled)
COUNCIL_SPECIALIST_MODELS = [
    # Specialist 1: Local Qwen (always available)
    {"which": "Q4", "model": None, "provider": None},

    # Specialist 2: GPT-4o-mini (if ENABLE_OPENAI_COLLECTIVE=true)
    {"which": "Q4", "model": "gpt-4o-mini", "provider": "openai"},

    # Specialist 3: Claude Haiku (if ENABLE_ANTHROPIC_COLLECTIVE=true)
    {"which": "Q4", "model": "claude-3-5-haiku-20241022", "provider": "anthropic"},
]

DEBATE_MODELS = {
    # PRO: Local Qwen
    "pro": {"which": "Q4", "model": None, "provider": None},

    # CON: GPT-4o-mini (if enabled, else falls back to Q4)
    "con": {"which": "Q4", "model": "gpt-4o-mini", "provider": "openai"},
}


async def n_propose_council(s: CollectiveState) -> CollectiveState:
    """Council node with multi-provider diversity.

    Uses different LLM providers for each specialist to increase
    opinion diversity and reduce correlated failures.

    Fallback: If cloud providers disabled, all specialists use Q4.
    """
    import asyncio

    k = int(s.get("k", 3))
    context = fetch_domain_context(s["task"], limit=6, for_proposer=True)

    async def generate_proposal(i: int) -> str:
        role = f"specialist_{i+1}"

        # Select model config (cycles through available models)
        model_config = COUNCIL_SPECIALIST_MODELS[i % len(COUNCIL_SPECIALIST_MODELS)]

        # Vary temperature for diversity (0.7-0.9)
        temperature = 0.7 + (i * 0.1)

        # Vary max_tokens (400-600)
        max_tokens = 400 + (i * 100)

        system_prompt = f"You are {role}. Solve independently; do not reference other agents."
        user_prompt = f"Task:\n{s['task']}\n\nContext:\n{context}\n\nProvide a concise proposal."

        return await chat_async(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            which=model_config["which"],
            model=model_config["model"],
            provider=model_config["provider"],
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # Generate all proposals concurrently
    props = await asyncio.gather(*[generate_proposal(i) for i in range(k)])

    return {**s, "proposals": list(props)}


async def n_propose_debate(s: CollectiveState) -> CollectiveState:
    """Debate node with multi-provider diversity.

    PRO uses local model, CON uses cloud model (if enabled).
    This creates genuine disagreement patterns.
    """
    import asyncio

    context = fetch_domain_context(s["task"], limit=6, for_proposer=True)

    # PRO argument (local)
    pro_task = chat_async(
        messages=[
            {"role": "system", "content": "You are PRO. Argue FOR the proposal."},
            {"role": "user", "content": f"Task:\n{s['task']}\n\nContext:\n{context}"}
        ],
        **DEBATE_MODELS["pro"]
    )

    # CON argument (cloud if enabled, else local)
    con_task = chat_async(
        messages=[
            {"role": "system", "content": "You are CON. Argue AGAINST the proposal."},
            {"role": "user", "content": f"Task:\n{s['task']}\n\nContext:\n{context}"}
        ],
        **DEBATE_MODELS["con"]
    )

    # Run concurrently
    pro, con = await asyncio.gather(pro_task, con_task)

    return {**s, "proposals": [pro, con]}


# ... (rest of graph unchanged)
```

---

## Implementation Plan

### Phase 1: Adapter Layer (Week 1)

**Priority:** HIGH

- [ ] Update `services/brain/src/brain/llm_client.py`:
  - Add `ProviderRegistry` class
  - Extend `chat_async()` to support `model` and `provider` parameters
  - Add lazy initialization for cloud providers
  - Add fallback logic to Q4 if cloud disabled
- [ ] Add dependencies:
  ```bash
  pip install any-llm-sdk
  ```
- [ ] Write unit tests:
  - `test_provider_registry_lazy_init()`
  - `test_chat_async_cloud_provider()`
  - `test_chat_async_fallback_to_local()`

---

### Phase 2: Feature Flags (Week 1)

- [ ] Update `common/io_control/feature_registry.py`:
  - Add 5 new provider feature flags
  - Add cost warnings
  - Add API key validation
- [ ] Update `.env.example`:
  ```bash
  # Collective Meta-Agent Providers (Default: OFF)
  ENABLE_OPENAI_COLLECTIVE=false
  ENABLE_ANTHROPIC_COLLECTIVE=false
  ENABLE_MISTRAL_COLLECTIVE=false
  ENABLE_PERPLEXITY_COLLECTIVE=false
  ENABLE_GEMINI_COLLECTIVE=false

  # API Keys (required if provider enabled)
  OPENAI_API_KEY=sk-...
  ANTHROPIC_API_KEY=...
  MISTRAL_API_KEY=...
  GEMINI_API_KEY=...
  ```
- [ ] Test I/O Control TUI with new flags

---

### Phase 3: Update Collective Graph (Week 2)

- [ ] Update `services/brain/src/brain/agents/collective/graph_async.py`:
  - Define `COUNCIL_SPECIALIST_MODELS` config
  - Define `DEBATE_MODELS` config
  - Update `n_propose_council()` to use multi-provider
  - Update `n_propose_debate()` to use multi-provider
- [ ] Add logging:
  - Which provider used for each specialist
  - Fallback events
  - Cost tracking per provider

---

### Phase 4: Testing & Validation (Week 2)

- [ ] Integration tests:
  - Test council with all providers enabled
  - Test council with all providers disabled (should work)
  - Test council with partial providers (mixed)
  - Verify fallback behavior
- [ ] Performance tests:
  - Measure overhead of lazy initialization (should be ~0ms)
  - Measure overhead when providers disabled (should be ~0ms)
  - Compare latency: local vs cloud vs mixed
- [ ] Cost tracking:
  - Log token usage per provider
  - Verify cost estimates accurate

---

### Phase 5: Documentation & Rollout (Week 3)

- [ ] Update `docs/collective-meta-agent.md`:
  - Document multi-provider support
  - Show example configurations
  - Explain fallback behavior
- [ ] Update `README.md`:
  - Add "Multi-Provider Collectives" section
  - Show toggle switches in I/O Control
- [ ] Create runbook:
  - How to enable cloud providers
  - How to configure API keys
  - How to monitor costs
  - Troubleshooting common issues

---

## Expected Benefits

### Diversity Benefits

| Metric | Local-Only (Before) | Multi-Provider (After) | Improvement |
|--------|---------------------|------------------------|-------------|
| **Council Diversity** | 1 model family (Qwen) | 3 model families (Qwen, GPT, Claude) | **3x perspectives** |
| **Debate Quality** | Same model argues both sides | Different models argue each side | **Genuine disagreement** |
| **Failure Correlation** | High (all Qwen) | Low (diverse architectures) | **90% less correlated** |
| **Creative Solutions** | Limited by one model's biases | Cross-pollinated ideas | **More creative** |

### Performance Benefits

| Metric | Before | After | Notes |
|--------|--------|-------|-------|
| **Overhead (Disabled)** | 0ms | 0ms | Lazy init = zero overhead when off |
| **Overhead (Enabled)** | N/A | ~100ms first call | One-time client init |
| **Latency (Cloud)** | N/A | 200-500ms | Network latency |
| **Fallback Latency** | N/A | 0ms | Instant fallback to local |

### Cost Management

**Example: 3-specialist council**

Scenario 1: All Local (Default)
- Cost: $0 (free)
- Diversity: Low (1 model family)

Scenario 2: Mixed (ENABLE_OPENAI_COLLECTIVE=true)
- Specialist 1: Q4 (local) = $0
- Specialist 2: gpt-4o-mini = ~$0.0004 per call
- Specialist 3: Q4 (local) = $0
- **Total: ~$0.0004/council**
- Diversity: Medium (2 model families)

Scenario 3: Full Cloud (all enabled)
- Specialist 1: Q4 (local) = $0
- Specialist 2: gpt-4o-mini = ~$0.0004
- Specialist 3: claude-haiku = ~$0.0008
- **Total: ~$0.0012/council**
- Diversity: High (3 model families)

**Budget Control:** Set daily limits in I/O Control Dashboard

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Accidental high costs | HIGH | Default OFF, cost warnings in UI, daily budget limits |
| API key leakage | HIGH | Store in .env (gitignored), never log keys, validate permissions |
| Provider outages | MEDIUM | Automatic fallback to local Q4, log fallback events |
| Latency spikes | MEDIUM | Monitor P99 latency, disable slow providers automatically |
| Dependency bloat | LOW | any-llm is lightweight (~5MB), optional install |

---

## Example Configurations

### Conservative (Default)

```bash
# All providers disabled - pure local operation
ENABLE_OPENAI_COLLECTIVE=false
ENABLE_ANTHROPIC_COLLECTIVE=false
ENABLE_MISTRAL_COLLECTIVE=false
ENABLE_PERPLEXITY_COLLECTIVE=false
ENABLE_GEMINI_COLLECTIVE=false
```

**Use case:** Development, testing, offline work, cost-sensitive
**Cost:** $0/day
**Diversity:** Low (1 model family)

---

### Moderate (Recommended)

```bash
# Enable one cheap provider for diversity
ENABLE_OPENAI_COLLECTIVE=true  # gpt-4o-mini is cheap
ENABLE_ANTHROPIC_COLLECTIVE=false
ENABLE_MISTRAL_COLLECTIVE=false
ENABLE_PERPLEXITY_COLLECTIVE=false
ENABLE_GEMINI_COLLECTIVE=false

OPENAI_API_KEY=sk-proj-...
```

**Use case:** Production, important decisions, council patterns
**Cost:** ~$0.05-0.10/day (100-200 councils)
**Diversity:** Medium (2 model families: Qwen + GPT)

---

### Aggressive (Research)

```bash
# Enable multiple providers for maximum diversity
ENABLE_OPENAI_COLLECTIVE=true
ENABLE_ANTHROPIC_COLLECTIVE=true
ENABLE_MISTRAL_COLLECTIVE=true
ENABLE_PERPLEXITY_COLLECTIVE=false
ENABLE_GEMINI_COLLECTIVE=false

OPENAI_API_KEY=sk-proj-...
ANTHROPIC_API_KEY=sk-ant-...
MISTRAL_API_KEY=...
```

**Use case:** Research, critical decisions, paper writing
**Cost:** ~$0.20-0.50/day (100-200 councils)
**Diversity:** High (4 model families: Qwen, GPT, Claude, Mistral)

---

## Testing Strategy

### Unit Tests

```python
# tests/unit/test_provider_registry.py
import pytest
from brain.llm_client import ProviderRegistry

def test_provider_registry_lazy_init():
    """Test that providers are not initialized until first use."""
    registry = ProviderRegistry()

    # No providers should be initialized yet
    assert len(registry._providers) == 0

    # Attempt to get disabled provider
    provider = registry.get_provider("openai")
    assert provider is None  # Returns None if disabled

    # Still no providers initialized
    assert len(registry._providers) == 0


@pytest.mark.skipif(
    not os.getenv("ENABLE_OPENAI_COLLECTIVE"),
    reason="ENABLE_OPENAI_COLLECTIVE not set"
)
def test_provider_registry_cloud_init():
    """Test that cloud provider initializes when enabled."""
    registry = ProviderRegistry()

    provider = registry.get_provider("openai")

    # Should be initialized now
    assert provider is not None
    assert "openai" in registry._providers
```

### Integration Tests

```python
# tests/integration/test_multi_provider_collective.py
import pytest
from brain.agents.collective.graph_async import n_propose_council, CollectiveState

@pytest.mark.integration
@pytest.mark.asyncio
async def test_council_with_cloud_providers():
    """Test council works with cloud providers enabled."""
    state = CollectiveState(
        task="Design a sustainable water filtration system",
        pattern="council",
        k=3
    )

    result = await n_propose_council(state)

    # Should have 3 proposals
    assert len(result["proposals"]) == 3

    # All proposals should be non-empty
    for prop in result["proposals"]:
        assert len(prop) > 50


@pytest.mark.integration
@pytest.mark.asyncio
async def test_council_fallback_to_local():
    """Test council falls back to local when cloud disabled."""
    # Temporarily disable all cloud providers
    import os
    old_openai = os.environ.get("ENABLE_OPENAI_COLLECTIVE")
    old_anthropic = os.environ.get("ENABLE_ANTHROPIC_COLLECTIVE")

    os.environ["ENABLE_OPENAI_COLLECTIVE"] = "false"
    os.environ["ENABLE_ANTHROPIC_COLLECTIVE"] = "false"

    try:
        state = CollectiveState(task="Test task", pattern="council", k=3)
        result = await n_propose_council(state)

        # Should still work (fallback to Q4)
        assert len(result["proposals"]) == 3
    finally:
        # Restore
        if old_openai:
            os.environ["ENABLE_OPENAI_COLLECTIVE"] = old_openai
        if old_anthropic:
            os.environ["ENABLE_ANTHROPIC_COLLECTIVE"] = old_anthropic
```

---

## Success Criteria

**Phase 1-2 Complete When:**
- ✅ `chat_async()` supports `model` and `provider` parameters
- ✅ Cloud providers load lazily (0ms overhead when disabled)
- ✅ Feature flags appear in I/O Control Dashboard
- ✅ Unit tests pass

**Phase 3-4 Complete When:**
- ✅ Council uses multiple providers when enabled
- ✅ Council falls back to Q4 when providers disabled
- ✅ Debate uses different models for PRO/CON
- ✅ Integration tests pass

**Phase 5 Complete When:**
- ✅ Documentation updated
- ✅ Runbook created
- ✅ Successful production deployment with 1 cloud provider enabled

---

## References

- [mozilla-ai/any-llm](https://github.com/mozilla-ai/any-llm) - Reference multi-provider SDK
- [KITTY Collective Meta-Agent](services/brain/src/brain/agents/collective/) - Current implementation
- [I/O Control Dashboard](services/common/src/common/io_control/) - Feature flag system
- [Connection Management Analysis](docs/connection-management-analysis.md) - Connection pooling strategy

---

## Status: Ready for Implementation

This design is ready for review and implementation. The phased approach allows gradual rollout with minimal risk.

**Next Steps:**
1. Review design with team
2. Implement Phase 1 (adapter layer)
3. Test with one cloud provider (OpenAI recommended)
4. Monitor costs and performance
5. Expand to additional providers

**Estimated Timeline:** 3 weeks
**Risk Level:** Low (default OFF, lazy init, fallback to local)
