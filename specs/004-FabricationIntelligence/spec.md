# Phase 4: Fabrication Intelligence

## Overview

Transform KITTY's fabrication capabilities from manual slicer launching to an intelligent, self-learning print optimization system that tracks materials, learns from outcomes, and autonomously optimizes print queues.

**Phase Status**: 🚧 In Progress
**Dependencies**: Phase 3 (Outcome Tracking & Learning), Multi-Printer Control (spec 002)
**Estimated Effort**: 4-6 weeks
**Target Completion**: TBD

---

## Vision

Enable KITTY to:
1. **Track material inventory** - Know what filaments are available, how much remains, and cost per print
2. **Learn from print outcomes** - Capture success/failure, quality scores, and actual costs for every print
3. **Predict print success** - Use historical data to estimate success probability before printing
4. **Optimize print queues** - Batch similar materials, prioritize by deadline, schedule during off-peak hours
5. **Autonomous material procurement** - Generate research goals when inventory runs low

### Success Criteria

- ✅ Material inventory tracked with ±5% accuracy
- ✅ Print outcomes captured for 95%+ of completed jobs
- ✅ Success prediction accuracy ≥70% after 50 historical prints
- ✅ Queue optimizer reduces material changes by 40%+
- ✅ Autonomous low-inventory alerts trigger procurement research
- ✅ Print cost tracking within ±10% of actual

---

## User Stories

### Story 1: Material Inventory Tracking
**As a** fabrication operator
**I want** KITTY to automatically track filament inventory
**So that** I never run out of material mid-print and can see cost per job

**Acceptance Criteria**:
- Material database includes: filament type, color, manufacturer, cost/kg, density
- Inventory database tracks: spool ID, material, purchase date, initial weight, current weight
- Print jobs automatically deduct material usage from inventory
- Low inventory alerts (≤100g remaining) generate procurement research goals
- CLI command to view inventory: `kitty-cli fabrication inventory`
- Web UI shows inventory status with color-coded levels (green/yellow/red)

### Story 2: Print Outcome Tracking
**As an** AI systems architect
**I want** KITTY to learn from every print job outcome
**So that** she can predict success and improve over time

**Acceptance Criteria**:
- Capture outcome for every completed print: success/failure, quality score (0-100), actual cost, actual duration
- Failure classification: first_layer_adhesion, warping, stringing, spaghetti, nozzle_clog, filament_runout, other
- Quality scoring based on: layer consistency, surface finish, dimensional accuracy (if measurable)
- Store print settings used: material, temperature, speed, layer height, infill, supports
- Link outcomes to Goals (when print was autonomous fabrication goal)
- Database migration adds PrintOutcome model

### Story 3: Print Intelligence (Feedback Loop)
**As a** design engineer
**I want** KITTY to recommend optimal print settings based on historical success
**So that** I can maximize print quality and minimize failures

**Acceptance Criteria**:
- Analyze historical print outcomes by material, printer, and settings
- Calculate success rate by material type (e.g., PLA: 95%, PETG: 87%, TPU: 72%)
- Identify high-risk combinations (e.g., "TPU on Bamboo H2D has 40% failure rate")
- Generate recommendations: "Use Elegoo Giga for TPU prints" or "Increase bed temp to 70°C for PETG"
- Predict success probability before print starts
- CLI command: `kitty-cli fabrication intelligence` shows learned insights

### Story 4: Queue Optimization
**As a** fabrication operator
**I want** KITTY to optimize the print queue automatically
**So that** I minimize material changes and energy costs

**Acceptance Criteria**:
- Queue optimizer batches jobs by material type
- Prioritizes by deadline (user-specified or autonomous goal deadline)
- Schedules large/long prints during off-peak hours (configurable time window)
- Considers printer maintenance intervals (e.g., "Bamboo H2D needs lubrication after 200 hours")
- CLI command: `kitty-cli fabrication queue` shows optimized queue
- Web UI displays queue with reasoning for order

### Story 5: Autonomous Procurement
**As a** facilities manager
**I want** KITTY to research material procurement options when inventory is low
**So that** I can proactively reorder before running out

**Acceptance Criteria**:
- Low inventory alert (<100g remaining) triggers autonomous goal generation
- Research goal type: `procurement` (new goal type)
- Goal description: "Research [Material] filament suppliers - inventory low (45g remaining)"
- Perplexity search for: current prices, sustainability ratings, delivery times, supplier reviews
- KB article documents findings with supplier comparison table
- User approves/rejects procurement research (does not auto-purchase)

---

## Technical Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 4: Fabrication Intelligence                          │
│                                                              │
│  ┌────────────────────┐      ┌─────────────────────────┐   │
│  │ Material Inventory │      │ Print Outcome Tracker   │   │
│  │                    │      │                         │   │
│  │ - Track spools     │      │ - Capture outcomes      │   │
│  │ - Deduct usage     │      │ - Classify failures     │   │
│  │ - Low alerts       │◄─────┤ - Calculate quality     │   │
│  └────────────────────┘      │ - Store settings        │   │
│           │                  └─────────────────────────┘   │
│           │                           │                     │
│           ▼                           ▼                     │
│  ┌────────────────────┐      ┌─────────────────────────┐   │
│  │ Procurement        │      │ Print Intelligence      │   │
│  │ Goal Generator     │      │ (Feedback Loop)         │   │
│  │                    │      │                         │   │
│  │ - Detect low inv   │      │ - Analyze outcomes      │   │
│  │ - Research suppliers│      │ - Learn best settings  │   │
│  │ - Compare options  │      │ - Predict success      │   │
│  └────────────────────┘      │ - Generate recommends  │   │
│                              └─────────────────────────┘   │
│                                       │                     │
│                                       ▼                     │
│                              ┌─────────────────────────┐   │
│                              │ Queue Optimizer         │   │
│                              │                         │   │
│                              │ - Batch by material     │   │
│                              │ - Prioritize deadline   │   │
│                              │ - Off-peak scheduling   │   │
│                              │ - Maintenance windows   │   │
│                              └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Component Details

#### 1. Material Inventory Tracker
**File**: `services/fabrication/src/fabrication/intelligence/material_inventory.py`

**Responsibilities**:
- Maintain material catalog (filament properties, costs)
- Track spool inventory (current weight, location, purchase date)
- Calculate material usage from STL volume + infill percentage
- Deduct usage after print completion
- Generate low-inventory alerts
- Estimate cost per print job

**Key Methods**:
```python
class MaterialInventory:
    def get_material(self, material_id: str) -> Material
    def get_inventory(self, spool_id: str) -> InventoryItem
    def calculate_usage(self, stl_volume_cm3: float, infill_percent: int, material_id: str) -> float
    def deduct_usage(self, spool_id: str, grams_used: float) -> None
    def check_low_inventory(self) -> List[InventoryItem]
    def estimate_print_cost(self, material_id: str, grams_used: float) -> Decimal
```

#### 2. Print Outcome Tracker
**File**: `services/fabrication/src/fabrication/intelligence/print_outcome_tracker.py`

**Responsibilities**:
- Capture print job outcomes (success/failure, quality, cost, duration)
- Classify failure reasons (first layer, warping, spaghetti, etc.)
- Store print settings (material, temp, speed, layer height, infill, supports)
- Link outcomes to autonomous goals (when applicable)
- Calculate quality scores based on available metrics

**Key Methods**:
```python
class PrintOutcomeTracker:
    def capture_outcome(self, job_id: str, outcome: PrintOutcome) -> PrintOutcomeRecord
    def classify_failure(self, job_id: str, failure_indicators: Dict) -> FailureReason
    def calculate_quality_score(self, job_id: str, metrics: QualityMetrics) -> float
    def get_historical_outcomes(self, filters: OutcomeFilters) -> List[PrintOutcomeRecord]
```

**Outcome Data Classes**:
```python
@dataclass
class PrintOutcome:
    """Print job outcome data."""
    job_id: str
    success: bool
    failure_reason: Optional[FailureReason]
    quality_score: float  # 0-100
    actual_duration_hours: float
    actual_cost_usd: Decimal
    material_used_grams: float

@dataclass
class PrintSettings:
    """Print settings used for the job."""
    material_id: str
    printer_id: str
    nozzle_temp_c: int
    bed_temp_c: int
    print_speed_mm_s: int
    layer_height_mm: float
    infill_percent: int
    supports_enabled: bool

@dataclass
class QualityMetrics:
    """Quality assessment metrics."""
    layer_consistency: float  # 0-100
    surface_finish: float  # 0-100
    dimensional_accuracy: Optional[float]  # 0-100, if measurable
```

#### 3. Print Intelligence (Feedback Loop)
**File**: `services/fabrication/src/fabrication/intelligence/print_intelligence.py`

**Responsibilities**:
- Analyze historical print outcomes
- Calculate success rates by material, printer, settings
- Identify high-risk combinations
- Predict print success probability
- Generate recommendations for optimal settings
- Learn from failures to improve future predictions

**Key Methods**:
```python
class PrintIntelligence:
    def analyze_historical_success(self) -> Dict[str, SuccessAnalysis]
    def predict_success_probability(self, job_params: PrintJobParams) -> float
    def get_recommendations(self, material_id: str, printer_id: str) -> List[str]
    def identify_high_risk_combinations(self) -> List[RiskWarning]
    def get_optimal_settings(self, material_id: str, printer_id: str) -> PrintSettings
    def get_intelligence_summary(self) -> Dict
```

**Analysis Data Classes**:
```python
@dataclass
class SuccessAnalysis:
    """Success rate analysis for a specific category."""
    category: str  # material, printer, material+printer
    total_prints: int
    successful_prints: int
    success_rate: float
    avg_quality_score: float
    common_failures: List[FailureReason]

@dataclass
class RiskWarning:
    """High-risk combination warning."""
    material_id: str
    printer_id: str
    success_rate: float
    failure_count: int
    recommendation: str
```

#### 4. Queue Optimizer
**File**: `services/fabrication/src/fabrication/intelligence/queue_optimizer.py`

**Responsibilities**:
- Optimize print queue order based on multiple factors
- Batch jobs by material type (minimize material changes)
- Prioritize by deadline (user-specified or goal deadline)
- Schedule large jobs during off-peak hours
- Consider printer maintenance intervals
- Generate reasoning for queue order

**Key Methods**:
```python
class QueueOptimizer:
    def optimize_queue(self, jobs: List[PrintJob]) -> List[OptimizedJob]
    def calculate_priority_score(self, job: PrintJob) -> float
    def batch_by_material(self, jobs: List[PrintJob]) -> Dict[str, List[PrintJob]]
    def schedule_for_off_peak(self, job: PrintJob) -> Optional[datetime]
    def check_maintenance_due(self, printer_id: str) -> bool
    def estimate_completion_time(self, queue: List[PrintJob]) -> datetime
```

**Queue Data Classes**:
```python
@dataclass
class PrintJob:
    """Print job to be queued."""
    job_id: str
    stl_path: str
    material_id: str
    printer_id: str
    deadline: Optional[datetime]
    priority: int  # 1-10
    estimated_duration_hours: float
    material_required_grams: float

@dataclass
class OptimizedJob:
    """Job with optimized scheduling."""
    job: PrintJob
    scheduled_start: datetime
    priority_score: float
    reasoning: str
```

#### 5. Procurement Goal Generator
**File**: `services/fabrication/src/fabrication/intelligence/procurement_generator.py`

**Responsibilities**:
- Monitor inventory levels
- Generate procurement research goals when inventory low
- Integrate with existing autonomous goal system
- Research suppliers, prices, sustainability, delivery times
- Document findings in KB

**Key Methods**:
```python
class ProcurementGenerator:
    def check_inventory_levels(self) -> List[InventoryItem]
    def generate_procurement_goal(self, item: InventoryItem) -> Goal
    def research_suppliers(self, material_id: str) -> SupplierResearchResult
    def create_kb_article(self, research: SupplierResearchResult) -> str
```

---

## Data Model

### New Database Models

#### Material Table
```python
class Material(Base):
    """Filament material catalog."""
    __tablename__ = "materials"

    id = Column(String, primary_key=True)  # e.g., "pla_black_esun"
    material_type = Column(String, nullable=False)  # pla, petg, abs, tpu, etc.
    color = Column(String, nullable=False)
    manufacturer = Column(String, nullable=False)
    cost_per_kg_usd = Column(Numeric(10, 2), nullable=False)
    density_g_cm3 = Column(Numeric(4, 2), nullable=False)  # e.g., 1.24 for PLA
    nozzle_temp_min_c = Column(Integer, nullable=False)
    nozzle_temp_max_c = Column(Integer, nullable=False)
    bed_temp_min_c = Column(Integer, nullable=False)
    bed_temp_max_c = Column(Integer, nullable=False)
    properties = Column(JSONB, nullable=True)  # strength, flexibility, food_safe, etc.
    sustainability_score = Column(Integer, nullable=True)  # 0-100
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
```

#### InventoryItem Table
```python
class InventoryItem(Base):
    """Physical filament spool inventory."""
    __tablename__ = "inventory"

    id = Column(String, primary_key=True)  # spool ID
    material_id = Column(String, ForeignKey("materials.id"), nullable=False)
    location = Column(String, nullable=True)  # shelf, bin, printer
    purchase_date = Column(Date, nullable=False)
    initial_weight_grams = Column(Numeric(10, 2), nullable=False)
    current_weight_grams = Column(Numeric(10, 2), nullable=False)
    status = Column(String, nullable=False)  # available, in_use, depleted
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    # Relationships
    material = relationship("Material", back_populates="inventory")
```

#### PrintOutcome Table
```python
class PrintOutcome(Base):
    """Historical print job outcomes for learning."""
    __tablename__ = "print_outcomes"

    id = Column(String, primary_key=True)
    job_id = Column(String, nullable=False, unique=True)
    goal_id = Column(String, ForeignKey("goals.id"), nullable=True)  # if autonomous
    printer_id = Column(String, nullable=False)
    material_id = Column(String, ForeignKey("materials.id"), nullable=False)

    # Outcome
    success = Column(Boolean, nullable=False)
    failure_reason = Column(String, nullable=True)  # first_layer, warping, spaghetti, etc.
    quality_score = Column(Numeric(5, 2), nullable=False)  # 0-100

    # Actuals
    actual_duration_hours = Column(Numeric(6, 2), nullable=False)
    actual_cost_usd = Column(Numeric(10, 2), nullable=False)
    material_used_grams = Column(Numeric(10, 2), nullable=False)

    # Print Settings
    print_settings = Column(JSONB, nullable=False)  # temp, speed, layer height, infill, etc.

    # Quality Metrics (if available)
    quality_metrics = Column(JSONB, nullable=True)  # layer_consistency, surface_finish, etc.

    # Timestamps
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=False)
    measured_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    goal = relationship("Goal", back_populates="print_outcomes")
    material = relationship("Material")
```

#### QueuedPrint Table
```python
class QueuedPrint(Base):
    """Print queue with optimization metadata."""
    __tablename__ = "print_queue"

    id = Column(String, primary_key=True)
    job_id = Column(String, nullable=False, unique=True)
    stl_path = Column(String, nullable=False)

    # Assignment
    printer_id = Column(String, nullable=False)
    material_id = Column(String, ForeignKey("materials.id"), nullable=False)
    spool_id = Column(String, ForeignKey("inventory.id"), nullable=True)

    # Scheduling
    status = Column(String, nullable=False)  # queued, printing, completed, failed, cancelled
    priority = Column(Integer, nullable=False)  # 1-10
    deadline = Column(DateTime, nullable=True)
    scheduled_start = Column(DateTime, nullable=True)

    # Estimates
    estimated_duration_hours = Column(Numeric(6, 2), nullable=False)
    estimated_material_grams = Column(Numeric(10, 2), nullable=False)
    estimated_cost_usd = Column(Numeric(10, 2), nullable=False)
    success_probability = Column(Numeric(5, 2), nullable=True)  # 0-100

    # Optimization Metadata
    priority_score = Column(Numeric(10, 4), nullable=True)
    optimization_reasoning = Column(Text, nullable=True)

    # Timestamps
    queued_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    material = relationship("Material")
    spool = relationship("InventoryItem")
```

### Database Relationships

```
Material (1) ──< (N) InventoryItem
Material (1) ──< (N) PrintOutcome
Material (1) ──< (N) QueuedPrint

InventoryItem (1) ──< (N) QueuedPrint

Goal (1) ──< (N) PrintOutcome

QueuedPrint (1) ──o (0-1) PrintOutcome  [after completion]
```

---

## Configuration

### Environment Variables

Add to `.env`:

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
MIN_PRINTS_FOR_LEARNING=10  # Minimum prints per category before making predictions

# Queue Optimization
QUEUE_OPTIMIZATION_ENABLED=true
OFF_PEAK_START_HOUR=22  # 10 PM
OFF_PEAK_END_HOUR=6     # 6 AM
MATERIAL_CHANGE_PENALTY_MINUTES=15  # Time cost of changing materials
MAINTENANCE_INTERVAL_HOURS=200  # Printer maintenance interval
```

---

## Integration Points

### 1. Existing Fabrication Service
**Integration**: Extend `services/fabrication/src/fabrication/app.py`

**New Endpoints**:
- `POST /api/fabrication/queue` - Add job to optimized queue
- `GET /api/fabrication/queue` - View optimized queue
- `POST /api/fabrication/outcome` - Report print outcome
- `GET /api/fabrication/intelligence` - Get learned insights
- `GET /api/fabrication/inventory` - View material inventory
- `POST /api/fabrication/inventory/deduct` - Manually deduct material usage

### 2. Autonomous Goal System
**Integration**: Extend `services/brain/src/brain/autonomous/goal_generator.py`

**Changes**:
- Add new goal type: `GoalType.procurement`
- Integrate procurement generator to create goals when inventory low
- Link fabrication goals to print outcomes for effectiveness tracking

### 3. Phase 3 Outcome Tracking
**Integration**: Reuse patterns from `services/brain/src/brain/autonomous/outcome_tracker.py`

**Similarities**:
- Baseline capture → Print job settings capture
- Outcome measurement → Print outcome capture
- Effectiveness calculation → Quality score calculation
- Feedback loop → Print intelligence learning

### 4. CLI
**Integration**: Extend `services/cli/src/cli/shell.py`

**New Commands**:
- `/fabrication inventory` - View material inventory
- `/fabrication queue` - View print queue
- `/fabrication intelligence` - View learned insights
- `/fabrication predict <job_id>` - Predict success probability

### 5. Web UI
**Integration**: Add fabrication intelligence dashboard

**New Views**:
- Material inventory table with color-coded levels
- Print queue with optimization reasoning
- Success rate charts by material/printer
- Failure analysis dashboard
- Print cost tracking

---

## Testing Strategy

### Unit Tests

**File**: `tests/unit/test_material_inventory.py`
- Material catalog operations
- Inventory tracking (add, deduct, check levels)
- Usage calculation from STL volume
- Cost estimation
- Low inventory detection

**File**: `tests/unit/test_print_outcome_tracker.py`
- Outcome capture
- Failure classification
- Quality score calculation
- Historical outcome queries

**File**: `tests/unit/test_print_intelligence.py`
- Success rate analysis
- Success prediction
- Recommendation generation
- High-risk combination identification

**File**: `tests/unit/test_queue_optimizer.py`
- Priority score calculation
- Material batching
- Deadline prioritization
- Off-peak scheduling
- Maintenance window detection

### Integration Tests

**File**: `tests/integration/test_phase4_integration.py`
- Full workflow: Queue job → Deduct material → Capture outcome → Learn → Optimize next queue
- Procurement goal generation on low inventory
- Queue optimization with multiple jobs
- Success prediction accuracy validation

---

## Success Metrics

### Quantitative Metrics

1. **Material Tracking Accuracy**: ±5% of actual weight
2. **Outcome Capture Rate**: ≥95% of completed prints
3. **Success Prediction Accuracy**: ≥70% after 50 prints
4. **Material Change Reduction**: 40%+ fewer changes with queue optimization
5. **Cost Tracking Accuracy**: ±10% of actual cost
6. **Low Inventory Alert Lead Time**: ≥7 days before depletion

### Qualitative Metrics

1. **User Confidence**: Operators trust success predictions
2. **Autonomous Procurement**: Low-inventory alerts lead to useful research
3. **Queue Transparency**: Users understand optimization reasoning
4. **Learning Visibility**: Clear insights into what works and what doesn't

---

## Risks and Mitigations

### Risk 1: Inaccurate Material Usage Estimation
**Impact**: Inventory tracking unreliable, cost estimates wrong
**Mitigation**:
- Calibrate usage calculation with actual measurements
- Add manual adjustment capability
- Start with conservative estimates (add 10% buffer)

### Risk 2: Insufficient Historical Data for Learning
**Impact**: Poor predictions, unhelpful recommendations
**Mitigation**:
- Set minimum thresholds (10+ prints per category)
- Display confidence intervals with predictions
- Start with conservative recommendations
- Gracefully degrade to "insufficient data" message

### Risk 3: Queue Optimization Conflicts with User Priorities
**Impact**: Users override optimization, reducing value
**Mitigation**:
- Allow manual priority overrides
- Display optimization reasoning clearly
- Support "urgent" priority level (always goes first)
- Make optimization opt-in per job

### Risk 4: Print Outcome Capture Requires Manual Input
**Impact**: Low adoption, incomplete data
**Mitigation**:
- Integrate with existing printer monitoring (MQTT, Moonraker)
- Auto-detect failures where possible (printer state = "failed")
- Simple CLI/UI for quick outcome entry
- Default to "success" if printer completed without error

---

## Future Enhancements (Post-Phase 4)

1. **Computer Vision Quality Assessment**: Automated quality scoring from camera images
2. **Advanced Failure Prediction**: ML models trained on printer telemetry (vibration, temperature variance)
3. **Multi-Material Optimization**: Optimize for prints requiring multiple filaments
4. **Supplier Integration**: Auto-order filament when approved (requires procurement API)
5. **Energy Cost Optimization**: Dynamic scheduling based on real-time electricity rates
6. **Collaborative Learning**: Share anonymized success/failure data across KITTY instances

---

## References

- Phase 3 Implementation: `services/brain/src/brain/autonomous/`
- Multi-Printer Control: `specs/002-MultiPrinterControl/`
- ProjectVision.md: `NorthStar/ProjectVision.md`
- Current Fabrication Service: `services/fabrication/src/fabrication/app.py`
