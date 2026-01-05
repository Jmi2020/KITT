# Prompt Suggestion & Enhancement Feature Design

## Overview

This document describes the design for an intelligent prompt suggestion and enhancement system that assists users as they type in input fields across the KITT Web UI and Shell interfaces.

## Goals

1. **Real-time Assistance**: Suggest and enhance prompts as users type
2. **Context-Aware**: Different refinement strategies per input field type
3. **Model Flexibility**: Use appropriate models for different contexts
4. **Non-Intrusive**: Suggestions appear on-demand, don't block user input

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Frontend (React)                          │
├─────────────────────────────────────────────────────────────────────┤
│  usePromptSuggestion Hook                                           │
│  ├── Debounced input handling (300ms)                               │
│  ├── Context detection (field type, page)                           │
│  └── Streaming response handling                                    │
│                                                                     │
│  SuggestionPopup Component                                          │
│  ├── Floating UI positioned near input                              │
│  ├── Keyboard navigation (↑/↓/Enter/Esc)                            │
│  └── Displays suggestions with accept/dismiss actions               │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼ POST /api/suggest
┌─────────────────────────────────────────────────────────────────────┐
│                    Backend (brain service)                          │
├─────────────────────────────────────────────────────────────────────┤
│  /api/suggest endpoint                                              │
│  ├── Context-based system prompt selection                          │
│  ├── Model routing (Gemma 3 21B / Qwen Coder)                       │
│  └── Streaming SSE response                                         │
│                                                                     │
│  PromptSuggestionService                                            │
│  ├── Field-specific system prompts                                  │
│  ├── History-aware context building                                 │
│  └── Token-efficient inference                                      │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Model Layer                                 │
├─────────────────────────────────────────────────────────────────────┤
│  Default: Gemma 3 21B (via llama.cpp)                               │
│  ├── General prompt enhancement                                     │
│  ├── CAD/fabrication suggestions                                    │
│  ├── Image generation prompts                                       │
│  └── Research query refinement                                      │
│                                                                     │
│  Coding: Qwen2.5-Coder-32B-Instruct                                 │
│  ├── Path: /Users/Shared/Coding/models/Qwen2.5-Coder-32B-Instruct-GGUF
│  └── Code-specific prompt enhancement                               │
└─────────────────────────────────────────────────────────────────────┘
```

## Input Fields & Contexts

| Page | Component | Field ID | Context Type | Model |
|------|-----------|----------|--------------|-------|
| Shell | Shell.tsx:959 | `shell-input` | `chat` | Gemma 3 21B |
| Coding | Coding/index.tsx:1031 | `coding-input` | `coding` | Qwen Coder |
| Fabrication | GenerateStep.tsx | `cad-prompt` | `cad` | Gemma 3 21B |
| MediaHub | Generate.tsx | `image-prompt` | `image` | Gemma 3 21B |
| ResearchHub | NewResearch.tsx | `research-query` | `research` | Gemma 3 21B |

## System Prompts by Context

### 1. Chat Context (`chat`)
```
You are a prompt enhancement assistant for a general-purpose AI chat interface.
Given the user's partial input, suggest 1-3 ways to make their prompt clearer,
more specific, or more effective. Focus on:
- Clarifying ambiguous terms
- Adding helpful context
- Structuring complex requests

User input: "{input}"

Respond with JSON: {"suggestions": [{"text": "enhanced prompt", "reason": "why this is better"}]}
```

### 2. Coding Context (`coding`)
```
You are a coding assistant prompt enhancer. The user is writing a request for
an AI coding agent that will generate, test, and refine code.

Given their partial input, suggest improvements that will help the coding agent:
- Understand the programming language/framework
- Know the expected inputs/outputs
- Understand edge cases to handle
- Know about testing requirements

User input: "{input}"

Respond with JSON: {"suggestions": [{"text": "enhanced prompt", "reason": "why this helps code generation"}]}
```

### 3. CAD/Fabrication Context (`cad`)
```
You are a 3D model generation prompt enhancer. The user is requesting a 3D model
that will be generated by AI (Meshy.ai, Tripo, or Zoo.dev) and potentially 3D printed.

Suggest improvements that specify:
- Physical dimensions and scale
- Material considerations (overhangs, supports)
- Level of detail (organic vs parametric)
- Functional requirements (mounting holes, tolerances)

User input: "{input}"

Respond with JSON: {"suggestions": [{"text": "enhanced prompt", "reason": "why this improves the 3D model"}]}
```

### 4. Image Generation Context (`image`)
```
You are an image generation prompt enhancer for Stable Diffusion.

Suggest improvements that add:
- Art style (photorealistic, illustration, etc.)
- Lighting and mood
- Composition details
- Quality boosters (detailed, high resolution, etc.)

User input: "{input}"

Respond with JSON: {"suggestions": [{"text": "enhanced prompt", "reason": "why this improves the image"}]}
```

### 5. Research Context (`research`)
```
You are a research query enhancer. The user is initiating an AI-powered
research session that will search multiple sources and synthesize findings.

Suggest improvements that:
- Narrow or broaden scope appropriately
- Specify time ranges or recency requirements
- Clarify the type of sources needed
- Define the expected output format

User input: "{input}"

Respond with JSON: {"suggestions": [{"text": "enhanced query", "reason": "why this improves research results"}]}
```

## API Design

### Endpoint: `POST /api/suggest`

**Request:**
```json
{
  "input": "create a wall mount for my",
  "context": "cad",
  "field_id": "cad-prompt",
  "history": [],
  "max_suggestions": 3
}
```

**Response (SSE Stream):**
```
data: {"type": "start", "request_id": "abc123"}

data: {"type": "suggestion", "index": 0, "text": "Create a wall mount bracket for my router with cable management channels, 2mm wall thickness, and screw mounting holes", "reason": "Adds specific dimensions and functional features"}

data: {"type": "suggestion", "index": 1, "text": "Design a minimalist wall mount for my wireless router, 150mm wide, with ventilation slots and hidden cable routing", "reason": "Specifies size and thermal considerations"}

data: {"type": "complete", "suggestions_count": 2}
```

### Configuration: `POST /api/suggest/config`

**Request:**
```json
{
  "enabled": true,
  "debounce_ms": 300,
  "min_input_length": 10,
  "max_suggestions": 3,
  "contexts": {
    "coding": {"model": "qwen-coder", "enabled": true},
    "cad": {"model": "gemma-3-21b", "enabled": true},
    "chat": {"model": "gemma-3-21b", "enabled": true}
  }
}
```

## Frontend Components

### 1. `usePromptSuggestion` Hook

```typescript
// services/ui/src/hooks/usePromptSuggestion.ts

interface PromptSuggestion {
  text: string;
  reason: string;
}

interface UsePromptSuggestionOptions {
  context: 'chat' | 'coding' | 'cad' | 'image' | 'research';
  fieldId: string;
  enabled?: boolean;
  debounceMs?: number;
  minLength?: number;
  maxSuggestions?: number;
}

interface UsePromptSuggestionResult {
  suggestions: PromptSuggestion[];
  isLoading: boolean;
  error: string | null;
  fetchSuggestions: (input: string) => void;
  clearSuggestions: () => void;
  acceptSuggestion: (index: number) => string;
}

export function usePromptSuggestion(
  options: UsePromptSuggestionOptions
): UsePromptSuggestionResult;
```

### 2. `SuggestionPopup` Component

```typescript
// services/ui/src/components/SuggestionPopup.tsx

interface SuggestionPopupProps {
  suggestions: PromptSuggestion[];
  isLoading: boolean;
  isVisible: boolean;
  selectedIndex: number;
  onSelect: (index: number) => void;
  onDismiss: () => void;
  anchorRef: React.RefObject<HTMLElement>;
  position?: 'above' | 'below';
}

export function SuggestionPopup(props: SuggestionPopupProps): JSX.Element;
```

### 3. Integration Pattern

```typescript
// Example: Coding page integration

function CodingInput() {
  const [inputValue, setInputValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const [selectedSuggestion, setSelectedSuggestion] = useState(0);
  const [showSuggestions, setShowSuggestions] = useState(false);

  const {
    suggestions,
    isLoading,
    fetchSuggestions,
    clearSuggestions,
    acceptSuggestion,
  } = usePromptSuggestion({
    context: 'coding',
    fieldId: 'coding-input',
    debounceMs: 300,
    minLength: 10,
  });

  // Fetch suggestions on input change
  useEffect(() => {
    if (inputValue.length >= 10) {
      fetchSuggestions(inputValue);
      setShowSuggestions(true);
    } else {
      clearSuggestions();
      setShowSuggestions(false);
    }
  }, [inputValue]);

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showSuggestions || suggestions.length === 0) return;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedSuggestion(i => Math.min(i + 1, suggestions.length - 1));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedSuggestion(i => Math.max(i - 1, 0));
        break;
      case 'Tab':
      case 'Enter':
        if (e.ctrlKey || e.metaKey) {
          e.preventDefault();
          setInputValue(acceptSuggestion(selectedSuggestion));
          setShowSuggestions(false);
        }
        break;
      case 'Escape':
        setShowSuggestions(false);
        break;
    }
  };

  return (
    <div className="input-wrapper">
      <input
        ref={inputRef}
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
        onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
      />
      <SuggestionPopup
        suggestions={suggestions}
        isLoading={isLoading}
        isVisible={showSuggestions}
        selectedIndex={selectedSuggestion}
        onSelect={(i) => {
          setInputValue(acceptSuggestion(i));
          setShowSuggestions(false);
        }}
        onDismiss={() => setShowSuggestions(false)}
        anchorRef={inputRef}
      />
    </div>
  );
}
```

## Model Configuration

### Gemma 3 21B (Default)

```yaml
# config/models/gemma-3-21b-suggest.yaml
model:
  name: gemma-3-21b
  path: /models/gemma-3-21b-it-Q4_K_M.gguf
  context_length: 8192
  gpu_layers: -1  # All layers on GPU

inference:
  temperature: 0.7
  top_p: 0.9
  max_tokens: 512
  stop_tokens: ["```", "\n\n\n"]

prompt_template: |
  <start_of_turn>user
  {system_prompt}

  {user_input}<end_of_turn>
  <start_of_turn>model
```

### Qwen2.5-Coder-32B (Coding)

```yaml
# config/models/qwen-coder-suggest.yaml
model:
  name: qwen2.5-coder-32b
  path: /Users/Shared/Coding/models/Qwen2.5-Coder-32B-Instruct-GGUF
  context_length: 32768
  gpu_layers: -1

inference:
  temperature: 0.3  # Lower for more focused suggestions
  top_p: 0.85
  max_tokens: 512
  stop_tokens: ["```", "\n\n\n"]

prompt_template: |
  <|im_start|>system
  {system_prompt}<|im_end|>
  <|im_start|>user
  {user_input}<|im_end|>
  <|im_start|>assistant
```

## Backend Implementation

### Service Structure

```
services/brain/src/brain/
├── suggest/
│   ├── __init__.py
│   ├── service.py          # PromptSuggestionService
│   ├── contexts.py         # Context-specific system prompts
│   ├── models.py           # Model routing logic
│   └── router.py           # FastAPI routes
```

### Key Classes

```python
# services/brain/src/brain/suggest/service.py

class PromptSuggestionService:
    """Handles prompt suggestion generation with context-aware routing."""

    def __init__(self):
        self.contexts = ContextRegistry()
        self.model_router = ModelRouter()

    async def suggest(
        self,
        input_text: str,
        context: str,
        field_id: str,
        history: list[dict] | None = None,
        max_suggestions: int = 3,
    ) -> AsyncIterator[SuggestionEvent]:
        """Generate suggestions as a stream."""

        # Get context-specific system prompt
        system_prompt = self.contexts.get_prompt(context)

        # Route to appropriate model
        model = self.model_router.get_model(context)

        # Build messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f'User input: "{input_text}"'},
        ]

        # Stream response
        async for chunk in model.stream(messages):
            yield self._parse_suggestion(chunk)
```

## UI/UX Considerations

### Trigger Behavior

1. **Activation**: Suggestions appear after 300ms of no typing AND input >= 10 chars
2. **Dismissal**: Escape key, clicking outside, or starting to type again
3. **Acceptance**: Tab/Enter to accept, Ctrl+Enter to accept and submit

### Visual Design

```css
.suggestion-popup {
  position: absolute;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  max-width: 500px;
  max-height: 300px;
  overflow-y: auto;
  z-index: 1000;
}

.suggestion-item {
  padding: 12px 16px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-color);
}

.suggestion-item.selected {
  background: var(--accent-color-dim);
  border-left: 3px solid var(--accent-color);
}

.suggestion-text {
  font-size: 14px;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.suggestion-reason {
  font-size: 12px;
  color: var(--text-secondary);
  font-style: italic;
}

.suggestion-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  color: var(--text-secondary);
}
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate suggestions |
| `Tab` | Accept selected suggestion |
| `Ctrl+Enter` | Accept and submit |
| `Escape` | Dismiss suggestions |
| `Ctrl+Space` | Manually trigger suggestions |

## Feature Flags

```env
# .env configuration
ENABLE_PROMPT_SUGGESTIONS=true
PROMPT_SUGGEST_MODEL=gemma-3-21b
PROMPT_SUGGEST_CODER_MODEL=/Users/Shared/Coding/models/Qwen2.5-Coder-32B-Instruct-GGUF
PROMPT_SUGGEST_DEBOUNCE_MS=300
PROMPT_SUGGEST_MIN_LENGTH=10
PROMPT_SUGGEST_MAX_SUGGESTIONS=3
```

## Implementation Phases

### Phase 1: Backend Foundation
- [ ] Create `/api/suggest` endpoint in brain service
- [ ] Implement context-specific system prompts
- [ ] Add model routing for Gemma 3 / Qwen Coder
- [ ] SSE streaming response

### Phase 2: Frontend Hook & Component
- [ ] Implement `usePromptSuggestion` hook
- [ ] Create `SuggestionPopup` component
- [ ] Add CSS styling matching design system

### Phase 3: Integration
- [ ] Integrate with Shell.tsx
- [ ] Integrate with Coding/index.tsx
- [ ] Integrate with FabricationConsole
- [ ] Integrate with MediaHub Generate
- [ ] Integrate with ResearchHub

### Phase 4: Polish
- [ ] Add feature flag toggle in Settings
- [ ] Add keyboard shortcut hints
- [ ] Performance optimization (caching, prefetch)
- [ ] Analytics/telemetry

## Testing Strategy

1. **Unit Tests**: Context prompt generation, model routing logic
2. **Integration Tests**: API endpoint with mock LLM responses
3. **E2E Tests**: Full flow from input to suggestion acceptance
4. **Performance Tests**: Latency under load, streaming reliability

## Security Considerations

1. **Input Sanitization**: Prevent prompt injection attacks
2. **Rate Limiting**: Max 10 requests/minute per session
3. **Content Filtering**: Apply safety filters to suggestions
4. **Audit Logging**: Log suggestion requests for debugging

## Metrics & Monitoring

- Suggestion request latency (p50, p95, p99)
- Suggestion acceptance rate per context
- Model inference time
- Error rates by context type
