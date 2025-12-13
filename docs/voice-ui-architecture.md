# KITT Voice UI Architecture Report

A comprehensive technical reference for the voice interface system, covering both frontend components and backend services.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Frontend Components](#frontend-components)
4. [Backend Services](#backend-services)
5. [WebSocket Protocol](#websocket-protocol)
6. [Data Flow](#data-flow)
7. [Design System](#design-system)
8. [Configuration](#configuration)
9. [Dependencies](#dependencies)
10. [Opportunities for Enhancement](#opportunities-for-enhancement)

---

## Overview

The KITT Voice UI provides a real-time, bidirectional voice interface with:

- **Push-to-talk** and **wake word** activation modes
- **Hybrid STT**: Local Whisper.cpp with OpenAI fallback
- **Hybrid TTS**: Kokoro ONNX (Apple Silicon optimized) with Piper/OpenAI fallback
- **Real-time streaming** via WebSocket
- **Tool execution visualization** for transparency
- **Mode-based workflows** (Basic, Maker, Research, Home, Creative)

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (React)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      VoiceAssistant.tsx (620 lines)                  │   │
│  │  Main container orchestrating all voice UI components                │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                           │
│    ┌────────────────────────────┼────────────────────────────────┐         │
│    │                            │                                │         │
│    ▼                            ▼                                ▼         │
│  ┌──────────────┐   ┌───────────────────────┐   ┌──────────────────────┐  │
│  │ AudioVisual- │   │    StatusBadge.tsx    │   │  SettingsDrawer.tsx  │  │
│  │ izer.tsx     │   │    (188 lines)        │   │  (464 lines)         │  │
│  │ (327 lines)  │   │                       │   │                      │  │
│  │              │   │  • Connection state   │   │  • Mode selection    │  │
│  │  • FFT rings │   │  • Mode indicator     │   │  • Tool toggles      │  │
│  │  • Particles │   │  • Tier indicator     │   │  • Glassmorphism UI  │  │
│  │  • Scan line │   └───────────────────────┘   └──────────────────────┘  │
│  └──────────────┘                                                          │
│                                                                             │
│    ┌───────────────────────────────────────────────────────────────────┐   │
│    │                     ConversationPanel.tsx                          │   │
│    │  Message history with user/assistant bubbles                       │   │
│    └───────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│    ┌───────────────────────────────────────────────────────────────────┐   │
│    │                   ToolExecutionCard.tsx (291 lines)                │   │
│    │  Real-time tool execution status with progress indicators          │   │
│    └───────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│    ┌───────────────────────────────────────────────────────────────────┐   │
│    │                       HUDFrame.tsx (238 lines)                     │   │
│    │  Sci-fi frame wrapper with corner brackets and glow effects        │   │
│    └───────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│    ┌───────────────────────────────────────────────────────────────────┐   │
│    │                    useVoiceStream.ts (619 lines)                   │   │
│    │  WebSocket hook managing real-time voice communication             │   │
│    └───────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ WebSocket /api/voice/stream
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           BACKEND (Python/FastAPI)                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         app.py (FastAPI)                             │   │
│  │  Endpoints: /healthz, /api/voice/status, /api/voice/stream          │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                 websocket.py (557 lines)                             │   │
│  │  VoiceWebSocketHandler - Real-time bidirectional audio/text         │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                           │
│    ┌────────────────────────────┼────────────────────────────────┐         │
│    │                            │                                │         │
│    ▼                            ▼                                ▼         │
│  ┌──────────────┐   ┌───────────────────────┐   ┌──────────────────────┐  │
│  │   stt.py     │   │       tts.py          │   │   wake_word.py       │  │
│  │  (418 lines) │   │      (733 lines)      │   │    (371 lines)       │  │
│  │              │   │                       │   │                      │  │
│  │  • HybridSTT │   │  • StreamingTTS       │   │  • WakeWordDetector  │  │
│  │  • Whisper   │   │  • KokoroTTSClient    │   │  • WakeWordManager   │  │
│  │  • OpenAI    │   │  • PiperTTSClient     │   │  • Porcupine engine  │  │
│  └──────────────┘   │  • OpenAITTSClient    │   └──────────────────────┘  │
│                     └───────────────────────┘                              │
│                                 │                                           │
│    ┌────────────────────────────┼────────────────────────────────┐         │
│    │                            │                                │         │
│    ▼                            ▼                                ▼         │
│  ┌──────────────┐   ┌───────────────────────┐   ┌──────────────────────┐  │
│  │kokoro_manager│   │    kokoro_tts.py      │   │     router.py        │  │
│  │   .py        │   │     (308 lines)       │   │    (239 lines)       │  │
│  │  (244 lines) │   │                       │   │                      │  │
│  │              │   │  • KokoroTTS          │   │  • VoiceRouter       │  │
│  │  • Singleton │   │  • Adaptive chunking  │   │  • Intent handling   │  │
│  │  • Apple M3  │   │  • TTSChunk streaming │   │  • Brain integration │  │
│  └──────────────┘   └───────────────────────┘   └──────────────────────┘  │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      parser.py (68 lines)                            │   │
│  │  VoiceParser - Intent classification (device/routing/note)           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                   dependencies.py (191 lines)                        │   │
│  │  Lazy initialization of STT, TTS, WakeWord, WebSocket handler        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Frontend Components

### 1. VoiceAssistant.tsx (620 lines)

**Location**: `services/ui/src/components/VoiceAssistant/VoiceAssistant.tsx`

**Purpose**: Main container component orchestrating all voice UI elements.

**Hooks Used**:
- `useVoiceStream` - WebSocket communication
- `useAudioCapture` - Microphone input
- `useAudioAnalyzer` - FFT analysis for visualizer
- `useConversations` - Conversation state management

**Key Features**:
- Push-to-talk with spacebar
- Text input fallback
- Local/Cloud toggle
- Wake word status indicator
- Mode-based tool filtering

**Layout Structure**:
```
┌─────────────────────────────────────────────────────────────┐
│  [Conversation ▼]              [History] [Settings]         │  Header
├─────────────────────────────────────────────────────────────┤
│                                                             │
│              ┌─────────────────────┐                        │
│              │   AudioVisualizer   │                        │
│              │    (400x400 canvas) │                        │
│              └─────────────────────┘                        │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ StatusBadge │ Mode: Basic │ Tier: LOCAL            │   │  StatusBar
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              ConversationPanel                      │   │
│  │              (scrollable messages)                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Tool: lights ████████░░ Running...                  │   │  ToolExecutionList
│  │ Tool: search ✓ Completed (1.2s)                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  [Text input.................................] [PTT]        │  Control Bar
│  [Local ○ Cloud] [Wake Word: ON]                            │
└─────────────────────────────────────────────────────────────┘
```

---

### 2. AudioVisualizer.tsx (327 lines)

**Location**: `services/ui/src/components/VoiceAssistant/AudioVisualizer.tsx`

**Purpose**: Jarvis-style circular FFT visualization with animated effects.

**Visual Elements**:
| Element | Description |
|---------|-------------|
| 3 Rings | Concentric circles with independent rotation speeds |
| 64 FFT Bars | Frequency visualization arranged radially |
| Scan Line | Rotating line (4s period) |
| 12 Particles | Floating ambient particles |
| Center Text | Status indicator text |

**States**:
| State | Visual Behavior |
|-------|-----------------|
| `idle` | Slow rotation, minimal activity |
| `listening` | Active FFT response, faster rotation |
| `responding` | Pulse effect, color intensity changes |
| `error` | Red color scheme |

**Color Configuration**:
```typescript
const MODE_COLORS = {
  cyan:   { primary: '#06b6d4', secondary: '#0891b2', glow: 'rgba(6,182,212,0.3)' },
  orange: { primary: '#f97316', secondary: '#ea580c', glow: 'rgba(249,115,22,0.3)' },
  purple: { primary: '#a855f7', secondary: '#9333ea', glow: 'rgba(168,85,247,0.3)' },
  green:  { primary: '#22c55e', secondary: '#16a34a', glow: 'rgba(34,197,94,0.3)' },
  pink:   { primary: '#ec4899', secondary: '#db2777', glow: 'rgba(236,72,153,0.3)' },
  red:    { primary: '#ef4444', secondary: '#dc2626', glow: 'rgba(239,68,68,0.3)' }
};
```

**Canvas**: 400x400 pixels

---

### 3. HUDFrame.tsx (238 lines)

**Location**: `services/ui/src/components/VoiceAssistant/HUDFrame.tsx`

**Purpose**: Sci-fi themed container frame with corner brackets and glow effects.

**Exported Components**:
- `HUDFrame` - Main frame wrapper
- `HUDIndicator` - Small status dots
- `HUDLabel` - Section labels
- `HUDDivider` - Horizontal dividers

**Props Interface**:
```typescript
interface HUDFrameProps {
  children: ReactNode;
  color?: 'cyan' | 'orange' | 'purple' | 'green' | 'pink' | 'red' | 'gray';
  glow?: 'none' | 'subtle' | 'medium' | 'intense';
  state?: 'idle' | 'active' | 'pulse' | 'alert';
  className?: string;
}
```

**Styling Techniques**:
- Corner brackets using CSS `clip-path`
- Animated glow using `box-shadow`
- Gradient borders via `background: linear-gradient`

---

### 4. StatusBadge.tsx (188 lines)

**Location**: `services/ui/src/components/VoiceAssistant/StatusBadge.tsx`

**Purpose**: Connection and processing state indicators.

**Status Configurations**:
```typescript
const STATUS_CONFIG = {
  disconnected: { label: 'Disconnected', icon: WifiOff,    color: 'text-gray-400',   pulse: false },
  connecting:   { label: 'Connecting',   icon: Loader2,   color: 'text-yellow-400', pulse: true  },
  connected:    { label: 'Connected',    icon: Wifi,      color: 'text-green-400',  pulse: false },
  listening:    { label: 'Listening',    icon: Mic,       color: 'text-cyan-400',   pulse: true  },
  responding:   { label: 'Responding',   icon: Volume2,   color: 'text-purple-400', pulse: true  },
  error:        { label: 'Error',        icon: AlertCircle, color: 'text-red-400', pulse: false }
};
```

**StatusBar Layout**:
- Left: StatusBadge (connection state)
- Center: Mode indicator badge
- Right: Tier indicator (LOCAL/CLOUD)

---

### 5. SettingsDrawer.tsx (464 lines)

**Location**: `services/ui/src/components/VoiceAssistant/SettingsDrawer.tsx`

**Purpose**: Voice mode selection panel with tool configuration.

**Implementation Details**:
- Uses React Portal for overlay positioning
- Slide-in animation from right
- Glassmorphism backdrop (`backdrop-blur-xl`, `bg-black/40`)

**ModeCard Structure**:
```
┌─────────────────────────────────────┐
│ [Icon]  Mode Name    [PAID] [ACTIVE]│
│                                     │
│ Description text here...            │
│                                     │
│ Tools: [tool1] [tool2] [tool3] ...  │
└─────────────────────────────────────┘
```

---

### 6. ToolExecutionCard.tsx (291 lines)

**Location**: `services/ui/src/components/VoiceAssistant/ToolExecutionCard.tsx`

**Purpose**: Display real-time tool execution status.

**Tool Status Types**:
| Status | Icon | Color | Features |
|--------|------|-------|----------|
| `pending` | Clock | Gray | Waiting indicator |
| `running` | Spinner | Blue | Progress bar animation |
| `completed` | Checkmark | Green | Duration display |
| `error` | X | Red | Error message |

**Icon Mapping**:
```typescript
const TOOL_ICONS: Record<string, LucideIcon> = {
  lights: Lightbulb,
  thermostat: Thermometer,
  printer: Printer,
  '3d_model': Box,
  search: Search,
  browser: Globe,
  memory: Brain,
  // ... 15+ tool types
};
```

---

### 7. voiceModes.ts (206 lines)

**Location**: `services/ui/src/types/voiceModes.ts`

**Purpose**: Mode definitions and tool configurations.

**VoiceMode Interface**:
```typescript
interface VoiceMode {
  id: string;
  name: string;
  icon: LucideIcon;
  description: string;
  allowPaid: boolean;
  preferLocal: boolean;
  enabledTools: string[];
  color: string;
  bgClass: string;
  borderClass: string;
  glowClass: string;
}
```

**System Modes**:
| Mode | Color | Tools | Description |
|------|-------|-------|-------------|
| Basic | Cyan | General | Default conversational mode |
| Maker | Orange | CAD, Fabrication | 3D modeling and printing |
| Research | Purple | Web Search, Deep Research | Information gathering |
| Home | Green | Home Assistant | Smart home control |
| Creative | Pink | Image Generation | AI art creation |

**Available Tools by Category**:
| Category | Tools |
|----------|-------|
| CAD | zoo_cad, tripo_3d |
| Research | web_search, deep_research |
| Home | home_assistant |
| Vision | vision_analyze |
| Image Gen | generate_image |
| Memory | semantic_memory |
| Fabrication | printer_control, slicer |
| Discovery | network_scan |
| Reasoning | deep_reasoning |

---

### 8. useVoiceStream.ts (619 lines)

**Location**: `services/ui/src/hooks/useVoiceStream.ts`

**Purpose**: WebSocket hook managing real-time voice communication.

**State Management**:
```typescript
{
  status: 'disconnected' | 'connecting' | 'connected' | 'listening' | 'responding' | 'error',
  transcript: string,
  response: string,
  tier: 'local' | 'mcp' | 'frontier' | null,
  capabilities: { stt: boolean, tts: boolean, streaming: boolean, wake_word: boolean },
  toolExecutions: ToolExecution[],
  mode: string,
  wakeWordEnabled: boolean,
  ttsProvider: string
}
```

**Reconnection Strategy**:
- Automatic reconnection on disconnect
- Exponential backoff (1s, 2s, 4s, 8s, max 30s)
- Max reconnection attempts: 10

---

## Backend Services

### 1. app.py (60 lines)

**Location**: `services/voice/src/voice/app.py`

**Endpoints**:
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/healthz` | GET | Health check |
| `/api/voice/status` | GET | STT/TTS provider status |
| `/api/voice/transcript` | POST | Legacy non-streaming endpoint |
| `/api/voice/stream` | WebSocket | Real-time voice streaming |

---

### 2. websocket.py (557 lines)

**Location**: `services/voice/src/voice/websocket.py`

**Purpose**: WebSocket handler for bidirectional voice streaming.

**VoiceSession Dataclass**:
```python
@dataclass
class VoiceSession:
    session_id: str
    conversation_id: str = "default"
    user_id: str = "anonymous"
    is_listening: bool = False
    is_responding: bool = False
    audio_buffer: bytearray
    cancelled: bool = False

    # Configuration
    voice: str = "alloy"
    language: str = "en"
    sample_rate: int = 16000
    channels: int = 1
    prefer_local: bool = True

    # Mode settings
    mode: str = "basic"
    allow_paid: bool = False
    enabled_tools: list

    # Wake word
    wake_word_enabled: bool = False
    activation_mode: str = "ptt"  # ptt or always_listening
```

**Message Types**:
```python
class MessageType(str, Enum):
    # Client → Server
    AUDIO_CHUNK = "audio.chunk"
    AUDIO_END = "audio.end"
    CONFIG = "config"
    CANCEL = "cancel"
    WAKE_WORD_TOGGLE = "wake_word.toggle"

    # Server → Client
    TRANSCRIPT = "transcript"
    RESPONSE_START = "response.start"
    RESPONSE_TEXT = "response.text"
    RESPONSE_AUDIO = "response.audio"
    RESPONSE_END = "response.end"
    FUNCTION_CALL = "function.call"
    FUNCTION_RESULT = "function.result"
    ERROR = "error"
    STATUS = "status"
    WAKE_WORD_DETECTED = "wake_word.detected"
    WAKE_WORD_STATUS = "wake_word.status"
```

---

### 3. stt.py (418 lines)

**Location**: `services/voice/src/voice/stt.py`

**Purpose**: Hybrid Speech-to-Text with local Whisper and OpenAI fallback.

**Classes**:

**STTProvider (Abstract Base)**:
```python
class STTProvider(ABC):
    async def transcribe(self, audio: bytes, language: str, sample_rate: int) -> str
    def is_available(self) -> bool
```

**WhisperCppClient**:
- Uses whisper-cpp-python bindings
- Supports `base.en`, `small.en`, `medium.en` models
- Lazy model loading
- WAV file generation for transcription

**OpenAIWhisperClient**:
- OpenAI Whisper API (`whisper-1` model)
- Async client with lazy initialization

**HybridSTT**:
- Tries local Whisper first
- Falls back to OpenAI after 3 consecutive failures
- Provider health tracking
- Status reporting

---

### 4. tts.py (733 lines)

**Location**: `services/voice/src/voice/tts.py`

**Purpose**: Streaming TTS with Kokoro/Piper local and OpenAI cloud fallback.

**Provider Priority** (configurable via `LOCAL_TTS_PROVIDER`):
1. `kokoro` - Kokoro ONNX (Apple Silicon optimized) → Piper → OpenAI
2. `piper` - Piper → Kokoro → OpenAI
3. `openai` - OpenAI only

**Classes**:

**TTSProvider (Abstract Base)**:
```python
class TTSProvider(ABC):
    async def synthesize(self, text: str, voice: str) -> bytes
    async def synthesize_stream(self, text: str, voice: str) -> AsyncIterator[bytes]
    def is_available(self) -> bool
    def get_voices(self) -> list[str]
```

**KokoroTTSClient**:
- Apple Silicon optimized via CoreML
- Voice mapping from OpenAI names to Kokoro voices
- Lazy initialization through KokoroManager

**PiperTTSClient**:
- CPU-based local TTS
- Sentence-level pseudo-streaming
- Model auto-discovery

**OpenAITTSClient**:
- OpenAI TTS API (`tts-1` model)
- True streaming via chunked response
- 6 voices: alloy, echo, fable, onyx, nova, shimmer

**StreamingTTS**:
- Automatic provider fallback
- Markdown stripping for clean speech
- Text stream synthesis (sentence buffering)
- Provider health tracking

---

### 5. kokoro_manager.py (244 lines)

**Location**: `services/voice/src/voice/kokoro_manager.py`

**Purpose**: Singleton manager for Kokoro TTS with Apple Silicon optimizations.

**Features**:
- Lazy ONNX runtime loading
- Apple Silicon detection and CoreML enablement
- Model path resolution from environment
- Voice preloading for warm starts

**Environment Variables**:
```bash
KOKORO_MODEL_PATH=~/.local/share/kitty/models/kokoro-v1.0.onnx
KOKORO_VOICES_PATH=~/.local/share/kitty/models/voices-v1.0.bin
KOKORO_DEFAULT_VOICE=bf_emma
```

**ONNX Runtime Selection**:
```python
# Apple Silicon: Try onnxruntime-silicon first, fall back to standard
# Other platforms: Use standard onnxruntime
```

---

### 6. kokoro_tts.py (308 lines)

**Location**: `services/voice/src/voice/kokoro_tts.py`

**Purpose**: Kokoro TTS with adaptive chunking for smooth playback.

**Adaptive Timing Thresholds**:
```python
ADAPTIVE_THRESHOLDS = [
    {"length": 100,  "max_chars": 150, "initial_delay": 0.05, "chunk_delay": 0.02},
    {"length": 300,  "max_chars": 180, "initial_delay": 0.08, "chunk_delay": 0.05},
    {"length": 800,  "max_chars": 200, "initial_delay": 0.12, "chunk_delay": 0.08},
    {"length": inf,  "max_chars": 220, "initial_delay": 0.15, "chunk_delay": 0.10},
]
```

**TTSChunk Dataclass**:
```python
@dataclass
class TTSChunk:
    samples: np.ndarray
    sample_rate: int
    chunk_index: int
    total_chunks: int
    text: str
```

**Chunking Strategy**:
1. Sentence-based splitting first
2. Punctuation-based splitting for oversized chunks
3. Background thread generation for remaining chunks
4. Queue-based streaming delivery

---

### 7. wake_word.py (371 lines)

**Location**: `services/voice/src/voice/wake_word.py`

**Purpose**: Wake word detection using Picovoice Porcupine.

**Classes**:

**WakeWordDetector**:
- Porcupine engine initialization
- PyAudio stream management
- Threaded audio processing
- Queue-based detection callbacks
- Resource cleanup with registry

**WakeWordManager**:
- Lifecycle management
- Configuration-based enable/disable
- Toggle functionality

**Environment Variables**:
```bash
PORCUPINE_ACCESS_KEY=your_key_here
WAKE_WORD_ENABLED=true
WAKE_WORD_MODEL_PATH=~/.local/share/kitty/models/Hey-Kitty_en_mac_v4_0_0.ppn
WAKE_WORD_SENSITIVITY=0.5
```

---

### 8. router.py (239 lines)

**Location**: `services/voice/src/voice/router.py`

**Purpose**: Voice routing integrating parser, brain orchestrator, and MQTT.

**VoiceRouter Methods**:
```python
async def handle_transcript(conversation_id, user_id, transcript) -> Dict
async def handle_transcript_stream(conversation_id, user_id, transcript, allow_paid, mode) -> AsyncIterator[Dict]
```

**Streaming Chunk Types**:
| Type | Fields | Description |
|------|--------|-------------|
| `device` | device, intent | Device command sent |
| `text` | delta | Text response chunk |
| `tool_call` | id, name, args, step | Tool invocation started |
| `tool_result` | id, name, result, status, step | Tool execution result |
| `done` | tier, tools_used | Stream complete |
| `error` | message | Error occurred |

---

### 9. parser.py (68 lines)

**Location**: `services/voice/src/voice/parser.py`

**Purpose**: Intent classification for voice commands.

**Command Types**:
| Type | Trigger Keywords | Example |
|------|-----------------|---------|
| `note` | note, remember, log | "Remember to check printer" |
| `device` | unlock, turn on/off, lights | "Turn on welding lights" |
| `routing` | (default) | Any other query |

**Output Format**:
```python
# Device command
{"type": "device", "intent": "light.turn_on", "payload": {"deviceId": "shop-lights"}}

# Routing request
{"type": "routing", "prompt": "What's the weather?"}

# Note
{"type": "note", "summary": "Check printer tomorrow"}
```

---

### 10. dependencies.py (191 lines)

**Location**: `services/voice/src/voice/dependencies.py`

**Purpose**: Lazy initialization of voice service components.

**Dependency Graph**:
```
get_websocket_handler()
├── get_router_optional()
│   ├── get_parser()
│   ├── MQTTClient
│   ├── get_orchestrator() (from brain)
│   └── SemanticCache
├── get_stt()
│   └── HybridSTT
├── get_tts()
│   └── StreamingTTS
└── get_wake_word_manager()
    └── WakeWordManager
```

---

## WebSocket Protocol

### Connection Flow

```
Client                                Server
  │                                     │
  │──────── Connect /api/voice/stream ──────►
  │                                     │
  │◄─────────── STATUS (connected) ─────────│
  │          {capabilities, tts_provider}   │
  │                                     │
  │──────────── CONFIG ─────────────────►
  │   {conversation_id, mode, voice}    │
  │                                     │
  │◄─────────── STATUS (configured) ────────│
  │                                     │
```

### Audio Streaming Flow

```
Client                                Server
  │                                     │
  │──────── AUDIO_CHUNK (base64) ───────►
  │──────── AUDIO_CHUNK (base64) ───────►
  │──────── AUDIO_END ──────────────────►
  │                                     │
  │◄─────────── TRANSCRIPT ─────────────────│
  │          {text, final: true}        │
  │                                     │
  │◄─────────── RESPONSE_START ─────────────│
  │                                     │
  │◄─────────── FUNCTION_CALL ──────────────│ (if tools used)
  │          {name, args}               │
  │◄─────────── FUNCTION_RESULT ────────────│
  │          {result, status}           │
  │                                     │
  │◄─────────── RESPONSE_TEXT ──────────────│
  │          {delta, done: false}       │
  │◄─────────── RESPONSE_TEXT ──────────────│
  │          {delta, done: true, tier}  │
  │                                     │
  │◄─────────── RESPONSE_AUDIO ─────────────│ (TTS)
  │          {audio: base64, format}    │
  │◄─────────── RESPONSE_AUDIO ─────────────│
  │                                     │
  │◄─────────── RESPONSE_END ───────────────│
  │                                     │
```

### Wake Word Flow

```
Client                                Server
  │                                     │
  │──────── WAKE_WORD_TOGGLE ───────────►
  │        {enable: true}               │
  │                                     │
  │◄─────────── WAKE_WORD_STATUS ───────────│
  │          {enabled: true}            │
  │                                     │
  │         ... user says "Hey Kitty" ...   │
  │                                     │
  │◄─────────── WAKE_WORD_DETECTED ─────────│
  │          {session_id}               │
  │                                     │
  │ (Client starts listening for audio) │
  │                                     │
```

---

## Data Flow

```
┌─────────────────┐     Audio      ┌─────────────────┐
│                 │ ──────────────► │                 │
│   Microphone    │                │   STT (Whisper) │
│                 │                │                 │
└─────────────────┘                └────────┬────────┘
                                            │
                                      Transcript
                                            │
                                            ▼
┌─────────────────┐                ┌─────────────────┐
│                 │                │                 │
│  Voice Parser   │ ◄───────────── │   WebSocket     │
│                 │                │   Handler       │
└────────┬────────┘                └────────┬────────┘
         │                                  │
    Intent Type                        Response
         │                                  │
         ▼                                  ▼
┌─────────────────┐                ┌─────────────────┐
│                 │   Routing      │                 │
│  Voice Router   │ ──────────────► │  Brain Service  │
│                 │                │  (Orchestrator) │
└────────┬────────┘                └─────────────────┘
         │
    Device Command
         │
         ▼
┌─────────────────┐                ┌─────────────────┐
│                 │   MQTT         │                 │
│  MQTT Broker    │ ──────────────► │  Home Assistant │
│                 │                │  / Devices      │
└─────────────────┘                └─────────────────┘

                                   ┌─────────────────┐
                         Audio     │                 │
                       ◄────────── │  TTS (Kokoro)   │
                                   │                 │
                                   └─────────────────┘
```

---

## Design System

### Color Palette

| Mode | Primary | Hex | CSS Classes |
|------|---------|-----|-------------|
| Basic | Cyan | `#06b6d4` | `bg-cyan-500/10`, `border-cyan-500/30`, `shadow-cyan-500/20` |
| Maker | Orange | `#f97316` | `bg-orange-500/10`, `border-orange-500/30`, `shadow-orange-500/20` |
| Research | Purple | `#a855f7` | `bg-purple-500/10`, `border-purple-500/30`, `shadow-purple-500/20` |
| Home | Green | `#22c55e` | `bg-green-500/10`, `border-green-500/30`, `shadow-green-500/20` |
| Creative | Pink | `#ec4899` | `bg-pink-500/10`, `border-pink-500/30`, `shadow-pink-500/20` |
| Error | Red | `#ef4444` | `bg-red-500/10`, `border-red-500/30`, `shadow-red-500/20` |

### Visual Effects

**Glassmorphism**:
```css
backdrop-blur-xl
bg-black/40 to bg-black/80
border with semi-transparent colors
```

**HUD Frame Effects**:
- Corner brackets using CSS `clip-path`
- Glow levels: none, subtle, medium, intense
- States: idle, active, pulse, alert
- Animated gradient borders

**AudioVisualizer Effects**:
- 3 concentric rings with rotation
- 64 FFT frequency bars
- Scanning line (4s rotation period)
- 12 floating particles
- Mode-specific color schemes

---

## Configuration

### Environment Variables

**Voice Service**:
```bash
# STT Configuration
WHISPER_MODEL=base.en
WHISPER_MODEL_PATH=
VOICE_PREFER_LOCAL=true

# TTS Configuration
LOCAL_TTS_PROVIDER=kokoro  # kokoro | piper | openai
OPENAI_TTS_MODEL=tts-1
VOICE_DEFAULT_VOICE=alloy

# Kokoro TTS (Apple Silicon Optimized)
KOKORO_ENABLED=true
KOKORO_MODEL_PATH=~/.local/share/kitty/models/kokoro-v1.0.onnx
KOKORO_VOICES_PATH=~/.local/share/kitty/models/voices-v1.0.bin
KOKORO_DEFAULT_VOICE=bf_emma
KOKORO_SAMPLE_RATE=24000

# Piper TTS (Fallback)
PIPER_MODEL_DIR=/path/to/piper/models

# Wake Word Detection
PORCUPINE_ACCESS_KEY=your_key_here
WAKE_WORD_ENABLED=true
WAKE_WORD_MODEL_PATH=~/.local/share/kitty/models/Hey-Kitty_en_mac_v4_0_0.ppn
WAKE_WORD_SENSITIVITY=0.5
```

### Model Files

**Location**: `~/.local/share/kitty/models/`

```
~/.local/share/kitty/models/
├── kokoro-v1.0.onnx              # Kokoro ONNX model (~82MB)
├── voices-v1.0.bin               # Voice embeddings
├── voices/
│   ├── am_michael.bin            # Male voice (American)
│   ├── bf_emma.bin               # Female voice (British) - DEFAULT
│   ├── af_bella.bin              # Female voice (American)
│   └── ... (52 voices total)
└── Hey-Kitty_en_mac_v4_0_0.ppn   # Porcupine wake word model
```

---

## Dependencies

### Frontend (package.json)
```json
{
  "react": "^18.x",
  "lucide-react": "^0.x",
  "tailwindcss": "^3.x"
}
```

### Backend (pyproject.toml)
```toml
[project]
dependencies = [
  "fastapi>=0.111",
  "httpx>=0.27",
  "numpy>=1.26",
  "pydantic>=2.7",
  "sounddevice>=0.5",
  "uvicorn[standard]>=0.30",
  "websockets>=12.0",
  "openai>=1.30",
]

[project.optional-dependencies]
local = [
  "whispercpp>=0.0.17",      # Local Whisper STT
  "kokoro-onnx>=0.4.0",      # Local TTS
  "pvporcupine>=3.0.0",      # Wake word
  "pyaudio>=0.2.14",         # Audio capture
]
apple-silicon = [
  "onnxruntime-silicon>=1.19.0",  # Apple Silicon optimization
]
```

---

## Opportunities for Enhancement

### Frontend Improvements

1. **AudioVisualizer**
   - Add waveform visualization option (alternative to rings)
   - 3D depth effects with WebGL/Three.js
   - Voice activity detection pulse animation

2. **Layout Options**
   - Compact mode for smaller screens
   - Full-screen immersive mode
   - Split view for conversation + visualization

3. **Conversation Panel**
   - Message grouping by session
   - Rich media previews (images, 3D models)
   - Typing indicators with animation
   - Markdown rendering improvements

4. **Tool Execution**
   - Timeline view for multiple parallel tools
   - Dependency graph visualization
   - Estimated time remaining
   - Tool result previews

5. **Mode Selection**
   - Quick-switch floating button
   - Mode-specific visualizer themes
   - Custom mode creation UI
   - Tool favorites/shortcuts

6. **Accessibility**
   - High contrast mode
   - Reduced motion option
   - Screen reader improvements
   - Keyboard navigation

### Backend Improvements

1. **STT**
   - Streaming transcription (partial results)
   - Speaker diarization
   - Multi-language detection

2. **TTS**
   - Voice cloning support
   - Emotion/tone control
   - SSML support for rich speech

3. **Wake Word**
   - Multiple wake word support
   - Confidence threshold display
   - Custom wake word training guide

4. **General**
   - Response caching for common queries
   - Conversation context management
   - Offline mode improvements

---

## File Reference

| File | Lines | Purpose |
|------|-------|---------|
| **Frontend** | | |
| VoiceAssistant.tsx | 620 | Main container component |
| useVoiceStream.ts | 619 | WebSocket communication hook |
| SettingsDrawer.tsx | 464 | Mode selection panel |
| AudioVisualizer.tsx | 327 | FFT ring visualization |
| ToolExecutionCard.tsx | 291 | Tool status display |
| HUDFrame.tsx | 238 | Sci-fi frame wrapper |
| voiceModes.ts | 206 | Mode definitions |
| StatusBadge.tsx | 188 | Status indicators |
| **Backend** | | |
| tts.py | 733 | Hybrid TTS system |
| websocket.py | 557 | WebSocket handler |
| stt.py | 418 | Hybrid STT system |
| wake_word.py | 371 | Porcupine wake word |
| kokoro_tts.py | 308 | Kokoro TTS streaming |
| kokoro_manager.py | 244 | Kokoro singleton manager |
| router.py | 239 | Voice routing |
| dependencies.py | 191 | Lazy initialization |
| parser.py | 68 | Intent classification |
| app.py | 60 | FastAPI endpoints |

**Total**: ~4,500 lines across frontend and backend

---

*Last updated: December 2024*
