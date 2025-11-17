# KITTY Autonomous Calendar Schedule Management

**Date:** 2025-11-17
**Status:** Design Proposal
**System Health:** 92/100 (Production Ready)

---

## Executive Summary

This document proposes a **Calendar Schedule Management Tool** for KITTY's autonomous jobs, enabling users to naturally and intuitively manage when, how, and under what conditions KITTY performs autonomous work. The design prioritizes user-friendliness, budget awareness, and seamless integration with KITTY's existing production-ready infrastructure.

---

## 1. Current State Analysis

### 1.1 Existing Autonomous Job System

**Backend Infrastructure (✅ Production Ready):**
- **APScheduler** with PostgreSQL job store (persists across restarts)
- **Distributed locking** via Redis (prevents race conditions)
- **RabbitMQ** message queue for async task distribution
- **Budget tracking** via BudgetManager ($5/day default ceiling)
- **Resource management** via ResourceManager (CPU/memory/budget checks)

**Current Jobs (7 total):**

| Job ID | Schedule | Purpose | Budget Impact |
|--------|----------|---------|---------------|
| `daily_health_check` | 12:00 UTC (4:00 AM PST) | System health audit | Free (local only) |
| `weekly_research_cycle` | Mon 13:00 UTC (5:00 AM PST) | Goal identification | Medium ($0.10-$0.50) |
| `project_generation_cycle` | 12:30 UTC (4:30 AM PST) | Create project proposals | Free (local) |
| `task_execution_cycle` | Every 15 min | Execute ready tasks | Varies by task |
| `printer_fleet_health_check` | Every 4 hours | Ping connected printers | Free (local) |
| `knowledge_base_update` | Mon 14:00 UTC (6:00 AM PST) | Refresh RAG knowledge | Low ($0.05-$0.15) |
| `outcome_measurement_cycle` | 14:00 UTC (6:00 AM PST) | Measure effectiveness | Free (local) |

**Issues with Current System:**
1. ❌ **No visual interface** - jobs configured via `.env` or code only
2. ❌ **Inflexible scheduling** - cron expressions are not user-friendly
3. ❌ **No calendar view** - can't see upcoming jobs at a glance
4. ❌ **No natural language** - can't say "run research on Monday mornings"
5. ❌ **Poor budget visibility** - users don't know when budget will be consumed
6. ❌ **No historical context** - can't see what ran when, or why it succeeded/failed

---

## 2. Design Goals

### 2.1 User Experience Principles

1. **Natural Language First**
   - "Run weekly research every Monday morning"
   - "Pause all autonomous jobs this weekend"
   - "Schedule a deep research session on multi-material printing tomorrow at 2 PM"

2. **Visual Calendar Interface**
   - Month/week/day views with color-coded job types
   - Drag-and-drop scheduling
   - Conflict detection (overlapping budget-heavy jobs)

3. **Budget Awareness**
   - Visual budget forecast (daily/weekly/monthly)
   - Color coding: green (free), yellow (low cost), red (high cost)
   - Budget alerts before job execution

4. **Intelligent Defaults**
   - Suggest optimal times (e.g., night/early morning for research)
   - Batch similar jobs to minimize context switching
   - Avoid scheduling during high-activity periods

5. **Controllability**
   - One-click enable/disable for any job
   - Temporary pause (skip next N executions)
   - Override budget limits for specific jobs

---

## 3. System Architecture

### 3.1 Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Calendar Schedule UI                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ Calendar View│  │ Job Editor   │  │ Budget View  │         │
│  │ (Month/Week) │  │ (NL + Visual)│  │ (Forecast)   │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                  │                  │                  │
└─────────┼──────────────────┼──────────────────┼─────────────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│              Calendar Schedule Service (Brain)                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Schedule Manager                                          │  │
│  │ • CRUD operations on jobs                                │  │
│  │ • Natural language parsing (NL → cron)                   │  │
│  │ • Conflict detection                                     │  │
│  │ • Budget forecasting                                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ APScheduler Integration                                   │  │
│  │ • Add/remove/update jobs                                 │  │
│  │ • Execute callbacks                                      │  │
│  │ • Job state persistence (PostgreSQL)                     │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Data Layer (PostgreSQL)                        │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────────┐ │
│  │ apscheduler_   │  │ job_execution_ │  │ budget_tracking  │ │
│  │ jobs (existing)│  │ history (new)  │  │ (existing)       │ │
│  └────────────────┘  └────────────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 New Database Schema

```sql
-- Track job execution history for calendar display
CREATE TABLE job_execution_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id VARCHAR(255) NOT NULL,  -- APScheduler job ID
    job_name VARCHAR(255) NOT NULL,
    execution_time TIMESTAMPTZ NOT NULL,
    duration_seconds FLOAT,
    status VARCHAR(50) NOT NULL,  -- 'success', 'failed', 'skipped', 'budget_exceeded'
    budget_spent_usd DECIMAL(10, 4),
    error_message TEXT,
    result_summary JSONB,  -- Summary of what was accomplished
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_job_execution_time (job_id, execution_time),
    INDEX idx_status (status)
);

-- Track user-defined schedules with natural language
CREATE TABLE autonomous_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    job_type VARCHAR(100) NOT NULL,  -- 'research', 'health_check', 'project_generation', etc.
    job_name VARCHAR(255) NOT NULL,
    description TEXT,
    natural_language_schedule TEXT,  -- "Every Monday at 5 AM"
    cron_expression VARCHAR(100),
    timezone VARCHAR(50) DEFAULT 'UTC',
    enabled BOOLEAN DEFAULT TRUE,
    budget_limit_usd DECIMAL(10, 4),
    priority INT DEFAULT 5,  -- 1 (low) to 10 (high)
    tags TEXT[],  -- ['weekly', 'research', 'fabrication']
    metadata JSONB,  -- Job-specific config
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    last_execution_at TIMESTAMPTZ,
    next_execution_at TIMESTAMPTZ,

    INDEX idx_user_schedules (user_id, enabled),
    INDEX idx_next_execution (next_execution_at)
);

-- Track budget forecasts
CREATE TABLE budget_forecasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    forecast_date DATE NOT NULL,
    total_scheduled_jobs INT,
    estimated_cost_usd DECIMAL(10, 4),
    actual_cost_usd DECIMAL(10, 4),
    daily_limit_usd DECIMAL(10, 4) DEFAULT 5.00,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (forecast_date)
);
```

---

## 4. User Interface Design

### 4.1 Calendar View (Primary Interface)

**Month View:**
```
┌─────────────────────────────────────────────────────────────────┐
│  ◀ November 2025 ▶           [Week] [Day] [List]    Budget: ✅  │
├─────────────────────────────────────────────────────────────────┤
│  Sun    Mon    Tue    Wed    Thu    Fri    Sat                 │
├─────────────────────────────────────────────────────────────────┤
│         1      2      3      4      5      6                    │
│         🔍     ✓      ✓      ✓      ✓      ✓                   │
│                                                                  │
│  7      8      9      10     11     12     13                   │
│  ✓      🔍     ✓      ✓      ✓      ✓      ✓                   │
│         📊                                                       │
│                                                                  │
│  14     15     16     17     18     19     20                   │
│  ✓      ✓      ✓      ⚠️     ✓      ✓      ✓                   │
│                     (Today)                                      │
│                                                                  │
│  21     22     23     24     25     26     27                   │
│  ✓      🔍     ✓      ✓      ✓      ✓      ✓                   │
│                                                                  │
│  28     29     30                                                │
│  ✓      ✓      ✓                                                │
└─────────────────────────────────────────────────────────────────┘

Legend:
🔍 Weekly Research (Mon 5 AM)    📊 Knowledge Base Update (Mon 6 AM)
✓  Daily Health Check (4 AM)     ⚠️  Budget warning (>80% projected)
```

**Day View (Drill-down):**
```
┌─────────────────────────────────────────────────────────────────┐
│  Monday, November 17, 2025       Budget: $0.45 / $5.00 (9%) ✅  │
├─────────────────────────────────────────────────────────────────┤
│  12:00 AM                                                        │
│  01:00 AM                                                        │
│  02:00 AM                                                        │
│  03:00 AM                                                        │
│  04:00 AM  ┌──────────────────────────────────────┐            │
│            │ 🟢 Daily Health Check                 │            │
│            │ Status: Scheduled                     │            │
│            │ Cost: Free                            │            │
│            │ Duration: ~2 min                      │            │
│            └──────────────────────────────────────┘            │
│  05:00 AM  ┌──────────────────────────────────────┐            │
│            │ 🟡 Weekly Research Cycle              │            │
│            │ Status: Enabled                       │            │
│            │ Est. Cost: $0.15 - $0.50              │            │
│            │ Duration: ~20 min                     │            │
│            │ [View Details] [Edit] [Pause]         │            │
│            └──────────────────────────────────────┘            │
│  06:00 AM  ┌──────────────────────────────────────┐            │
│            │ 🟢 Knowledge Base Update              │            │
│            │ Status: Enabled                       │            │
│            │ Cost: $0.05 - $0.15                   │            │
│            │ Duration: ~10 min                     │            │
│            └──────────────────────────────────────┘            │
│  ...                                                             │
│  02:00 PM  ┌──────────────────────────────────────┐            │
│            │ 🟢 Outcome Measurement                │            │
│            │ Status: Scheduled                     │            │
│            │ Cost: Free                            │            │
│            │ Duration: ~5 min                      │            │
│            └──────────────────────────────────────┘            │
│                                                                  │
│  [+ Add Job]  [Natural Language: "Schedule..."]                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Job Editor (Modal/Sidebar)

**Create/Edit Job Interface:**
```
┌─────────────────────────────────────────────────────────────────┐
│  Create Autonomous Job                                     [×]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Natural Language Input:                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Run a deep research session every weekday at 3 AM        │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ✓ Parsed: "Every weekday at 3:00 AM PST"                      │
│                                                                  │
│  Job Type:                                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ [▼] Research Session                                      │  │
│  │     • Health Check                                        │  │
│  │     • Research Session                                    │  │
│  │     • Project Generation                                  │  │
│  │     • Knowledge Base Update                               │  │
│  │     • Custom Task                                         │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Configuration:                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Research Query: [Multi-material 3D printing advances]    │  │
│  │ Strategy: [▼] Hybrid                                      │  │
│  │ Quality Target: [0.80] ──────●──── (0.0 - 1.0)           │  │
│  │ Budget Limit: [$0.50] per execution                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Schedule:                                                      │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Cron: [0 3 * * 1-5]                                       │  │
│  │ Timezone: [PST] ▼                                         │  │
│  │ Next 3 runs:                                              │  │
│  │   • Mon Nov 18, 2025 at 3:00 AM PST                       │  │
│  │   • Tue Nov 19, 2025 at 3:00 AM PST                       │  │
│  │   • Wed Nov 20, 2025 at 3:00 AM PST                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Advanced:                                                      │
│  ☑ Enabled                                                      │
│  ☐ Skip if budget exceeded                                      │
│  ☑ Send notification on completion                              │
│  Priority: [5] ───●─── (1-10)                                   │
│                                                                  │
│  [Cancel]                            [Save Job]                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 Budget Dashboard

```
┌─────────────────────────────────────────────────────────────────┐
│  Budget Overview - November 2025                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Daily Budget: $5.00                                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Today: $0.45 / $5.00 (9%) ████░░░░░░░░░░░░░░░░░░░░░      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Monthly Forecast: $18.50 / $155.00 (12%)                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Nov 1-17: $18.50                                          │  │
│  │ Nov 18-30 (projected): $16.25                             │  │
│  │ Total: $34.75 ███░░░░░░░░░░░░░░░░░░░░░░░░░░░            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Cost Breakdown by Job Type:                                    │
│  ┌────────────────────────────────┬─────────┬──────────────┐   │
│  │ Job Type                       │ Count   │ Total Cost   │   │
│  ├────────────────────────────────┼─────────┼──────────────┤   │
│  │ Weekly Research Cycle          │ 3       │ $12.50       │   │
│  │ Knowledge Base Update          │ 3       │ $3.00        │   │
│  │ Custom Research (User)         │ 2       │ $3.00        │   │
│  │ Daily Health Check             │ 17      │ $0.00        │   │
│  │ Task Execution                 │ 1,632   │ $0.00        │   │
│  └────────────────────────────────┴─────────┴──────────────┘   │
│                                                                  │
│  Top Spenders This Week:                                        │
│  1. Weekly Research (Mon 5 AM) - $4.50 (GPT-5 escalation)       │
│  2. Knowledge Base Update (Mon 6 AM) - $1.50                    │
│  3. Custom Research (Tue 2 PM) - $1.50                          │
│                                                                  │
│  [Export CSV] [Adjust Daily Limit] [View Full History]         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Natural Language Processing

### 5.1 Supported Patterns

The system will parse natural language scheduling commands using a combination of:
- **spaCy** for entity extraction
- **dateparser** for datetime parsing
- **Custom regex patterns** for domain-specific phrases

**Examples:**

| User Input | Parsed Schedule | Cron Expression |
|------------|-----------------|-----------------|
| "Run research every Monday at 5 AM" | Every Monday 05:00 PST | `0 5 * * 1` |
| "Daily health check at 4 AM" | Every day 04:00 PST | `0 4 * * *` |
| "Check printers every 4 hours" | Every 4 hours | `0 */4 * * *` |
| "Research session weekdays at 3 AM" | Mon-Fri 03:00 PST | `0 3 * * 1-5` |
| "Update knowledge base first Monday of month" | First Monday 06:00 PST | `0 6 1-7 * 1` |
| "Pause all jobs this weekend" | (Disable jobs for Sat-Sun) | N/A (temp disable) |

### 5.2 NL Parsing Implementation

```python
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import dateparser
from croniter import croniter

class NaturalLanguageScheduler:
    """Parse natural language into cron expressions."""

    PATTERNS = {
        r"every (\w+) at (\d{1,2})(:\d{2})?\s*(am|pm)?": "weekly_time",
        r"every (\d+) (hour|minute|day|week)s?": "interval",
        r"(daily|every day) at (\d{1,2})(:\d{2})?\s*(am|pm)?": "daily_time",
        r"weekdays at (\d{1,2})(:\d{2})?\s*(am|pm)?": "weekday_time",
        r"first (\w+) of (?:the )?month": "monthly_first",
    }

    def parse(self, text: str, timezone: str = "PST") -> Dict[str, Any]:
        """
        Parse natural language into schedule config.

        Returns:
            {
                "cron": "0 5 * * 1",
                "timezone": "PST",
                "description": "Every Monday at 5:00 AM PST",
                "next_run": datetime(2025, 11, 18, 5, 0),
                "confidence": 0.95
            }
        """
        text_lower = text.lower().strip()

        # Try each pattern
        for pattern, handler_name in self.PATTERNS.items():
            match = re.match(pattern, text_lower)
            if match:
                handler = getattr(self, f"_handle_{handler_name}")
                return handler(match, timezone)

        # Fallback: Use dateparser
        return self._handle_freeform(text, timezone)

    def _handle_weekly_time(self, match, timezone: str):
        """Handle: 'every Monday at 5 AM'"""
        day = match.group(1)
        hour = int(match.group(2))
        minute = match.group(3) or ":00"
        ampm = match.group(4) or ""

        # Convert day name to cron day (0=Sun, 6=Sat)
        day_map = {"monday": 1, "tuesday": 2, "wednesday": 3,
                   "thursday": 4, "friday": 5, "saturday": 6, "sunday": 0}
        day_num = day_map.get(day, 1)

        # Handle 12-hour time
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

        minute = int(minute.strip(":"))
        cron = f"{minute} {hour} * * {day_num}"

        return {
            "cron": cron,
            "timezone": timezone,
            "description": f"Every {day.capitalize()} at {hour}:{minute:02d} {timezone}",
            "next_run": self._get_next_run(cron, timezone),
            "confidence": 0.95
        }

    def _get_next_run(self, cron: str, timezone: str) -> datetime:
        """Calculate next execution time."""
        import pytz
        tz = pytz.timezone("US/Pacific" if timezone == "PST" else "UTC")
        now = datetime.now(tz)
        iter = croniter(cron, now)
        return iter.get_next(datetime)
```

---

## 6. API Endpoints

### 6.1 Schedule Management API

```python
# services/brain/src/brain/routes/autonomy_calendar.py

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, date

router = APIRouter(prefix="/api/autonomy/calendar", tags=["autonomy"])

# ============================================================================
# Request/Response Models
# ============================================================================

class ScheduleCreateRequest(BaseModel):
    """Create a new autonomous job schedule."""
    job_type: str  # 'research', 'health_check', 'project_generation', etc.
    job_name: str
    description: Optional[str] = None
    natural_language_schedule: Optional[str] = None  # "Every Monday at 5 AM"
    cron_expression: Optional[str] = None  # Explicit cron if NL not provided
    timezone: str = "PST"
    budget_limit_usd: Optional[float] = None
    priority: int = 5
    enabled: bool = True
    metadata: Optional[dict] = None

class ScheduleUpdateRequest(BaseModel):
    """Update an existing schedule."""
    job_name: Optional[str] = None
    description: Optional[str] = None
    natural_language_schedule: Optional[str] = None
    cron_expression: Optional[str] = None
    timezone: Optional[str] = None
    budget_limit_usd: Optional[float] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None
    metadata: Optional[dict] = None

class ScheduleResponse(BaseModel):
    """Schedule details."""
    id: str
    user_id: str
    job_type: str
    job_name: str
    description: Optional[str]
    natural_language_schedule: Optional[str]
    cron_expression: str
    timezone: str
    enabled: bool
    budget_limit_usd: Optional[float]
    priority: int
    tags: List[str]
    metadata: dict
    created_at: datetime
    updated_at: datetime
    last_execution_at: Optional[datetime]
    next_execution_at: Optional[datetime]

class ExecutionHistoryResponse(BaseModel):
    """Job execution record."""
    id: str
    job_id: str
    job_name: str
    execution_time: datetime
    duration_seconds: float
    status: str  # 'success', 'failed', 'skipped', 'budget_exceeded'
    budget_spent_usd: Optional[float]
    error_message: Optional[str]
    result_summary: Optional[dict]

class BudgetForecastResponse(BaseModel):
    """Budget forecast for a time period."""
    forecast_date: date
    total_scheduled_jobs: int
    estimated_cost_usd: float
    actual_cost_usd: Optional[float]
    daily_limit_usd: float

# ============================================================================
# Endpoints
# ============================================================================

@router.post("/schedules", response_model=ScheduleResponse)
async def create_schedule(req: ScheduleCreateRequest, user_id: str = Depends(get_current_user)):
    """
    Create a new autonomous job schedule.

    Supports natural language input:
    - "Run research every Monday at 5 AM"
    - "Check printers every 4 hours"
    - "Daily health check at 4 AM"

    Or explicit cron expressions:
    - "0 5 * * 1" (Monday 5 AM)
    """
    # Parse natural language if provided
    if req.natural_language_schedule:
        nl_parser = NaturalLanguageScheduler()
        parsed = nl_parser.parse(req.natural_language_schedule, req.timezone)
        cron = parsed["cron"]
        next_run = parsed["next_run"]
    elif req.cron_expression:
        cron = req.cron_expression
        next_run = _get_next_run(cron, req.timezone)
    else:
        raise HTTPException(400, "Must provide either natural_language_schedule or cron_expression")

    # Create schedule in database
    schedule = await db.autonomous_schedules.create({
        "user_id": user_id,
        "job_type": req.job_type,
        "job_name": req.job_name,
        "description": req.description,
        "natural_language_schedule": req.natural_language_schedule,
        "cron_expression": cron,
        "timezone": req.timezone,
        "enabled": req.enabled,
        "budget_limit_usd": req.budget_limit_usd,
        "priority": req.priority,
        "metadata": req.metadata or {},
        "next_execution_at": next_run,
    })

    # Register with APScheduler
    if req.enabled:
        await scheduler_manager.add_job(
            job_id=schedule.id,
            func=execute_autonomous_job,
            trigger="cron",
            **_parse_cron(cron),
            timezone=req.timezone,
            kwargs={"schedule_id": schedule.id}
        )

    return ScheduleResponse(**schedule.dict())

@router.get("/schedules", response_model=List[ScheduleResponse])
async def list_schedules(
    user_id: str = Depends(get_current_user),
    enabled: Optional[bool] = None,
    job_type: Optional[str] = None
):
    """List all schedules for current user."""
    filters = {"user_id": user_id}
    if enabled is not None:
        filters["enabled"] = enabled
    if job_type:
        filters["job_type"] = job_type

    schedules = await db.autonomous_schedules.find_many(filters)
    return [ScheduleResponse(**s.dict()) for s in schedules]

@router.get("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(schedule_id: str, user_id: str = Depends(get_current_user)):
    """Get details of a specific schedule."""
    schedule = await db.autonomous_schedules.find_one({"id": schedule_id, "user_id": user_id})
    if not schedule:
        raise HTTPException(404, "Schedule not found")
    return ScheduleResponse(**schedule.dict())

@router.patch("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: str,
    req: ScheduleUpdateRequest,
    user_id: str = Depends(get_current_user)
):
    """Update an existing schedule."""
    schedule = await db.autonomous_schedules.find_one({"id": schedule_id, "user_id": user_id})
    if not schedule:
        raise HTTPException(404, "Schedule not found")

    updates = req.dict(exclude_unset=True)

    # Re-parse natural language if changed
    if "natural_language_schedule" in updates and updates["natural_language_schedule"]:
        nl_parser = NaturalLanguageScheduler()
        parsed = nl_parser.parse(
            updates["natural_language_schedule"],
            updates.get("timezone", schedule.timezone)
        )
        updates["cron_expression"] = parsed["cron"]
        updates["next_execution_at"] = parsed["next_run"]

    # Update database
    updated = await db.autonomous_schedules.update(schedule_id, updates)

    # Update APScheduler
    if "enabled" in updates or "cron_expression" in updates:
        await scheduler_manager.reschedule_job(
            job_id=schedule_id,
            trigger="cron",
            **_parse_cron(updated.cron_expression),
            timezone=updated.timezone
        )

    return ScheduleResponse(**updated.dict())

@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str, user_id: str = Depends(get_current_user)):
    """Delete a schedule."""
    schedule = await db.autonomous_schedules.find_one({"id": schedule_id, "user_id": user_id})
    if not schedule:
        raise HTTPException(404, "Schedule not found")

    # Remove from APScheduler
    await scheduler_manager.remove_job(schedule_id)

    # Delete from database
    await db.autonomous_schedules.delete(schedule_id)

    return {"status": "deleted", "id": schedule_id}

@router.post("/schedules/{schedule_id}/pause")
async def pause_schedule(
    schedule_id: str,
    skip_executions: int = 1,
    user_id: str = Depends(get_current_user)
):
    """
    Temporarily pause a schedule.

    Args:
        skip_executions: Number of executions to skip (default: 1)
    """
    schedule = await db.autonomous_schedules.find_one({"id": schedule_id, "user_id": user_id})
    if not schedule:
        raise HTTPException(404, "Schedule not found")

    # Calculate resume time
    next_runs = _get_next_n_runs(schedule.cron_expression, schedule.timezone, skip_executions + 1)
    resume_at = next_runs[-1]

    # Pause in APScheduler
    await scheduler_manager.pause_job(schedule_id)

    # Update database
    await db.autonomous_schedules.update(schedule_id, {
        "enabled": False,
        "metadata": {
            **schedule.metadata,
            "paused_until": resume_at.isoformat(),
            "paused_by": "user"
        }
    })

    return {
        "status": "paused",
        "resume_at": resume_at,
        "skipped_executions": skip_executions
    }

@router.post("/schedules/{schedule_id}/resume")
async def resume_schedule(schedule_id: str, user_id: str = Depends(get_current_user)):
    """Resume a paused schedule."""
    schedule = await db.autonomous_schedules.find_one({"id": schedule_id, "user_id": user_id})
    if not schedule:
        raise HTTPException(404, "Schedule not found")

    # Resume in APScheduler
    await scheduler_manager.resume_job(schedule_id)

    # Update database
    metadata = schedule.metadata.copy()
    metadata.pop("paused_until", None)
    metadata.pop("paused_by", None)

    await db.autonomous_schedules.update(schedule_id, {
        "enabled": True,
        "metadata": metadata
    })

    return {"status": "resumed", "next_run": _get_next_run(schedule.cron_expression, schedule.timezone)}

@router.get("/history", response_model=List[ExecutionHistoryResponse])
async def get_execution_history(
    user_id: str = Depends(get_current_user),
    job_type: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[str] = None,
    limit: int = 100
):
    """Get execution history for all jobs."""
    filters = {}

    if job_type:
        # Get all schedule IDs for this job type
        schedules = await db.autonomous_schedules.find_many({"user_id": user_id, "job_type": job_type})
        filters["job_id"] = {"$in": [s.id for s in schedules]}

    if start_date:
        filters["execution_time"] = {"$gte": start_date}
    if end_date:
        filters.setdefault("execution_time", {})["$lte"] = end_date
    if status:
        filters["status"] = status

    history = await db.job_execution_history.find_many(filters, limit=limit, order_by="-execution_time")
    return [ExecutionHistoryResponse(**h.dict()) for h in history]

@router.get("/budget/forecast", response_model=List[BudgetForecastResponse])
async def get_budget_forecast(
    start_date: date,
    end_date: date,
    user_id: str = Depends(get_current_user)
):
    """
    Get budget forecast for a date range.

    Estimates cost based on:
    - Historical execution costs
    - Scheduled jobs
    - Average cost per job type
    """
    # Get all enabled schedules
    schedules = await db.autonomous_schedules.find_many({"user_id": user_id, "enabled": True})

    # Get historical costs for estimation
    history = await db.job_execution_history.find_many({
        "execution_time": {"$gte": start_date - timedelta(days=30)}
    })

    # Calculate average cost per job type
    cost_by_type = {}
    for h in history:
        if h.budget_spent_usd and h.budget_spent_usd > 0:
            schedule = await db.autonomous_schedules.find_one({"id": h.job_id})
            if schedule:
                cost_by_type.setdefault(schedule.job_type, []).append(h.budget_spent_usd)

    avg_cost_by_type = {
        job_type: sum(costs) / len(costs)
        for job_type, costs in cost_by_type.items()
    }

    # Build forecast
    forecasts = []
    current_date = start_date

    while current_date <= end_date:
        total_jobs = 0
        estimated_cost = 0.0

        for schedule in schedules:
            # Count executions on this date
            executions = _count_executions_on_date(
                schedule.cron_expression,
                schedule.timezone,
                current_date
            )
            total_jobs += executions

            # Estimate cost
            avg_cost = avg_cost_by_type.get(schedule.job_type, 0.0)
            if schedule.budget_limit_usd:
                avg_cost = min(avg_cost, schedule.budget_limit_usd)

            estimated_cost += executions * avg_cost

        # Get actual cost if date has passed
        actual_cost = None
        if current_date < date.today():
            actual = await db.job_execution_history.aggregate([
                {"$match": {
                    "execution_time": {
                        "$gte": datetime.combine(current_date, datetime.min.time()),
                        "$lt": datetime.combine(current_date + timedelta(days=1), datetime.min.time())
                    }
                }},
                {"$group": {"_id": None, "total": {"$sum": "$budget_spent_usd"}}}
            ])
            actual_cost = actual[0]["total"] if actual else 0.0

        forecasts.append(BudgetForecastResponse(
            forecast_date=current_date,
            total_scheduled_jobs=total_jobs,
            estimated_cost_usd=round(estimated_cost, 2),
            actual_cost_usd=actual_cost,
            daily_limit_usd=5.00  # From env var
        ))

        current_date += timedelta(days=1)

    return forecasts

@router.get("/calendar/month/{year}/{month}")
async def get_calendar_month(
    year: int,
    month: int,
    user_id: str = Depends(get_current_user)
):
    """
    Get calendar view data for a specific month.

    Returns all scheduled jobs and execution history for calendar rendering.
    """
    from calendar import monthrange

    start_date = date(year, month, 1)
    _, last_day = monthrange(year, month)
    end_date = date(year, month, last_day)

    # Get schedules
    schedules = await list_schedules(user_id=user_id, enabled=None)

    # Get execution history
    history = await get_execution_history(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date
    )

    # Get budget forecast
    forecast = await get_budget_forecast(start_date, end_date, user_id)

    # Build calendar data
    calendar_data = {}
    current_date = start_date

    while current_date <= end_date:
        day_key = current_date.isoformat()

        # Find jobs scheduled for this day
        scheduled_jobs = []
        for schedule in schedules:
            if schedule.enabled and _will_run_on_date(schedule.cron_expression, schedule.timezone, current_date):
                scheduled_jobs.append({
                    "id": schedule.id,
                    "job_name": schedule.job_name,
                    "job_type": schedule.job_type,
                    "time": _get_execution_time(schedule.cron_expression, schedule.timezone, current_date),
                    "budget_limit_usd": schedule.budget_limit_usd,
                    "priority": schedule.priority
                })

        # Find execution history for this day
        executions = [
            h for h in history
            if h.execution_time.date() == current_date
        ]

        # Get forecast for this day
        day_forecast = next((f for f in forecast if f.forecast_date == current_date), None)

        calendar_data[day_key] = {
            "date": current_date,
            "scheduled_jobs": scheduled_jobs,
            "executions": executions,
            "budget_forecast": day_forecast,
            "is_over_budget": day_forecast and day_forecast.estimated_cost_usd > day_forecast.daily_limit_usd
        }

        current_date += timedelta(days=1)

    return calendar_data
```

---

## 7. Implementation Roadmap

### Phase 1: Backend Foundation (Week 1-2)

**Goals:**
- Database schema implementation
- Core API endpoints
- Natural language parser
- APScheduler integration

**Tasks:**
1. Create database migrations for new tables
2. Implement `NaturalLanguageScheduler` class
3. Build API endpoints (`/api/autonomy/calendar/*`)
4. Write unit tests for NL parsing and cron conversion
5. Integration tests with APScheduler

**Deliverables:**
- ✅ Database schema deployed
- ✅ API endpoints functional
- ✅ 90%+ test coverage on NL parser
- ✅ Documentation for API

### Phase 2: Calendar UI (Week 3-4)

**Goals:**
- React calendar component
- Job editor modal
- Budget dashboard
- Real-time updates via WebSocket

**Tasks:**
1. Build calendar view component (month/week/day)
2. Implement job editor with NL input
3. Create budget forecast visualization
4. Add drag-and-drop scheduling
5. WebSocket integration for live updates

**Deliverables:**
- ✅ Fully functional calendar UI
- ✅ Job CRUD operations via UI
- ✅ Budget visualization
- ✅ Real-time job status updates

### Phase 3: Intelligence & Optimization (Week 5-6)

**Goals:**
- Conflict detection
- Smart scheduling suggestions
- Budget alerts
- Historical analysis

**Tasks:**
1. Implement conflict detection (overlapping high-cost jobs)
2. Build suggestion engine (optimal times, batching)
3. Add budget warning system
4. Create execution analytics dashboard
5. Email/MQTT notifications

**Deliverables:**
- ✅ Conflict warnings before save
- ✅ AI-suggested schedules
- ✅ Budget alerts (email/MQTT)
- ✅ Analytics dashboard

### Phase 4: Polish & Production (Week 7-8)

**Goals:**
- Mobile responsiveness
- Performance optimization
- Documentation
- User testing

**Tasks:**
1. Mobile UI optimization
2. Performance testing (1000+ schedules)
3. User guide and tutorials
4. Beta testing with 3-5 users
5. Bug fixes and polish

**Deliverables:**
- ✅ Production-ready calendar
- ✅ Complete documentation
- ✅ Positive user feedback
- ✅ Zero critical bugs

---

## 8. User Workflows

### 8.1 Scenario: Schedule Weekly Research

**User Story:** "I want KITTY to research multi-material 3D printing every Monday morning and stay under $0.50 per session."

**Workflow:**

1. **Open Calendar**: User navigates to `/autonomy/calendar`
2. **Click "Add Job"**: Opens job editor modal
3. **Natural Language Input**: Types "Run research on multi-material 3D printing every Monday at 5 AM"
4. **Configure**:
   - Job type: Research Session
   - Budget limit: $0.50
   - Strategy: Hybrid
   - Quality target: 0.80
5. **Preview**: System shows next 3 execution times and estimated cost
6. **Save**: Job added to calendar and APScheduler
7. **Confirmation**: Calendar highlights Mondays with 🔍 icon

**Result:** Every Monday at 5 AM PST, KITTY automatically runs research and stops when quality threshold or budget limit is reached.

### 8.2 Scenario: Pause Autonomy During Vacation

**User Story:** "I'm on vacation next week and don't want KITTY spending money."

**Workflow:**

1. **Open Calendar**: Navigate to next week's view
2. **Batch Pause**: Select all jobs or use "Pause All" button
3. **Set Duration**: Choose "Resume on [date]" or "Skip next N executions"
4. **Confirm**: All jobs marked as paused with ⏸ icon
5. **Automatic Resume**: On selected date, jobs automatically re-enable

**Result:** No autonomous jobs run during vacation, budget preserved.

### 8.3 Scenario: Budget Alert

**User Story:** "I want to be notified if KITTY is about to exceed my daily budget."

**Workflow:**

1. **Budget Dashboard**: Shows real-time spend vs. limit
2. **Threshold Warning**: At 80% of daily budget, yellow warning appears
3. **Notification**: MQTT message sent to UI: "Budget at 80% ($4.00 / $5.00)"
4. **Automatic Pause**: At 100%, system pauses all non-critical jobs
5. **User Override**: User can approve emergency job with omega password

**Result:** Budget overruns prevented, user stays informed.

---

## 9. Technical Considerations

### 9.1 Performance

**Expected Load:**
- 10-50 autonomous schedules per user
- 1,000+ execution history records per month
- Real-time WebSocket updates for 5-10 concurrent users

**Optimizations:**
- PostgreSQL indexes on `next_execution_at`, `user_id`, `execution_time`
- Redis caching for calendar month views (TTL: 5 minutes)
- Debounced WebSocket updates (max 1 update/second)
- Pagination for execution history (100 records/page)

### 9.2 Security

**Access Control:**
- JWT authentication on all endpoints
- Users can only manage their own schedules
- Admin users can view all schedules (read-only)

**Input Validation:**
- Cron expression validation (max 10 jobs/minute)
- Budget limits enforced (max $50/job)
- NL parser timeout (5 seconds max)

**Rate Limiting:**
- 100 API requests/minute per user
- 10 schedule creates/minute (prevent spam)

### 9.3 Error Handling

**Job Execution Failures:**
- Retry logic: 3 attempts with exponential backoff
- Error logged to `job_execution_history`
- MQTT notification to user
- Auto-disable after 5 consecutive failures

**Budget Exceeded:**
- Job marked as `budget_exceeded` in history
- User notified via MQTT
- Next execution proceeds normally (unless auto-pause enabled)

**System Failures:**
- APScheduler persists to PostgreSQL (survives restarts)
- Missed jobs marked as `skipped` in history
- Catchup logic for critical jobs (configurable)

---

## 10. Success Metrics

### 10.1 User Adoption

**Targets (3 months post-launch):**
- 80% of users create at least 1 autonomous schedule
- 50% of users use natural language input
- Average 5 schedules per active user

**Measurement:**
- Track schedule creation events
- NL vs. manual cron usage ratio
- User retention (weekly active users)

### 10.2 System Reliability

**Targets:**
- 99.5% uptime for calendar UI
- <1% job execution failure rate
- <5 second API response time (P95)

**Measurement:**
- Prometheus metrics for uptime
- APScheduler job success rate
- API latency monitoring

### 10.3 Cost Efficiency

**Targets:**
- <10% users exceed daily budget
- Average cost per autonomous job: $0.15
- 70%+ jobs use free tools (web_search, local models)

**Measurement:**
- Budget tracking in `budget_forecasts` table
- Cost breakdown by job type
- Provider usage distribution

---

## 11. Future Enhancements

### 11.1 Advanced Scheduling

- **Conditional triggers**: "Run research if printer is idle"
- **Event-based**: "Generate project after 3 print failures"
- **Chain jobs**: "After research, generate CAD, then print"

### 11.2 AI-Powered Suggestions

- **Optimal timing**: ML model suggests best times based on past success
- **Budget optimization**: Recommend job consolidation to save costs
- **Quality prediction**: Estimate research outcome quality before execution

### 11.3 Collaboration Features

- **Shared schedules**: Team members can view/edit shared jobs
- **Templates**: Pre-built schedule templates ("Weekly Research", "Daily Monitoring")
- **Approval workflows**: Require manager approval for high-cost jobs

### 11.4 Mobile App

- **Push notifications**: Job completion, budget alerts
- **Quick actions**: Pause/resume schedules from phone
- **Calendar sync**: iCal export for integration with Apple Calendar/Google Calendar

---

## 12. Conclusion

The **KITTY Autonomous Calendar Schedule Management** tool transforms how users interact with autonomous jobs—from opaque cron expressions buried in `.env` files to an intuitive, visual, natural language interface.

**Key Benefits:**

1. **Accessibility**: Anyone can schedule jobs without understanding cron syntax
2. **Visibility**: Calendar view shows past, present, and future autonomy at a glance
3. **Control**: Easy pause/resume, budget limits, and priority settings
4. **Intelligence**: Smart suggestions, conflict detection, and cost forecasting
5. **Safety**: Budget guardrails prevent runaway costs

**Production Readiness:**

This design leverages KITTY's existing production-grade infrastructure (APScheduler + PostgreSQL, distributed locking, RabbitMQ) and extends it with a user-friendly layer. All P0/P1 issues are already resolved, making this a low-risk, high-value addition to the KITT platform.

**Next Steps:**

1. **Stakeholder Review**: Gather feedback on UI mockups and API design
2. **Sprint Planning**: Allocate 8-week roadmap across engineering team
3. **Prototype**: Build Phase 1 (backend + basic UI) for user testing
4. **Iterate**: Refine based on feedback, launch Phase 2-4

With this calendar tool, KITTY truly becomes a **collaborative partner** in autonomous fabrication—one that works **with** users, not despite them.

---

**Document Version:** 1.0
**Author:** Claude (Sonnet 4.5)
**Review Status:** Pending stakeholder approval
**Implementation Target:** Q1 2026
