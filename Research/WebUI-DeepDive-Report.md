# KITTY Web UI Deep Dive Report

**Date:** December 10, 2025
**Purpose:** UX Consolidation Planning
**Scope:** Complete analysis of the `/services/ui` codebase

---

## Executive Summary

The KITTY Web UI is a feature-rich React application with **17 distinct pages** accessible from a central menu. While functionally comprehensive, the UI suffers from **fragmented navigation**, **redundant entry points**, and **overlapping functionality** that creates a confusing user experience.

### Key Findings

| Metric | Value |
|--------|-------|
| Total Pages | 17 |
| Menu Items | 16 |
| Quick Nav Buttons | 5 |
| Duplicate Camera Interfaces | 3 |
| Overlapping Feature Areas | 6 |
| Reusable Components | ~40 |
| Custom Hooks | 10 |
| Voice Modes (System) | 5 |
| WebSocket Endpoints | 3 |
| CSS Custom Properties | 30+ |

### Critical Issues for Consolidation

1. **Camera functionality exists in 3 places** (Cameras, Dashboard, VisionService)
2. **Research workflow fragmented** across 3 pages (Research, Results, Calendar)
3. **Image handling split** between Vision Gallery and Image Generator
4. **No persistent navigation** - users must return to menu to switch contexts
5. **Inconsistent terminology** - "Vision" means different things in different places

---

## 1. Architecture Overview

### Real-Time Communication

The UI relies heavily on real-time communication for responsive updates:

#### MQTT Subscriptions
| Topic Pattern | Purpose | Data Format |
|---------------|---------|-------------|
| `kitty/devices/+/state` | Device state updates | JSON device status |
| `kitty/ctx/+` | Conversation context | JSON context data |

#### WebSocket Endpoints
| Endpoint | Purpose | Message Types |
|----------|---------|---------------|
| `wss://host/api/voice/stream` | Bidirectional voice | status, transcript, response.start, response.text, function.call, function.result, response.audio, response.end, error |
| `ws://host/api/cameras/stream` | Camera frame delivery | subscribe, unsubscribe, frame (JPEG) |
| `/api/settings/sync` | Settings synchronization | settings object with version |

#### Connection Resilience
- **Voice Stream**: Auto-reconnect with exponential backoff (1-30 seconds with jitter), max 5 attempts
- **Camera Stream**: Periodic list refresh every 10 seconds
- **Settings Sync**: Falls back to localStorage if WebSocket unavailable

### Tech Stack
- **Framework:** React 18 + TypeScript (strict mode)
- **Build Tool:** Vite
- **Styling:** Plain CSS with CSS variables (no Tailwind/CSS-in-JS)
- **State:** React Hooks + Context API (no Redux/Zustand)
- **Real-time:** MQTT + WebSocket
- **UI Library:** Minimal Ant Design usage, mostly custom components

### Routing Approach
The app uses a **custom view-based routing system** via `useState` in App.tsx - NOT React Router:

```typescript
type ViewType = 'menu' | 'dashboard' | 'projects' | 'console' | 'shell' |
                'wall' | 'vision' | 'images' | 'research' | 'results' |
                'iocontrol' | 'inventory' | 'intelligence' | 'cameras' |
                'calendar' | 'voice' | 'settings';
```

URL support is limited to `?view=<page-id>` query parameter.

---

## 2. Complete Page Inventory

### All 17 Pages

| # | Page ID | Title | Description | Category |
|---|---------|-------|-------------|----------|
| 1 | `voice` | KITTY (Voice) | Real-time voice assistant with STT/TTS | **Interaction** |
| 2 | `shell` | Chat Shell | Text chat with function calling | **Interaction** |
| 3 | `console` | Fabrication Console | Text-to-3D model generation | **Fabrication** |
| 4 | `projects` | Projects | Manage 3D printing projects | **Fabrication** |
| 5 | `dashboard` | 3D Printers | Monitor and control Bambu Lab printers | **Fabrication** |
| 6 | `vision` | Vision Gallery | Generated 3D models and assets | **Media** |
| 7 | `images` | Image Generator | Generate images from prompts | **Media** |
| 8 | `cameras` | Cameras | Live dashboard for connected cameras | **Monitoring** |
| 9 | `research` | Research | Deep research and analysis tools | **Research** |
| 10 | `results` | Results | Research results and reports | **Research** |
| 11 | `calendar` | Calendar | Schedule and event management | **Research** |
| 12 | `iocontrol` | I/O Control | Device and automation control | **System** |
| 13 | `inventory` | Inventory | Asset and material tracking | **Fabrication** |
| 14 | `intelligence` | Intelligence | Analytics and insights dashboard | **Analytics** |
| 15 | `wall` | Wall Terminal | Full-screen display mode | **Special** |
| 16 | `settings` | Settings | KITTY configuration and preferences | **System** |
| 17 | `menu` | Menu | Main navigation hub | **Navigation** |

### Page Categories Summary

| Category | Pages | Count |
|----------|-------|-------|
| **Interaction** | Voice, Shell | 2 |
| **Fabrication** | Console, Projects, Dashboard, Inventory | 4 |
| **Media** | Vision Gallery, Image Generator | 2 |
| **Monitoring** | Cameras | 1 |
| **Research** | Research, Results, Calendar | 3 |
| **System** | I/O Control, Settings | 2 |
| **Analytics** | Intelligence | 1 |
| **Special** | Wall Terminal, Menu | 2 |

---

## 3. Navigation Analysis

### Current Navigation Structure

```
┌─────────────────────────────────────────────────────────────┐
│  HEADER (always visible except on menu page)                │
│  ┌──────┬────────┬────────────────────────────────────────┐ │
│  │ ☰    │ KITTY  │  🎙️ Voice │ 💬 Shell │ 🎨 Fab │ ...   │ │
│  └──────┴────────┴────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                     MAIN CONTENT AREA                       │
│                    (one page at a time)                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Quick Navigation Buttons (Header)

Only 5 pages have header shortcuts:

| Button | Page | Rationale |
|--------|------|-----------|
| 🎙️ Voice | Voice | Primary interaction mode |
| 💬 Shell | Shell | Alternative interaction |
| 🎨 Fabricate | Console | Core feature |
| 🖨️ Printers | Dashboard | Core feature |
| ⚙️ Settings | Settings | Configuration |

**Missing from quick nav:**
- Research (core workflow)
- Results (research output)
- Cameras (monitoring)
- Calendar (scheduling)
- Vision Gallery (media management)
- Intelligence (analytics)

### Navigation Problems

1. **Menu is a Dead End**
   - User must return to menu to access unlisted pages
   - No breadcrumbs or back navigation history
   - Loses context when switching pages

2. **Quick Nav Coverage**
   - Only covers 5 of 16 destinations (31%)
   - Research workflow entirely missing
   - No camera access shortcut despite having dedicated page

3. **No Visual Hierarchy**
   - All 16 menu items displayed equally
   - No indication of usage frequency or importance
   - No grouping by workflow or category

4. **Hidden Dependencies**
   - Research → Results → Synthesis workflow not obvious
   - Console → Projects → Dashboard flow not guided
   - No task completion indicators

---

## 4. Redundancy & Overlap Analysis

### 🔴 Critical: Camera Functionality (3 locations)

| Location | Component | Purpose | Unique Features |
|----------|-----------|---------|-----------------|
| **Cameras page** | `VisionService.tsx` | Dedicated camera interface | Grid/single view toggle, snapshots |
| **Dashboard** | Embedded camera grid | Printer monitoring | Alongside printer status |
| **VisionGallery** | Image display | Curated images | Search/filter capabilities |

**Issue:** The "cameras" route in App.tsx actually loads `VisionService.tsx`:
```typescript
case 'cameras':
  return <VisionService />;
```

This naming mismatch adds confusion - there's no `Cameras.tsx` file, yet "Cameras" appears in the menu.

### 🔴 Critical: Research Workflow (3 pages)

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Research   │ ──▶ │   Results   │ ──▶ │ (Synthesis) │
│  (Execute)  │     │   (View)    │     │   in modal  │
└─────────────┘     └─────────────┘     └─────────────┘
        │
        ▼
┌─────────────┐
│  Calendar   │  (Schedule future research)
│ (Schedule)  │
└─────────────┘
```

**Issues:**
- Three separate pages for one workflow
- No clear progression indicators
- User doesn't know where to start
- Scheduled research results appear in Results, not Calendar

### 🟡 Moderate: Image/Vision Split

| Page | Purpose | Overlap |
|------|---------|---------|
| **Vision Gallery** | Search/curate existing images | Image display, filtering |
| **Image Generator** | Create new images via Stable Diffusion | Generation tracking, gallery |

**Issues:**
- Both handle image display
- Similar card-based UI patterns
- "Vision" terminology confusing (also used for cameras)
- Generated images could flow to gallery but don't automatically

### 🟡 Moderate: Chat Interfaces (2 modes)

| Page | Interface | Use Case |
|------|-----------|----------|
| **Voice** | Full-screen, audio visualization | Hands-free interaction |
| **Shell** | Text-based, inline tools | Detailed/precise commands |

**Assessment:** These are legitimately different modalities, but could share:
- Conversation history
- Tool execution display
- Provider selection

### 🟡 Moderate: Settings Fragmentation

| Location | Settings Type |
|----------|---------------|
| **Settings page** | Connections, Voice, Fabrication, UI |
| **Voice SettingsDrawer** | Voice speed, voice selection |
| **I/O Control** | Feature flags, device toggles |

**Issue:** Unclear where to find specific settings.

### 🟢 Minor: Printer Control (2 entry points)

| Page | Printer Interaction |
|------|---------------------|
| **Dashboard** | Full monitoring, job control |
| **Fabrication Console** | Printer selection for new jobs |

**Assessment:** Complementary, but could be better integrated.

---

## 5. Component Reuse Analysis

### Well-Designed Reusable Components

| Component | Location | Used In | Quality |
|-----------|----------|---------|---------|
| `VoiceAssistant` | components/VoiceAssistant/ | Voice page | ⭐⭐⭐⭐⭐ |
| `CameraDashboard` | components/CameraDashboard/ | VisionService, Dashboard | ⭐⭐⭐⭐ |
| `MeshSegmenter` | components/MeshSegmenter/ | FabricationConsole | ⭐⭐⭐⭐ |
| `ProviderSelector` | components/ProviderSelector.tsx | Multiple pages | ⭐⭐⭐ |

### Missing Shared Components

| Pattern | Current State | Should Be |
|---------|---------------|-----------|
| **Modal dialogs** | Each page implements own | Shared Modal component |
| **Filter toolbars** | Duplicated in 5+ pages | Shared FilterBar component |
| **Stat cards** | Similar styling, no shared code | Shared StatCard component |
| **Data tables** | Similar patterns, no abstraction | Shared DataTable component |
| **Loading states** | Inconsistent across pages | Shared LoadingSpinner |
| **Error displays** | Various implementations | Shared ErrorBanner |

---

## 6. Voice Mode System

The Voice interface supports configurable "modes" that customize tool availability and visual appearance.

### System-Defined Modes

| Mode | Icon | Color | Primary Tools |
|------|------|-------|---------------|
| **Basic** | 💬 | Cyan | General conversation |
| **Maker** | 🔧 | Orange | CAD, Fabrication |
| **Research** | 🔬 | Purple | Research, Reasoning |
| **Smart Home** | 🏠 | Green | Home Assistant |
| **Creative** | 🎨 | Pink | Image Generation, Vision |

### Color Presets

8 available colors for custom modes:
```
cyan | orange | purple | green | pink | red | blue | yellow
```

### Tool Categories

Tools are organized by category for mode configuration:

| Category | Tools Included |
|----------|----------------|
| **CAD** | 3D model generation, mesh operations |
| **Research** | Deep research, web search |
| **Home Assistant** | Device control, automation |
| **Vision** | Image analysis, camera access |
| **Image Generation** | Stable Diffusion |
| **Memory** | Semantic memory, context recall |
| **Fabrication** | Print queue, segmentation |
| **Discovery** | Network scanning |
| **Reasoning** | Chain-of-thought, analysis |

### Custom Mode Creation

Users can create custom modes with:
- Unique name and icon
- Color selection from 8 presets
- Selective tool enablement/disablement
- Paid API allowance toggle

Custom modes are persisted in settings and sync across devices.

---

## 7. Audio Processing Pipeline

The Voice interface includes sophisticated audio processing for capture and visualization.

### Audio Capture

```
Microphone → AudioWorklet (16kHz) → PCM16 → WebSocket
                    ↓
         ScriptProcessor (fallback for legacy browsers)
```

**Implementation Details:**
- Primary: AudioWorklet at `/audio-processor.js`
- Fallback: ScriptProcessor with PCM16 → Float32 conversion
- Sample rate: 16kHz mono
- Shared AudioContext via `AudioContextProvider` (prevents multiple context creation)

### Audio Visualization

#### FFT Frequency Bars
- 64 frequency bars
- Power law scaling: `value^0.5 × 1.8`
- Smooth animation via requestAnimationFrame

#### Input Level Meter
- Real-time microphone level (0-1 normalized)
- Normalization curve: `value^0.6 × 1.5`
- Visual feedback for speaking detection

### TTS Playback

```
Server → Base64 PCM16 → ArrayBuffer → AudioBufferSourceNode → Speakers
```

- Queued playback for seamless audio
- Sequential source node creation
- Automatic cleanup on completion

---

## 8. Enhanced Page Details

Additional technical details for key pages not covered in the inventory:

### Research.tsx

| Feature | Implementation |
|---------|----------------|
| **WebSocket Progress** | Real-time iteration counter, findings count, budget tracking |
| **Saturation Visualization** | Visual indicator when research reaches diminishing returns |
| **Research Templates** | Pre-configured query templates for common research types |
| **Source Tracking** | Citation management with URL validation |

### AutonomyCalendar.tsx

| Feature | Implementation |
|---------|----------------|
| **Cron Expressions** | Standard cron syntax for scheduling |
| **Natural Language** | "Every Monday at 9am" style scheduling |
| **Budget Limits** | Per-job cost caps |
| **Job Status** | Pending, running, completed, failed states |

### PrintIntelligence.tsx

| Feature | Implementation |
|---------|----------------|
| **Quality Scoring** | ML-based print quality assessment |
| **Failure Analysis** | Categorized failure reasons with frequency |
| **Human Review** | Manual override workflow for edge cases |
| **Cost Analytics** | Material and time cost tracking |

### WallTerminal.tsx

| Feature | Implementation |
|---------|----------------|
| **Purpose** | Physical display mode for workshop monitors |
| **Live Updates** | Real-time conversation monitoring |
| **Minimal UI** | Reduced chrome for distraction-free display |

---

## 9. User Journey Mapping

### Primary Workflows

#### Workflow 1: Voice Interaction
```
Menu → Voice → (conversation) → [Tool Executions] → (end)
                     ↓
              SettingsDrawer (adjust voice)
```
**Pain Points:** None significant - well-designed flow

#### Workflow 2: 3D Model Creation
```
Menu → Fabrication Console → Generate Model → Preview
                ↓                               ↓
         Select Provider              Mesh Segmenter
                                            ↓
                                    Projects (save)
                                            ↓
                                    Dashboard (print)
```
**Pain Points:**
- Multi-page workflow not guided
- Must manually navigate between pages
- No project status tracking across pages

#### Workflow 3: Research
```
Menu → Research → Run Query → [Wait for completion]
                      ↓
        ← Back to Menu → Results → View Findings
                                        ↓
                                Generate Synthesis
```
**Pain Points:**
- Must return to menu to see results
- No notification when research completes
- Synthesis buried in modal

#### Workflow 4: Camera Monitoring
```
Menu → Cameras → View Feeds → Take Snapshot
         ↓
    Which page? (VisionService vs embedded in Dashboard)
```
**Pain Points:**
- Unclear which camera interface to use
- Naming inconsistency (Cameras → VisionService.tsx)

---

## 10. Terminology Inconsistencies

| Term | Used For | Confusion |
|------|----------|-----------|
| **Vision** | VisionGallery (images), VisionService (cameras) | Different domains |
| **Console** | Fabrication Console only | Could mean command console |
| **Intelligence** | PrintIntelligence (analytics) | Suggests AI/brain function |
| **Calendar** | Research scheduling | General calendar expectation |
| **I/O Control** | Feature flags | Sounds like hardware I/O |
| **Wall** | Full-screen display | Unclear purpose |

---

## 11. Custom Hooks Reference

The UI implements several custom hooks for state management and real-time features:

### Audio Hooks

| Hook | File | Purpose |
|------|------|---------|
| `useAudioCapture` | hooks/useAudioCapture.ts | Microphone capture with AudioWorklet/ScriptProcessor |
| `useAudioAnalyzer` | hooks/useAudioAnalyzer.ts | FFT analysis for frequency visualization |
| `useAudioContext` | hooks/useAudioContext.ts | Shared AudioContext provider (prevents multiple contexts) |

### Communication Hooks

| Hook | File | Purpose |
|------|------|---------|
| `useVoiceStream` | hooks/useVoiceStream.ts | Voice WebSocket lifecycle, auto-reconnect, message handling |
| `useCameraStream` | hooks/useCameraStream.ts | WebSocket camera frame subscription with subscribe/unsubscribe |
| `useKittyContext` | hooks/useKittyContext.ts | MQTT subscription for device state and conversation context |

### Data Hooks

| Hook | File | Purpose |
|------|------|---------|
| `useConversationApi` | hooks/useConversationApi.ts | REST CRUD for conversations (list, fetch, rename, delete) |
| `useConversations` | hooks/useConversations.ts | Local conversation state management |
| `useSettings` | hooks/useSettings.ts | Settings with REST + WebSocket sync, localStorage fallback |
| `useRemoteMode` | hooks/useRemoteMode.ts | Tailscale/remote detection via 30s polling of `/api/remote/status` |

---

## 12. Feature Flags & Conditional Rendering

### Remote Mode Detection

When the UI detects a Tailscale/remote connection:
- Voice capture is disabled (microphone access blocked)
- Warning badges appear on affected features
- Read-only mode indicator shown

Detection: Periodic fetch (30s interval) of `/api/remote/status`

### IOControl Feature Flags

The I/O Control page manages runtime feature flags with:

| Feature | Restart Scope | Description |
|---------|---------------|-------------|
| None | `NONE` | Hot-swappable, immediate effect |
| Service | `SERVICE` | Requires service restart |
| Stack | `STACK` | Requires Docker stack restart |
| LlamaCPP | `LLAMACPP` | Requires llama.cpp server restart |

### Preset Configurations

IOControl supports applying pre-configured feature sets:
- Development presets
- Production presets
- Custom saved configurations

### Capability Reporting

Voice stream reports capabilities separately:
- STT availability
- TTS availability
- Streaming support

---

## 13. VoiceAssistant Component Architecture

The VoiceAssistant is the most complex component, with 10+ subcomponents:

```
VoiceAssistant/
├── index.tsx              # Main orchestrator
├── AudioVisualizer.tsx    # FFT-based frequency bars (64 bars)
├── InputLevelMeter.tsx    # Microphone level display
├── ConversationPanel.tsx  # Scrollable message history with auto-scroll
├── ConversationSelector.tsx # Browse/search past conversations
├── StreamingIndicator.tsx # Visual feedback during response streaming
├── StatusBadge.tsx        # Connection status (cyan/yellow/gray)
├── ToolExecutionCard.tsx  # Tool execution with 4 states
├── HUDFrame.tsx           # Sci-fi styled container
├── SettingsDrawer.tsx     # Voice mode selection (React Portal)
└── VoiceModeEditor.tsx    # Custom mode creation UI
```

### ToolExecutionCard States

| State | Visual | Meaning |
|-------|--------|---------|
| `pending` | Gray | Tool queued |
| `running` | Cyan pulse | Tool executing |
| `completed` | Green | Success |
| `error` | Red | Failed |

### HUDFrame Visual Elements

The sci-fi themed HUD frame includes:
- Corner brackets with glow effects
- Animated borders (state-based)
- Scan line overlay effect
- Glow shadows matching mode color

### SettingsDrawer

- Rendered via React Portal for proper z-index
- Escape key closes drawer
- Voice mode selection grid
- Custom mode creation button

---

## 14. Styling System

### CSS Custom Properties

The theme system uses 30+ CSS variables:

```css
/* Background */
--bg-primary, --bg-secondary, --bg-tertiary, --bg-overlay

/* Accent colors */
--accent-primary, --accent-secondary, --accent-glow

/* Text */
--text-primary, --text-secondary, --text-muted

/* Borders & Shadows */
--border-color, --border-glow, --shadow-color, --shadow-glow
```

### Theme Application

Themes applied via data attribute on document root:
```css
[data-theme='dark'] { /* dark mode variables */ }
[data-theme='light'] { /* light mode variables */ }
```

### Visual Effects

| Effect | CSS |
|--------|-----|
| **Glassmorphism** | `backdrop-filter: blur(20px)` with opacity overlays |
| **Gradient overlays** | Radial gradients at 20%,20% and 80%,0% |
| **Glow effects** | `box-shadow` with accent colors |
| **Scan lines** | CSS pseudo-elements with linear gradients |

### Hybrid Styling Approach

The UI uses both:
- **Tailwind CSS**: Utility classes for layout, spacing, responsive
- **CSS Variables**: Theme colors, component-specific styles

---

## 15. Hidden Features & Shortcuts

### Keyboard Shortcuts

| Key | Context | Action |
|-----|---------|--------|
| `Escape` | SettingsDrawer open | Close drawer |
| `Escape` | Modal open | Close modal |

### URL Parameters

| Parameter | Values | Effect |
|-----------|--------|--------|
| `?view=` | voice, dashboard, shell, console, research, results, cameras, etc. | Direct navigation to page |

### Configuration Options

| Setting | Location | Effect |
|---------|----------|--------|
| Push-to-Talk | Voice settings | Toggle voice activation mode |
| Paid API Allowance | Voice mode | Enable/disable paid API calls per mode |

### Identity Management

User ID resolution order:
1. Environment variable `VITE_KITTY_USER_ID`
2. localStorage `kitty_user_id`
3. Generated UUID (persisted to localStorage)

---

## 16. Error Handling Patterns

### Graceful Degradation

| Failure | Fallback |
|---------|----------|
| Settings API unavailable | localStorage persistence |
| SpeechRecognition unavailable | Server-side STT via WebSocket |
| WebSocket disconnect | Auto-reconnect with exponential backoff |
| Camera stream failure | Periodic retry every 10s |

### User-Facing Error States

| Pattern | Implementation |
|---------|----------------|
| Empty states | Helpful guidance text (e.g., "Start a conversation with KITTY") |
| API errors | Toast notifications with context |
| Connection errors | Status badges with retry options |
| Tool failures | ToolExecutionCard shows error state with message |

### Retry Logic

```
Attempt 1: 1 second delay
Attempt 2: 2 seconds + jitter
Attempt 3: 4 seconds + jitter
Attempt 4: 8 seconds + jitter
Attempt 5: 16 seconds + jitter (max 30s)
```

---

## 17. Consolidation Recommendations

### High Priority (Immediate Impact)

#### 1. Merge Research Workflow
Combine Research, Results, and Calendar scheduling into a **single Research Hub**:

```
┌────────────────────────────────────────────┐
│  RESEARCH HUB                              │
├────────────────────────────────────────────┤
│ [New Query] [Schedule] [History] [Active]  │ ← Tabs
├────────────────────────────────────────────┤
│                                            │
│  Content area based on selected tab        │
│                                            │
└────────────────────────────────────────────┘
```

**Benefits:**
- Single entry point for all research
- Clear workflow progression
- Active research visible alongside history

#### 2. Unify Camera Experience
Merge camera functionality into Dashboard or create clear separation:

**Option A:** Camera tab in Dashboard
```
Dashboard: [Printers] [Cameras] [Jobs] [Stats]
```

**Option B:** Rename and clarify
- Rename "Cameras" to "Live Feeds"
- Remove from menu, embed in Dashboard
- VisionGallery remains for static images

#### 3. Add Persistent Navigation
Replace menu-centric model with sidebar or bottom nav:

```
┌────────┬──────────────────────────────────────┐
│ SIDEBAR│  CONTENT AREA                        │
├────────┤                                      │
│ 🏠 Home│                                      │
│ 🎙️ Talk│                                      │
│ 🎨 Make│                                      │
│ 🔬 Find│                                      │
│ 📊 View│                                      │
│ ⚙️ Conf│                                      │
└────────┴──────────────────────────────────────┘
```

### Medium Priority

#### 4. Consolidate Settings
Merge I/O Control into Settings as a "System" tab:

```
Settings: [Connections] [Voice] [Fabrication] [UI] [System]
                                                      ↑
                                              (former I/O Control)
```

#### 5. Merge Image Interfaces
Combine Vision Gallery and Image Generator:

```
Media Hub: [Generate] [Gallery] [Search]
```

#### 6. Quick Nav Expansion
Add missing shortcuts:
```
Header: 🎙️ Voice | 💬 Shell | 🎨 Fab | 🖨️ Print | 🔬 Research | ⚙️ Settings
```

### Lower Priority

#### 7. Shared Component Library
Extract common patterns:
- `<Modal>` - unified modal system
- `<FilterBar>` - reusable filter toolbar
- `<StatCard>` - consistent stat display
- `<DataTable>` - sortable/filterable tables
- `<LoadingState>` - consistent loading UX

#### 8. Terminology Cleanup
| Current | Proposed |
|---------|----------|
| Vision Gallery | Media Gallery |
| VisionService | Camera Feeds |
| Intelligence | Print Analytics |
| I/O Control | System Controls |
| Wall Terminal | Kiosk Mode |

---

## 18. Proposed Consolidated Structure

### From 17 Pages to 8 Sections

| Current Pages | Consolidated To | Notes |
|---------------|-----------------|-------|
| Voice, Shell | **Talk** | Tabbed interaction modes |
| Console, Projects | **Make** | Fabrication workflow |
| Dashboard, Cameras, Inventory | **Print** | Printer operations hub |
| Vision Gallery, Image Generator | **Media** | All media management |
| Research, Results, Calendar | **Research** | Unified research hub |
| Intelligence | **Analytics** | Print analytics |
| Settings, I/O Control | **Settings** | All configuration |
| Wall Terminal | **Kiosk** | Special display mode (hidden from nav) |
| Menu | (Removed) | Replaced by persistent nav |

### Proposed Navigation

```
┌──────────────────────────────────────────────────────────────┐
│  KITTY     [Talk] [Make] [Print] [Media] [Research] [⚙️]    │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│                      CONTENT AREA                            │
│                                                              │
│  Within each section, use tabs for sub-features:            │
│  e.g., Talk: [Voice] [Chat]                                 │
│        Make: [Generate] [Projects]                          │
│        Print: [Printers] [Cameras] [Materials]              │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 19. Implementation Approach

### Phase 1: Navigation Overhaul (1 sprint)
1. Add React Router for proper routing
2. Implement persistent top navigation
3. Add breadcrumbs for context
4. Remove menu page (content becomes nav)

### Phase 2: Research Consolidation (1 sprint)
1. Merge Research + Results + Calendar into Research Hub
2. Add tabs for different views
3. Implement cross-tab state sharing

### Phase 3: Camera/Print Consolidation (1 sprint)
1. Move camera functionality into Dashboard tabs
2. Clarify VisionService vs VisionGallery naming
3. Integrate inventory into printer workflow

### Phase 4: Media Consolidation (1 sprint)
1. Merge Vision Gallery and Image Generator
2. Create unified media management experience
3. Add generation → gallery flow

### Phase 5: Settings Consolidation (1 sprint)
1. Merge I/O Control into Settings
2. Add System tab for feature flags
3. Consolidate voice settings from drawer

### Phase 6: Component Library (ongoing)
1. Extract shared components
2. Document component usage
3. Enforce consistent patterns

---

## Appendix A: File Structure Reference

```
services/ui/src/
├── pages/
│   ├── AutonomyCalendar.tsx    # Research scheduling
│   ├── Dashboard.tsx            # Printer monitoring
│   ├── FabricationConsole.tsx   # CAD generation
│   ├── ImageGenerator.tsx       # Stable Diffusion
│   ├── IOControl.tsx            # Feature flags
│   ├── MaterialInventory.tsx    # Printer materials
│   ├── Menu.tsx                 # Navigation hub
│   ├── PrintIntelligence.tsx    # Print analytics
│   ├── Projects.tsx             # Project management
│   ├── Research.tsx             # Research execution
│   ├── Results.tsx              # Research results
│   ├── Settings.tsx             # Configuration
│   ├── Shell.tsx                # Text chat
│   ├── VisionGallery.tsx        # Image gallery
│   ├── VisionService.tsx        # Camera feeds (confusingly named)
│   ├── Voice.tsx                # Voice interface
│   └── WallTerminal.tsx         # Kiosk mode
├── components/
│   ├── VoiceAssistant/          # 10+ voice subcomponents
│   ├── CameraDashboard/         # Camera grid component
│   ├── MeshSegmenter/           # 3D mesh viewer
│   ├── KittyBadge/              # Mascot component
│   └── [various .tsx files]     # Other components
├── hooks/
│   ├── useKittyContext.ts       # MQTT state
│   ├── useSettings.ts           # Settings persistence
│   ├── useVoiceStream.ts        # Audio handling
│   └── [other hooks]
├── contexts/
│   └── ThemeContext.tsx         # Dark/light theme
├── App.tsx                      # Root + routing
└── main.tsx                     # Entry point
```

---

## Appendix B: API Endpoints Used

| Service | Endpoints | Pages Using |
|---------|-----------|-------------|
| Brain | `/api/chat/*`, `/api/conversations/*` | Shell, Voice |
| Fabrication | `/api/fabrication/*` | Console, Dashboard, Inventory |
| Research | `/api/research/*` | Research, Results |
| Vision | `/api/vision/*` | VisionGallery |
| Images | `/api/images/*` | ImageGenerator |
| Settings | `/api/settings/*` | Settings |
| I/O Control | `/api/io-control/*` | IOControl |
| Autonomy | `/api/autonomy/*` | Calendar |

---

## Appendix C: Quick Reference

### Pages by Usage Frequency (Estimated)

| Tier | Pages | Rationale |
|------|-------|-----------|
| **Daily** | Voice, Shell, Dashboard | Core interaction |
| **Frequent** | Console, Research | Primary workflows |
| **Occasional** | Settings, Results, Projects | Supporting tasks |
| **Rare** | Inventory, Intelligence, Cameras, Calendar | Specialized |
| **Special** | Wall, Menu | Non-standard use |

### Header Quick Nav Coverage

| In Nav | Not in Nav |
|--------|------------|
| Voice ✅ | Research ❌ |
| Shell ✅ | Results ❌ |
| Console ✅ | Cameras ❌ |
| Dashboard ✅ | Calendar ❌ |
| Settings ✅ | Vision ❌ |
| | Images ❌ |
| | Inventory ❌ |
| | Intelligence ❌ |
| | I/O Control ❌ |

---

*Report generated for KITTY UX Consolidation Initiative*
