# Multi-Provider Chat Interface Design

**Date:** 2025-11-15
**Author:** Claude
**Parent Doc:** `multi-provider-collective-design.md`
**Status:** Design Proposal

---

## Overview

Enable users to select cloud providers directly from the chat interface (CLI, Web UI, API) in addition to I/O Control Dashboard toggles. This provides per-query provider control for flexibility and experimentation.

**Goals:**
- ✅ Allow provider/model selection in chat queries
- ✅ Support CLI, Web UI, and API interfaces
- ✅ Maintain backward compatibility (default: local Q4)
- ✅ Respect I/O Control feature flags (can't use disabled providers)
- ✅ Show clear feedback about which provider was used

---

## User Experience Patterns

### Pattern 1: CLI Commands

**New Commands:**

```bash
# Set provider for subsequent queries
kitty-cli> /provider openai
✓ Provider set to: openai (gpt-4o-mini)
Note: Will fallback to Q4 if ENABLE_OPENAI_COLLECTIVE=false

kitty-cli> /model claude-3-5-haiku-20241022
✓ Model set to: claude-3-5-haiku-20241022 (anthropic)
✓ Provider set to: anthropic

kitty-cli> What is quantum entanglement?
[Using: anthropic/claude-3-5-haiku-20241022]
Quantum entanglement is a phenomenon where...

# Reset to default (local Q4)
kitty-cli> /provider local
✓ Provider set to: local (Q4)

# Show available providers
kitty-cli> /providers
Available providers:
  ✓ local (Q4, F16, CODER, Q4B) - Always available
  ✓ openai (gpt-4o-mini, gpt-4o, o1-mini, o1-preview)
  ✗ anthropic (ENABLE_ANTHROPIC_COLLECTIVE=false)
  ✗ mistral (ENABLE_MISTRAL_COLLECTIVE=false)
  ✓ perplexity (sonar, sonar-pro, sonar-reasoning-pro)
```

**Implementation:**

```python
# services/cli/src/cli/main.py

def handle_provider_command(provider: str) -> None:
    """Set provider for subsequent queries."""
    from brain.llm_client import ProviderRegistry

    registry = ProviderRegistry()

    if provider == "local":
        # Reset to default
        cli_state["provider"] = None
        cli_state["model"] = None
        console.print("✓ Provider set to: local (Q4)", style="green")
        return

    # Validate provider enabled
    if not registry.is_enabled(provider):
        console.print(
            f"✗ Provider '{provider}' is disabled. "
            f"Enable via I/O Control or set ENABLE_{provider.upper()}_COLLECTIVE=true",
            style="red"
        )
        return

    # Set provider state
    cli_state["provider"] = provider
    cli_state["model"] = None  # Use provider default

    # Get default model for provider
    default_models = {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-5-haiku-20241022",
        "mistral": "mistral-small-latest",
        "perplexity": "sonar",
        "gemini": "gemini-1.5-flash",
    }

    default_model = default_models.get(provider, "unknown")
    console.print(f"✓ Provider set to: {provider} ({default_model})", style="green")
    console.print(
        f"Note: Will fallback to Q4 if provider unavailable",
        style="dim"
    )


def handle_model_command(model: str) -> None:
    """Set specific model (auto-detects provider)."""
    # Provider detection based on model name patterns
    provider_patterns = {
        "gpt-": "openai",
        "o1-": "openai",
        "claude-": "anthropic",
        "mistral-": "mistral",
        "sonar": "perplexity",
        "gemini-": "gemini",
    }

    provider = None
    for pattern, prov in provider_patterns.items():
        if model.startswith(pattern):
            provider = prov
            break

    if not provider:
        console.print(f"✗ Unknown model: {model}", style="red")
        return

    # Validate provider enabled
    from brain.llm_client import ProviderRegistry
    registry = ProviderRegistry()

    if not registry.is_enabled(provider):
        console.print(
            f"✗ Provider '{provider}' is disabled for model '{model}'",
            style="red"
        )
        return

    cli_state["provider"] = provider
    cli_state["model"] = model

    console.print(f"✓ Model set to: {model} ({provider})", style="green")


def handle_providers_command() -> None:
    """List available providers."""
    from brain.llm_client import ProviderRegistry

    registry = ProviderRegistry()

    console.print("\nAvailable providers:", style="bold")

    # Local (always available)
    console.print("  ✓ local (Q4, F16, CODER, Q4B) - Always available", style="green")

    # Cloud providers
    providers = ["openai", "anthropic", "mistral", "perplexity", "gemini"]
    models = {
        "openai": "gpt-4o-mini, gpt-4o, o1-mini, o1-preview",
        "anthropic": "claude-3-5-haiku-20241022, claude-3-5-sonnet-20241022",
        "mistral": "mistral-small-latest, mistral-large-latest",
        "perplexity": "sonar, sonar-pro, sonar-reasoning-pro",
        "gemini": "gemini-1.5-flash, gemini-1.5-pro",
    }

    for provider in providers:
        if registry.is_enabled(provider):
            console.print(f"  ✓ {provider} ({models[provider]})", style="green")
        else:
            env_var = f"ENABLE_{provider.upper()}_COLLECTIVE"
            console.print(f"  ✗ {provider} ({env_var}=false)", style="dim")


# Update query handler to respect provider/model
async def send_query(query: str) -> None:
    """Send query with optional provider/model override."""
    # Get provider/model from CLI state
    provider = cli_state.get("provider")
    model = cli_state.get("model")

    # Call brain API with overrides
    response = await api_client.post(
        "/api/query",
        json={
            "query": query,
            "provider": provider,  # New field
            "model": model,        # New field
            # ... existing fields ...
        }
    )

    # Show which provider was used
    used_provider = response.get("metadata", {}).get("provider_used")
    used_model = response.get("metadata", {}).get("model_used")

    if used_provider:
        console.print(
            f"[Using: {used_provider}/{used_model}]",
            style="dim"
        )

    console.print(response["response"])
```

---

### Pattern 2: Inline Syntax (Quick Override)

**Syntax:**

```bash
# Prefix query with @provider: or #model:
kitty-cli> @openai: What is the capital of France?
[Using: openai/gpt-4o-mini]
The capital of France is Paris.

kitty-cli> #claude-3-5-haiku: Explain quantum computing
[Using: anthropic/claude-3-5-haiku-20241022]
Quantum computing leverages quantum mechanics...

# Works in web UI too
Web UI Input: @perplexity: Latest news on AI regulations
```

**Implementation:**

```python
# services/brain/src/brain/routes/query.py

import re

def parse_query_for_provider_override(query: str) -> tuple[str, Optional[str], Optional[str]]:
    """Parse query for inline provider/model syntax.

    Supports:
    - @provider: query text
    - #model: query text

    Returns:
        (cleaned_query, provider, model)
    """
    # Check for @provider: syntax
    provider_match = re.match(r'^@(\w+):\s*(.+)$', query)
    if provider_match:
        provider = provider_match.group(1)
        cleaned_query = provider_match.group(2)
        return cleaned_query, provider, None

    # Check for #model: syntax
    model_match = re.match(r'^#([\w\-\.]+):\s*(.+)$', query)
    if model_match:
        model = model_match.group(1)
        cleaned_query = model_match.group(2)

        # Auto-detect provider from model name
        provider = detect_provider_from_model(model)

        return cleaned_query, provider, model

    # No override
    return query, None, None


def detect_provider_from_model(model: str) -> Optional[str]:
    """Detect provider from model name."""
    patterns = {
        "gpt-": "openai",
        "o1-": "openai",
        "claude-": "anthropic",
        "mistral-": "mistral",
        "sonar": "perplexity",
        "gemini-": "gemini",
    }

    for pattern, provider in patterns.items():
        if model.startswith(pattern):
            return provider

    return None


@router.post("/api/query")
async def query(
    request: QueryRequest,
    db: Session = Depends(get_db)
) -> QueryResponse:
    """Handle conversational query with optional provider override."""

    # Parse inline syntax
    cleaned_query, inline_provider, inline_model = parse_query_for_provider_override(
        request.query
    )

    # Determine final provider/model (priority: inline > explicit > default)
    provider = inline_provider or request.provider or None
    model = inline_model or request.model or None

    # Validate provider enabled
    if provider:
        from brain.llm_client import ProviderRegistry
        registry = ProviderRegistry()

        if not registry.is_enabled(provider):
            logger.warning(
                f"Provider '{provider}' requested but disabled, falling back to Q4"
            )
            provider = None
            model = None

    # Route to brain
    result = await brain_router.route(
        query=cleaned_query,
        provider=provider,
        model=model,
        conversation_id=request.conversation_id,
        user_id=request.user_id,
    )

    # Include metadata about which provider was used
    return QueryResponse(
        response=result["response"],
        metadata={
            "provider_used": result.get("provider_used", "local/Q4"),
            "model_used": result.get("model_used", "kitty-q4"),
            "fallback_occurred": result.get("fallback_occurred", False),
        }
    )
```

---

### Pattern 3: Web UI Dropdown

**UI Components:**

```typescript
// services/ui/src/components/ChatInput.tsx

interface ChatInputProps {
  onSend: (message: string, provider?: string, model?: string) => void;
}

const ChatInput: React.FC<ChatInputProps> = ({ onSend }) => {
  const [message, setMessage] = useState("");
  const [provider, setProvider] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [showProviderMenu, setShowProviderMenu] = useState(false);

  // Fetch available providers from API
  const { data: providers } = useQuery("/api/providers/available");

  const handleSend = () => {
    onSend(message, provider, model);
    setMessage("");
  };

  return (
    <div className="chat-input-container">
      {/* Provider selector (optional dropdown) */}
      {showProviderMenu && (
        <div className="provider-menu">
          <div className="provider-option" onClick={() => {
            setProvider(null);
            setModel(null);
            setShowProviderMenu(false);
          }}>
            <span className="provider-icon">🏠</span>
            Local (Q4)
          </div>

          {providers?.openai?.enabled && (
            <div className="provider-option" onClick={() => {
              setProvider("openai");
              setModel("gpt-4o-mini");
              setShowProviderMenu(false);
            }}>
              <span className="provider-icon">🤖</span>
              OpenAI (GPT-4o-mini)
            </div>
          )}

          {providers?.anthropic?.enabled && (
            <div className="provider-option" onClick={() => {
              setProvider("anthropic");
              setModel("claude-3-5-haiku-20241022");
              setShowProviderMenu(false);
            }}>
              <span className="provider-icon">🧠</span>
              Anthropic (Claude Haiku)
            </div>
          )}

          {/* Add other providers */}
        </div>
      )}

      {/* Input with provider badge */}
      <div className="input-wrapper">
        {/* Provider badge (shows current selection) */}
        <button
          className="provider-badge"
          onClick={() => setShowProviderMenu(!showProviderMenu)}
        >
          {provider === null ? "🏠 Local" : `${getProviderIcon(provider)} ${provider}`}
          <span className="dropdown-arrow">▼</span>
        </button>

        {/* Text input */}
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyPress={(e) => e.key === "Enter" && handleSend()}
          placeholder="Type your message..."
        />

        {/* Send button */}
        <button onClick={handleSend}>Send</button>
      </div>

      {/* Cost estimate (if cloud provider selected) */}
      {provider && (
        <div className="cost-estimate">
          Est. cost: ~$0.0004 per message
        </div>
      )}
    </div>
  );
};

function getProviderIcon(provider: string): string {
  const icons = {
    openai: "🤖",
    anthropic: "🧠",
    mistral: "🌀",
    perplexity: "🔍",
    gemini: "💎",
  };
  return icons[provider] || "❓";
}
```

**API Endpoint:**

```python
# services/brain/src/brain/routes/providers.py

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Dict

router = APIRouter(prefix="/api/providers", tags=["providers"])


class ProviderInfo(BaseModel):
    """Information about a provider."""
    enabled: bool
    name: str
    models: list[str]
    cost_per_1m_tokens: Dict[str, float]
    icon: str


@router.get("/available")
async def get_available_providers() -> Dict[str, ProviderInfo]:
    """Get list of available providers with their status."""
    from brain.llm_client import ProviderRegistry, PROVIDER_COSTS

    registry = ProviderRegistry()

    providers = {
        "local": ProviderInfo(
            enabled=True,
            name="Local (llama.cpp)",
            models=["Q4", "F16", "CODER", "Q4B"],
            cost_per_1m_tokens={"input": 0.0, "output": 0.0},
            icon="🏠",
        ),
        "openai": ProviderInfo(
            enabled=registry.is_enabled("openai"),
            name="OpenAI",
            models=["gpt-4o-mini", "gpt-4o", "o1-mini", "o1-preview"],
            cost_per_1m_tokens=PROVIDER_COSTS["openai"],
            icon="🤖",
        ),
        "anthropic": ProviderInfo(
            enabled=registry.is_enabled("anthropic"),
            name="Anthropic",
            models=["claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022"],
            cost_per_1m_tokens=PROVIDER_COSTS["anthropic"],
            icon="🧠",
        ),
        "mistral": ProviderInfo(
            enabled=registry.is_enabled("mistral"),
            name="Mistral AI",
            models=["mistral-small-latest", "mistral-large-latest"],
            cost_per_1m_tokens=PROVIDER_COSTS["mistral"],
            icon="🌀",
        ),
        "perplexity": ProviderInfo(
            enabled=registry.is_enabled("perplexity"),
            name="Perplexity",
            models=["sonar", "sonar-pro", "sonar-reasoning-pro"],
            cost_per_1m_tokens=PROVIDER_COSTS["perplexity"],
            icon="🔍",
        ),
        "gemini": ProviderInfo(
            enabled=registry.is_enabled("gemini"),
            name="Google Gemini",
            models=["gemini-1.5-flash", "gemini-1.5-pro"],
            cost_per_1m_tokens=PROVIDER_COSTS["gemini"],
            icon="💎",
        ),
    }

    return providers
```

---

### Pattern 4: API Query Parameters

**HTTP API:**

```bash
# Default (local Q4)
POST /api/query
{
  "query": "What is quantum computing?"
}

# With provider override
POST /api/query
{
  "query": "What is quantum computing?",
  "provider": "openai",
  "model": "gpt-4o-mini"
}

# Or via query parameters
POST /api/query?provider=anthropic&model=claude-3-5-haiku-20241022
{
  "query": "What is quantum computing?"
}

# Response includes metadata
{
  "response": "Quantum computing is...",
  "metadata": {
    "provider_used": "anthropic",
    "model_used": "claude-3-5-haiku-20241022",
    "fallback_occurred": false,
    "tokens_used": 245,
    "cost_usd": 0.000061
  }
}
```

**Request Model:**

```python
# services/brain/src/brain/routes/query.py

class QueryRequest(BaseModel):
    """Chat query request with optional provider override."""
    query: str
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
    model_alias: Optional[str] = None  # Existing: Q4/F16/CODER

    # New fields for multi-provider support
    provider: Optional[str] = None
    model: Optional[str] = None

    # Optional parameters
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tools: Optional[list] = None
```

---

## State Management

### CLI State

```python
# services/cli/src/cli/main.py

# Persistent state for CLI session
cli_state = {
    "conversation_id": None,
    "user_id": None,
    "provider": None,  # Current provider selection
    "model": None,     # Current model selection
    "model_alias": "kitty-primary",  # Existing
}

# State persists across queries until explicitly changed
```

### Web UI State

```typescript
// services/ui/src/store/chatStore.ts

interface ChatState {
  messages: Message[];
  conversationId: string | null;
  provider: string | null;  // Current provider selection
  model: string | null;     // Current model selection
  availableProviders: ProviderInfo[];
}

const useChatStore = create<ChatState>((set) => ({
  messages: [],
  conversationId: null,
  provider: null,  // Default: local
  model: null,     // Default: Q4

  setProvider: (provider: string | null, model: string | null) =>
    set({ provider, model }),

  sendMessage: async (content: string, provider?: string, model?: string) => {
    // Use explicit override or store state
    const finalProvider = provider || get().provider;
    const finalModel = model || get().model;

    const response = await api.post("/api/query", {
      query: content,
      provider: finalProvider,
      model: finalModel,
      conversation_id: get().conversationId,
    });

    // Update messages with provider info
    set((state) => ({
      messages: [
        ...state.messages,
        {
          role: "user",
          content,
        },
        {
          role: "assistant",
          content: response.data.response,
          metadata: response.data.metadata,
        },
      ],
    }));
  },
}));
```

---

## User Feedback & Transparency

### Show Which Provider Was Used

**CLI:**

```bash
kitty-cli> @openai: What is the meaning of life?
[Using: openai/gpt-4o-mini | Tokens: 245 | Cost: $0.0001]
The meaning of life is a philosophical question...

kitty-cli> Same question
[Using: local/Q4 | Tokens: 0 | Cost: $0.00]
The meaning of life is a deep philosophical question...
```

**Web UI:**

```typescript
// Message component with provider badge
<div className="message assistant">
  <div className="message-header">
    <span className="provider-badge">
      {message.metadata?.provider_used === "local/Q4" ? (
        <span>🏠 Local</span>
      ) : (
        <span>
          {getProviderIcon(message.metadata?.provider_used)}
          {message.metadata?.provider_used}
        </span>
      )}
    </span>
    <span className="timestamp">{message.timestamp}</span>
    {message.metadata?.cost_usd > 0 && (
      <span className="cost-badge">
        ${message.metadata.cost_usd.toFixed(4)}
      </span>
    )}
  </div>
  <div className="message-content">
    {message.content}
  </div>
</div>
```

---

## Implementation Checklist

### Phase 1: Backend API (Week 1)

- [ ] Update `QueryRequest` model with `provider` and `model` fields
- [ ] Add `parse_query_for_provider_override()` function
- [ ] Update `/api/query` endpoint to accept provider overrides
- [ ] Add `/api/providers/available` endpoint
- [ ] Add metadata to responses (`provider_used`, `cost_usd`, etc.)
- [ ] Test with curl/postman

### Phase 2: CLI Interface (Week 1)

- [ ] Add `/provider <name>` command
- [ ] Add `/model <name>` command
- [ ] Add `/providers` command (list available)
- [ ] Add inline syntax parser (`@provider:` and `#model:`)
- [ ] Add provider badge to query responses
- [ ] Update CLI state management
- [ ] Test all commands

### Phase 3: Web UI (Week 2)

- [ ] Create `ProviderSelector` component
- [ ] Add provider dropdown to chat input
- [ ] Add provider badge to messages
- [ ] Add cost estimate display
- [ ] Integrate with chat store
- [ ] Add keyboard shortcuts (Ctrl+P for provider menu)
- [ ] Test UI interactions

### Phase 4: Testing (Week 2)

- [ ] Unit tests for inline syntax parser
- [ ] Integration tests for provider overrides
- [ ] E2E tests for CLI commands
- [ ] E2E tests for web UI
- [ ] Test fallback behavior
- [ ] Test with all providers enabled/disabled

### Phase 5: Documentation (Week 3)

- [ ] Update CLI help text
- [ ] Create user guide for provider selection
- [ ] Add examples to README
- [ ] Create video demo
- [ ] Document cost estimates

---

## Example Workflows

### Workflow 1: Quick Comparison

**User wants to compare answers from different models:**

```bash
# CLI
kitty-cli> /provider local
kitty-cli> Explain quantum entanglement
[Using: local/Q4] <response>

kitty-cli> /provider openai
kitty-cli> Explain quantum entanglement
[Using: openai/gpt-4o-mini] <response>

kitty-cli> /provider anthropic
kitty-cli> Explain quantum entanglement
[Using: anthropic/claude-3-5-haiku] <response>
```

### Workflow 2: Inline Override

**User wants one-off cloud query without changing default:**

```bash
kitty-cli> @openai: What are the latest AI regulations?
[Using: openai/gpt-4o-mini] <response>

kitty-cli> What is 2+2?
[Using: local/Q4] <response>  # Back to default
```

### Workflow 3: Web UI Session

**User starts with local, switches to cloud for complex query:**

1. User opens chat, default provider is "Local"
2. User asks simple question → Local Q4 responds
3. User clicks provider dropdown, selects "OpenAI"
4. User asks complex research question → GPT-4o responds
5. User clicks provider dropdown, selects "Local" → Back to default

---

## Success Metrics

**Phase 1-2 Complete When:**
- ✅ `/provider` and `/model` commands work in CLI
- ✅ Inline syntax (`@provider:`, `#model:`) works
- ✅ API accepts `provider` and `model` parameters
- ✅ Responses include `provider_used` metadata

**Phase 3-4 Complete When:**
- ✅ Web UI has working provider dropdown
- ✅ Provider badges show on messages
- ✅ Cost estimates display for cloud providers
- ✅ All tests pass

**Phase 5 Complete When:**
- ✅ Documentation complete
- ✅ Video demo created
- ✅ User guide published

---

## Status: Ready for Implementation

This design complements the I/O Control Dashboard toggles with in-chat provider selection, giving users both global (I/O Control) and per-query (chat) control over providers.

**Next Steps:**
1. Implement backend API changes
2. Add CLI commands
3. Build Web UI components
4. Test all workflows
5. Document usage patterns
