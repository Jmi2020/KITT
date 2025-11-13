# KITTY Autonomous Operations Guide

**Your AI Fabrication Partner Working While You Sleep**

---

## 🎯 Overview

KITTY is your autonomous fabrication assistant that works during your downtime to improve the workshop. While you're away, KITTY analyzes fabrication data, identifies problems, researches solutions, and creates documentation - all with your approval and oversight.

**What KITTY Does Autonomously:**
- 🔍 Analyzes print failures and identifies patterns
- 📚 Researches missing materials and techniques
- 💰 Optimizes API costs and routing efficiency
- 📖 Creates knowledge base articles
- 🔧 Updates fabrication techniques
- ✅ Commits improvements to version control

**What KITTY Doesn't Do Without You:**
- ❌ Start fabrication jobs (requires explicit approval)
- ❌ Unlock doors or control safety systems
- ❌ Spend money without budget limits ($5/day default)
- ❌ Work during active hours (respects 4am-6am PST window in dev mode)

---

## 🤖 How KITTY's Autonomy Works

### The Autonomous Cycle

```
Monday 5:00am PST - Weekly Research Cycle
│
├─ 1. ANALYZE 🔍
│  └─ KITTY analyzes the past 30 days:
│     • Print failure patterns (first layer, warping, spaghetti)
│     • Knowledge base gaps (missing materials, techniques)
│     • API cost patterns (excessive cloud usage)
│
├─ 2. IDENTIFY OPPORTUNITIES 💡
│  └─ KITTY generates goals with impact scores (0-100):
│     • Goal Type: research | improvement | optimization
│     • Description: Clear problem statement
│     • Rationale: Why this matters (data-driven)
│     • Budget: Estimated cost ($1.50-$5.00 typical)
│     • Duration: Estimated time (2-6 hours typical)
│
├─ 3. AWAIT APPROVAL ⏸️
│  └─ Goals created with status=identified
│     ⚠️ KITTY STOPS HERE - Waiting for your approval
│
├─ 4. YOU APPROVE/REJECT ✅❌
│  └─ Review via CLI or Web UI
│     • Approve: Goal proceeds to execution
│     • Reject: Goal archived with notes
│
├─ 5. PROJECT GENERATION 📋
│  └─ Every 4 hours, KITTY checks for approved goals:
│     • Creates project with task breakdown
│     • Sets task dependencies (sequential execution)
│     • Allocates budget across tasks
│
├─ 6. TASK EXECUTION 🚀
│  └─ Every 15 minutes, KITTY executes ready tasks:
│     • Research: Perplexity API queries
│     • Synthesis: AI analysis and writing
│     • Documentation: Knowledge base creation
│     • Git: Auto-commit with audit trail
│
└─ 7. COMPLETION & LEARNING 📈
   └─ Project completes → Goal status: completed
      • 30 days later: Measure outcome effectiveness
      • Learn from results: Adjust future priorities
      • Improve autonomously over time
```

### Operating Modes

**Development Mode (Default)**: `AUTONOMOUS_FULL_TIME_MODE=false`
- Autonomous work only happens **4:00am - 6:00am PST**
- Ensures KITTY doesn't disrupt your active work hours
- Health checks and monitoring run 24/7
- Perfect for testing and gradual adoption

**Production Mode**: `AUTONOMOUS_FULL_TIME_MODE=true`
- Autonomous work happens **24/7 when system is idle** (2+ hours)
- Requires CPU < 20%, Memory < 70%
- Suitable for fully autonomous operation
- Budget limits still enforced

---

## 📋 Managing Goals: CLI Interface

### Installation

```bash
# Install CLI (if not already installed)
pip install -e services/cli/

# Verify installation
kitty-cli --version
```

### Checking System Status

**View autonomous system health:**
```bash
kitty-cli autonomy status
```

**Output:**
```
Autonomous System Status

✓ Ready: True
   Budget Available: $4.50 / $5.00 per day
   Budget Used Today: $0.50
   System Idle: True
   CPU Usage: 15.0%
   Memory Usage: 45.0%

Scheduler: 7 jobs active
- daily_health_check: 4:00am PST daily
- weekly_research_cycle: Monday 5:00am PST
- knowledge_base_update: Monday 6:00am PST
- printer_fleet_health_check: Every 4 hours
- project_generation_cycle: Every 4 hours (4am-6am PST in dev mode)
- task_execution_cycle: Every 15 minutes (4am-6am PST in dev mode)
- outcome_measurement_cycle: Daily 6:00am PST (Phase 3)

7-Day Budget Summary:
   Total Cost: $15.50
   Total Requests: 45
   Average/Day: $2.21
```

### Listing Pending Goals

**See what KITTY wants to work on:**
```bash
kitty-cli autonomy list
```

**Output:**
```
Pending Autonomous Goals (3)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. [IMPROVEMENT] Reduce first_layer failures in 3D printing
   ID: abc123def456
   Impact Score: 68 / 100

   Rationale: Observed 8 failures due to 'first_layer' adhesion issues
   in the past 30 days. Pattern detected across multiple materials (PLA,
   PETG, ABS). Addressing this could reduce failure rate by ~75%.

   Estimated: $2.50, 4 hours
   Source: print_failure_analysis
   Identified: 2025-11-13 05:23:15 PST

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

2. [RESEARCH] Research and document NYLON material properties
   ID: def456ghi789
   Impact Score: 62 / 100

   Rationale: Knowledge base is missing comprehensive NYLON documentation.
   NYLON has been mentioned in 15 support questions but no KB article exists.
   Creating this documentation will enable better material selection guidance.

   Estimated: $1.50, 3 hours
   Source: knowledge_gap_analysis
   Identified: 2025-11-13 05:23:18 PST

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

3. [OPTIMIZATION] Optimize routing to reduce frontier tier usage
   ID: ghi789jkl012
   Impact Score: 71 / 100

   Rationale: Frontier tier accounts for 35.2% of routing costs ($12.50)
   over the past 30 days. Local tier confidence threshold may be too
   conservative. Optimizing could save $8-10/month.

   Estimated: $3.00, 6 hours
   Source: cost_optimization_analysis
   Identified: 2025-11-13 05:23:21 PST

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Filter by status or type:**
```bash
# Only show research goals
kitty-cli autonomy list --type research

# Show approved goals
kitty-cli autonomy list --status approved

# Show completed goals
kitty-cli autonomy list --status completed

# Limit results
kitty-cli autonomy list --limit 10
```

### Approving Goals

**Approve a goal by ID:**
```bash
kitty-cli autonomy approve abc123def456
```

**With approval notes:**
```bash
kitty-cli autonomy approve abc123def456 --notes "High priority - seeing this failure pattern frequently"
```

**Output:**
```
✅ Goal approved successfully!

Goal: Reduce first_layer failures in 3D printing
Status: identified → approved
Approved by: user-jmi2020
Approved at: 2025-11-13 08:45:22 PST

Next steps:
- Project will be created within 4 hours (next project_generation_cycle)
- Tasks will execute automatically during 4am-6am PST window
- Check progress: kitty-cli autonomy projects
```

### Rejecting Goals

**Reject a goal:**
```bash
kitty-cli autonomy reject ghi789jkl012 --notes "Not a priority right now"
```

**Output:**
```
❌ Goal rejected

Goal: Optimize routing to reduce frontier tier usage
Status: identified → rejected
Rejected by: user-jmi2020
Rejected at: 2025-11-13 08:50:15 PST
Notes: Not a priority right now

This goal will not generate a project.
```

### Viewing Goal Details

**Get comprehensive information:**
```bash
kitty-cli autonomy goal abc123def456
```

**Output:**
```
Goal Details
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ID: abc123def456
Type: improvement
Status: approved

Description:
Reduce first_layer failures in 3D printing

Rationale:
Observed 8 failures due to 'first_layer' adhesion issues in the past
30 days. Pattern detected across multiple materials (PLA, PETG, ABS).
Addressing this could reduce failure rate by ~75%.

Estimated Budget: $2.50
Estimated Duration: 4 hours
Impact Score: 68 / 100

Timeline:
Identified: 2025-11-13 05:23:15 PST
Approved: 2025-11-13 08:45:22 PST
Approved By: user-jmi2020

Metadata:
- source: print_failure_analysis
- failure_reason: first_layer
- failure_count: 8
- lookback_days: 30
- base_impact_score: 68.0
- adjustment_factor: 1.0 (Phase 3: Learning not yet active)
- adjusted_impact_score: 68.0

Associated Project: (will be created within 4 hours)
```

### Viewing Projects and Tasks

**List active projects:**
```bash
kitty-cli autonomy projects
```

**Output:**
```
Active Autonomous Projects (2)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Project: Research and document NYLON material properties
ID: proj_xyz789
Status: in_progress
Progress: 2 / 4 tasks completed (50%)

Goal: Research NYLON material (approved 2025-11-12)
Budget: $1.50 allocated, $0.85 spent

Tasks:
✅ Task 1: Gather information from web sources (completed)
   Cost: $0.45
✅ Task 2: Synthesize research findings (completed)
   Cost: $0.40
⏳ Task 3: Create knowledge base article (in_progress)
   Depends on: Task 2
⏸️ Task 4: Review and commit to repository (pending)
   Depends on: Task 3

Next execution: Task 3 will complete in next cycle (4am-6am PST)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**View project details:**
```bash
kitty-cli autonomy project proj_xyz789
```

### Viewing Effectiveness Scores (Phase 3)

**See how well KITTY's autonomous work is performing:**
```bash
kitty-cli autonomy effectiveness
```

**Output:**
```
Goal Effectiveness Metrics (Phase 3: Learning)

Overall Performance: 72.5 / 100 (Good)
Goals Measured: 12
Learning Active: Yes (10+ samples per goal type)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Goal Type: Research
Average Effectiveness: 82.5 / 100 (Excellent)
Goals Completed: 6
Adjustment Factor: 1.15x (boosting priority by 15%)

✅ High Impact: KB articles averaging 23 views
✅ Strong ROI: Estimated $75 time saved per goal
✅ Good Adoption: Articles referenced 5x on average

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Goal Type: Improvement
Average Effectiveness: 58.3 / 100 (Moderate)
Goals Completed: 3
Adjustment Factor: 0.95x (slight priority reduction)

⚠️ Moderate Impact: 45% average failure reduction
✅ Good ROI: $50 saved per goal
⚠️ Lower Adoption: Techniques not widely referenced yet

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Goal Type: Optimization
Average Effectiveness: 71.2 / 100 (Good)
Goals Completed: 3
Adjustment Factor: 1.05x (slight priority boost)

✅ Strong Impact: 35% cost reduction average
✅ Excellent ROI: $33 saved per goal
✅ Good Quality: <5% performance degradation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Learning Insights:
🎯 Research goals are highly effective - will prioritize more
🔍 Improvement goals need better technique adoption tracking
💰 Optimization goals delivering strong ROI
📈 System is learning and improving over time
```

---

## 🌐 Managing Goals: Web Interface

### Accessing the Autonomy Dashboard

**URL**: `http://localhost:4173/autonomy`

### Dashboard Features

**1. Goals Overview Panel**
- Pending goals requiring approval (badge count)
- Active projects in progress
- Completed goals with effectiveness scores
- 7-day budget visualization

**2. Goal Cards**
```
┌─────────────────────────────────────────────────────────┐
│ [RESEARCH] Research and document NYLON material         │
│ Impact Score: 62 / 100                                  │
├─────────────────────────────────────────────────────────┤
│ Rationale: Knowledge base is missing comprehensive     │
│ NYLON documentation. NYLON has been mentioned in 15    │
│ support questions but no KB article exists...           │
│                                                         │
│ Estimated: $1.50 • 3 hours                             │
│ Identified: 2025-11-13 05:23 PST                       │
├─────────────────────────────────────────────────────────┤
│ [Approve] [Reject] [View Details]                      │
└─────────────────────────────────────────────────────────┘
```

**3. Approval Modal**
- Click "Approve" or "Reject" button
- Optional notes field
- Confirmation with next steps

**4. Project Timeline View**
- Gantt chart of active projects
- Task status indicators (pending, in progress, completed, failed)
- Budget tracking bar
- Real-time updates via MQTT

**5. Effectiveness Dashboard (Phase 3)**
- Goal type performance charts
- ROI visualization
- Learning progress metrics
- Historical trends

### Web Interface Workflow

**Step 1: Navigate to Dashboard**
```
http://localhost:4173/autonomy
```

**Step 2: Review Pending Goals**
- Click "Pending Goals (3)" tab
- Browse goal cards with full rationale
- Sort by impact score, type, or date

**Step 3: Approve/Reject**
- Click [Approve] button → Modal opens
- Add optional notes: "High priority - critical for production"
- Click [Confirm Approval]
- Goal moves to "Approved" tab

**Step 4: Monitor Progress**
- Click "Active Projects (2)" tab
- View project cards with task progress bars
- Click project for detailed task breakdown
- Real-time status updates via MQTT subscription

**Step 5: Review Outcomes (Phase 3)**
- Click "Effectiveness" tab
- View performance metrics by goal type
- See learning insights and recommendations
- Filter by date range or goal type

---

## 📊 Understanding Goal Types

### Research Goals

**What They Are:**
- Knowledge base gaps (missing materials, techniques)
- Documentation needs identified from support questions
- Technical deep-dives on fabrication topics

**Example:**
> "Research and document NYLON material properties"

**Typical Workflow:**
1. **Gather** (Task 1): Perplexity API searches (4-6 queries)
   - "NYLON 3D printing properties specifications"
   - "NYLON print temperature bed temperature"
   - "NYLON moisture absorption handling"
2. **Synthesize** (Task 2): AI analysis with collective meta-agent
   - Council pattern: 3 specialists + 1 judge
   - Structured KB article outline
3. **Document** (Task 3): Create markdown article with YAML frontmatter
   - Filename: `2025-W46-nylon-material-guide.md`
   - Location: `knowledge/materials/` or `knowledge/research/`
4. **Commit** (Task 4): Git automation
   - Message: "KB: autonomous update - NYLON material guide"
   - Commit SHA logged for audit trail

**Estimated Cost:** $1.50 - $3.00
**Estimated Time:** 3-6 hours
**Risk:** Low (read-only research, no fabrication)

### Improvement Goals

**What They Are:**
- Print failure pattern corrections
- Technique guide updates
- Process optimizations

**Example:**
> "Reduce first_layer failures in 3D printing"

**Typical Workflow:**
1. **Research** (Task 1): Quick Perplexity lookup
   - "first layer adhesion troubleshooting 3D printing"
2. **Update** (Task 2): Update existing technique guide
   - File: `knowledge/techniques/first-layer-adhesion.md`
   - Add new troubleshooting section
   - Git commit with autonomous tag

**Estimated Cost:** $1.00 - $2.50
**Estimated Time:** 2-4 hours
**Risk:** Low (documentation only, no fabrication)

### Optimization Goals

**What They Are:**
- API cost reductions
- Routing efficiency improvements
- Performance optimizations

**Example:**
> "Optimize routing to reduce frontier tier usage"

**Typical Workflow:**
1. **Analyze** (Task 1): Query routing_decisions table
   - Calculate tier distribution
   - Identify optimization opportunities
2. **Document** (Task 2): Create recommendation document
   - Suggest threshold adjustments
   - Estimate cost savings
   - Present findings for user review

**Estimated Cost:** $2.00 - $4.00
**Estimated Time:** 4-8 hours
**Risk:** Low (recommendations only, no code changes)

### Fabrication Goals (Future - Phase 4)

**What They Are:**
- CAD generation and printing
- Multi-part assemblies
- Physical prototyping

**Example:**
> "Design and print replacement bracket for printer enclosure"

**Typical Workflow:**
1. CAD generation via Zoo or Tripo API
2. STL analysis and optimization
3. Printer selection and queuing
4. **REQUIRES EXPLICIT APPROVAL** before print starts
5. Print monitoring and quality checks

**Estimated Cost:** $5.00 - $20.00
**Estimated Time:** 6-24 hours
**Risk:** Medium (uses materials, requires safety checks)

---

## 🔐 Safety & Governance

### Budget Controls

**Daily Budget Limit:** `$5.00` (default, configurable)
- Enforced by ResourceManager
- Resets at midnight UTC
- Prevents runaway costs
- Logged to reasoning.jsonl

**Per-Goal Budget Allocation:**
- Research: 40% to gathering, 30% to synthesis, 20% to documentation, 10% to review
- Improvement: 60% to research, 40% to updates
- Optimization: 50% to analysis, 50% to documentation

**Budget Exhaustion Behavior:**
```bash
# Budget exceeded
kitty-cli autonomy status
# Output: ⚠️ Budget exhausted: $5.00 / $5.00 used today
#         Autonomous jobs paused until midnight UTC reset

# Increase budget (edit .env)
AUTONOMOUS_DAILY_BUDGET_USD=10.00

# Restart brain service
docker compose restart brain
```

### Time Window Controls

**Development Mode (Default):**
- Autonomous work: **4:00am - 6:00am PST only**
- Health checks: 24/7
- Prevents disruption during active work hours

**Production Mode:**
- Autonomous work: **24/7 when idle** (2+ hours, CPU < 20%, Memory < 70%)
- Suitable for fully autonomous operation

**Override for Testing:**
```bash
# Temporarily trigger goal generation (testing only)
docker exec -it brain python -c "
from services.brain.src.brain.autonomous.jobs import weekly_research_cycle
import asyncio
asyncio.run(weekly_research_cycle())
"
```

### Approval Requirements

**Goals Requiring Approval:**
- ✅ All goals (default)
- ✅ Research (low-risk, could auto-approve after 48h in future)
- ✅ Improvement (low-risk)
- ✅ Optimization (low-risk)
- ✅ Fabrication (high-risk, always requires approval)

**Approval Workflow:**
1. Goal created with `status=identified`
2. User reviews rationale, budget, impact score
3. User approves via CLI or Web UI
4. Goal status changes to `approved`
5. Project generation begins within 4 hours
6. Tasks execute automatically during time window
7. Completion logged to reasoning.jsonl and MQTT

### Audit Trail

**All autonomous operations are logged:**

**Structured Logs (reasoning.jsonl):**
```json
{
  "event": "goal_generation_completed",
  "timestamp": "2025-11-13T05:23:15Z",
  "total_candidates": 5,
  "high_impact_count": 3,
  "top_scores": [68, 62, 71],
  "feedback_loop_active": true
}
```

**Git Commits:**
```bash
# All KB updates include autonomous tag
git log --oneline --grep="autonomous"
# 887136d KB: autonomous update - NYLON material guide
# 837a3ec KB: autonomous update - first layer adhesion technique
```

**Database Records:**
```sql
-- Full audit trail in database
SELECT
  g.description,
  g.status,
  g.identified_at,
  g.approved_at,
  g.approved_by,
  g.completed_at
FROM goals g
WHERE g.created_by = 'system-autonomous'
ORDER BY g.identified_at DESC;
```

### Rollback Procedures

**Emergency Disable:**
```bash
# Edit .env
AUTONOMOUS_ENABLED=false

# Restart brain
docker compose restart brain

# Verify disabled
docker logs brain | grep "Autonomous mode disabled"
```

**Revert KB Changes:**
```bash
# View recent autonomous commits
cd knowledge/
git log --oneline --grep="autonomous" | head -5

# Revert specific commit
git revert 887136d

# Or revert all autonomous changes from today
git log --since="today" --grep="autonomous" --oneline | \
  cut -d' ' -f1 | \
  xargs -I {} git revert {}
```

**Cancel Active Project:**
```bash
# Via CLI (future feature)
kitty-cli autonomy project proj_xyz789 cancel

# Via database (immediate)
docker exec -it postgres psql -U postgres -d kitty
UPDATE projects SET status = 'cancelled' WHERE id = 'proj_xyz789';
```

---

## 📈 Monitoring & Observability

### Reasoning Logs

**Watch autonomous events in real-time:**
```bash
tail -f .logs/reasoning.jsonl | jq 'select(.event | contains("autonomous")) | {event, timestamp, message}'
```

**Filter by event type:**
```bash
# Goal generation events
jq 'select(.event | contains("goal_generation"))' .logs/reasoning.jsonl

# Project generation events
jq 'select(.event | contains("project_generation"))' .logs/reasoning.jsonl

# Task execution events
jq 'select(.event | contains("task_execution"))' .logs/reasoning.jsonl

# Outcome measurement events (Phase 3)
jq 'select(.event | contains("outcome_measurement"))' .logs/reasoning.jsonl
```

### MQTT Topics

**Subscribe to autonomous updates:**
```bash
mosquitto_sub -h localhost -t "kitty/autonomy/#" -v
```

**Topics:**
- `kitty/autonomy/goal/created` - New goal identified
- `kitty/autonomy/goal/approved` - Goal approved by user
- `kitty/autonomy/goal/rejected` - Goal rejected by user
- `kitty/autonomy/project/created` - Project generated
- `kitty/autonomy/project/completed` - Project finished
- `kitty/autonomy/task/started` - Task execution began
- `kitty/autonomy/task/completed` - Task finished
- `kitty/autonomy/budget/warning` - 80% budget used
- `kitty/autonomy/budget/exhausted` - 100% budget used

### Database Queries

**Recent goals:**
```sql
SELECT
  id,
  goal_type,
  description,
  status,
  identified_at,
  approved_at
FROM goals
WHERE created_by = 'system-autonomous'
ORDER BY identified_at DESC
LIMIT 10;
```

**Active projects:**
```sql
SELECT
  p.id,
  p.title,
  p.status,
  COUNT(t.id) AS total_tasks,
  SUM(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed_tasks,
  p.budget_allocated,
  p.budget_spent
FROM projects p
LEFT JOIN tasks t ON t.project_id = p.id
WHERE p.status IN ('proposed', 'active', 'in_progress')
GROUP BY p.id;
```

**Budget usage:**
```sql
SELECT
  DATE(created_at) AS date,
  SUM(budget_spent) AS daily_cost,
  COUNT(*) AS projects_completed
FROM projects
WHERE created_by = 'system-autonomous'
  AND status = 'completed'
GROUP BY DATE(created_at)
ORDER BY date DESC
LIMIT 7;
```

**Effectiveness scores (Phase 3):**
```sql
SELECT
  goal_type,
  AVG(effectiveness_score) AS avg_effectiveness,
  COUNT(*) AS goals_measured,
  MIN(effectiveness_score) AS min_effectiveness,
  MAX(effectiveness_score) AS max_effectiveness
FROM goals
WHERE outcome_measured_at IS NOT NULL
  AND learn_from = TRUE
GROUP BY goal_type
ORDER BY avg_effectiveness DESC;
```

### Grafana Dashboards

**Autonomous Operations Dashboard:**
- Panel 1: Goals Generated per Week (time series)
- Panel 2: Goal Approval Rate (gauge: approved / total)
- Panel 3: Projects Completed per Week (time series)
- Panel 4: Budget Usage (stacked area: daily spend by goal type)
- Panel 5: Task Execution Success Rate (pie chart)
- Panel 6: Effectiveness Scores by Goal Type (bar chart, Phase 3)
- Panel 7: Active Projects (table: title, status, progress %)
- Panel 8: Recent Completions (table: goal, cost, duration)

**Access:** `http://localhost:3000/d/autonomous`

---

## 🚀 Getting Started

### Initial Setup

**1. Enable Autonomous Mode**

Edit `.env`:
```bash
# Core autonomy settings
AUTONOMOUS_ENABLED=true
AUTONOMOUS_DAILY_BUDGET_USD=5.00
AUTONOMOUS_IDLE_THRESHOLD_MINUTES=120
AUTONOMOUS_FULL_TIME_MODE=false  # Development mode (4am-6am PST)

# Phase 3: Outcome tracking (learning)
OUTCOME_MEASUREMENT_ENABLED=true
OUTCOME_MEASUREMENT_WINDOW_DAYS=30
FEEDBACK_LOOP_ENABLED=true
FEEDBACK_LOOP_MIN_SAMPLES=10

# External API keys (required for research)
PERPLEXITY_API_KEY=your_perplexity_api_key_here
```

**2. Run Database Migrations**

```bash
# Apply Phase 3 outcome tracking schema
alembic -c services/common/alembic.ini upgrade head
```

**3. Restart Services**

```bash
docker compose restart brain
```

**4. Verify Scheduler Started**

```bash
docker logs brain | grep "Autonomous scheduler"
# Expected: "Autonomous scheduler started with 7 jobs registered"
```

### First Autonomous Cycle

**Monday Morning Workflow:**

**1. KITTY Generates Goals (Monday 5:00am PST - automatic)**
```bash
# Check logs
tail -f .logs/reasoning.jsonl | jq 'select(.event == "goal_generation_completed")'
```

**2. Review Goals (Morning - manual)**
```bash
# List pending goals
kitty-cli autonomy list

# Review each goal's rationale and impact score
kitty-cli autonomy goal <goal-id>
```

**3. Approve Goals (Morning - manual)**
```bash
# Approve research goals (low-risk)
kitty-cli autonomy approve <goal-id> --notes "Approved for research"

# Reject if not aligned with current priorities
kitty-cli autonomy reject <goal-id> --notes "Defer to next quarter"
```

**4. KITTY Creates Projects (Within 4 hours - automatic)**
```bash
# Check for new projects
kitty-cli autonomy projects

# View project details
kitty-cli autonomy project <project-id>
```

**5. KITTY Executes Tasks (4am-6am PST next day - automatic)**
```bash
# Monitor task execution (next morning)
tail -f .logs/reasoning.jsonl | jq 'select(.event | contains("task_execution"))'

# Check progress
kitty-cli autonomy projects
```

**6. KITTY Completes Project (Within 2-3 days - automatic)**
```bash
# Verify completion
kitty-cli autonomy projects --status completed

# Review KB article created
ls -lah knowledge/research/
git log --oneline -5
```

**7. KITTY Measures Effectiveness (30 days later - automatic, Phase 3)**
```bash
# View effectiveness scores
kitty-cli autonomy effectiveness

# See learning adjustments
kitty-cli autonomy list
# Note: Impact scores now show adjustment_factor from feedback loop
```

---

## 🛠️ Configuration Reference

### Environment Variables

**Core Settings:**
```bash
# Enable/disable autonomy
AUTONOMOUS_ENABLED=true

# Budget control
AUTONOMOUS_DAILY_BUDGET_USD=5.00

# Idle detection (production mode)
AUTONOMOUS_IDLE_THRESHOLD_MINUTES=120      # 2 hours
AUTONOMOUS_CPU_THRESHOLD_PERCENT=20.0      # Max 20% CPU
AUTONOMOUS_MEMORY_THRESHOLD_PERCENT=70.0   # Max 70% memory

# Operating mode
AUTONOMOUS_FULL_TIME_MODE=false  # false = dev (4am-6am PST), true = prod (24/7 idle)

# User ID for autonomous operations
AUTONOMOUS_USER_ID=system-autonomous
```

**Phase 3: Learning Settings:**
```bash
# Outcome measurement
OUTCOME_MEASUREMENT_ENABLED=true
OUTCOME_MEASUREMENT_WINDOW_DAYS=30  # Measure outcomes 30 days after completion

# Feedback loop
FEEDBACK_LOOP_ENABLED=true
FEEDBACK_LOOP_MIN_SAMPLES=10      # Need 10+ goals before adjusting priorities
FEEDBACK_LOOP_ADJUSTMENT_MAX=1.5  # Maximum 1.5x priority boost/reduction
```

**External APIs:**
```bash
# Required for research goals
PERPLEXITY_API_KEY=your_key_here

# Optional for fabrication goals (Phase 4)
ZOO_API_KEY=your_key_here
TRIPO_API_KEY=your_key_here
```

### Scheduler Configuration

**Job Schedules (PST):**
```
daily_health_check:          4:00am daily
weekly_research_cycle:       Monday 5:00am (goal generation)
knowledge_base_update:       Monday 6:00am
printer_fleet_health_check:  Every 4 hours
project_generation_cycle:    Every 4 hours (4am-6am PST in dev mode)
task_execution_cycle:        Every 15 minutes (4am-6am PST in dev mode)
outcome_measurement_cycle:   6:00am daily (Phase 3)
```

**Modify Schedules (advanced):**

Edit `services/brain/src/brain/app.py`:
```python
# Change weekly_research_cycle to daily
scheduler.add_cron_job(
    func=weekly_research_cycle,
    hour=13,  # 5am PST = 13:00 UTC
    minute=0,
    job_id="daily_research_cycle",  # Renamed
)
```

---

## 🐛 Troubleshooting

### Goals Not Being Generated

**Symptom:** No goals appear on Monday morning

**Diagnosis:**
```bash
# Check scheduler status
kitty-cli autonomy status

# Verify job ran
grep "weekly_research_cycle" .logs/reasoning.jsonl | tail -5

# Check resource availability
kitty-cli autonomy status
# Look for: Budget Available, System Idle status
```

**Solutions:**

1. **Budget Exhausted:**
```bash
# Increase budget
echo "AUTONOMOUS_DAILY_BUDGET_USD=10.00" >> .env
docker compose restart brain
```

2. **Scheduler Not Running:**
```bash
# Verify AUTONOMOUS_ENABLED=true in .env
docker exec brain env | grep AUTONOMOUS_ENABLED

# Restart brain
docker compose restart brain

# Check logs
docker logs brain | grep "Autonomous scheduler started"
```

3. **No Opportunities Found:**
```bash
# Check if there's data to analyze
docker exec -it postgres psql -U postgres -d kitty
SELECT COUNT(*) FROM print_monitor_events;
SELECT COUNT(*) FROM routing_decisions;

# If no data, seed some test data (development only)
# See: tests/integration/test_autonomous_integration.py for examples
```

### Projects Not Being Created

**Symptom:** Goal approved but no project created

**Diagnosis:**
```bash
# Check project generation logs
grep "project_generation_cycle" .logs/reasoning.jsonl | tail -10

# Verify goal is approved
kitty-cli autonomy list --status approved

# Check time window (dev mode only)
date  # Verify current time is 4am-6am PST
```

**Solutions:**

1. **Outside Time Window (Dev Mode):**
```bash
# Wait for next 4am-6am PST window
# OR manually trigger (testing only)
docker exec -it brain python -c "
from services.brain.src.brain.autonomous.jobs import project_generation_cycle
import asyncio
asyncio.run(project_generation_cycle())
"
```

2. **Project Already Exists:**
```bash
# Check database
docker exec -it postgres psql -U postgres -d kitty
SELECT * FROM projects WHERE goal_id = '<goal-id>';

# If project exists, view via CLI
kitty-cli autonomy projects
```

### Tasks Not Executing

**Symptom:** Project created but tasks stuck at "pending"

**Diagnosis:**
```bash
# Check task execution logs
grep "task_execution_cycle" .logs/reasoning.jsonl | tail -10

# Verify task dependencies
docker exec -it postgres psql -U postgres -d kitty
SELECT id, title, status, depends_on FROM tasks WHERE project_id = '<project-id>';
```

**Solutions:**

1. **Dependency Not Met:**
```bash
# Task 2 waits for Task 1 to complete
# Check if previous task failed:
SELECT * FROM tasks WHERE id = '<depends_on-task-id>';

# If failed, view logs for error
grep "task_id.*<task-id>" .logs/reasoning.jsonl
```

2. **Outside Time Window:**
```bash
# Same as project generation - wait for 4am-6am PST
# OR switch to production mode (if ready)
echo "AUTONOMOUS_FULL_TIME_MODE=true" >> .env
docker compose restart brain
```

3. **API Key Missing:**
```bash
# Check Perplexity API key
docker exec brain env | grep PERPLEXITY_API_KEY

# Add to .env if missing
echo "PERPLEXITY_API_KEY=your_key" >> .env
docker compose restart brain
```

### Budget Exhausted Unexpectedly

**Symptom:** Budget exhausted mid-cycle

**Diagnosis:**
```bash
# Check 7-day spending
kitty-cli autonomy status

# View per-project costs
docker exec -it postgres psql -U postgres -d kitty
SELECT
  title,
  budget_allocated,
  budget_spent,
  status
FROM projects
WHERE DATE(created_at) = CURRENT_DATE;
```

**Solutions:**

1. **Increase Daily Budget:**
```bash
echo "AUTONOMOUS_DAILY_BUDGET_USD=10.00" >> .env
docker compose restart brain
```

2. **Investigate High-Cost Projects:**
```bash
# Find expensive projects
docker exec -it postgres psql -U postgres -d kitty
SELECT
  title,
  budget_spent,
  status
FROM projects
WHERE budget_spent > 5.0
ORDER BY budget_spent DESC
LIMIT 10;

# Check task costs
SELECT
  t.title,
  t.task_metadata->>'cost_usd' AS cost,
  t.status
FROM tasks t
JOIN projects p ON p.id = t.project_id
WHERE p.budget_spent > 5.0;
```

### Knowledge Base Articles Not Created

**Symptom:** Project completes but no KB article found

**Diagnosis:**
```bash
# Check kb_create task status
docker exec -it postgres psql -U postgres -d kitty
SELECT
  t.title,
  t.status,
  t.task_result
FROM tasks t
WHERE t.task_metadata->>'task_type' = 'kb_create'
ORDER BY t.updated_at DESC
LIMIT 5;

# Check git commits
cd knowledge/
git log --oneline --since="1 week ago" --grep="autonomous"
```

**Solutions:**

1. **Task Failed:**
```bash
# Check task error
grep "kb_create.*failed" .logs/reasoning.jsonl

# Common issues:
# - Invalid YAML frontmatter
# - File path permissions
# - Missing directory (knowledge/research/)
```

2. **Git Commit Failed:**
```bash
# Check review_commit task
grep "review_commit" .logs/reasoning.jsonl | tail -5

# Manually verify file exists
ls -lah knowledge/research/

# If file exists but not committed:
cd knowledge/
git add research/*.md
git commit -m "Manual commit: autonomous KB article"
```

---

## 📞 Support & Contact

### Getting Help

**Documentation:**
- This guide: `docs/KITTY_AUTONOMOUS_OPERATIONS_GUIDE.md`
- Implementation details: `docs/AUTONOMOUS_SYSTEM_IMPLEMENTATION.md`
- Progress updates: `docs/AUTONOMOUS_PROGRESS_UPDATE.md`
- Phase 3 design: `docs/Phase3_Outcome_Tracking_Design.md`

**Logs:**
- Reasoning logs: `.logs/reasoning.jsonl`
- Application logs: `docker logs brain -f`
- Test logs: `.logs/test-autonomous.log`

**Database:**
```bash
# PostgreSQL access
docker exec -it postgres psql -U postgres -d kitty

# Useful queries
\dt goals projects tasks  # List tables
SELECT * FROM goals ORDER BY identified_at DESC LIMIT 10;
```

**Issue Reporting:**
```bash
# Gather diagnostic info
./ops/scripts/autonomous-diagnostic.sh

# Output includes:
# - Scheduler status
# - Recent logs (last 100 lines)
# - Budget status
# - Active jobs
# - Database counts

# Attach to GitHub issue
```

### Feature Requests

**Current Capabilities (Phases 1-3):**
- ✅ Autonomous goal generation
- ✅ Human-in-the-loop approval workflow
- ✅ Project and task execution
- ✅ Research with Perplexity integration
- ✅ Knowledge base auto-updates
- ✅ Git automation
- ✅ Outcome tracking and learning (Phase 3)
- ✅ Effectiveness scoring
- ✅ Feedback loop for continuous improvement

**Coming Soon (Phase 4):**
- ⏳ CAD generation and printing
- ⏳ Multi-week project tracking
- ⏳ 48h auto-approve for research goals
- ⏳ Enhanced web UI with timeline view
- ⏳ Fabrication execution with safety checks

---

## 🎉 Success Stories

### Example 1: NYLON Material Research

**Timeline:**
- **Monday 5:00am**: Goal generated (impact score: 62)
- **Monday 8:45am**: User approved via CLI
- **Monday 12:30pm**: Project created with 4 tasks
- **Tuesday 4:15am**: Task 1 completed (Perplexity research)
- **Tuesday 4:45am**: Task 2 completed (synthesis)
- **Tuesday 5:10am**: Task 3 completed (KB article created)
- **Tuesday 5:12am**: Task 4 completed (git commit)

**Outcome:**
- KB article: `knowledge/materials/nylon-material-guide.md`
- Cost: $1.35 (under $1.50 budget)
- Duration: 57 minutes (under 3-hour estimate)
- Commit: `887136d KB: autonomous update - NYLON material guide`

**30-Day Effectiveness (Phase 3):**
- Views: 23 (good adoption)
- References: 5 (cited in other articles)
- Time saved: ~15 hours (engineers self-served)
- Effectiveness score: 85 / 100 (excellent)

**Learning Impact:**
- Research goals adjustment: 1.0x → 1.15x (boosted by 15%)
- Future material research goals prioritized higher

### Example 2: First Layer Failure Reduction

**Timeline:**
- **Monday 5:00am**: Goal generated (impact score: 68)
- **Monday 9:00am**: User approved
- **Monday 12:30pm**: Project created with 2 tasks
- **Tuesday 4:20am**: Task 1 completed (research)
- **Tuesday 4:35am**: Task 2 completed (technique update)

**Outcome:**
- Updated: `knowledge/techniques/first-layer-adhesion.md`
- Added: New troubleshooting section with 5 solutions
- Cost: $1.20 (under $2.50 budget)
- Commit: `837a3ec KB: autonomous update - first layer adhesion technique`

**30-Day Effectiveness (Phase 3):**
- Baseline failures: 8 in 30 days (before update)
- Post-update failures: 2 in 30 days (75% reduction!)
- Failure rate: 15% → 4% (excellent improvement)
- Effectiveness score: 78 / 100 (good)

**Learning Impact:**
- Improvement goals adjustment: 1.0x → 1.05x (slight boost)
- High-ROI pattern detected for failure-reduction goals

---

## 🚦 Quick Start Checklist

**Initial Setup:**
- [ ] Edit `.env`: Set `AUTONOMOUS_ENABLED=true`
- [ ] Add Perplexity API key to `.env`
- [ ] Run database migrations: `alembic upgrade head`
- [ ] Restart brain service: `docker compose restart brain`
- [ ] Verify scheduler: `docker logs brain | grep "7 jobs"`

**First Monday:**
- [ ] Wait for goal generation (5:00am PST automatic)
- [ ] Review goals: `kitty-cli autonomy list`
- [ ] Approve/reject: `kitty-cli autonomy approve <id>`
- [ ] Monitor project creation (within 4 hours)

**Ongoing Management:**
- [ ] Check status weekly: `kitty-cli autonomy status`
- [ ] Review effectiveness: `kitty-cli autonomy effectiveness` (after 30 days)
- [ ] Monitor budget: `kitty-cli autonomy status`
- [ ] Review KB articles: `ls knowledge/research/`

**Troubleshooting:**
- [ ] Check logs: `tail -f .logs/reasoning.jsonl`
- [ ] Verify budget: `kitty-cli autonomy status`
- [ ] Test manually: See "Troubleshooting" section

---

**🤖 KITTY is ready to work autonomously! Start by approving your first goal and watch KITTY improve your fabrication workflow while you sleep.** ✨

**Questions? Check the troubleshooting section or review the reasoning logs for detailed execution traces.**
