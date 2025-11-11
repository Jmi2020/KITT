# Multi-Printer Control Specification

## Feature Overview

Enable KITTY to control three different 3D printers on the local network with intelligent printer selection based on model characteristics:

1. **Bamboo Labs H2D** - Optimal for small-medium FDM prints (≤200mm)
2. **Elegoo OrangeStorm Giga** - Large format FDM printing with Klipper (800x800x1000mm)
3. **Snapmaker Artisan Pro** - Multi-mode fabrication (3D print, CNC, laser engraving)

All printers are on the same local WiFi network as KITTY (192.168.1.x subnet).

## Business Value

### Current State
- KITTY can generate CAD models but has no fabrication capability
- Existing fabrication service only supports single OctoPrint instance
- No intelligent routing based on model size or fabrication mode
- Manual printer selection required

### Desired State
- Autonomous CAD-to-fabrication workflow with minimal human intervention
- Smart printer selection based on:
  - Model dimensions (STL bounding box analysis)
  - Fabrication mode (3D print, CNC, laser)
  - Printer availability
- Unified control interface for all three printer types
- Real-time status monitoring across printer farm

### Success Metrics
- ≥90% of print jobs routed to optimal printer automatically
- <5 minutes from CAD completion to print start (after user confirmation)
- Zero printer selection errors (wrong printer for model size/mode)
- Full observability: printer status, job progress, failure detection

## User Stories

### Story 1: Autonomous Small Part Fabrication
**As a** fabrication operator
**I want** KITTY to automatically print small parts on the Bamboo H2D
**So that** I don't have to manually select printers for routine jobs

**Acceptance Criteria:**
- Given a 150mm STL model
- When I say "print this on the best printer"
- Then KITTY selects Bamboo H2D
- And uploads G-code via FTPS
- And starts print via MQTT
- And confirms "Printing on Bamboo H2D, ETA 1h 45m"

### Story 2: Large Format Automatic Routing
**As a** design engineer
**I want** large models (>200mm) to automatically use the Elegoo Giga
**So that** I can leverage the 800mm build volume without manual configuration

**Acceptance Criteria:**
- Given a 650mm enclosure STL
- When queuing the print job
- Then KITTY detects max dimension > 200mm
- And selects Elegoo Giga
- And validates model fits in 800x800x1000mm build volume
- And uploads via Moonraker HTTP
- And starts print via JSON-RPC

### Story 3: CNC/Laser Mode Selection
**As a** maker
**I want** CNC and laser jobs to automatically route to Snapmaker
**So that** I can use the correct tool head without printer selection

**Acceptance Criteria:**
- Given a CAM file for CNC milling
- When setting print_mode="cnc"
- Then KITTY selects Snapmaker Artisan (only CNC-capable printer)
- And uploads via SACP protocol
- And switches to CNC tool head
- And starts job

### Story 4: Multi-Printer Status Dashboard
**As a** facilities operator
**I want** to see all printer statuses in one view
**So that** I can monitor the fabrication farm at a glance

**Acceptance Criteria:**
- When calling fabrication.list_printers
- Then I see:
  - Online/offline status for all 3 printers
  - Current job ID and progress %
  - Bed/extruder temperatures
  - Build volume capabilities
  - Supported materials and modes

### Story 5: Manual Override
**As a** power user
**I want** to manually specify a printer
**So that** I can override automatic selection when needed

**Acceptance Criteria:**
- Given a 180mm model (would auto-select Bamboo)
- When I specify printer_id="elegoo_giga"
- Then KITTY uses Elegoo instead
- And validates model still fits
- And proceeds with print

## Technical Requirements

### Functional Requirements

#### FR-1: Printer Discovery and Registration
- System shall load printer configurations from `config/printers.yaml`
- Each printer must have: type, IP address, authentication credentials
- System shall validate connectivity on startup
- System shall expose printer capabilities (build volume, supported modes)

#### FR-2: Automatic Printer Selection
- System shall analyze STL bounding box using trimesh library
- Selection logic:
  - `print_mode=cnc` or `laser` → Snapmaker Artisan
  - `print_mode=3d_print` AND max_dimension ≤ 200mm → Bamboo H2D
  - `print_mode=3d_print` AND max_dimension > 200mm → Elegoo Giga
- System shall validate model fits on selected printer
- System shall fail gracefully if no printer can accommodate model

#### FR-3: Bamboo Labs H2D Driver
- Connect to local MQTT broker (port 1883) or Bambu cloud (port 8883)
- Authenticate with serial number + 16-character access code
- Upload G-code via FTPS (port 990, implicit TLS)
- Send print commands via MQTT publish to `device/{serial}/request`
- Subscribe to status updates on `device/{serial}/report`
- Parse JSON status for bed temp, nozzle temp, progress %, state

#### FR-4: Klipper/Moonraker Driver (Elegoo Giga)
- Connect to Moonraker HTTP API (port 7125)
- Query printer status via JSON-RPC 2.0 (`printer.objects.query`)
- Upload G-code via HTTP POST `/server/files/upload`
- Start print via JSON-RPC `printer.print.start`
- Control via G-code commands (PAUSE, RESUME, CANCEL_PRINT)
- No authentication required (local network only)

#### FR-5: Snapmaker SACP Driver
- Connect to TCP socket on port 8888
- Implement SACP protocol: length-prefixed JSON frames
- Send authentication via `enclosure.auth` command
- Upload files via chunked SACP transfer
- Send print commands with mode selection (3d_print, cnc, laser)
- Parse status responses for temperature, progress, job state

#### FR-6: Gateway API Endpoints
- `POST /api/fabrication/queue` - Queue print with auto-selection
- `GET /api/fabrication/printers` - List all printers with status
- `GET /api/fabrication/printers/{id}/status` - Get specific printer status
- `POST /api/fabrication/printers/{id}/pause` - Pause print
- `POST /api/fabrication/printers/{id}/resume` - Resume print
- `POST /api/fabrication/printers/{id}/cancel` - Cancel print

#### FR-7: Safety and Confirmation
- All `fabrication.queue_print` actions require confirmation phrase
- Hazard class: medium (physical device control)
- Audit logging: Log all print starts to PostgreSQL telemetry_events
- Validate printer online before queueing job
- Prevent simultaneous jobs on same printer

#### FR-8: Error Handling
- Handle printer offline gracefully (return status: "offline")
- Handle MQTT/HTTP/SACP connection failures with retry logic
- Validate file existence before upload
- Return actionable error messages to user
- Log all errors to structured logging

### Non-Functional Requirements

#### NFR-1: Performance
- Printer status query: <2 seconds per printer
- File upload: Accept files up to 500MB
- Total workflow (upload + start): <30 seconds for 50MB file

#### NFR-2: Reliability
- Driver connection retry: 3 attempts with exponential backoff
- Graceful degradation: If one printer offline, others remain functional
- No data loss: Failed uploads don't corrupt printer storage

#### NFR-3: Security
- All communication over local network (192.168.1.x)
- No internet exposure of printer APIs
- Credentials stored in `.env`, never committed to git
- FTPS for Bamboo uploads (TLS encrypted)

#### NFR-4: Observability
- Structured logging with correlation IDs
- Metrics: print job count, success rate, avg duration per printer
- Status updates published to MQTT `kitty/devices/{printer}/state`
- Integration with existing Prometheus/Grafana stack

#### NFR-5: Maintainability
- Abstract PrinterDriver interface for future printer types
- Configuration-driven printer registry (no hardcoded IPs)
- Comprehensive unit tests for selection logic
- Integration tests with mock MQTT/HTTP servers

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

## Dependencies

```txt
paho-mqtt==1.6.1       # Bamboo Labs MQTT client
trimesh==4.0.10        # STL bounding box analysis
httpx==0.25.2          # HTTP client (already in use)
pyyaml==6.0.1          # YAML config parsing (already in use)
```

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
