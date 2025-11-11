# Multi-Printer Control Specification

## Feature Overview

Enable KITTY to intelligently prepare 3D models and route them to appropriate slicer applications with two distinct workflows:

### Supported Printers (Priority Order)

1. **Bamboo Labs H2D** (BambuStudio.app) - **First choice** for superior print quality and accuracy
2. **Elegoo OrangeStorm Giga** (ElegySlicer.app) - **Second choice** if Bamboo too small or busy, fast print speed
3. **Snapmaker Artisan Pro** (Luban.app) - **CNC/Laser only**, multi-mode fabrication

All printers are on the same local WiFi network as KITTY (192.168.1.x subnet).

### Two Workflows

**Manual Workflow (Default):**
- KITTY analyzes model dimensions and printer availability
- KITTY opens STL in the appropriate slicer application
- User handles final orientation, supports, slicing, and print start
- Most control, fastest to implement

**Automatic Workflow (Future):**
- KITTY asks user for desired model height
- KITTY scales model appropriately
- KITTY uses vision server to validate orientation (widest base down)
- KITTY checks if supports are needed
- KITTY opens model in slicer with pre-configured settings
- User confirms and starts print
- More autonomous, requires vision integration

## Business Value

### Current State
- KITTY can generate CAD models but has no fabrication capability
- Users must manually determine which slicer to use
- No intelligent routing based on model size, printer quality, or availability
- No model scaling or orientation validation before slicing

### Desired State

**Phase 1 (Manual Workflow):**
- KITTY analyzes model and suggests optimal printer
- KITTY opens STL directly in correct slicer application
- User retains full control over slicing and print settings
- Fast time-to-value with minimal implementation complexity

**Phase 2 (Automatic Workflow):**
- KITTY asks user for target model size
- KITTY scales model to fit printer and user requirements
- KITTY uses computer vision to validate orientation and support needs
- KITTY pre-configures slicer settings for optimal results
- User reviews and approves before print starts

### Success Metrics

**Phase 1 (Manual):**
- ≥95% of models routed to correct slicer app
- <30 seconds from "print this" to slicer open
- Zero incorrect printer selections (CNC to wrong app, etc.)
- User satisfaction: "KITTY picked the right tool"

**Phase 2 (Automatic):**
- ≥90% of scaled models print successfully without size issues
- ≥85% of orientation recommendations accepted by users
- ≥80% of support generation recommendations accurate
- <2 minutes from CAD to ready-to-slice with optimal settings

## User Stories

### Story 1: Manual Workflow - Quick Slicer Launch (Phase 1)
**As a** fabrication operator
**I want** KITTY to open my STL in the correct slicer application
**So that** I can quickly start preparing the print without figuring out which tool to use

**Acceptance Criteria:**
- Given a 150mm STL model
- When I say "print this"
- Then KITTY analyzes dimensions (150mm max)
- And detects Bamboo H2D is available (not busy)
- And opens BambuStudio.app with the STL loaded
- And confirms "Opening in BambuStudio (Bamboo H2D) - 150mm model, excellent quality"
- And I can then orient, support, slice, and print manually

### Story 2: Manual Workflow - Bamboo Busy Fallback (Phase 1)
**As a** design engineer
**I want** KITTY to use Elegoo if Bamboo is busy
**So that** I don't have to wait or figure out printer availability myself

**Acceptance Criteria:**
- Given a 180mm STL model
- When Bamboo H2D is currently printing (busy)
- Then KITTY detects Bamboo unavailable
- And selects Elegoo Giga (model fits 800mm volume)
- And opens ElegySlicer.app with the STL loaded
- And confirms "Opening in ElegySlicer (Elegoo Giga) - Bamboo busy, Elegoo ready"

### Story 3: Manual Workflow - Large Model Routing (Phase 1)
**As a** maker
**I want** large models to automatically route to Elegoo
**So that** KITTY doesn't waste time trying to fit a 600mm model on a 250mm printer

**Acceptance Criteria:**
- Given a 600mm enclosure STL
- When I request to print
- Then KITTY analyzes dimensions (600mm max)
- And detects model exceeds Bamboo capacity (250mm)
- And selects Elegoo Giga (800mm capacity)
- And opens ElegySlicer.app
- And confirms "Opening in ElegySlicer (Elegoo Giga) - Large model, 600mm requires Elegoo"

### Story 4: Manual Workflow - CNC/Laser Mode (Phase 1)
**As a** maker
**I want** CNC and laser jobs to open in Luban
**So that** I can use the Snapmaker's multi-mode capabilities

**Acceptance Criteria:**
- Given a CAM file for CNC milling or DXF for laser engraving
- When I say "mill this" or "engrave this"
- Then KITTY detects mode="cnc" or mode="laser"
- And selects Snapmaker Artisan (only multi-mode printer)
- And opens Luban.app with the file loaded
- And confirms "Opening in Luban (Snapmaker Artisan) - CNC milling mode"

### Story 5: Automatic Workflow - Model Sizing (Phase 2)
**As a** design engineer
**I want** KITTY to ask me for target size and scale the model
**So that** I get the right size without manual CAD adjustments

**Acceptance Criteria:**
- Given a generic STL (e.g., 50mm bracket)
- When I say "print this at 200mm tall"
- Then KITTY calculates scale factor (4x)
- And scales STL from 50mm to 200mm using trimesh
- And validates 200mm fits on Bamboo H2D (250mm capacity)
- And saves scaled STL to artifacts directory
- And opens BambuStudio with scaled model
- And confirms "Scaled to 200mm, opening in BambuStudio"

### Story 6: Automatic Workflow - Orientation Validation (Phase 2)
**As a** fabrication operator
**I want** KITTY to check if my model is oriented correctly
**So that** I avoid failed prints due to poor orientation

**Acceptance Criteria:**
- Given an STL with narrow base (likely to tip)
- When KITTY analyzes the model
- Then vision server calculates bounding box and center of mass
- And detects widest dimension is not on Z-axis (build plate)
- And suggests rotation: "Model should be rotated 90° for stability"
- And asks "Rotate automatically or open for manual adjustment?"
- If auto-approved, KITTY rotates STL using trimesh
- And opens slicer with corrected orientation

### Story 7: Automatic Workflow - Support Detection (Phase 2)
**As a** maker
**I want** KITTY to warn me if supports are needed
**So that** I don't waste time on failed prints with overhangs

**Acceptance Criteria:**
- Given an STL with 70° overhang (needs supports)
- When KITTY analyzes the model with vision server
- Then vision detects overhang angle > 45°
- And calculates approximate support volume
- And warns "This model has steep overhangs, supports recommended"
- And notes "Enable tree supports in slicer settings"
- And opens slicer with visual indication of problem areas

## Technical Requirements

### Functional Requirements (Phase 1 - Manual Workflow)

#### FR-1: STL Analysis and Dimensioning
- System shall load STL files using trimesh library
- System shall calculate bounding box [min_x, min_y, min_z], [max_x, max_y, max_z]
- System shall extract max dimension from bounding box
- System shall report model dimensions in mm
- System shall validate STL file integrity before processing

#### FR-2: Printer Capability Registry
- System shall maintain printer capabilities in `config/printers.yaml`:
  - Bamboo H2D: build_volume=(250, 250, 250), quality="excellent", speed="medium"
  - Elegoo Giga: build_volume=(800, 800, 1000), quality="good", speed="fast"
  - Snapmaker Artisan: build_volume=(400, 400, 400), modes=["3d_print", "cnc", "laser"]
- System shall expose printer capabilities via API

#### FR-3: Printer Availability Detection
- System shall check Bamboo H2D status via MQTT subscription to `device/{serial}/report`
- System shall parse printer state: "idle", "printing", "paused", "offline"
- System shall query Elegoo Giga status via Moonraker HTTP GET `/printer/info`
- System shall cache printer status for 30 seconds to reduce network calls
- If status check fails, assume printer offline

#### FR-4: Intelligent Printer Selection Logic
**Priority hierarchy:**
1. **CNC or Laser mode** → Always Snapmaker Artisan (only multi-mode printer)
2. **3D Print mode:**
   - IF max_dimension ≤ 250mm AND Bamboo status="idle" → Bamboo H2D (best quality)
   - ELSE IF max_dimension ≤ 250mm AND Bamboo status="printing" → Elegoo Giga (fallback)
   - ELSE IF max_dimension > 250mm AND max_dimension ≤ 800mm → Elegoo Giga (only option)
   - ELSE → Error: "Model too large for all printers (max 800mm)"

#### FR-5: Slicer Application Launching (macOS)
- System shall use `open` command to launch slicer apps:
  - BambuStudio: `open -a BambuStudio {stl_path}`
  - ElegySlicer: `open -a ElegySlicer {stl_path}`
  - Luban: `open -a Luban {stl_path}`
- System shall verify app exists before launching: `mdfind "kMDItemCFBundleIdentifier == 'app.id'"`
- System shall handle app not found gracefully with installation instructions
- System shall log app launch events to telemetry

#### FR-6: Gateway API Endpoints (Phase 1)
- `POST /api/fabrication/open_in_slicer` - Manual workflow endpoint
  - Parameters: `stl_path`, `mode` (optional: "3d_print", "cnc", "laser")
  - Returns: `{"printer": "bamboo_h2d", "app": "BambuStudio", "message": "..."}`
- `GET /api/fabrication/analyze_model` - STL analysis only
  - Parameters: `stl_path`
  - Returns: `{"dimensions": {...}, "volume": ..., "recommended_printer": "..."}`
- `GET /api/fabrication/printer_status` - Get all printer statuses
  - Returns: `{"bamboo_h2d": {"status": "idle", ...}, ...}`

### Functional Requirements (Phase 2 - Automatic Workflow)

#### FR-7: Model Scaling
- System shall accept target_height parameter from user
- System shall calculate scale_factor = target_height / current_max_dimension
- System shall apply uniform scaling using `trimesh.Trimesh.apply_scale(scale_factor)`
- System shall validate scaled model fits on selected printer
- System shall save scaled STL to artifacts directory with suffix `_scaled_{height}mm.stl`
- System shall preserve original STL file unchanged

#### FR-8: Vision Server Integration - Orientation Analysis
- System shall call vision service endpoint: `POST /api/vision/analyze_orientation`
- System shall send STL mesh data or file path
- Vision server shall:
  - Calculate center of mass
  - Identify widest cross-section (XY plane when properly oriented)
  - Detect if widest dimension is on Z-axis (build plate)
  - Suggest rotation matrix if orientation suboptimal
- System shall receive orientation score (0-100) and rotation recommendation
- If score < 70, system shall prompt user for automatic rotation

#### FR-9: Vision Server Integration - Support Detection
- System shall call vision service endpoint: `POST /api/vision/analyze_supports`
- System shall send STL mesh data
- Vision server shall:
  - Iterate through triangles, calculate normal vectors
  - Detect faces with angle > 45° from vertical (overhangs)
  - Calculate percentage of model requiring supports
  - Identify support attachment points
- System shall receive support_required (boolean) and severity ("low", "medium", "high")
- System shall present findings: "Supports needed: 15% of model has overhangs"

#### FR-10: Safety and Confirmation
- Manual workflow (open_in_slicer): No confirmation required (hazard_class: low)
- Automatic workflow with modifications: Requires confirmation if:
  - Scaling factor > 2x or < 0.5x
  - Automatic rotation applied
  - Supports recommended but not yet configured
- All slicer launches logged to PostgreSQL telemetry_events

#### FR-11: Error Handling
- Handle STL file not found → Clear error message with path
- Handle corrupted STL → Suggest re-export from CAD software
- Handle slicer app not found → Provide download link
- Handle model too large → Suggest scaling or splitting
- Handle all printers offline → Notify user to check power/network
- Log all errors to structured logging with correlation IDs

### Non-Functional Requirements

#### NFR-1: Performance (Phase 1)
- STL analysis (bounding box): <1 second for models up to 100MB
- Printer status query: <2 seconds per printer (with 30s cache)
- Slicer app launch: <3 seconds from command to app open
- Total workflow: <10 seconds from "print this" to slicer open

#### NFR-2: Performance (Phase 2)
- Model scaling: <5 seconds for models up to 100MB
- Vision orientation analysis: <10 seconds for models up to 50MB
- Vision support detection: <15 seconds for complex models
- Total automatic workflow: <30 seconds from request to slicer open with prep

#### NFR-3: Reliability
- Graceful degradation: If printer status check fails, assume offline and continue
- Cache printer status for 30 seconds to handle network hiccups
- Retry slicer app launch once if initial attempt fails
- Validate STL integrity before processing (catch corrupted files early)

#### NFR-4: Security
- All printer communication over local network (192.168.1.x)
- MQTT credentials stored in `.env`, never committed to git
- No file uploads to printers (user handles in slicer)
- Slicer apps sandboxed by macOS (no elevation required)

#### NFR-5: Observability
- Structured logging with correlation IDs for each print request
- Metrics: slicer launches, printer selection accuracy, model dimensions
- Log model path, selected printer, dimensions, and decision rationale
- Integration with existing Prometheus/Grafana stack

#### NFR-6: Maintainability
- Configuration-driven printer registry (`config/printers.yaml`)
- Modular design: STL analyzer, printer selector, slicer launcher as separate classes
- Comprehensive unit tests for selection logic with various model sizes
- Mock vision server responses for Phase 2 testing

## Data Model

### Printer Configuration Schema

```yaml
printers:
  {printer_id}:
    type: bamboo_h2d | elegoo_giga | snapmaker_artisan
    ip: string (IPv4 address)
    port: integer (optional, defaults per type)
    serial: string (Bamboo only)
    access_code: string (Bamboo only)
    token: string (Snapmaker only, optional)
    mqtt_host: string (Bamboo only, optional)
    mqtt_port: integer (Bamboo only, optional)
```

### PrinterCapabilities

```python
@dataclass
class PrinterCapabilities:
    printer_type: PrinterType
    print_modes: list[PrintMode]  # [FDM_3D_PRINT, CNC_MILL, LASER_ENGRAVE]
    max_x: float  # mm
    max_y: float  # mm
    max_z: float  # mm
    supported_materials: list[str]
```

### PrinterStatus

```python
@dataclass
class PrinterStatus:
    is_online: bool
    is_printing: bool
    current_job_id: Optional[str]
    bed_temp: Optional[float]
    extruder_temp: Optional[float]
    progress_percent: Optional[float]
    estimated_time_remaining: Optional[int]  # seconds
```

### PrintJobSpec

```python
@dataclass
class PrintJobSpec:
    job_id: str
    file_path: Path
    print_mode: PrintMode
    nozzle_temp: Optional[int] = None
    bed_temp: Optional[int] = None
    material: Optional[str] = None
```

## Integration Points

### Upstream Dependencies
- **CAD Service**: Provides STL files for printing
- **Common Config**: Loads printer credentials from `.env`
- **Common Messaging**: Uses existing MQTT client
- **Common Logging**: Structured logging utilities

### Downstream Consumers
- **Gateway**: Exposes fabrication endpoints to ReAct agent
- **Brain Service**: Calls fabrication tools via MCP protocol
- **UI Dashboard**: Displays printer farm status
- **Voice Service**: Accepts "print this" commands

### External Systems
- **Bamboo Labs H2D**: MQTT broker (local/cloud), FTPS server
- **Elegoo Giga Moonraker**: HTTP JSON-RPC API (port 7125)
- **Snapmaker Artisan**: SACP TCP server (port 8888)

## Security Considerations

1. **Network Isolation**: All printers on trusted local WiFi, no WAN access
2. **Credential Management**: Access codes and tokens in `.env`, excluded from git
3. **TLS Encryption**: Bamboo FTPS uses implicit TLS (port 990)
4. **Confirmation Required**: Medium hazard class requires user approval phrase
5. **Audit Trail**: All print jobs logged with timestamp, user, model file
6. **No Remote Access**: Printers not exposed via ngrok/Cloudflare tunnels

## Constraints and Assumptions

### Constraints
- All printers must be on same local network as KITTY
- Static IP addresses required for reliable communication
- Bamboo requires LAN-only mode or Bambu Cloud credentials
- Snapmaker SACP protocol lacks official Python SDK (community-driven)
- Klipper Moonraker has no authentication (relies on network security)

### Assumptions
- User has physical access to printers for initial setup
- User knows Bamboo serial number and access code
- Elegoo Giga has Klipper + Moonraker pre-installed
- Snapmaker has default SACP port 8888 enabled
- Local network has reliable WiFi coverage
- No multi-tenant use (single KITTY instance per printer farm)

## Out of Scope (Future Enhancements)

1. **Automatic Slicing**: STL → G-code conversion (use Orca Slicer CLI separately)
2. **Multi-Material Detection**: Analyze STL for multi-color requirements
3. **Queue Management**: Job queuing when all printers busy
4. **Printer Health Monitoring**: Track failure rates, maintenance schedules
5. **Cost Estimation**: Calculate material cost per print
6. **Print Farm Scaling**: Support multiple instances of same printer type
7. **Cloud Print Submission**: Remote print via internet (security concern)
8. **Webcam Streaming**: Live video from printer cameras

## Training Data Collection (Phase 2/3)

To enable KITTY to learn from operator workflows and improve automatic print preparation, the system shall capture training data from manual slicer interactions.

### Approach 1: Screen Recording (Recommended)

**Concept:**
- Record slicer window when user interacts with it
- Start recording on **first user interaction** (not when slicer opens)
- Capture all user actions: orientation changes, support placement, slicer settings
- Stop recording when user closes slicer or explicitly stops recording

**Implementation (macOS):**

```python
# Using AVFoundation for window-specific recording
class SlicerRecorder:
    """Record slicer interactions for training data."""

    def monitor_slicer(self, app_name: str, session_id: str):
        """
        Start monitoring slicer window for user interaction.

        Workflow:
        1. Launch slicer (Phase 1)
        2. Monitor for window focus change to slicer
        3. Detect first mouse click or keyboard input in slicer window
        4. Start recording at that moment (not before)
        5. Record until slicer closed or timeout (30 min)
        """

    def start_recording(self, window_id: int, output_path: Path):
        """
        Record specific window using AVFoundation.

        Uses:
        - CGWindowListCreateImage for window capture
        - AVAssetWriter for video encoding
        - H.264 codec at 30fps
        """

    def annotate_recording(self, video_path: Path, events: List[Event]):
        """
        Add metadata track with user actions and timestamps.

        Events captured:
        - Mouse clicks (with coordinates relative to slicer window)
        - Keyboard shortcuts (e.g., Ctrl+R for rotate)
        - Button clicks (identified via Accessibility API if available)
        - Settings changes (detected via screen diff)
        """
```

**Captured Data Structure:**

```yaml
session_id: "fab_20250111_143022"
model_path: "/Users/Shared/KITT/artifacts/cad/bracket.stl"
model_dimensions: {width: 150, depth: 100, height: 50}
printer: "bamboo_h2d"
slicer_app: "BambuStudio"
recording_start: "2025-01-11T14:30:45Z"
recording_duration: 342  # seconds

user_actions:
  - timestamp: "2025-01-11T14:30:47Z"
    action: "rotate_model"
    params: {axis: "z", degrees: 90}

  - timestamp: "2025-01-11T14:31:12Z"
    action: "enable_supports"
    params: {type: "tree", density: "15%"}

  - timestamp: "2025-01-11T14:32:05Z"
    action: "change_infill"
    params: {pattern: "gyroid", density: "20%"}

  - timestamp: "2025-01-11T14:35:30Z"
    action: "slice_model"
    params: {layer_height: 0.2, print_time: "1h 45m"}

outcome: "print_started"  # or "abandoned", "error"
video_path: "/Users/Shared/KITT/training/recordings/fab_20250111_143022.mp4"
annotations_path: "/Users/Shared/KITT/training/recordings/fab_20250111_143022.json"
```

**Privacy & Consent:**
- Recording only starts when user interacts (not automatically)
- Option to disable recording in settings: `ENABLE_SLICER_RECORDING=false`
- Recordings stored locally, never uploaded without explicit consent
- User can review and delete recordings before they're used for training
- Only record slicer window, not full screen (no sensitive data capture)

### Approach 2: Inter-Process Communication Monitoring (Advanced)

**Concept:**
- Monitor commands sent to slicer via IPC mechanisms
- Capture structured data instead of video
- More precise but requires reverse engineering each slicer

**macOS IPC Monitoring Options:**

1. **Apple Script** (if slicer supports it):
```applescript
tell application "BambuStudio"
  get properties of document 1
  -- Capture model orientation, support settings, etc.
end tell
```

2. **Accessibility API** (NSAccessibility):
```python
from AppKit import NSAccessibility

class SlicerAccessibilityMonitor:
    """Monitor slicer UI elements via Accessibility API."""

    def capture_ui_state(self, app_name: str):
        """
        Query UI elements to capture slicer state.

        Requires: Accessibility permissions in System Preferences

        Captures:
        - Button clicks (e.g., "Add Supports" button)
        - Slider changes (e.g., infill density slider)
        - Text field edits (e.g., layer height input)
        - Menu selections (e.g., "Orient for printing")
        """
```

3. **System-Level Event Monitoring**:
```python
from Quartz import (
    CGEventTapCreate,
    kCGEventTapOptionDefault,
    kCGEventLeftMouseDown,
    kCGEventKeyDown,
    kCGHIDEventTap
)

class SystemEventMonitor:
    """Monitor system events when slicer is active window."""

    def start_monitoring(self):
        """
        Capture mouse and keyboard events.

        Requires: Input Monitoring permission

        Filters events to only capture when slicer is active:
        - Mouse clicks (position relative to slicer window)
        - Keyboard shortcuts (Cmd+R, Cmd+S, etc.)
        - Scroll events (zooming, panning)
        """
```

**Structured Data Output:**

```json
{
  "session_id": "fab_20250111_143022",
  "slicer_commands": [
    {
      "timestamp": "2025-01-11T14:30:47Z",
      "command": "rotate_model",
      "method": "button_click",
      "ui_element": "RotateZButton",
      "parameters": {"degrees": 90}
    },
    {
      "timestamp": "2025-01-11T14:31:12Z",
      "command": "enable_supports",
      "method": "menu_selection",
      "ui_element": "SupportMenu > TreeSupports",
      "parameters": {"enabled": true, "type": "tree"}
    }
  ]
}
```

### Training Data Usage

**Collected data will enable:**

1. **Supervised Learning for Automatic Workflow (Phase 2)**:
   - Train model to predict optimal orientation based on geometry + user corrections
   - Learn which models typically need supports (features → support decision)
   - Predict slicer settings based on model characteristics

2. **Reinforcement Learning from Human Feedback (RLHF)**:
   - Reward function: Did user change KITTY's suggested orientation? (negative reward)
   - Reward function: Did print succeed without user intervention? (positive reward)
   - Learn to minimize user corrections over time

3. **Vision Model Training**:
   - Annotated screen recordings → train computer vision to detect:
     - Good vs bad orientation (visual features)
     - Support attachment points (visual cues)
     - Overhangs and problematic geometry

4. **Intent Classification**:
   - User says "print this" → What did they actually do in slicer?
   - Build dataset: {model_features, user_prompt} → {final_slicer_settings}
   - Improve natural language understanding for print requests

### Storage & Infrastructure

**Data Storage:**
```
/Users/Shared/KITT/training/
├── recordings/
│   ├── fab_20250111_143022.mp4       # Screen recording
│   ├── fab_20250111_143022.json      # Annotations
│   └── fab_20250111_143022_stl.json  # Model metadata
├── ipc_logs/
│   └── fab_20250111_143022.json      # IPC commands (if using Approach 2)
└── training_dataset/
    ├── orientation_corrections.jsonl  # Aggregated training data
    ├── support_decisions.jsonl
    └── slicer_settings.jsonl
```

**PostgreSQL Schema Addition:**
```sql
CREATE TABLE slicer_sessions (
    session_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    model_path TEXT NOT NULL,
    model_dimensions JSONB NOT NULL,
    printer_id VARCHAR(50) NOT NULL,
    slicer_app VARCHAR(50) NOT NULL,
    recording_path TEXT,
    annotations_path TEXT,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    outcome VARCHAR(20),  -- 'print_started', 'abandoned', 'error'
    user_actions JSONB,  -- Array of action events
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_slicer_sessions_model ON slicer_sessions(model_path);
CREATE INDEX idx_slicer_sessions_printer ON slicer_sessions(printer_id);
CREATE INDEX idx_slicer_sessions_outcome ON slicer_sessions(outcome);
```

### Implementation Priority

**Phase 2 (After Manual Workflow Stable):**
- [ ] Implement screen recording with user interaction detection
- [ ] Add recording start/stop controls to UI
- [ ] Store recordings with metadata in PostgreSQL
- [ ] User consent and privacy controls

**Phase 3 (Advanced Training Data):**
- [ ] IPC monitoring for structured command capture
- [ ] Accessibility API integration for UI state capture
- [ ] Annotation tools for manual labeling of recordings
- [ ] Export training datasets for model fine-tuning

### Ethical Considerations

1. **Transparency**: User must know when recording is active (indicator in UI)
2. **Consent**: Opt-in only, disabled by default
3. **Privacy**: Only record slicer window, no personal/sensitive data
4. **Control**: User can review, delete, or opt-out of recordings at any time
5. **Security**: Recordings stored locally, encrypted at rest
6. **Anonymization**: Remove personally identifiable information before training

## Dependencies

**Phase 1 (Manual Workflow):**
```txt
trimesh==4.0.10        # STL loading, bounding box, scaling
numpy==1.24.3          # Mesh calculations (trimesh dependency)
paho-mqtt==1.6.1       # Bamboo H2D status checking via MQTT
httpx==0.25.2          # Elegoo Giga status via Moonraker (already in use)
pyyaml==6.0.1          # Printer config parsing (already in use)
```

**Phase 2 (Automatic Workflow):**
```txt
scipy==1.11.3          # Center of mass calculations
numpy-stl==3.0.1       # STL manipulation and rotation
```

**Phase 2/3 (Training Data Collection):**
```txt
pyobjc-framework-Quartz==10.1   # macOS screen recording, window capture
pyobjc-framework-AVFoundation==10.1  # Video encoding, H.264 codec
pyobjc-framework-AppKit==10.1   # Accessibility API for UI monitoring
psutil==5.9.6          # Process monitoring, window detection
```

**Slicer Applications (macOS):**
- **BambuStudio**: [https://bambulab.com/en/download](https://bambulab.com/en/download)
- **ElegySlicer** (OrcaSlicer fork): Check Elegoo website or use OrcaSlicer
- **Luban**: [https://snapmaker.com/product/snapmaker-luban](https://snapmaker.com/product/snapmaker-luban)

## Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Bamboo MQTT authentication changes | High | Low | Use official bambulabs_api library as fallback |
| Snapmaker SACP protocol undocumented | Medium | Medium | Reference official TypeScript SDK, use Wireshark analysis |
| Network instability causes failed uploads | Medium | Medium | Implement retry logic with exponential backoff |
| Model too large for all printers | Low | Low | Return clear error with size requirements |
| Printer firmware updates break API | High | Low | Version-lock firmware, test before prod updates |

## Testing Strategy

### Unit Tests
- ✅ Printer selection logic with various STL sizes
- ✅ Build volume validation
- ✅ Print mode routing (3d_print, cnc, laser)
- ✅ Driver connection retry logic
- ✅ Configuration parsing

### Integration Tests
- ✅ Bamboo MQTT connection and status parsing
- ✅ Klipper Moonraker HTTP upload and start
- ✅ Snapmaker SACP handshake and command sending
- ✅ Gateway API endpoints with mock fabrication service
- ✅ Full CAD → Print workflow

### Manual Testing
- ✅ Upload 10MB, 50MB, 100MB files to each printer
- ✅ Verify automatic selection for small/medium/large models
- ✅ Test CNC mode routes to Snapmaker only
- ✅ Validate pause/resume/cancel on all printers
- ✅ Check error messages when printer offline

## Acceptance Criteria

### Must Have
- [x] All three printers accessible from KITTY
- [x] Automatic printer selection based on model size
- [x] Manual printer override via `printer_id` parameter
- [x] Real-time status for all printers via `list_printers`
- [x] Full control: upload, start, pause, resume, cancel
- [x] Safety confirmation for all print jobs
- [x] Tool registry updated with fabrication tools
- [x] Gateway routes registered and proxying to fabrication service

### Nice to Have
- [ ] WebSocket status streaming for real-time progress
- [ ] Computer vision integration for failure detection
- [ ] Auto-retry failed uploads
- [ ] Estimated print time calculation
- [ ] Material usage estimation

## Rollout Plan

### Phase 1: Development (Week 1)
- Implement driver interface and three concrete drivers
- Create printer registry and selection engine
- Update job manager for multi-printer support

### Phase 2: Integration (Week 2)
- Add gateway fabrication routes
- Update tool registry
- Wire up MQTT handlers

### Phase 3: Testing (Week 3)
- Unit and integration tests
- Manual testing with all three printers
- Validation of CAD → Print workflow

### Phase 4: Documentation (Week 4)
- Update Operations Manual
- Create printer setup guide
- Document troubleshooting procedures

### Phase 5: Production (Week 5)
- Deploy to production
- Monitor metrics and logs
- Iterate based on user feedback

## Monitoring and Metrics

### Key Metrics
- **Print Job Success Rate**: % of jobs completed without error
- **Printer Selection Accuracy**: % of auto-selections that complete successfully
- **Average Time to Print**: Median time from queue to print start
- **Printer Uptime**: % time each printer reports online status
- **Error Rate by Printer**: Failures grouped by printer type

### Alerts
- Printer offline for >10 minutes
- Print failure rate >10% in 1 hour
- Upload failure (3 retries exhausted)
- Model too large for all printers

### Dashboards
- Grafana: Printer farm overview (status, current jobs, temps)
- Prometheus: Job count, success rate, duration percentiles
- PostgreSQL: Historical job data for analysis

## References

- Research document: `Research/3dPrinterControl.md`
- Implementation plan: `specs/002-MultiPrinterControl/plan.md`
- Tool registry: `config/tool_registry.yaml`
- Operations Manual: `KITTY_OperationsManual.md`
- Conversation Framework: `Research/KITTY_Conversation_Framework_Implementation.md`
