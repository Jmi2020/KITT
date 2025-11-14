# Phase 4: Fabrication Intelligence - Task Breakdown

## Task Status Legend
- ⏳ Not Started
- 🚧 In Progress
- ✅ Complete
- ⏸️ Blocked

---

## Week 1-2: Foundation

### Task 1.1: Database Schema & Migration ⏳
**Owner**: TBD
**Estimated**: 1-2 days
**Priority**: P0 (Blocker for all other tasks)

**Subtasks**:
- [ ] 1.1.1 Create Alembic migration file
- [ ] 1.1.2 Add `Material` model to `common.db.models`
- [ ] 1.1.3 Add `InventoryItem` model to `common.db.models`
- [ ] 1.1.4 Add `PrintOutcome` model to `common.db.models`
- [ ] 1.1.5 Add `QueuedPrint` model to `common.db.models`
- [ ] 1.1.6 Add `procurement` to `GoalType` enum
- [ ] 1.1.7 Add `print_outcomes` relationship to `Goal` model
- [ ] 1.1.8 Test migration up: `alembic upgrade head`
- [ ] 1.1.9 Test migration down: `alembic downgrade -1`
- [ ] 1.1.10 Verify foreign keys and indexes

**Acceptance Criteria**:
- Migration runs without errors on clean database
- All tables created with correct schema
- Foreign keys enforce referential integrity
- Indexes on: `material_id`, `printer_id`, `job_id`, `status`, `queued_at`
- Rollback works correctly

**Files**:
- `services/common/alembic/versions/XXX_add_fabrication_intelligence.py`
- `services/common/src/common/db/models.py`

**Blocked By**: None
**Blocks**: All subsequent tasks

---

### Task 1.2: Material Catalog & Seed Data ⏳
**Owner**: TBD
**Estimated**: 1 day
**Priority**: P0

**Subtasks**:
- [ ] 1.2.1 Research common filament properties (PLA, PETG, ABS, TPU, ASA, Nylon)
- [ ] 1.2.2 Create seed data JSON with 10+ materials
- [ ] 1.2.3 Include: material_type, color, manufacturer, cost_per_kg, density, temp ranges
- [ ] 1.2.4 Add sustainability scores (where available)
- [ ] 1.2.5 Create seed script: `ops/scripts/seed-materials.py`
- [ ] 1.2.6 Test seed script on dev database
- [ ] 1.2.7 Document how to add new materials

**Acceptance Criteria**:
- Seed data includes 10+ materials with accurate properties
- Density values verified (e.g., PLA ~1.24 g/cm³, PETG ~1.27 g/cm³)
- Cost values representative of current market (2025)
- Temperature ranges match manufacturer specs
- Seed script idempotent (can run multiple times safely)

**Files**:
- `data/seed_materials.json`
- `ops/scripts/seed-materials.py`
- `docs/materials-database-guide.md`

**Blocked By**: Task 1.1
**Blocks**: Task 1.3

---

### Task 1.3: MaterialInventory Class ⏳
**Owner**: TBD
**Estimated**: 2 days
**Priority**: P0

**Subtasks**:
- [ ] 1.3.1 Create `material_inventory.py` module
- [ ] 1.3.2 Implement `get_material(material_id)` method
- [ ] 1.3.3 Implement `get_inventory(spool_id)` method
- [ ] 1.3.4 Implement `list_inventory(filters)` method
- [ ] 1.3.5 Implement `calculate_usage(stl_volume, infill, material)` method
- [ ] 1.3.6 Implement `deduct_usage(spool_id, grams)` method
- [ ] 1.3.7 Implement `check_low_inventory()` method
- [ ] 1.3.8 Implement `estimate_print_cost(material, grams)` method
- [ ] 1.3.9 Add type hints and docstrings
- [ ] 1.3.10 Write unit tests (target: 90%+ coverage)

**Acceptance Criteria**:
- All methods functional with correct calculations
- Usage calculation formula: `volume_cm3 * infill% * density * 1.05 (waste)`
- Supports estimation adds 15% for supports if enabled
- Cost calculation: `grams / 1000 * cost_per_kg`
- Low inventory detection returns items <100g (configurable)
- Unit tests pass with >90% coverage
- Handles edge cases (missing materials, zero inventory, negative deductions)

**Files**:
- `services/fabrication/src/fabrication/intelligence/material_inventory.py`
- `tests/unit/test_material_inventory.py`

**Blocked By**: Task 1.1, Task 1.2
**Blocks**: Task 1.4

---

### Task 1.4: Material Inventory API Endpoints ⏳
**Owner**: TBD
**Estimated**: 1 day
**Priority**: P1

**Subtasks**:
- [ ] 1.4.1 Add `GET /api/fabrication/materials` endpoint (list catalog)
- [ ] 1.4.2 Add `GET /api/fabrication/materials/{material_id}` endpoint
- [ ] 1.4.3 Add `GET /api/fabrication/inventory` endpoint (list spools)
- [ ] 1.4.4 Add `GET /api/fabrication/inventory/{spool_id}` endpoint
- [ ] 1.4.5 Add `POST /api/fabrication/inventory/deduct` endpoint
- [ ] 1.4.6 Add request/response Pydantic models
- [ ] 1.4.7 Add OpenAPI documentation
- [ ] 1.4.8 Test endpoints with curl/httpie

**Acceptance Criteria**:
- All endpoints return correct HTTP status codes
- Request validation works (400 for invalid input)
- Response models match OpenAPI spec
- Swagger docs at `/docs` show new endpoints
- Error handling returns useful messages
- Integration with MaterialInventory class works

**Files**:
- `services/fabrication/src/fabrication/app.py`

**Blocked By**: Task 1.3
**Blocks**: Task 4.1 (CLI)

---

## Week 3-4: Learning

### Task 2.1: PrintOutcomeTracker Class ⏳
**Owner**: TBD
**Estimated**: 2-3 days
**Priority**: P0

**Subtasks**:
- [ ] 2.1.1 Create `print_outcome_tracker.py` module
- [ ] 2.1.2 Define `PrintOutcome` dataclass
- [ ] 2.1.3 Define `PrintSettings` dataclass
- [ ] 2.1.4 Define `QualityMetrics` dataclass
- [ ] 2.1.5 Define `FailureReason` literal type
- [ ] 2.1.6 Implement `capture_outcome(job_id, outcome)` method
- [ ] 2.1.7 Implement `classify_failure(indicators)` method
- [ ] 2.1.8 Implement `calculate_quality_score(metrics)` method
- [ ] 2.1.9 Implement `get_historical_outcomes(filters)` method
- [ ] 2.1.10 Add type hints and docstrings
- [ ] 2.1.11 Write unit tests (target: 90%+ coverage)

**Acceptance Criteria**:
- Outcome capture stores all required fields
- Failure classification handles 12+ failure reasons
- Quality score weighted: layer_consistency (40%), surface_finish (40%), dimensional_accuracy (20%)
- Quality score handles missing metrics gracefully
- Historical queries support filters: material, printer, date range, success/failure
- Unit tests cover all failure reasons and quality calculation edge cases
- Handles database errors gracefully (rollback on failure)

**Files**:
- `services/fabrication/src/fabrication/intelligence/print_outcome_tracker.py`
- `tests/unit/test_print_outcome_tracker.py`

**Blocked By**: Task 1.1
**Blocks**: Task 2.2, Task 2.3

---

### Task 2.2: Print Outcome API Endpoints ⏳
**Owner**: TBD
**Estimated**: 1 day
**Priority**: P1

**Subtasks**:
- [ ] 2.2.1 Add `POST /api/fabrication/outcome` endpoint (report outcome)
- [ ] 2.2.2 Add `GET /api/fabrication/outcomes` endpoint (list with filters)
- [ ] 2.2.3 Add `GET /api/fabrication/outcomes/{job_id}` endpoint
- [ ] 2.2.4 Add request/response Pydantic models
- [ ] 2.2.5 Add OpenAPI documentation
- [ ] 2.2.6 Test endpoints

**Acceptance Criteria**:
- Outcome reporting validates required fields
- List endpoint supports query params: material_id, printer_id, success, date_from, date_to
- Returns outcomes sorted by completed_at DESC
- Error handling for duplicate job_id
- Swagger docs clear and accurate

**Files**:
- `services/fabrication/src/fabrication/app.py`

**Blocked By**: Task 2.1
**Blocks**: Task 4.1 (CLI)

---

### Task 2.3: Printer Monitoring Integration ⏳
**Owner**: TBD
**Estimated**: 2 days
**Priority**: P1

**Subtasks**:
- [ ] 2.3.1 Extend MQTT handler to capture Bamboo H2D print completion
- [ ] 2.3.2 Create job record on print start (capture settings)
- [ ] 2.3.3 Create outcome record on print completion (auto-detect success/failure)
- [ ] 2.3.4 Extract print settings from MQTT state (temps, speed, layer height)
- [ ] 2.3.5 Extend Moonraker client to capture Elegoo Giga completion
- [ ] 2.3.6 Poll for job completion and create outcome
- [ ] 2.3.7 Test with real printers (if available) or mock MQTT messages
- [ ] 2.3.8 Log outcome capture to LOGGER

**Acceptance Criteria**:
- Print completion detected automatically for Bamboo H2D (MQTT)
- Print completion detected automatically for Elegoo Giga (Moonraker polling)
- Success/failure inferred from printer state (state=completed → success, state=failed → failure)
- Print settings extracted and stored with outcome
- Default quality_score=75.0 when no metrics available
- Works without manual outcome reporting (fully automatic)
- Fallback: Manual outcome reporting via API if auto-detect fails

**Files**:
- `services/fabrication/src/fabrication/mqtt/handlers.py`
- `services/fabrication/src/fabrication/klipper/moonraker_client.py`

**Blocked By**: Task 2.1
**Blocks**: Task 2.4

---

### Task 2.4: PrintIntelligence Class ⏳
**Owner**: TBD
**Estimated**: 3 days
**Priority**: P0

**Subtasks**:
- [ ] 2.4.1 Create `print_intelligence.py` module
- [ ] 2.4.2 Define `SuccessAnalysis` dataclass
- [ ] 2.4.3 Define `RiskWarning` dataclass
- [ ] 2.4.4 Implement `analyze_historical_success()` method
- [ ] 2.4.5 Implement `predict_success_probability(job_params)` method
- [ ] 2.4.6 Implement `get_recommendations(material, printer)` method
- [ ] 2.4.7 Implement `identify_high_risk_combinations()` method
- [ ] 2.4.8 Implement `get_optimal_settings(material, printer)` method
- [ ] 2.4.9 Implement `get_intelligence_summary()` method
- [ ] 2.4.10 Add type hints and docstrings
- [ ] 2.4.11 Write unit tests with mock historical data

**Acceptance Criteria**:
- Success analysis calculates rates by material, printer, material+printer
- Prediction requires ≥10 prints per category (configurable)
- Prediction uses weighted average: 70% all-time, 30% recent
- Recommendations actionable and specific (e.g., "Increase bed temp by 5°C")
- High-risk warnings for combinations with <60% success rate
- Optimal settings based on most successful historical prints
- Intelligence summary shows: total prints, success rates, learning status
- Unit tests achieve >90% coverage
- Graceful degradation with insufficient data

**Files**:
- `services/fabrication/src/fabrication/intelligence/print_intelligence.py`
- `tests/unit/test_print_intelligence.py`

**Blocked By**: Task 2.1
**Blocks**: Task 2.5, Task 3.1

---

### Task 2.5: Print Intelligence API Endpoints ⏳
**Owner**: TBD
**Estimated**: 1 day
**Priority**: P1

**Subtasks**:
- [ ] 2.5.1 Add `GET /api/fabrication/intelligence` endpoint (summary)
- [ ] 2.5.2 Add `POST /api/fabrication/intelligence/predict` endpoint
- [ ] 2.5.3 Add `GET /api/fabrication/intelligence/recommendations` endpoint
- [ ] 2.5.4 Add request/response Pydantic models
- [ ] 2.5.5 Add OpenAPI documentation
- [ ] 2.5.6 Test endpoints

**Acceptance Criteria**:
- Intelligence summary returns learning status, success rates, warnings
- Prediction endpoint accepts job params (material, printer, settings)
- Prediction returns probability (0-100%) and confidence level
- Recommendations endpoint accepts material+printer filters
- Returns list of actionable recommendations
- Error handling for invalid parameters

**Files**:
- `services/fabrication/src/fabrication/app.py`

**Blocked By**: Task 2.4
**Blocks**: Task 4.1 (CLI)

---

## Week 5-6: Optimization

### Task 3.1: QueueOptimizer Class ⏳
**Owner**: TBD
**Estimated**: 3 days
**Priority**: P0

**Subtasks**:
- [ ] 3.1.1 Create `queue_optimizer.py` module
- [ ] 3.1.2 Define `PrintJob` dataclass
- [ ] 3.1.3 Define `OptimizedJob` dataclass
- [ ] 3.1.4 Implement `optimize_queue(jobs)` method
- [ ] 3.1.5 Implement `calculate_priority_score(job, current_material)` method
- [ ] 3.1.6 Implement `batch_by_material(jobs)` method
- [ ] 3.1.7 Implement `schedule_for_off_peak(job, current_time)` method
- [ ] 3.1.8 Implement `check_maintenance_due(printer)` method
- [ ] 3.1.9 Implement `estimate_completion_time(queue)` method
- [ ] 3.1.10 Implement `_generate_reasoning(job, context)` method
- [ ] 3.1.11 Add type hints and docstrings
- [ ] 3.1.12 Write unit tests with mock job data

**Acceptance Criteria**:
- Priority score formula: deadline (0-40) + user_priority (0-25) + material_match (0-20) + success_prob (0-10) + inventory (0-5)
- Material batching reduces changes by 40%+ vs. FIFO
- Off-peak scheduling delays jobs ≥8 hours to configured window (22:00-06:00)
- Maintenance check triggers warning when printer hours exceed threshold
- Completion time estimation accurate within ±20%
- Reasoning explains queue order clearly ("Scheduled for off-peak due to 10h duration")
- Unit tests cover edge cases (empty queue, all urgent, no material matches)
- Unit tests achieve >90% coverage

**Files**:
- `services/fabrication/src/fabrication/intelligence/queue_optimizer.py`
- `tests/unit/test_queue_optimizer.py`

**Blocked By**: Task 2.4 (uses success predictions)
**Blocks**: Task 3.2

---

### Task 3.2: Print Queue API Endpoints ⏳
**Owner**: TBD
**Estimated**: 1 day
**Priority**: P1

**Subtasks**:
- [ ] 3.2.1 Add `POST /api/fabrication/queue` endpoint (add job)
- [ ] 3.2.2 Add `GET /api/fabrication/queue` endpoint (view optimized queue)
- [ ] 3.2.3 Add `DELETE /api/fabrication/queue/{job_id}` endpoint (remove job)
- [ ] 3.2.4 Add `PUT /api/fabrication/queue/{job_id}/priority` endpoint (override)
- [ ] 3.2.5 Add request/response Pydantic models
- [ ] 3.2.6 Add OpenAPI documentation
- [ ] 3.2.7 Test endpoints

**Acceptance Criteria**:
- Add job validates required fields (stl_path, material_id, printer_id)
- Add job calculates estimates (duration, material usage, cost) automatically
- View queue returns optimized order with reasoning
- Priority override allows values 1-10 or "urgent" flag
- Remove job updates database and reoptimizes remaining queue
- Error handling for non-existent jobs
- Swagger docs clear

**Files**:
- `services/fabrication/src/fabrication/app.py`

**Blocked By**: Task 3.1
**Blocks**: Task 4.1 (CLI)

---

### Task 3.3: ProcurementGenerator Class ⏳
**Owner**: TBD
**Estimated**: 2 days
**Priority**: P1

**Subtasks**:
- [ ] 3.3.1 Create `procurement_generator.py` module
- [ ] 3.3.2 Implement `check_inventory_levels()` method
- [ ] 3.3.3 Implement `generate_procurement_goal(item)` method
- [ ] 3.3.4 Implement `should_create_goal(item)` method (check for duplicates)
- [ ] 3.3.5 Add goal metadata with material details
- [ ] 3.3.6 Integrate with MaterialInventory class
- [ ] 3.3.7 Add type hints and docstrings
- [ ] 3.3.8 Write unit tests

**Acceptance Criteria**:
- Detects inventory items below threshold (default: 100g)
- Generates goal with type `GoalType.procurement`
- Goal description includes: material, color, manufacturer, current weight
- Goal rationale explains why procurement needed
- Prevents duplicate goals (checks for existing procurement goals for same material)
- Goal metadata includes: material_id, spool_id, current_weight, manufacturer, cost
- Unit tests verify duplicate prevention
- Unit tests achieve >85% coverage

**Files**:
- `services/fabrication/src/fabrication/intelligence/procurement_generator.py`
- `tests/unit/test_procurement_generator.py`

**Blocked By**: Task 1.3 (MaterialInventory)
**Blocks**: Task 3.4

---

### Task 3.4: Procurement Job Integration ⏳
**Owner**: TBD
**Estimated**: 1 day
**Priority**: P1

**Subtasks**:
- [ ] 3.4.1 Add scheduled job: `check_procurement_needs()` in `jobs.py`
- [ ] 3.4.2 Schedule daily at 9:00 AM (configurable)
- [ ] 3.4.3 Call ProcurementGenerator to check inventory
- [ ] 3.4.4 Log procurement goals created
- [ ] 3.4.5 Test job execution manually
- [ ] 3.4.6 Add job to scheduler initialization

**Acceptance Criteria**:
- Job runs daily at configured time
- Calls procurement generator and logs results
- Creates goals when inventory low
- No errors if inventory sufficient
- Job logged in autonomous job history

**Files**:
- `services/brain/src/brain/autonomous/jobs.py`

**Blocked By**: Task 3.3
**Blocks**: None

---

## Week 7: Integration & Polish

### Task 4.1: CLI Commands ⏳
**Owner**: TBD
**Estimated**: 2-3 days
**Priority**: P1

**Subtasks**:
- [ ] 4.1.1 Create `fabrication.py` module in CLI
- [ ] 4.1.2 Implement `/fabrication inventory` command
- [ ] 4.1.3 Implement `/fabrication queue` command
- [ ] 4.1.4 Implement `/fabrication intelligence` command
- [ ] 4.1.5 Implement `/fabrication predict <job_params>` command
- [ ] 4.1.6 Implement `/fabrication outcome report <job_id>` command
- [ ] 4.1.7 Implement `/fabrication procurement check` command
- [ ] 4.1.8 Add formatted table output (rich library)
- [ ] 4.1.9 Add color coding (green=good, yellow=warning, red=critical)
- [ ] 4.1.10 Update CLI help documentation

**Acceptance Criteria**:
- All commands functional and call correct API endpoints
- Inventory command shows: spool ID, material, weight, status (color-coded)
- Queue command shows: job ID, material, printer, priority, deadline, scheduled start
- Intelligence command shows: success rates, warnings, recommendations
- Predict command shows: probability, confidence, reasoning
- Outcome report command prompts for required fields interactively
- Procurement check command shows low inventory items and actions taken
- Output formatted with tables and colors (rich library)
- Help text clear and comprehensive

**Files**:
- `services/cli/src/cli/fabrication.py`
- `services/cli/src/cli/shell.py` (extend with /fabrication routing)

**Blocked By**: Task 1.4, Task 2.2, Task 2.5, Task 3.2
**Blocks**: None

---

### Task 4.2: Web UI Dashboard ⏳
**Owner**: TBD
**Estimated**: 4-5 days
**Priority**: P2

**Subtasks**:
- [ ] 4.2.1 Create `FabricationIntelligence.tsx` page
- [ ] 4.2.2 Create `MaterialInventory.tsx` component (table with color-coded levels)
- [ ] 4.2.3 Create `PrintQueue.tsx` component (queue with reasoning)
- [ ] 4.2.4 Create `SuccessAnalysis.tsx` component (charts: success rates by material/printer)
- [ ] 4.2.5 Create `FailureAnalysis.tsx` component (pie chart: failure reasons)
- [ ] 4.2.6 Create `CostTracking.tsx` component (total spent, cost per print, cost by material)
- [ ] 4.2.7 Add real-time updates via MQTT subscriptions
- [ ] 4.2.8 Add interactive elements (click spool for history, click job for prediction)
- [ ] 4.2.9 Responsive design for wall terminal
- [ ] 4.2.10 Test on multiple screen sizes

**Acceptance Criteria**:
- Dashboard loads without errors
- Material inventory table shows: spool, material, weight, status (green/yellow/red)
- Print queue shows jobs with priority, deadline, reasoning
- Success analysis charts display correctly (use recharts or similar)
- Failure analysis pie chart shows failure reason distribution
- Cost tracking shows cumulative and per-print costs
- Real-time updates work via MQTT
- Interactive elements functional (tooltips, click for details)
- Responsive layout works on desktop, tablet, wall terminal
- Follows existing UI design system

**Files**:
- `services/ui/src/pages/FabricationIntelligence.tsx`
- `services/ui/src/components/MaterialInventory.tsx`
- `services/ui/src/components/PrintQueue.tsx`
- `services/ui/src/components/SuccessAnalysis.tsx`
- `services/ui/src/components/FailureAnalysis.tsx`
- `services/ui/src/components/CostTracking.tsx`

**Blocked By**: Task 1.4, Task 2.2, Task 2.5, Task 3.2
**Blocks**: None

---

### Task 4.3: Documentation ⏳
**Owner**: TBD
**Estimated**: 2-3 days
**Priority**: P2

**Subtasks**:
- [ ] 4.3.1 Update `KITTY_AUTONOMOUS_OPERATIONS_GUIDE.md` with Phase 4
- [ ] 4.3.2 Create `docs/FABRICATION_INTELLIGENCE_GUIDE.md`
- [ ] 4.3.3 Document material inventory tracking workflow
- [ ] 4.3.4 Document how to interpret success predictions
- [ ] 4.3.5 Document queue optimization logic and reasoning
- [ ] 4.3.6 Document procurement alert workflow
- [ ] 4.3.7 Add troubleshooting section
- [ ] 4.3.8 Add FAQ section
- [ ] 4.3.9 Create seed data guide (how to add materials, inventory)
- [ ] 4.3.10 Review and proofread all documentation

**Acceptance Criteria**:
- Operations guide updated with Phase 4 capabilities
- Fabrication intelligence guide comprehensive (≥2,000 words)
- Workflows explained with diagrams (mermaid or similar)
- CLI commands documented with examples
- API endpoints documented (OpenAPI + guide)
- Troubleshooting covers common issues
- FAQ answers 10+ expected questions
- Seed data guide clear and step-by-step
- All documentation reviewed for accuracy

**Files**:
- `KITTY_AUTONOMOUS_OPERATIONS_GUIDE.md`
- `docs/FABRICATION_INTELLIGENCE_GUIDE.md`
- `docs/materials-database-guide.md`

**Blocked By**: All implementation tasks
**Blocks**: None

---

## Testing Tasks

### Task T.1: Unit Test Suite ⏳
**Owner**: TBD
**Estimated**: Ongoing (parallel with implementation)
**Priority**: P0

**Test Files**:
- [ ] T.1.1 `tests/unit/test_material_inventory.py` (Task 1.3)
- [ ] T.1.2 `tests/unit/test_print_outcome_tracker.py` (Task 2.1)
- [ ] T.1.3 `tests/unit/test_print_intelligence.py` (Task 2.4)
- [ ] T.1.4 `tests/unit/test_queue_optimizer.py` (Task 3.1)
- [ ] T.1.5 `tests/unit/test_procurement_generator.py` (Task 3.3)

**Coverage Targets**:
- Each module: ≥90% line coverage
- Overall Phase 4: ≥85% line coverage

**Test Count Target**: 100-120 test cases

**Blocked By**: Respective implementation tasks
**Blocks**: Task T.2

---

### Task T.2: Integration Test Suite ⏳
**Owner**: TBD
**Estimated**: 2-3 days
**Priority**: P1

**Subtasks**:
- [ ] T.2.1 Create `tests/integration/test_phase4_integration.py`
- [ ] T.2.2 Test full print workflow (queue → deduct material → complete → capture outcome → update intelligence)
- [ ] T.2.3 Test learning cycle (20 outcomes → analyze → predict → validate accuracy)
- [ ] T.2.4 Test queue optimization (10 jobs → optimize → verify batching and deadlines)
- [ ] T.2.5 Test procurement trigger (deplete inventory → check goal generation → verify no duplicates)
- [ ] T.2.6 Test multi-printer coordination (queue for multiple printers → verify independent optimization)
- [ ] T.2.7 Use real SQLite in-memory database
- [ ] T.2.8 Use pytest fixtures for setup

**Acceptance Criteria**:
- All integration tests pass
- Tests use real database (not mocked)
- Tests verify end-to-end workflows
- Tests catch regressions in integration points
- Tests run in <30 seconds
- 10-15 integration test cases

**Files**:
- `tests/integration/test_phase4_integration.py`

**Blocked By**: All implementation tasks (T.1.1-T.1.5)
**Blocks**: Task T.3

---

### Task T.3: Manual Testing & Validation ⏳
**Owner**: TBD
**Estimated**: 2 days
**Priority**: P1

**Test Checklist**:
- [ ] T.3.1 Material inventory tracked across 5+ real prints
- [ ] T.3.2 Usage estimation within ±20% of actual weight
- [ ] T.3.3 Print outcome capture works automatically (MQTT/Moonraker)
- [ ] T.3.4 Success prediction accuracy measured (requires 50+ historical prints)
- [ ] T.3.5 Queue optimizer reduces material changes (measure before/after)
- [ ] T.3.6 Procurement goal generated when inventory low (trigger manually)
- [ ] T.3.7 CLI commands work and display correctly
- [ ] T.3.8 Web UI dashboard loads and updates in real-time
- [ ] T.3.9 No database deadlocks or race conditions under load
- [ ] T.3.10 Performance acceptable (<500ms API response time)

**Acceptance Criteria**:
- All checklist items validated on workstation
- Issues documented and fixed
- Success metrics met (see spec.md)

**Blocked By**: Task T.2
**Blocks**: Release

---

## Documentation Deliverables

### Deliverable D.1: Phase 4 Specification ✅
**Status**: Complete
**File**: `specs/004-FabricationIntelligence/spec.md`

### Deliverable D.2: Implementation Plan ✅
**Status**: Complete
**File**: `specs/004-FabricationIntelligence/plan.md`

### Deliverable D.3: Task Breakdown ✅
**Status**: Complete
**File**: `specs/004-FabricationIntelligence/tasks.md`

### Deliverable D.4: Data Model Documentation ⏳
**Status**: Pending
**File**: `specs/004-FabricationIntelligence/data-model.md`
**Includes**:
- ER diagram (Material, InventoryItem, PrintOutcome, QueuedPrint, Goal)
- Table schemas with field descriptions
- Relationship descriptions
- Query examples

### Deliverable D.5: API Documentation ⏳
**Status**: Pending (auto-generated from OpenAPI)
**File**: Available at `/docs` endpoint after implementation

### Deliverable D.6: User Guide ⏳
**Status**: Pending (Task 4.3)
**File**: `docs/FABRICATION_INTELLIGENCE_GUIDE.md`

---

## Dependency Graph

```
Task 1.1 (Database Schema)
  ├─> Task 1.2 (Material Seed Data)
  │     └─> Task 1.3 (MaterialInventory Class)
  │           ├─> Task 1.4 (Inventory API)
  │           └─> Task 3.3 (ProcurementGenerator)
  │                 └─> Task 3.4 (Procurement Job)
  ├─> Task 2.1 (PrintOutcomeTracker Class)
  │     ├─> Task 2.2 (Outcome API)
  │     ├─> Task 2.3 (Printer Monitoring)
  │     └─> Task 2.4 (PrintIntelligence Class)
  │           ├─> Task 2.5 (Intelligence API)
  │           └─> Task 3.1 (QueueOptimizer Class)
  │                 └─> Task 3.2 (Queue API)
  │
  └─> Task 4.1 (CLI Commands) <──┐
        └─> Task 4.2 (Web UI)      │
              └─> Task 4.3 (Docs)  │
                                  │
  All Implementation Tasks ───────┘
        └─> Task T.1 (Unit Tests)
              └─> Task T.2 (Integration Tests)
                    └─> Task T.3 (Manual Testing)
```

---

## Risk Register

| Risk | Impact | Probability | Mitigation | Owner |
|------|--------|-------------|------------|-------|
| Inaccurate material usage calculation | High | Medium | Calibrate with 10 real prints, add 10% buffer | TBD |
| Low historical print data quality | Medium | High | Auto-capture via MQTT/Moonraker, allow manual entry | TBD |
| Queue optimization conflicts with user priorities | Medium | Medium | Allow priority overrides, show reasoning clearly | TBD |
| Database migration fails on production | High | Low | Test thoroughly on dev, have rollback plan | TBD |
| Printer integration complexity | Medium | Medium | Start with Bamboo H2D (MQTT), Elegoo Giga fallback | TBD |
| Insufficient time for Web UI | Low | Medium | Prioritize CLI, defer UI to post-MVP | TBD |

---

## Success Metrics

### MVP (Minimum Viable Product)
- [ ] Material inventory tracked for 3+ materials
- [ ] Print outcomes captured for 20+ historical prints
- [ ] Success prediction available (accuracy TBD)
- [ ] Basic queue optimization (material batching)
- [ ] Low inventory alerts trigger procurement goals

### Full Success
- [ ] All MVP criteria met
- [ ] Success prediction accuracy ≥70% after 50 prints
- [ ] Material changes reduced by 40%+ with queue optimization
- [ ] CLI commands functional and user-friendly
- [ ] Web UI dashboard provides clear insights
- [ ] Documentation complete and accurate
- [ ] Test coverage ≥90% (unit), ≥80% (integration)

---

## Timeline Estimate

| Week | Focus | Milestones |
|------|-------|------------|
| 1 | Foundation | Task 1.1-1.4 (Database, Material Inventory) |
| 2 | Foundation | Task 1.3-1.4 complete, start Task 2.1 |
| 3 | Learning | Task 2.1-2.3 (Print Outcome Tracking) |
| 4 | Learning | Task 2.4-2.5 (Print Intelligence) |
| 5 | Optimization | Task 3.1-3.2 (Queue Optimizer) |
| 6 | Optimization | Task 3.3-3.4 (Procurement), start Task 4.1 |
| 7 (Optional) | Integration & Polish | Task 4.1-4.3 (CLI, UI, Docs) |

**Target Completion**: 6-7 weeks
**MVP Possible**: 4-5 weeks (skip Web UI, minimal documentation)

---

## Notes

- **Parallel Work**: Tasks 1.3 and 2.1 can run in parallel after Task 1.1 complete
- **CLI Priority**: CLI commands (Task 4.1) are higher priority than Web UI (Task 4.2) for MVP
- **Testing Continuous**: Write unit tests alongside implementation (TDD approach)
- **Feature Flags**: Use environment variables to enable/disable features during development
- **Incremental Deployment**: Deploy completed milestones to staging for early feedback

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-11-14 | Initial task breakdown created | Claude |
| TBD | Task assignments and owner updates | TBD |
| TBD | Timeline adjustments based on progress | TBD |
