# Print Intelligence Dashboard - User Guide

## Overview

The **Print Intelligence Dashboard** provides comprehensive analytics, historical tracking, and human-in-loop review capabilities for 3D printing operations. This dashboard enables operators to monitor success rates, analyze failure patterns, review print quality, and build a knowledge base for future print intelligence and automation.

**Status**: ✅ **Production Ready** (P2 #12 Implementation Complete)

**Access**: http://localhost:4173/?view=intelligence

---

## Features

### 1. Real-Time Statistics Overview

**Statistics Cards** display key performance metrics:
- **Total Prints**: Count of all recorded print outcomes
- **Success Rate**: Percentage of successful prints (success/total)
- **Avg Quality Score**: Mean quality score across all prints (0-100 scale)
- **Avg Duration**: Average print time in hours
- **Total Cost**: Cumulative material costs across all prints
- **Pending Review**: Count of prints awaiting human feedback

### 2. Failure Reason Breakdown

Visual bar chart showing distribution of failure types:
- **First Layer Adhesion**: Bed adhesion issues
- **Warping**: Part warping during printing
- **Stringing**: Excessive stringing between features
- **Spaghetti**: Complete print failure (spaghetti detection)
- **Nozzle Clog**: Clogged nozzle causing extrusion issues
- **Filament Runout**: Material exhaustion mid-print
- **Layer Shift**: Layer misalignment
- **Overheating**: Thermal management failures
- **Support Failure**: Support structure collapse
- **User Cancelled**: Manual print cancellation
- **Power Failure**: Power loss mid-print
- **Other**: Miscellaneous failures

Each bar shows:
- Failure type label
- Count of occurrences
- Percentage of total failures

### 3. Advanced Filtering

Filter print outcomes by multiple criteria:
- **Printer**: Filter by printer_id (e.g., "bamboo_h2d", "elegoo_giga")
- **Material**: Filter by material_id (e.g., "pla_black_esun", "petg_orange_prusa")
- **Status**: Filter by success/failure
  - All Outcomes
  - Successful Only
  - Failed Only
- **Pending Review Only**: Toggle to show only unreviewed prints

**Dynamic Filter Updates**:
- Statistics recalculate based on active filters
- Failure breakdown updates for filtered subset
- Dropdown options populate from available data

### 4. Outcome History Table

Comprehensive table of all print outcomes:

| Column | Description |
|--------|-------------|
| **Job ID** | Unique print job identifier |
| **Printer** | Printer used for the job |
| **Material** | Material used (links to inventory) |
| **Status** | Success or failure with reason badge |
| **Quality** | Quality score (0-100) with color coding |
| **Duration** | Actual print time in hours |
| **Cost** | Material cost in USD |
| **Completed** | Completion timestamp |
| **Review** | Human review status (Reviewed/Pending) |
| **Actions** | View details + Review button |

**Visual Indicators**:
- Failed rows: Light red background
- Unreviewed rows: Light yellow background
- Quality scores color-coded:
  - 🟢 Excellent: 80-100 (green)
  - 🔵 Good: 60-79 (blue)
  - 🟡 Fair: 40-59 (yellow)
  - 🔴 Poor: 0-39 (red)

### 5. Detailed Outcome View

Modal showing complete print outcome details:

**Job Information**:
- Job ID, Printer, Material
- Started/Completed timestamps
- Duration in hours

**Outcome Summary**:
- Success/Failure status
- Quality score with color coding
- Failure reason (if applicable)
- Cost and material usage

**Print Settings**:
- JSON display of all print parameters
- Temperature, speed, layer height, infill, etc.

**Quality Metrics**:
- Layer consistency scores
- Surface finish ratings
- Human notes and observations

**Visual Evidence**:
- First layer snapshot
- Final result snapshot
- Progress snapshots (captured during print)
- Timelapse video (if available)

**Review Information**:
- Reviewer name
- Review timestamp
- Review notes

### 6. Human Feedback Interface

Interactive modal for reviewing print outcomes:

**Review Form Fields**:
- **Reviewer Name** (required): Operator ID
- **Quality Score** (0-100): Overall print quality
  - 0 = Complete failure
  - 50 = Usable but flawed
  - 80 = Good quality
  - 100 = Perfect print
- **Failure Reason** (optional): Select from 12 failure types
- **Notes** (optional): Free-form observations

**Workflow**:
1. Click "Review" button on pending outcome
2. Fill out review form with quality assessment
3. Submit review to update outcome record
4. Outcome marked as "Reviewed" with timestamp

---

## API Integration

The dashboard consumes the following fabrication service endpoints:

### GET /api/fabrication/outcomes/statistics
Get aggregate statistics for print outcomes.

**Query Parameters**:
- `printer_id` (optional): Filter stats by printer
- `material_id` (optional): Filter stats by material

**Response**:
```json
{
  "total_outcomes": 150,
  "success_rate": 0.867,
  "avg_quality_score": 82.5,
  "avg_duration_hours": 3.2,
  "total_cost_usd": 345.67
}
```

### GET /api/fabrication/outcomes
List print outcomes with filters.

**Query Parameters**:
- `printer_id` (optional): Filter by printer
- `material_id` (optional): Filter by material
- `success` (optional): true/false
- `limit` (optional): Max results (default: 100)
- `offset` (optional): Pagination offset

**Response**: Array of `PrintOutcomeResponse` objects

### GET /api/fabrication/outcomes/{job_id}
Get single outcome by job ID.

**Response**:
```json
{
  "id": "uuid-here",
  "job_id": "print_20251116_001",
  "printer_id": "bamboo_h2d",
  "material_id": "pla_black_esun",
  "success": true,
  "failure_reason": null,
  "quality_score": 85.0,
  "actual_duration_hours": 2.5,
  "actual_cost_usd": 1.25,
  "material_used_grams": 62.5,
  "print_settings": {...},
  "quality_metrics": {...},
  "started_at": "2025-11-16T14:00:00Z",
  "completed_at": "2025-11-16T16:30:00Z",
  "measured_at": "2025-11-16T16:35:00Z",
  "initial_snapshot_url": "s3://snapshots/first_layer.jpg",
  "final_snapshot_url": "s3://snapshots/final.jpg",
  "snapshot_urls": ["s3://snapshots/progress_1.jpg", ...],
  "video_url": "s3://snapshots/timelapse.mp4",
  "human_reviewed": true,
  "review_requested_at": "2025-11-16T16:30:00Z",
  "reviewed_at": "2025-11-16T17:00:00Z",
  "reviewed_by": "operator_1",
  "goal_id": null
}
```

### PATCH /api/fabrication/outcomes/{job_id}/review
Update outcome with human review.

**Request Body**:
```json
{
  "reviewed_by": "operator_1",
  "quality_score": 85.0,
  "failure_reason": null,
  "notes": "Excellent first layer adhesion, minor stringing on overhangs"
}
```

**Response**: Updated `PrintOutcomeResponse` object

---

## Usage Workflows

### Workflow 1: Review Recent Print

1. Navigate to Print Intelligence dashboard
2. Locate print in outcome history table
3. Click **"Review"** button
4. Fill out review form:
   - Name: "operator_1"
   - Quality Score: 85 (good quality with minor issues)
   - Failure Reason: None (successful)
   - Notes: "Minor stringing on overhangs, otherwise excellent"
5. Click **"Submit Review"**
6. Outcome marked as reviewed with quality score

### Workflow 2: Analyze Failure Patterns

1. Set **Status filter** to "Failed Only"
2. Review **Failure Reason Breakdown** chart
3. Identify most common failure (e.g., "First Layer Adhesion: 12 occurrences, 45%")
4. Click on failed prints in table
5. View **Visual Evidence** (snapshots) to understand failure modes
6. Document patterns in review notes

### Workflow 3: Track Success Rate by Material

1. Set **Material filter** to specific material (e.g., "pla_black_esun")
2. Review **Success Rate** statistic
3. Compare with other materials
4. Identify materials with lower success rates
5. Plan process improvements or material changes

### Workflow 4: Monitor Pending Reviews

1. Toggle **"Pending Review Only"** checkbox
2. Review list of unreviewed prints
3. Click **"View"** to see outcome details and snapshots
4. Click **"Review This Print"** button in detail modal
5. Submit reviews systematically
6. Track progress via "Pending Review" stat card

### Workflow 5: Investigate Print Quality Trends

1. Filter by specific printer (e.g., "bamboo_h2d")
2. Note **Avg Quality Score** statistic
3. Review recent prints in history table
4. Look for quality score trends (improving/declining)
5. Identify correlation with materials, settings, or environmental factors

---

## Architecture

### Frontend (services/ui/src/pages/PrintIntelligence.tsx)
- **React Component**: Functional component with hooks
- **State Management**: Local useState for outcomes, statistics, filters, modals
- **API Client**: Fetch API with async/await
- **Styling**: CSS modules (PrintIntelligence.css)
- **Modals**: Detail view modal + Review form modal
- **Real-time Updates**: Data reloads after review submission

### Backend (services/fabrication/src/fabrication/)
- **API Layer**: FastAPI endpoints in `app.py` (lines 957-1195)
- **Business Logic**: `monitoring/outcome_tracker.py`
- **Database Models**: `common/db/models.py` (PrintOutcome model)
- **ORM**: SQLAlchemy with PostgreSQL

### Database Schema

**print_outcomes** table:
```sql
CREATE TABLE print_outcomes (
  id VARCHAR(100) PRIMARY KEY,
  job_id VARCHAR(100) UNIQUE NOT NULL,
  goal_id VARCHAR(100) REFERENCES goals(id),
  printer_id VARCHAR(100) NOT NULL,
  material_id VARCHAR(100) REFERENCES materials(id),

  -- Outcome
  success BOOLEAN NOT NULL,
  failure_reason VARCHAR(50),  -- FailureReason enum
  quality_score NUMERIC(5,2) NOT NULL,

  -- Actuals
  actual_duration_hours NUMERIC(6,2) NOT NULL,
  actual_cost_usd NUMERIC(10,2) NOT NULL,
  material_used_grams NUMERIC(10,2) NOT NULL,

  -- Settings & Metrics
  print_settings JSONB NOT NULL,
  quality_metrics JSONB DEFAULT '{}',

  -- Timestamps
  started_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP NOT NULL,
  measured_at TIMESTAMP DEFAULT NOW(),

  -- Visual Evidence
  initial_snapshot_url VARCHAR(500),
  final_snapshot_url VARCHAR(500),
  snapshot_urls JSONB DEFAULT '[]',
  video_url VARCHAR(500),

  -- Human Review
  human_reviewed BOOLEAN DEFAULT FALSE,
  review_requested_at TIMESTAMP,
  reviewed_at TIMESTAMP,
  reviewed_by VARCHAR(100),

  -- Future: Autonomous Detection
  visual_defects JSONB DEFAULT '[]',
  anomaly_detected BOOLEAN DEFAULT FALSE,
  anomaly_confidence NUMERIC(3,2),
  auto_stopped BOOLEAN DEFAULT FALSE
);
```

---

## Configuration

### Feature Flags

**Print Outcome Tracking** (must be enabled):
```bash
ENABLE_PRINT_OUTCOME_TRACKING=true
```

**Human Feedback Requests** (MQTT notifications):
```bash
ENABLE_HUMAN_FEEDBACK_REQUESTS=true  # Auto-request reviews via MQTT
HUMAN_FEEDBACK_AUTO_REQUEST=true     # Auto-request after every print
```

### Failure Reason Enum

Complete list of failure classifications:
```python
class FailureReason(enum.Enum):
    first_layer_adhesion = "first_layer_adhesion"
    warping = "warping"
    stringing = "stringing"
    spaghetti = "spaghetti"
    nozzle_clog = "nozzle_clog"
    filament_runout = "filament_runout"
    layer_shift = "layer_shift"
    overheating = "overheating"
    support_failure = "support_failure"
    user_cancelled = "user_cancelled"
    power_failure = "power_failure"
    other = "other"
```

---

## Roadmap

### Phase 4 Enhancements (Current)
- ✅ Outcome history tracking with filtering
- ✅ Statistics dashboard (success rate, quality, cost)
- ✅ Failure reason breakdown visualization
- ✅ Detail view with visual evidence (snapshots)
- ✅ Human feedback/review interface
- ✅ Quality score color coding

### Phase 5 Enhancements (Planned)
- [ ] **Quality Score Trends**: Line charts showing quality over time
- [ ] **Success Rate by Material**: Comparative bar charts
- [ ] **Cost Analytics**: Material cost per print, trends
- [ ] **Print Intelligence Predictions**: ML model for success prediction
- [ ] **Recommendations Engine**: Setting suggestions based on historical data
- [ ] **Autonomous Failure Detection**: CV-based anomaly detection (Phase 4+ spec)
- [ ] **Export to CSV**: Download outcome reports
- [ ] **Advanced Analytics**: Correlation analysis, A/B testing

---

## Testing

### Manual Test Checklist

1. **Load Dashboard**:
   - Navigate to `http://localhost:4173/?view=intelligence`
   - Verify statistics cards load correctly
   - Check failure breakdown displays if failures exist

2. **Filter Outcomes**:
   - Test printer filter
   - Test material filter
   - Test status filter (All/Successful/Failed)
   - Toggle "Pending Review Only" checkbox

3. **View Outcome Details**:
   - Click "View" button on an outcome
   - Verify all details display correctly
   - Check snapshot images load (if URLs present)
   - Verify video player works (if video URL present)

4. **Submit Review**:
   - Click "Review" button on unreviewed outcome
   - Fill form with valid data
   - Submit review
   - Verify outcome marked as reviewed
   - Check statistics update

5. **Visual Indicators**:
   - Verify failed rows have red background
   - Check unreviewed rows have yellow background
   - Confirm quality badges show correct colors

### API Testing

```bash
# Get statistics
curl http://localhost:8080/api/fabrication/outcomes/statistics | jq

# List all outcomes
curl http://localhost:8080/api/fabrication/outcomes | jq

# Filter by success status
curl "http://localhost:8080/api/fabrication/outcomes?success=false" | jq

# Get specific outcome
curl http://localhost:8080/api/fabrication/outcomes/print_20251116_001 | jq

# Submit review
curl -X PATCH http://localhost:8080/api/fabrication/outcomes/print_20251116_001/review \
  -H "Content-Type: application/json" \
  -d '{
    "reviewed_by": "operator_1",
    "quality_score": 85.0,
    "failure_reason": null,
    "notes": "Excellent print quality"
  }' | jq
```

---

## Troubleshooting

### Issue: Dashboard shows "Loading print intelligence data..." indefinitely

**Cause**: Backend service not running or API endpoint unreachable

**Solution**:
1. Check if fabrication service is running:
   ```bash
   docker compose -f infra/compose/docker-compose.yml ps fabrication
   ```
2. Verify API endpoint:
   ```bash
   curl http://localhost:8080/api/fabrication/outcomes/statistics
   ```
3. Check service logs:
   ```bash
   docker compose -f infra/compose/docker-compose.yml logs fabrication
   ```

### Issue: "Failed to load data" error

**Cause**: Database not initialized or print_outcomes table missing

**Solution**:
1. Run database migrations:
   ```bash
   alembic -c services/common/alembic.ini upgrade head
   ```
2. Verify table exists:
   ```sql
   \d print_outcomes
   ```

### Issue: Review submission fails with 400 error

**Cause**: Invalid failure_reason value or missing required fields

**Solution**:
1. Use valid FailureReason enum values (see Configuration section)
2. Ensure `reviewed_by` field is populated
3. Check browser console for detailed error message

### Issue: Snapshots don't load (broken image icons)

**Cause**: MinIO URLs incorrect or MinIO service not accessible

**Solution**:
1. Verify MinIO service is running:
   ```bash
   docker compose -f infra/compose/docker-compose.yml ps minio
   ```
2. Check if ENABLE_MINIO_SNAPSHOT_UPLOAD feature flag is enabled
3. Verify snapshot URLs in database match MinIO endpoint
4. Test snapshot URL directly in browser

### Issue: No failure breakdown chart shows

**Cause**: No failed prints in database

**Solution**:
1. Filter shows "0 records" → No failures recorded yet
2. Record some test failures with failure_reason set
3. Chart will appear once failures exist

---

## Integration with Other Features

### Material Inventory Dashboard
- Outcome costs link to material inventory
- Material usage tracked for inventory deduction
- Cost per print calculated from material_id

### I/O Control Dashboard
- Feature flags control outcome tracking
- Camera capture integration for visual evidence
- MQTT broker for human feedback requests

### Autonomous Learning (Phase 3)
- Outcomes feed into goal effectiveness tracking
- Success rates inform autonomous project planning
- Quality metrics train future intelligence models

---

## Related Documentation

- **Phase 4 Fabrication Intelligence**: `docs/PHASE4_PROGRESS_SUMMARY.md`
- **Print Outcome Tracker Backend**: `services/fabrication/src/fabrication/monitoring/outcome_tracker.py`
- **API Contracts**: `services/fabrication/src/fabrication/app.py` (lines 957-1195)
- **Database Models**: `services/common/src/common/db/models.py` (lines 663-720)
- **Material Inventory Dashboard**: `docs/MATERIAL_INVENTORY_DASHBOARD.md`
- **Camera Capture Design**: `docs/CV_PRINT_MONITORING_DESIGN.md`

---

## Support

For questions or issues:
1. Check logs: `docker compose logs fabrication`
2. Review API docs: `http://localhost:8080/docs`
3. File issue: https://github.com/Jmi2020/KITT/issues
