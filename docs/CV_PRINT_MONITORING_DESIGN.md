# Computer Vision Print Monitoring - Design Document

## Overview

KITTY will use visual monitoring from multiple camera sources to track print quality and eventually detect failures automatically. This document outlines the phased approach from human-in-the-loop feedback to autonomous failure detection.

---

## Camera Sources

### 1. Bamboo Labs H2D
- **Camera**: Built-in camera system
- **Access**: Via Bamboo Labs API/MQTT
- **Resolution**: HD (typically 1280x720 or 1920x1080)
- **Features**: Time-lapse, live stream, snapshot on-demand
- **Integration**: MQTT topics for camera state, snapshot URLs

### 2. Snapmaker Artisan
- **Camera**: Raspberry Pi Camera Module installed
- **Access**: Direct HTTP/RTSP stream or snapshots
- **Resolution**: Configurable (suggest 1080p)
- **Features**: Live stream, snapshot capture, motion detection
- **Integration**: Custom endpoints for snapshot/video

### 3. Elegoo Giga (Future)
- **Camera**: Raspberry Pi Camera Module (to be installed)
- **Access**: Same as Snapmaker
- **Resolution**: Configurable
- **Features**: Live stream, snapshot capture
- **Integration**: Same architecture as Snapmaker

---

## Phased Implementation

### Phase 1: Human-in-the-Loop (Now - Task 2.1)

**Goal**: Collect labeled training data with human feedback

**Workflow**:
1. Print job starts → Capture initial snapshot
2. Periodic snapshots during print (every 5 min, or key milestones: first layer, 25%, 50%, 75%)
3. Print completes → Capture final snapshot
4. **KITTY asks human**: "How did print {job_id} go?"
5. Human provides:
   - Pass/Fail
   - Defect types (if failed)
   - Quality scores (1-10 scale for layer consistency, surface finish)
   - Notes
6. Store outcome + snapshots + human feedback

**Data Collection**:
- 100+ prints with human feedback = training dataset
- Snapshots stored in MinIO with timestamps
- Outcome linked to visual evidence

**Benefits**:
- No ML required yet
- Builds labeled dataset for future CV model
- KITTY learns from human expertise
- Iterative improvement

---

### Phase 2: Failure Type Research (Task 2.1 Extended)

**Goal**: KITTY researches print failure visual characteristics

**Research Topics** (Perplexity queries):
1. "What do 3D print first layer adhesion failures look like visually?"
2. "Visual characteristics of 3D print warping and curling"
3. "How to identify spaghetti failures in 3D printing from camera images"
4. "Visual indicators of nozzle clogs during 3D printing"
5. "Stringing and oozing visual patterns in FDM printing"
6. "Layer shift detection in 3D printing computer vision"

**Output**: KB articles with:
- Visual failure characteristics
- Key indicators to look for
- Reference images/descriptions
- Detection strategies

**Storage**: `knowledge/fabrication/failure_detection/{failure_type}.md`

---

### Phase 3: Anomaly Detection (Future - Phase 5)

**Goal**: KITTY detects obvious failures and alerts human

**Approach**:
- Simple anomaly detection (not full ML)
- Monitor: printer stopped unexpectedly, no extrusion, bed empty
- Trigger: Send notification to human for confirmation
- Human confirms: Yes, stop print / No, false alarm

**Examples**:
- Spaghetti detection: Large blob in image vs. clean model shape
- Bed adhesion failure: Model detached (empty bed, filament pile)
- Complete failure: Printer idle, no progress for 30+ minutes

**Notification Channels**:
- Push notification (mobile)
- MQTT message to UI
- Email/SMS for critical failures

---

### Phase 4: Autonomous Failure Detection (Future - Phase 6+)

**Goal**: KITTY autonomously detects failures and stops prints

**Requirements**:
- 500+ labeled training images per failure type
- Computer vision model trained on dataset
- High confidence threshold (≥95%) before auto-stop
- Human review queue for low-confidence detections

**ML Approach**:
- Image classification model (ResNet, EfficientNet, or YOLO)
- Multi-class: normal, first_layer_fail, warping, spaghetti, stringing, etc.
- Real-time inference on snapshot (every 1-5 min)
- Action: Pause print + notify human if failure detected

**Safety**:
- Never auto-stop without high confidence
- Always notify human when pausing
- Human can override and resume
- Log all auto-stop decisions for review

---

## Architecture

### Camera Feed Integration

```
┌─────────────────────────────────────────────────────┐
│  Print Job Lifecycle                                │
│                                                      │
│  1. Start Print                                     │
│     ├─> Capture initial snapshot                   │
│     ├─> Store snapshot URL in print_outcomes       │
│     └─> Start periodic snapshot schedule           │
│                                                      │
│  2. During Print (every 5 min)                     │
│     ├─> Capture snapshot                           │
│     ├─> Store in MinIO: /prints/{job_id}/{ts}.jpg │
│     ├─> [Future] Run anomaly detection            │
│     └─> [Future] Alert if anomaly detected        │
│                                                      │
│  3. Print Complete                                  │
│     ├─> Capture final snapshot                     │
│     ├─> Stop periodic snapshots                    │
│     └─> Trigger human feedback workflow            │
│                                                      │
│  4. Human Feedback (MQTT notification)             │
│     ├─> KITTY publishes: "How did print go?"      │
│     ├─> UI shows: Snapshot gallery + feedback form│
│     ├─> Human submits: Pass/Fail + defects + scores│
│     └─> Store outcome with visual evidence        │
└─────────────────────────────────────────────────────┘
```

### Data Model Extensions

**PrintOutcome** (extended):
```python
class PrintOutcome(Base):
    # ... existing fields ...

    # Visual Evidence (Phase 1)
    initial_snapshot_url: Optional[str]  # First layer snapshot
    final_snapshot_url: Optional[str]    # Completed print
    snapshot_urls: List[str]              # JSONB: All periodic snapshots
    video_url: Optional[str]              # Full timelapse (optional)

    # Human Feedback (Phase 1)
    human_reviewed: bool = False
    review_requested_at: Optional[datetime]
    reviewed_at: Optional[datetime]
    reviewed_by: Optional[str]

    # Visual Characteristics (Phase 2+)
    visual_defects: List[str]             # JSONB: Detected visual issues
    anomaly_detected: bool = False
    anomaly_confidence: Optional[float]   # 0-1 confidence score
    auto_stopped: bool = False            # Did KITTY auto-stop?
```

### Snapshot Capture Service

**New Component**: `services/fabrication/src/fabrication/monitoring/camera_capture.py`

```python
class CameraCapture:
    """Capture snapshots from printer cameras."""

    async def capture_snapshot(
        self,
        printer_id: str,
        job_id: str,
        milestone: str  # "start", "first_layer", "progress", "complete"
    ) -> str:
        """Capture snapshot and return MinIO URL."""

        if printer_id == "bamboo_h2d":
            # Bamboo Labs: Use MQTT to request snapshot
            snapshot_data = await self._capture_bamboo_snapshot()
        elif printer_id in ["snapmaker_artisan", "elegoo_giga"]:
            # Raspberry Pi: HTTP request to camera endpoint
            snapshot_data = await self._capture_pi_snapshot(printer_id)

        # Store in MinIO
        object_name = f"prints/{job_id}/{milestone}_{timestamp}.jpg"
        minio_url = await self._upload_to_minio(object_name, snapshot_data)

        return minio_url

    async def start_periodic_capture(
        self,
        printer_id: str,
        job_id: str,
        interval_minutes: int = 5
    ):
        """Start background task for periodic snapshots."""
        # Schedule periodic snapshots
        # Store URLs in Redis or database
```

### Human Feedback Workflow

**MQTT Topics**:
```
kitty/fabrication/print/{job_id}/completed
kitty/fabrication/print/{job_id}/review_request
kitty/fabrication/print/{job_id}/review_response
```

**UI Workflow**:
1. Print completes → MQTT message published
2. UI receives notification: "Print {job_id} completed - Review needed"
3. UI displays:
   - Snapshot gallery (initial, progress, final)
   - Video player (if available)
   - Feedback form:
     - Pass/Fail radio buttons
     - If Fail: Checklist of defect types (multi-select)
     - Quality scores: Layer consistency (1-10), Surface finish (1-10)
     - Notes (optional text field)
4. Human submits → API call to POST /api/fabrication/outcome
5. Outcome stored with visual evidence links

**CLI Workflow** (alternative):
```bash
# KITTY notification
kitty-cli fabrication review-needed

# Shows:
# Print Job: abc123
# Printer: Bamboo H2D
# Material: PLA Black eSUN
# Duration: 4h 23m
# Snapshots: [View in browser]
#
# How did it go? (pass/fail): fail
# Defects (comma-separated): warping, first_layer_adhesion
# Layer consistency (1-10): 6
# Surface finish (1-10): 5
# Notes: Bed not level, corners lifted

# Submit feedback
kitty-cli fabrication review abc123 --result fail --defects warping,first_layer_adhesion --quality 6,5 --notes "Bed not level"
```

---

## Implementation Plan

### Task 2.1: PrintOutcomeTracker with Visual Evidence (Now)

**Changes to PrintOutcomeTracker**:
1. Add visual evidence fields to PrintOutcome model
2. Integrate with camera capture service
3. Store snapshot URLs with outcomes
4. Support human feedback workflow
5. API endpoint: POST /api/fabrication/outcome (with snapshots)

**Deliverables**:
- Extended PrintOutcome model
- CameraCapture service (basic implementation)
- Snapshot storage in MinIO
- Human feedback API
- Unit tests

**Does NOT include** (future phases):
- Automated failure detection
- Real-time anomaly detection
- ML model training
- Auto-stop functionality

---

### Task 2.3: Camera Integration (Week 3-4)

**Bamboo Labs**:
- MQTT snapshot request: `device/{serial}/request` with `command: "pushall"`
- Snapshot URL from MQTT: `device/{serial}/report` → `ipcam.img`
- Store in MinIO, link to print outcome

**Raspberry Pi Camera** (Snapmaker, Elegoo):
- HTTP endpoint: `http://{pi_ip}:8080/snapshot.jpg` (via motion or custom service)
- Periodic snapshots via scheduled task
- Store in MinIO with timestamps

**Scheduled Snapshots**:
- First layer: 5 minutes after start (critical for failure detection)
- Progress: Every 5 minutes during print
- Completion: Immediately when print ends
- Store all in: `minio://prints/{job_id}/snapshots/`

---

### Task 2.2: Failure Research Goals (Week 3-4)

**Autonomous Research**:
KITTY generates goals to research each failure type:

```python
# Example autonomous goal
Goal(
    goal_type=GoalType.research,
    description="Research visual characteristics of 3D print spaghetti failures",
    rationale="Need to understand how spaghetti failures appear in camera images for future computer vision detection",
    estimated_budget=Decimal("1.50"),  # Perplexity search
)
```

**Research Output** (KB articles):
- `knowledge/fabrication/failure_detection/spaghetti.md`
- `knowledge/fabrication/failure_detection/warping.md`
- `knowledge/fabrication/failure_detection/first_layer_adhesion.md`
- etc.

**Content**:
- Visual characteristics description
- Key indicators (e.g., "Loose filament strands", "Filament pile on bed")
- Reference images (from Perplexity results)
- Detection strategies for future CV implementation

---

## Future: Computer Vision Model

### Training Dataset Structure

```
training_data/
├── first_layer_adhesion_fail/
│   ├── fail_001.jpg (with metadata.json: printer, material, settings)
│   ├── fail_002.jpg
│   └── ...
├── warping/
│   ├── warp_001.jpg
│   └── ...
├── spaghetti/
│   ├── spaghetti_001.jpg
│   └── ...
├── normal/
│   ├── normal_001.jpg
│   └── ...
└── metadata.json (dataset info, label counts, statistics)
```

### Model Training (Phase 5+)

**Requirements**:
- 500+ images per failure type
- Balanced dataset (equal normal vs. failure images)
- Multiple angles, lighting conditions, materials

**Model Architecture** (suggestions):
- EfficientNet-B0 (lightweight, fast inference)
- ResNet-50 (proven for image classification)
- YOLO (if need bounding boxes for defect location)

**Training Pipeline**:
1. Export labeled images from MinIO
2. Train model offline (GPU required)
3. Export model (ONNX or TensorFlow Lite)
4. Deploy to fabrication service
5. Real-time inference on snapshots

**Confidence Thresholds**:
- High confidence (≥95%): Auto-stop print + notify
- Medium confidence (80-94%): Notify human, don't stop
- Low confidence (<80%): Log only, no action

---

## Benefits of This Approach

1. **Iterative**: Start simple (human feedback), evolve to autonomous
2. **Data-Driven**: Build training dataset from real prints
3. **Safe**: Human-in-loop prevents false positives from causing print failures
4. **Flexible**: Works with multiple camera types
5. **Learning**: KITTY learns from human expertise before autonomy
6. **Traceable**: Visual evidence stored with every outcome
7. **Scalable**: Once CV works, applies to all printers

---

## Open Questions

1. **Raspberry Pi Camera Setup**:
   - What software is running on Pi? (motion, mjpg-streamer, custom?)
   - HTTP endpoint available for snapshots?
   - Resolution and framerate?

2. **Bamboo Labs Camera**:
   - Does current MQTT integration support snapshot requests?
   - Image format and resolution?
   - Timelapse available via API?

3. **Storage**:
   - MinIO already configured? (yes, from existing architecture)
   - Retention policy for snapshots? (keep forever, or delete after 90 days?)
   - Disk space considerations? (estimate: 100 prints/month × 20 snapshots × 500KB = 1GB/month)

4. **Notification System**:
   - Preferred channel for "review needed" alerts? (UI notification, push, email, SMS?)
   - How urgent? (Immediate review, or batch at end of day?)

---

## Next Steps

1. **Implement PrintOutcomeTracker** with visual evidence fields
2. **Create CameraCapture service** (basic snapshot capture)
3. **Test snapshot capture** from each printer type
4. **Implement human feedback API** and UI workflow
5. **Generate failure research goals** for KITTY
6. **Collect 100+ print outcomes** with human feedback (training data)
7. **Phase 2**: Implement anomaly detection (simple rules)
8. **Phase 3**: Train CV model once dataset sufficient

---

**Status**: Design complete, ready to implement PrintOutcomeTracker with camera integration!
