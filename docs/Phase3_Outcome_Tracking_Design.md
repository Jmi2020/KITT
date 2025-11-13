# Phase 3: Outcome Tracking & Learning - Design Document

**Phase**: Learning "The Reflection"
**Status**: Design Phase
**Created**: 2025-11-13
**Dependencies**: Phase 2 complete (execution system operational)

---

## Overview

Phase 3 adds intelligence to KITTY's autonomous system by tracking outcomes, measuring goal effectiveness, and creating feedback loops to improve future goal generation.

**Core Question**: *Did the autonomous work actually help?*

---

## Success Metrics for Phase 3

1. **Outcome Tracking**: 100% of completed goals have outcome measurements
2. **Effectiveness Scoring**: Goals scored 0-100 based on actual impact
3. **Feedback Loop**: Goal generator uses historical effectiveness to improve future goals
4. **ROI Tracking**: Cost vs benefit analysis for research goals

---

## Key Concepts

### 1. Outcome Measurement

**What We Track**:
- For **research goals**: KB article usage, reference count, time-to-resolution improvements
- For **improvement goals**: Failure rate reduction, technique adoption rate
- For **optimization goals**: Cost savings, performance improvements

**How We Measure**:
- Baseline metrics (before goal execution)
- Post-completion metrics (after goal execution)
- Attribution (can we link improvement to the goal?)

### 2. Effectiveness Scoring

**EffectivenessScore** (0-100):
- **Impact** (40%): Did it solve the problem?
- **ROI** (30%): Was it worth the cost?
- **Adoption** (20%): Is it being used?
- **Quality** (10%): Is the output high-quality?

### 3. Feedback Loop

**Learning Mechanism**:
- Goals with high effectiveness → boost similar goal generation
- Goals with low effectiveness → reduce similar goal generation
- Patterns emerge (e.g., "material research goals are 85% effective")

---

## Database Schema Additions

### New Table: `goal_outcomes`

```sql
CREATE TABLE goal_outcomes (
    id UUID PRIMARY KEY,
    goal_id UUID NOT NULL REFERENCES goals(id),

    -- Measurement window
    baseline_date TIMESTAMP NOT NULL,
    measurement_date TIMESTAMP NOT NULL,

    -- Baseline metrics (before goal execution)
    baseline_metrics JSONB NOT NULL,

    -- Post-execution metrics
    outcome_metrics JSONB NOT NULL,

    -- Effectiveness scoring
    impact_score NUMERIC(5, 2),         -- 0-100
    roi_score NUMERIC(5, 2),            -- 0-100
    adoption_score NUMERIC(5, 2),       -- 0-100
    quality_score NUMERIC(5, 2),        -- 0-100
    effectiveness_score NUMERIC(5, 2),  -- 0-100 (weighted average)

    -- Metadata
    measurement_method VARCHAR(50),     -- 'kb_usage', 'failure_rate', 'cost_savings'
    notes TEXT,
    measured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    measured_by VARCHAR(100) DEFAULT 'system-autonomous',

    UNIQUE(goal_id)  -- One outcome per goal
);

CREATE INDEX idx_goal_outcomes_effectiveness ON goal_outcomes(effectiveness_score DESC);
CREATE INDEX idx_goal_outcomes_goal_type ON goal_outcomes((SELECT goal_type FROM goals WHERE id = goal_id));
```

### Enhanced: `goals` table

```sql
-- Add effectiveness tracking columns
ALTER TABLE goals ADD COLUMN effectiveness_score NUMERIC(5, 2);
ALTER TABLE goals ADD COLUMN outcome_measured_at TIMESTAMP;
ALTER TABLE goals ADD COLUMN learn_from BOOLEAN DEFAULT true;  -- Use in feedback loop
```

### Enhanced: `projects` table

```sql
-- Add completion tracking
ALTER TABLE projects ADD COLUMN actual_cost_usd NUMERIC(12, 6);
ALTER TABLE projects ADD COLUMN actual_duration_hours INTEGER;
ALTER TABLE projects ADD COLUMN completed_at TIMESTAMP;
```

---

## Outcome Measurement Strategies

### For Research Goals

**Metrics to Track**:

**Baseline** (before KB article created):
```json
{
  "baseline_type": "kb_gap",
  "related_failures": 8,
  "questions_asked": 15,
  "manual_research_time_hours": 4.5,
  "material_usage_count": 0
}
```

**Outcome** (30 days after KB article created):
```json
{
  "kb_article_views": 23,
  "kb_article_references": 5,  // Referenced in other articles
  "related_failures_after": 2,  // 75% reduction
  "questions_answered": 12,     // Self-service reduction
  "estimated_time_saved_hours": 15.2,
  "material_usage_count": 18    // Adoption
}
```

**Effectiveness Calculation**:
```python
# Impact: Failure reduction
impact = ((baseline_failures - outcome_failures) / baseline_failures) * 100
# ROI: Time saved / cost
roi = (time_saved_hours * $50_per_hour) / total_cost_usd * 10  # Scaled to 0-100
# Adoption: Usage metrics
adoption = min((views + references * 5) / 50 * 100, 100)
# Quality: Manual review or automated checks
quality = check_article_quality(article_path)  # Grammar, completeness, citations

effectiveness = (
    impact * 0.40 +
    roi * 0.30 +
    adoption * 0.20 +
    quality * 0.10
)
```

### For Improvement Goals

**Metrics to Track**:

**Baseline** (before technique update):
```json
{
  "baseline_type": "print_failure",
  "failure_count_30d": 12,
  "failure_rate": 0.15,  // 15% failure rate
  "technique_usage": 8   // Times technique referenced
}
```

**Outcome** (30 days after technique update):
```json
{
  "failure_count_30d": 3,
  "failure_rate": 0.04,  // 4% failure rate
  "failure_reduction_pct": 73.3,
  "technique_usage": 24,  // Adoption increased
  "user_feedback": "positive"
}
```

**Effectiveness Calculation**:
```python
impact = failure_reduction_pct
roi = (failures_prevented * $10_per_failure) / cost * 10
adoption = ((post_usage - baseline_usage) / baseline_usage) * 50  # Capped at 50
quality = 80  # Default for improvements (hard to measure)

effectiveness = impact * 0.40 + roi * 0.30 + adoption * 0.20 + quality * 0.10
```

### For Optimization Goals

**Metrics to Track**:

**Baseline** (before optimization):
```json
{
  "baseline_type": "cost_optimization",
  "frontier_cost_30d": 45.00,
  "local_cost_30d": 5.00,
  "total_queries": 1250
}
```

**Outcome** (30 days after optimization):
```json
{
  "frontier_cost_30d": 12.00,  // 73% reduction
  "local_cost_30d": 5.50,
  "cost_savings_usd": 33.00,
  "total_queries": 1300,
  "performance_degradation_pct": 2  // Minimal impact
}
```

**Effectiveness Calculation**:
```python
impact = cost_reduction_pct
roi = cost_savings / optimization_cost * 10
adoption = 100 if performance_degradation < 5 else 50  # Binary: works or doesn't
quality = 100 - performance_degradation_pct

effectiveness = impact * 0.40 + roi * 0.30 + adoption * 0.20 + quality * 0.10
```

---

## Implementation Components

### 1. OutcomeTracker Class

**File**: `services/brain/src/brain/autonomous/outcome_tracker.py`

**Responsibilities**:
- Capture baseline metrics when goal approved
- Measure outcome metrics 30 days after goal completion
- Calculate effectiveness scores
- Store outcomes in `goal_outcomes` table

**Key Methods**:
```python
class OutcomeTracker:
    def capture_baseline(self, goal: Goal) -> BaselineMetrics:
        """Capture baseline metrics when goal is approved."""

    def measure_outcome(self, goal: Goal) -> OutcomeMetrics:
        """Measure outcome 30 days after goal completion."""

    def calculate_effectiveness(
        self, baseline: BaselineMetrics, outcome: OutcomeMetrics
    ) -> EffectivenessScore:
        """Calculate effectiveness score (0-100)."""

    def store_outcome(self, goal: Goal, effectiveness: EffectivenessScore):
        """Store outcome in database."""
```

### 2. Scheduled Job: outcome_measurement_cycle

**Schedule**: Daily at 6:00am PST (14:00 UTC)
**Purpose**: Measure outcomes for goals completed 30 days ago

**Workflow**:
```python
async def outcome_measurement_cycle():
    # Find goals completed exactly 30 days ago
    goals = find_goals_for_measurement(days_ago=30)

    for goal in goals:
        # Capture baseline (if not already captured)
        if not goal.baseline_captured:
            baseline = tracker.capture_baseline(goal)

        # Measure outcome
        outcome = tracker.measure_outcome(goal)

        # Calculate effectiveness
        effectiveness = tracker.calculate_effectiveness(baseline, outcome)

        # Store in database
        tracker.store_outcome(goal, effectiveness)

        # Update goal
        goal.effectiveness_score = effectiveness.total
        goal.outcome_measured_at = datetime.utcnow()
```

### 3. FeedbackLoop Class

**File**: `services/brain/src/brain/autonomous/feedback_loop.py`

**Responsibilities**:
- Analyze historical goal effectiveness
- Adjust goal generation parameters
- Learn patterns (e.g., "research goals 85% effective, improvements 65% effective")

**Key Methods**:
```python
class FeedbackLoop:
    def analyze_historical_effectiveness(self) -> Dict[GoalType, float]:
        """Calculate average effectiveness by goal type."""

    def get_adjustment_factor(self, goal_type: GoalType) -> float:
        """Return adjustment factor (0.5-1.5) based on historical effectiveness.

        Examples:
        - Research goals with 85% avg effectiveness → 1.2x boost
        - Improvement goals with 45% avg effectiveness → 0.8x penalty
        """

    def update_goal_generator_weights(self):
        """Update goal generator's scoring weights based on learning."""
```

### 4. Enhanced GoalGenerator

**Modification**: `services/brain/src/brain/autonomous/goal_generator.py`

**Changes**:
```python
class GoalGenerator:
    def __init__(self, feedback_loop: Optional[FeedbackLoop] = None):
        self.feedback_loop = feedback_loop or FeedbackLoop()

    def _calculate_impact_score(self, goal: Goal) -> OpportunityScore:
        # ... existing scoring logic ...

        # Apply feedback loop adjustment
        adjustment = self.feedback_loop.get_adjustment_factor(goal.goal_type)
        adjusted_score = base_score * adjustment

        return adjusted_score
```

---

## Measurement Windows

**Timeline**:
1. **T0**: Goal identified
2. **T+0**: Baseline captured (when approved)
3. **T+1 to T+7 days**: Project execution
4. **T+7**: Goal completed
5. **T+37**: Outcome measured (30 days after completion)
6. **T+38**: Effectiveness score calculated and stored

**Why 30 days?**
- Allows time for KB articles to be referenced
- Sufficient data for failure rate trends
- Not too long to lose attribution

**Configurable** via `OUTCOME_MEASUREMENT_WINDOW_DAYS` (default: 30)

---

## Feedback Loop Learning

### Pattern Recognition

**After 10 completed goals**:
```python
{
  "goal_type_effectiveness": {
    "research": {
      "avg_effectiveness": 82.5,
      "count": 6,
      "adjustment_factor": 1.15  # Boost research goals
    },
    "improvement": {
      "avg_effectiveness": 58.3,
      "count": 3,
      "adjustment_factor": 0.95  # Slight penalty
    },
    "optimization": {
      "avg_effectiveness": 71.2,
      "count": 1,
      "adjustment_factor": 1.05
    }
  }
}
```

### Goal Generation Adjustment

**Before feedback loop**:
```
Goal: "Research NYLON material"
Base impact score: 68
Final score: 68
```

**After feedback loop (research goals 85% effective)**:
```
Goal: "Research NYLON material"
Base impact score: 68
Feedback adjustment: 1.15x (research goals effective)
Final score: 78.2  → Higher priority!
```

---

## Testing Strategy

### Unit Tests

```python
def test_baseline_capture():
    """Test baseline metrics capture for research goal."""

def test_outcome_measurement():
    """Test outcome measurement 30 days later."""

def test_effectiveness_calculation():
    """Test effectiveness scoring with known metrics."""

def test_feedback_loop_adjustment():
    """Test adjustment factor calculation."""
```

### Integration Tests

```python
@pytest.mark.integration
def test_full_outcome_cycle():
    """Test complete outcome tracking workflow."""
    # 1. Create and approve goal
    # 2. Capture baseline
    # 3. Execute goal (mock 30 days passing)
    # 4. Measure outcome
    # 5. Verify effectiveness score
    # 6. Verify feedback loop learns
```

---

## Configuration

### Environment Variables

```bash
# Outcome tracking configuration
OUTCOME_MEASUREMENT_ENABLED=true
OUTCOME_MEASUREMENT_WINDOW_DAYS=30
OUTCOME_MEASUREMENT_SCHEDULE="0 6 * * *"  # Daily 6am PST

# Feedback loop configuration
FEEDBACK_LOOP_ENABLED=true
FEEDBACK_LOOP_MIN_SAMPLES=10  # Minimum outcomes before adjusting
FEEDBACK_LOOP_ADJUSTMENT_MAX=1.5  # Maximum 1.5x boost
```

---

## Implementation Phases

### Sprint 4.1: Database Schema & OutcomeTracker

**Tasks**:
1. Create migration for `goal_outcomes` table
2. Implement `OutcomeTracker` class
3. Add baseline capture on goal approval
4. Add unit tests

**Estimated**: 3-4 hours

### Sprint 4.2: Measurement Job & Effectiveness Scoring

**Tasks**:
1. Implement `outcome_measurement_cycle` job
2. Add effectiveness calculation logic
3. Create measurement strategies for each goal type
4. Add integration tests

**Estimated**: 4-5 hours

### Sprint 4.3: Feedback Loop & Learning

**Tasks**:
1. Implement `FeedbackLoop` class
2. Integrate with `GoalGenerator`
3. Add historical analysis queries
4. Test adjustment factors

**Estimated**: 3-4 hours

### Sprint 4.4: UI & Observability

**Tasks**:
1. Add CLI commands to view effectiveness scores
2. Add effectiveness metrics to reasoning.jsonl
3. Create effectiveness dashboard queries
4. Documentation

**Estimated**: 2-3 hours

---

## Success Criteria

Phase 3 is complete when:
- ✅ All completed goals have outcome measurements
- ✅ Effectiveness scores calculated and stored
- ✅ Feedback loop adjusts goal generation based on learning
- ✅ CLI shows effectiveness scores: `kitty-cli autonomy effectiveness`
- ✅ Historical analysis shows improvement trends
- ✅ Integration tests pass

---

## Risks & Mitigation

**Risk**: Attribution problem (can't prove goal caused improvement)
**Mitigation**: Use conservative estimates, require 30-day window, track confidence level

**Risk**: Feedback loop overfits to recent data
**Mitigation**: Require minimum 10 samples, use exponential moving average

**Risk**: Outcome measurement is expensive
**Mitigation**: Run daily (not real-time), batch process, limit to completed goals only

---

## Next Steps

1. Review this design document
2. Create database migration for `goal_outcomes`
3. Implement `OutcomeTracker` class
4. Start Sprint 4.1

**Estimated Total Effort**: 12-16 hours (2-3 work sessions)
