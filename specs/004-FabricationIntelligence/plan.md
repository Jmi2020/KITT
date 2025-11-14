# Phase 4: Fabrication Intelligence - Implementation Plan

## Overview

This document outlines the step-by-step implementation plan for Phase 4: Fabrication Intelligence. The plan follows a proven pattern from Phase 3 (Outcome Tracking & Learning) and adapts it for fabrication workflows.

**Estimated Timeline**: 4-6 weeks
**Dependencies**: Phase 3 complete, Multi-Printer Control operational
**Risk Level**: Medium (new domain, hardware integration complexity)

---

## Implementation Strategy

### Principles

1. **Incremental Delivery**: Each component provides value independently
2. **Test-Driven**: Write tests before implementation
3. **Learn from Phase 3**: Reuse outcome tracking patterns
4. **Hardware-Agnostic**: Design for multiple printer types (Bamboo, Elegoo, Snapmaker)
5. **Graceful Degradation**: Work without complete data (e.g., quality scores optional)

### Delivery Order

```
Week 1-2: Foundation (Database + Material Inventory)
Week 3-4: Learning (Print Outcomes + Intelligence)
Week 5-6: Optimization (Queue + Procurement)
```

---

## Phase 1: Foundation (Week 1-2)

### Milestone 1.1: Database Schema & Models

**Goal**: Create database tables for materials, inventory, print outcomes, queue

**Tasks**:
1. Create Alembic migration for new tables
2. Add ORM models to `common.db.models`:
   - `Material`
   - `InventoryItem`
   - `PrintOutcome`
   - `QueuedPrint`
3. Add relationships to existing `Goal` model
4. Test migration up/down on dev database

**Files**:
- `services/common/alembic/versions/XXX_add_fabrication_intelligence.py`
- `services/common/src/common/db/models.py` (extend)

**Validation**:
- Migration runs without errors
- All tables created with correct schema
- Foreign keys enforce referential integrity
- Indexes on frequently queried columns

**Estimated Effort**: 1-2 days

---

### Milestone 1.2: Material Inventory System

**Goal**: Track filament materials and spool inventory

**Tasks**:
1. Create `MaterialInventory` class in `services/fabrication/src/fabrication/intelligence/material_inventory.py`
2. Implement methods:
   - `get_material(material_id)` - Retrieve material properties
   - `get_inventory(spool_id)` - Get spool details
   - `calculate_usage(stl_volume, infill, material)` - Estimate grams needed
   - `deduct_usage(spool_id, grams)` - Update inventory after print
   - `check_low_inventory()` - Find spools below threshold
   - `estimate_print_cost(material, grams)` - Calculate cost
3. Add API endpoints to fabrication service:
   - `GET /api/fabrication/inventory` - View all inventory
   - `GET /api/fabrication/inventory/{spool_id}` - Get spool details
   - `POST /api/fabrication/inventory/deduct` - Deduct material usage
   - `GET /api/fabrication/materials` - List material catalog
4. Create seed data for common materials (PLA, PETG, ABS, TPU)
5. Write unit tests for all methods

**Files**:
- `services/fabrication/src/fabrication/intelligence/material_inventory.py` (new)
- `services/fabrication/src/fabrication/app.py` (extend with endpoints)
- `tests/unit/test_material_inventory.py` (new)
- `data/seed_materials.json` (new)

**Material Usage Calculation Formula**:
```python
# Volume from STL (cm³)
stl_volume_cm3 = stl_analyzer.get_volume()

# Adjust for infill percentage (e.g., 20% infill = 0.2)
adjusted_volume = stl_volume_cm3 * (infill_percent / 100.0)

# Add supports estimate (typically 10-20% of model volume)
if supports_enabled:
    adjusted_volume *= 1.15  # 15% support material

# Convert to weight using material density (g/cm³)
material_density = material.density_g_cm3
estimated_grams = adjusted_volume * material_density

# Add 5% waste factor (purge, ooze, failed first layer retry)
final_grams = estimated_grams * 1.05
```

**Validation**:
- Material catalog includes 10+ common filaments
- Usage calculation within ±20% of actual (calibrate with real prints)
- Low inventory detection triggers when <100g remaining
- Cost estimation accurate to ±10%

**Estimated Effort**: 3-4 days

---

## Phase 2: Learning (Week 3-4)

### Milestone 2.1: Print Outcome Tracking

**Goal**: Capture outcomes for every completed print job

**Tasks**:
1. Create `PrintOutcomeTracker` class in `services/fabrication/src/fabrication/intelligence/print_outcome_tracker.py`
2. Implement methods:
   - `capture_outcome(job_id, outcome)` - Store outcome in database
   - `classify_failure(job_id, indicators)` - Determine failure reason
   - `calculate_quality_score(metrics)` - Compute quality 0-100
   - `get_historical_outcomes(filters)` - Query outcomes
3. Add API endpoints:
   - `POST /api/fabrication/outcome` - Report print outcome
   - `GET /api/fabrication/outcomes` - List historical outcomes
   - `GET /api/fabrication/outcomes/{job_id}` - Get specific outcome
4. Integrate with existing printer monitoring:
   - Listen for MQTT completion events (Bamboo H2D)
   - Poll Moonraker for job completion (Elegoo Giga)
   - Create outcome record with default values (success=true if no error)
5. Add CLI command: `kitty-cli fabrication outcome report <job_id>`
6. Write unit tests

**Files**:
- `services/fabrication/src/fabrication/intelligence/print_outcome_tracker.py` (new)
- `services/fabrication/src/fabrication/mqtt/handlers.py` (extend - listen for completion)
- `services/fabrication/src/fabrication/app.py` (extend with endpoints)
- `tests/unit/test_print_outcome_tracker.py` (new)

**Failure Classification Logic**:
```python
FailureReason = Literal[
    "first_layer_adhesion",    # Bed adhesion failure
    "warping",                  # Thermal warping/curling
    "stringing",                # Excessive stringing
    "spaghetti",                # Complete failure (spaghetti)
    "nozzle_clog",              # Nozzle blockage
    "filament_runout",          # Ran out of material
    "layer_shift",              # Layer misalignment
    "overheating",              # Part overheating
    "support_failure",          # Support structure failed
    "user_cancelled",           # User stopped print
    "power_failure",            # Power loss
    "other"                     # Unknown/other reason
]

def classify_failure(indicators: Dict) -> FailureReason:
    """Classify failure reason from indicators."""
    if indicators.get("bed_detach"):
        return "first_layer_adhesion"
    elif indicators.get("thermal_runaway"):
        return "overheating"
    elif indicators.get("filament_sensor_triggered"):
        return "filament_runout"
    elif indicators.get("user_stopped"):
        return "user_cancelled"
    elif indicators.get("spaghetti_detected"):  # From CV monitor
        return "spaghetti"
    else:
        return "other"
```

**Quality Score Calculation**:
```python
def calculate_quality_score(metrics: QualityMetrics) -> float:
    """Calculate overall quality score 0-100."""
    weights = {
        "layer_consistency": 0.4,
        "surface_finish": 0.4,
        "dimensional_accuracy": 0.2,
    }

    score = 0.0
    if metrics.layer_consistency is not None:
        score += metrics.layer_consistency * weights["layer_consistency"]
    if metrics.surface_finish is not None:
        score += metrics.surface_finish * weights["surface_finish"]
    if metrics.dimensional_accuracy is not None:
        score += metrics.dimensional_accuracy * weights["dimensional_accuracy"]
    else:
        # If no dimensional data, redistribute weight
        score = (metrics.layer_consistency * 0.5 + metrics.surface_finish * 0.5)

    return round(min(100.0, max(0.0, score)), 2)
```

**Validation**:
- Outcome captured for 95%+ of completed prints
- Failure classification accurate for common failures
- Quality score calculation handles missing metrics gracefully
- Integration with MQTT/Moonraker captures completion automatically

**Estimated Effort**: 4-5 days

---

### Milestone 2.2: Print Intelligence (Feedback Loop)

**Goal**: Learn from historical outcomes to predict success and recommend settings

**Tasks**:
1. Create `PrintIntelligence` class in `services/fabrication/src/fabrication/intelligence/print_intelligence.py`
2. Implement methods (similar to Phase 3 FeedbackLoop):
   - `analyze_historical_success()` - Calculate success rates by material/printer
   - `predict_success_probability(job_params)` - Predict success 0-100%
   - `get_recommendations(material, printer)` - Generate setting recommendations
   - `identify_high_risk_combinations()` - Find problematic material+printer combos
   - `get_optimal_settings(material, printer)` - Suggest best settings
   - `get_intelligence_summary()` - Overall learning status
3. Add API endpoints:
   - `GET /api/fabrication/intelligence` - Learning summary
   - `POST /api/fabrication/intelligence/predict` - Predict success for job params
   - `GET /api/fabrication/intelligence/recommendations` - Get recommendations
4. Add CLI command: `kitty-cli fabrication intelligence`
5. Write unit tests with mock historical data

**Files**:
- `services/fabrication/src/fabrication/intelligence/print_intelligence.py` (new)
- `services/fabrication/src/fabrication/app.py` (extend with endpoints)
- `tests/unit/test_print_intelligence.py` (new)

**Success Prediction Algorithm**:
```python
def predict_success_probability(self, job_params: PrintJobParams) -> float:
    """Predict success probability 0-100% based on historical data."""

    # Get historical outcomes for this material+printer combination
    outcomes = self.db.query(PrintOutcome).filter(
        PrintOutcome.material_id == job_params.material_id,
        PrintOutcome.printer_id == job_params.printer_id
    ).all()

    if len(outcomes) < self.min_prints_for_learning:
        return 50.0  # Neutral prediction, insufficient data

    # Calculate base success rate
    successful = [o for o in outcomes if o.success]
    base_success_rate = len(successful) / len(outcomes)

    # Adjust for settings similarity (optional, advanced)
    # Compare job_params settings to successful historical settings
    # Boost probability if settings match successful prints

    # Adjust for recent trends (recent 10 prints weighted higher)
    recent_outcomes = sorted(outcomes, key=lambda o: o.completed_at, reverse=True)[:10]
    recent_success_rate = len([o for o in recent_outcomes if o.success]) / len(recent_outcomes)

    # Weighted average: 70% all-time, 30% recent
    predicted_rate = base_success_rate * 0.7 + recent_success_rate * 0.3

    return round(predicted_rate * 100.0, 2)
```

**Recommendation Generation**:
```python
def get_recommendations(self, material_id: str, printer_id: str) -> List[str]:
    """Generate human-readable recommendations."""
    recommendations = []

    # Analyze outcomes for this combination
    outcomes = self._get_filtered_outcomes(material_id, printer_id)

    if len(outcomes) < 10:
        recommendations.append(
            f"Insufficient data for {material_id} on {printer_id} "
            f"({len(outcomes)} prints). Predictions will improve with more data."
        )
        return recommendations

    success_rate = self._calculate_success_rate(outcomes)

    if success_rate >= 0.85:
        recommendations.append(
            f"✅ Excellent success rate ({success_rate:.0%}) for {material_id} "
            f"on {printer_id}. Continue with current settings."
        )
    elif success_rate >= 0.70:
        recommendations.append(
            f"✓ Good success rate ({success_rate:.0%}) for {material_id} on {printer_id}."
        )
    else:
        recommendations.append(
            f"⚠️ Low success rate ({success_rate:.0%}) for {material_id} "
            f"on {printer_id}. Consider alternative printer or settings."
        )

        # Analyze common failures
        failures = [o for o in outcomes if not o.success]
        failure_reasons = [o.failure_reason for o in failures]
        most_common = max(set(failure_reasons), key=failure_reasons.count)

        if most_common == "first_layer_adhesion":
            recommendations.append(
                "🔧 Most common failure: First layer adhesion. "
                "Try increasing bed temperature by 5°C or cleaning bed surface."
            )
        elif most_common == "warping":
            recommendations.append(
                "🔧 Most common failure: Warping. "
                "Try adding brim, increasing bed temp, or reducing cooling fan speed."
            )
        # ... more failure-specific recommendations

    return recommendations
```

**Validation**:
- Success prediction accuracy ≥70% after 50 historical prints per category
- Recommendations actionable and specific
- High-risk combinations identified correctly
- Graceful degradation with insufficient data

**Estimated Effort**: 4-5 days

---

## Phase 3: Optimization (Week 5-6)

### Milestone 3.1: Queue Optimizer

**Goal**: Intelligently order print queue to minimize material changes and meet deadlines

**Tasks**:
1. Create `QueueOptimizer` class in `services/fabrication/src/fabrication/intelligence/queue_optimizer.py`
2. Implement methods:
   - `optimize_queue(jobs)` - Reorder queue for optimal execution
   - `calculate_priority_score(job)` - Compute priority score
   - `batch_by_material(jobs)` - Group by material type
   - `schedule_for_off_peak(job)` - Delay large jobs to off-peak hours
   - `check_maintenance_due(printer)` - Check if maintenance needed
   - `estimate_completion_time(queue)` - Calculate total queue time
3. Add API endpoints:
   - `POST /api/fabrication/queue` - Add job to queue
   - `GET /api/fabrication/queue` - View optimized queue
   - `DELETE /api/fabrication/queue/{job_id}` - Remove job
   - `PUT /api/fabrication/queue/{job_id}/priority` - Override priority
4. Add CLI command: `kitty-cli fabrication queue`
5. Write unit tests with mock job data

**Files**:
- `services/fabrication/src/fabrication/intelligence/queue_optimizer.py` (new)
- `services/fabrication/src/fabrication/app.py` (extend with endpoints)
- `tests/unit/test_queue_optimizer.py` (new)

**Priority Score Algorithm**:
```python
def calculate_priority_score(self, job: PrintJob, current_material: Optional[str]) -> float:
    """Calculate priority score for queue ordering (higher = sooner)."""

    score = 0.0

    # 1. Deadline urgency (0-40 points)
    if job.deadline:
        hours_until_deadline = (job.deadline - datetime.utcnow()).total_seconds() / 3600
        if hours_until_deadline < job.estimated_duration_hours:
            score += 40  # Urgent! Would miss deadline
        elif hours_until_deadline < job.estimated_duration_hours * 2:
            score += 30  # Tight deadline
        elif hours_until_deadline < 48:
            score += 20  # Due within 2 days
        else:
            score += 10  # Future deadline
    else:
        score += 5  # No deadline = low urgency

    # 2. User priority (0-25 points)
    score += job.priority * 2.5  # priority 1-10 → 2.5-25 points

    # 3. Material match bonus (0-20 points)
    if current_material and job.material_id == current_material:
        score += 20  # Same material = no change needed

    # 4. Success probability (0-10 points)
    if job.success_probability:
        score += job.success_probability / 10.0  # 90% success → 9 points

    # 5. Material availability (0-5 points)
    inventory = self.inventory.get_inventory(job.material_id)
    if inventory and inventory.current_weight_grams >= job.estimated_material_grams * 2:
        score += 5  # Plenty of material
    elif inventory and inventory.current_weight_grams >= job.estimated_material_grams:
        score += 2  # Just enough material
    else:
        score -= 10  # Not enough material! Deprioritize

    return round(score, 2)
```

**Queue Optimization Logic**:
```python
def optimize_queue(self, jobs: List[PrintJob]) -> List[OptimizedJob]:
    """Optimize queue order based on multiple factors."""

    optimized = []
    current_material = None
    current_time = datetime.utcnow()

    # Sort by priority score (will recalculate as we go)
    remaining_jobs = sorted(
        jobs,
        key=lambda j: self.calculate_priority_score(j, current_material),
        reverse=True
    )

    while remaining_jobs:
        # Select next job
        next_job = remaining_jobs[0]

        # Check if this job should be delayed to off-peak
        if (next_job.estimated_duration_hours >= 8 and  # Long print
            not self._is_off_peak(current_time) and      # Currently peak hours
            not next_job.deadline or                      # No deadline OR
            (next_job.deadline - current_time).total_seconds() > 24*3600):  # Deadline >24h away

            # Schedule for next off-peak window
            scheduled_start = self._next_off_peak_start(current_time)
        else:
            scheduled_start = current_time

        # Create optimized job
        optimized_job = OptimizedJob(
            job=next_job,
            scheduled_start=scheduled_start,
            priority_score=self.calculate_priority_score(next_job, current_material),
            reasoning=self._generate_reasoning(next_job, current_material, scheduled_start)
        )

        optimized.append(optimized_job)
        remaining_jobs.remove(next_job)

        # Update state for next iteration
        current_material = next_job.material_id
        current_time = scheduled_start + timedelta(hours=next_job.estimated_duration_hours)

        # Recalculate priority scores for remaining jobs (material match changed)
        remaining_jobs.sort(
            key=lambda j: self.calculate_priority_score(j, current_material),
            reverse=True
        )

    return optimized
```

**Validation**:
- Material changes reduced by 40%+ vs. FIFO queue
- Deadline misses reduced vs. no optimization
- Off-peak scheduling works for long prints
- Reasoning explains queue order clearly

**Estimated Effort**: 4-5 days

---

### Milestone 3.2: Procurement Goal Generator

**Goal**: Automatically generate research goals when material inventory is low

**Tasks**:
1. Create `ProcurementGenerator` class in `services/fabrication/src/fabrication/intelligence/procurement_generator.py`
2. Implement methods:
   - `check_inventory_levels()` - Find low inventory items
   - `generate_procurement_goal(item)` - Create autonomous goal
   - `should_create_goal(item)` - Check if goal already exists for this item
3. Integrate with autonomous goal system:
   - Add new `GoalType.procurement` to `common.db.models`
   - Call procurement generator from `weekly_research_cycle` job
4. Add scheduled job: Check inventory daily, generate goals if needed
5. Add CLI command: `kitty-cli fabrication procurement check`
6. Write unit tests

**Files**:
- `services/fabrication/src/fabrication/intelligence/procurement_generator.py` (new)
- `services/brain/src/brain/autonomous/jobs.py` (extend with procurement check)
- `services/common/src/common/db/models.py` (extend GoalType enum)
- `tests/unit/test_procurement_generator.py` (new)

**Procurement Goal Generation**:
```python
def generate_procurement_goal(self, item: InventoryItem) -> Goal:
    """Generate procurement research goal for low inventory item."""

    material = self.db.query(Material).filter_by(id=item.material_id).first()

    goal_id = f"procurement_{item.material_id}_{datetime.utcnow().strftime('%Y%m%d')}"

    description = (
        f"Research {material.material_type.upper()} filament suppliers "
        f"({material.color}, {material.manufacturer}). "
        f"Current inventory: {item.current_weight_grams:.0f}g remaining "
        f"({item.status}). Find best options for price, sustainability, and delivery."
    )

    rationale = (
        f"Material inventory low: {material.material_type} {material.color} "
        f"has only {item.current_weight_grams:.0f}g remaining "
        f"(threshold: {self.low_inventory_threshold}g). "
        f"Proactive procurement research ensures continuous fabrication capability."
    )

    goal = Goal(
        id=goal_id,
        goal_type=GoalType.procurement,
        description=description,
        rationale=rationale,
        estimated_budget=Decimal("1.50"),  # Perplexity search cost
        estimated_duration_hours=2,
        status=GoalStatus.identified,
        created_by="system-autonomous",
        identified_at=datetime.utcnow(),
        metadata={
            "material_id": item.material_id,
            "spool_id": item.id,
            "current_weight_grams": float(item.current_weight_grams),
            "material_type": material.material_type,
            "manufacturer": material.manufacturer,
            "current_cost_per_kg": float(material.cost_per_kg_usd),
        }
    )

    self.db.add(goal)
    self.db.commit()

    return goal
```

**Research Execution** (handled by existing collective agent):
- Perplexity search: "{material_type} filament suppliers 2025 price sustainability"
- Extract: Supplier names, price per kg, sustainability ratings, delivery times, reviews
- Create KB article: `knowledge/materials/procurement/{material_type}_{date}.md`
- Include comparison table and recommendation

**Validation**:
- Low inventory triggers goal generation within 24 hours
- Only one goal per material (check existing before creating)
- Research findings documented in KB
- User can approve/reject procurement (no auto-purchase)

**Estimated Effort**: 3-4 days

---

## Phase 4: Integration & Polish (Week 7, if needed)

### Milestone 4.1: CLI Integration

**Goal**: Add fabrication intelligence commands to CLI

**Tasks**:
1. Extend `services/cli/src/cli/shell.py` with new commands:
   - `/fabrication inventory` - View material inventory
   - `/fabrication queue` - View print queue
   - `/fabrication intelligence` - View learned insights
   - `/fabrication predict <params>` - Predict success probability
   - `/fabrication outcome report <job_id>` - Report print outcome
   - `/fabrication procurement check` - Check for low inventory
2. Add formatted output (tables for inventory, charts for success rates)
3. Add color coding (green=good, yellow=warning, red=critical)
4. Update CLI help documentation

**Files**:
- `services/cli/src/cli/shell.py` (extend)
- `services/cli/src/cli/fabrication.py` (new - fabrication subcommands)

**Estimated Effort**: 2-3 days

---

### Milestone 4.2: Web UI Dashboard

**Goal**: Add fabrication intelligence views to web UI

**Tasks**:
1. Create Fabrication Intelligence page in UI:
   - Material inventory table with color-coded levels
   - Print queue with optimization reasoning
   - Success rate charts (by material, by printer, by material+printer)
   - Failure analysis dashboard (pie chart of failure reasons)
   - Print cost tracking (total spent, cost per print, cost by material)
2. Add real-time updates via MQTT subscriptions
3. Add interactive elements:
   - Click spool to see usage history
   - Click job to see predicted success and reasoning
   - Click material+printer combo to see recommendations
4. Responsive design for wall terminal view

**Files**:
- `services/ui/src/pages/FabricationIntelligence.tsx` (new)
- `services/ui/src/components/MaterialInventory.tsx` (new)
- `services/ui/src/components/PrintQueue.tsx` (new)
- `services/ui/src/components/SuccessAnalysis.tsx` (new)

**Estimated Effort**: 4-5 days

---

### Milestone 4.3: Documentation & Training Data

**Goal**: Document Phase 4 and create initial training data

**Tasks**:
1. Update `KITTY_AUTONOMOUS_OPERATIONS_GUIDE.md` with Phase 4 capabilities
2. Create `docs/FABRICATION_INTELLIGENCE_GUIDE.md` with:
   - How material inventory tracking works
   - How to interpret success predictions
   - How queue optimization works
   - How to respond to procurement alerts
3. Create seed data:
   - 10+ common materials with accurate properties
   - Initial inventory for testing (5 spools)
   - Mock historical print outcomes (20+ prints) for demo
4. Create video walkthrough (optional, if time permits)

**Files**:
- `KITTY_AUTONOMOUS_OPERATIONS_GUIDE.md` (extend)
- `docs/FABRICATION_INTELLIGENCE_GUIDE.md` (new)
- `data/seed_materials.json` (new)
- `data/seed_inventory.json` (new)
- `data/seed_print_outcomes.json` (new)

**Estimated Effort**: 2-3 days

---

## Testing Strategy

### Unit Test Coverage (Target: 90%+)

**Test Files** (all in `tests/unit/`):
1. `test_material_inventory.py` - Material catalog, inventory tracking, usage calculation, cost estimation
2. `test_print_outcome_tracker.py` - Outcome capture, failure classification, quality scoring
3. `test_print_intelligence.py` - Success analysis, prediction, recommendations, risk identification
4. `test_queue_optimizer.py` - Priority scoring, queue optimization, off-peak scheduling, batching
5. `test_procurement_generator.py` - Low inventory detection, goal generation

**Total Expected Tests**: ~100-120 test cases

### Integration Test Coverage

**Test File**: `tests/integration/test_phase4_integration.py`

**Test Scenarios**:
1. **Full Print Workflow**:
   - Queue print job → Deduct material from inventory → Complete print → Capture outcome → Update intelligence
2. **Learning Cycle**:
   - Capture 20 outcomes → Analyze success rates → Generate predictions → Validate accuracy
3. **Queue Optimization**:
   - Add 10 jobs with different materials/deadlines → Optimize queue → Verify material batching and deadline prioritization
4. **Procurement Trigger**:
   - Deplete inventory below threshold → Check for goal generation → Verify goal created → Verify no duplicates
5. **Multi-Printer Coordination**:
   - Queue jobs for multiple printers → Verify independent queue optimization → Check maintenance scheduling

**Total Expected Integration Tests**: ~10-15 test cases

### Manual Testing Checklist

**Pre-Production Testing**:
- [ ] Material inventory tracked across 5+ real prints
- [ ] Usage estimation within ±20% of actual weight
- [ ] Print outcome capture works automatically via MQTT/Moonraker
- [ ] Success prediction improves with more data
- [ ] Queue optimizer reduces material changes vs. FIFO
- [ ] Procurement goal generated when inventory low
- [ ] CLI commands work and display formatted output
- [ ] Web UI dashboard loads and updates in real-time
- [ ] No database deadlocks or race conditions under load

---

## Configuration Management

### Required .env Variables

```bash
# Phase 4: Fabrication Intelligence
FABRICATION_INTELLIGENCE_ENABLED=true

# Material Inventory
LOW_INVENTORY_THRESHOLD_GRAMS=100
PROCUREMENT_RESEARCH_ENABLED=true

# Print Outcome Tracking
OUTCOME_TRACKING_ENABLED=true
QUALITY_SCORING_ENABLED=true

# Print Intelligence (Feedback Loop)
PRINT_INTELLIGENCE_ENABLED=true
MIN_PRINTS_FOR_LEARNING=10

# Queue Optimization
QUEUE_OPTIMIZATION_ENABLED=true
OFF_PEAK_START_HOUR=22  # 10 PM
OFF_PEAK_END_HOUR=6     # 6 AM
MATERIAL_CHANGE_PENALTY_MINUTES=15
MAINTENANCE_INTERVAL_HOURS=200
```

### Database Migration

**Migration Steps**:
1. Create migration: `alembic -c services/common/alembic.ini revision --autogenerate -m "add fabrication intelligence"`
2. Review generated migration for correctness
3. Test migration on dev database: `alembic upgrade head`
4. Verify tables created: `psql -d kitty -c "\dt"`
5. Test rollback: `alembic downgrade -1` then `alembic upgrade head`
6. Run on production: `alembic upgrade head`

---

## Risk Mitigation

### Risk 1: Inaccurate Material Usage Estimation
**Mitigation Plan**:
- Week 1: Implement conservative estimates (add 10% buffer)
- Week 3: Calibrate with 10 real prints, measure actual weight
- Week 5: Adjust formula based on calibration data
- Ongoing: Allow manual corrections to improve estimates

### Risk 2: Low Historical Data Quality
**Mitigation Plan**:
- Phase 1: Create 20+ mock outcomes for testing/demo
- Phase 2: Make outcome capture as automatic as possible (MQTT/Moonraker integration)
- Phase 3: Graceful degradation - show "insufficient data" when <10 prints
- Phase 4: Confidence intervals on predictions

### Risk 3: Queue Optimization Conflicts with User Intent
**Mitigation Plan**:
- Always show optimization reasoning in UI/CLI
- Allow manual priority overrides (1-10 scale, plus "urgent" flag)
- Add "pin to top" feature for critical jobs
- Make optimization opt-in per job (default: enabled)

### Risk 4: Integration Complexity with Existing Systems
**Mitigation Plan**:
- Reuse Phase 3 patterns (OutcomeTracker → PrintOutcomeTracker)
- Minimal changes to existing fabrication service (add endpoints, don't restructure)
- Feature flags for gradual rollout (disable if issues arise)
- Comprehensive integration tests before production

---

## Success Criteria

### MVP (Minimum Viable Product)
At minimum, Phase 4 delivers:
- ✅ Material inventory tracked for 3+ materials
- ✅ Print outcomes captured for 20+ historical prints
- ✅ Success prediction available (even if accuracy <70% initially)
- ✅ Basic queue optimization (material batching)
- ✅ Low inventory alerts trigger procurement goals

### Full Success
For complete Phase 4 success:
- ✅ All MVP criteria met
- ✅ Success prediction accuracy ≥70% after 50 prints
- ✅ Material changes reduced by 40%+ with queue optimization
- ✅ CLI commands functional and user-friendly
- ✅ Web UI dashboard provides clear insights
- ✅ Documentation complete and accurate
- ✅ Test coverage ≥90% (unit), ≥80% (integration)

---

## Future Enhancements (Post-Phase 4)

1. **Computer Vision Quality Assessment**: Automated quality scoring from camera images (integrate with existing `cv/monitor.py`)
2. **Advanced Failure Prediction**: ML models trained on printer telemetry (temperature curves, vibration patterns)
3. **Multi-Material Print Optimization**: Handle prints requiring multiple filaments (Bambu AMS integration)
4. **Supplier API Integration**: Auto-order filament when procurement approved (requires API keys, payment integration)
5. **Energy Cost Optimization**: Dynamic scheduling based on real-time electricity rates (utility API integration)
6. **Collaborative Learning**: Share anonymized success/failure data across KITTY instances (privacy-preserving federation)
7. **Predictive Maintenance**: Predict printer failures before they occur (bearing wear, nozzle degradation)

---

## References

- Phase 3 Implementation: `services/brain/src/brain/autonomous/`
- Current Fabrication Service: `services/fabrication/src/fabrication/`
- Multi-Printer Control Spec: `specs/002-MultiPrinterControl/`
- ProjectVision.md Phase 4: `Reference/NorthStar/ProjectVision.md:304-328`
- Autonomous Operations Guide: `KITTY_AUTONOMOUS_OPERATIONS_GUIDE.md`
