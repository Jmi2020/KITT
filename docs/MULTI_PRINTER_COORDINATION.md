# Multi-Printer Coordination - P3 #20

**Status:** In Development
**Priority:** P3
**Effort:** 2-3 weeks
**Dependencies:** RabbitMQ (P2 #15), Distributed Locking (P1 #6), Material Inventory (P2 #11)

---

## Overview

Multi-printer coordination enables **parallel job scheduling** across 3 printers (Bamboo H2D, Elegoo OrangeStorm Giga, Snapmaker Artisan) with intelligent queue optimization, material batching, and deadline-aware prioritization.

### Goals

1. **2-3x throughput increase** - Run multiple prints concurrently instead of sequentially
2. **Material efficiency** - Batch jobs by material to reduce filament swaps
3. **Smart scheduling** - Deadline-aware prioritization, best-fit printer selection
4. **Fault tolerance** - Job retry on printer failure, queue persistence
5. **Real-time visibility** - Queue status, job progress, ETA tracking

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────┐
│               Multi-Printer Coordinator                 │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ Job Queue    │  │ Scheduler    │  │ Optimizer    │ │
│  │ (PostgreSQL) │  │ (Parallel)   │  │ (Batching)   │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
│         │                  │                  │          │
│  ┌──────▼──────────────────▼──────────────────▼───────┐ │
│  │          Job Distributor (RabbitMQ)                │ │
│  │  - Task queue per printer                          │ │
│  │  - Dead letter queue for failed jobs               │ │
│  │  - Event bus for status updates                    │ │
│  └──────┬──────────────────┬──────────────────┬───────┘ │
│         │                  │                  │          │
└─────────┼──────────────────┼──────────────────┼─────────┘
          │                  │                  │
     ┌────▼────┐        ┌────▼────┐       ┌────▼────┐
     │ Bamboo  │        │ Elegoo  │       │Snapmaker│
     │   H2D   │        │  Giga   │       │ Artisan │
     └─────────┘        └─────────┘       └─────────┘
```

### Data Flow

1. **Job Submission** → API receives print request (STL + settings)
2. **Queue Insertion** → Job stored in PostgreSQL with priority/deadline
3. **Optimization** → Queue optimizer batches by material, sorts by priority
4. **Scheduling** → Scheduler selects best printer, publishes to RabbitMQ
5. **Distribution** → RabbitMQ routes job to printer-specific queue
6. **Execution** → Printer agent consumes job, executes print
7. **Status Updates** → Progress published to event bus
8. **Completion** → Outcome recorded, next job scheduled

---

## Database Schema

### PrintJob Table

```sql
CREATE TABLE print_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name VARCHAR(255) NOT NULL,

    -- Files
    stl_path TEXT NOT NULL,
    gcode_path TEXT,  -- Generated after slicing

    -- Material & Settings
    material_id VARCHAR(50) NOT NULL REFERENCES materials(id),
    print_settings JSONB NOT NULL,  -- {nozzle_temp, bed_temp, layer_height, infill, speed}
    estimated_grams DECIMAL(10, 2),
    estimated_cost_usd DECIMAL(10, 2),
    estimated_duration_hours DECIMAL(5, 2),

    -- Scheduling
    priority INT NOT NULL DEFAULT 5,  -- 1 (highest) to 10 (lowest)
    deadline_at TIMESTAMP,
    assigned_printer_id VARCHAR(50),  -- bamboo_h2d, elegoo_giga, snapmaker_artisan

    -- Status
    status VARCHAR(20) NOT NULL,  -- queued, scheduled, slicing, uploading, printing, completed, failed, cancelled
    status_reason TEXT,  -- Error details if failed

    -- Execution
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    actual_duration_hours DECIMAL(5, 2),
    actual_cost_usd DECIMAL(10, 2),

    -- Tracking
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by VARCHAR(100),  -- user_id or "autonomous"

    -- Retry Logic
    retry_count INT DEFAULT 0,
    max_retries INT DEFAULT 2,

    -- Relations
    goal_id VARCHAR(100),  -- Optional: autonomous goal linkage
    outcome_id UUID REFERENCES print_outcomes(id),

    CONSTRAINT valid_priority CHECK (priority BETWEEN 1 AND 10),
    CONSTRAINT valid_status CHECK (status IN ('queued', 'scheduled', 'slicing', 'uploading', 'printing', 'completed', 'failed', 'cancelled'))
);

CREATE INDEX idx_print_jobs_status ON print_jobs(status);
CREATE INDEX idx_print_jobs_priority ON print_jobs(priority, deadline_at);
CREATE INDEX idx_print_jobs_material ON print_jobs(material_id);
CREATE INDEX idx_print_jobs_printer ON print_jobs(assigned_printer_id);
CREATE INDEX idx_print_jobs_created ON print_jobs(created_at DESC);
```

### JobStatusHistory Table (Audit Trail)

```sql
CREATE TABLE job_status_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES print_jobs(id) ON DELETE CASCADE,
    from_status VARCHAR(20),
    to_status VARCHAR(20) NOT NULL,
    reason TEXT,
    changed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    changed_by VARCHAR(100)
);

CREATE INDEX idx_job_status_history_job ON job_status_history(job_id, changed_at DESC);
```

---

## Scheduler Algorithm

### Parallel Scheduling Strategy

```python
class ParallelJobScheduler:
    """
    Schedule jobs across multiple printers with optimization.

    Strategy:
    1. Get all printers with status
    2. Find idle printers
    3. For each idle printer:
       a. Get top-priority jobs from optimized queue
       b. Filter jobs that fit printer's build volume
       c. Prefer jobs with matching material (reduce swaps)
       d. Assign job and publish to RabbitMQ
    4. Reschedule after 30 seconds or on printer-idle event
    """

    async def schedule_next_jobs(self) -> List[JobAssignment]:
        # Get printer statuses
        statuses = await self.status_checker.get_all_statuses()
        idle_printers = [
            printer_id for printer_id, status in statuses.items()
            if status.is_online and not status.is_printing
        ]

        assignments = []
        for printer_id in idle_printers:
            # Get optimized job queue
            job = await self.queue_optimizer.get_next_job(
                printer_id=printer_id,
                current_material=await self.get_current_material(printer_id)
            )

            if job:
                # Assign job to printer
                assignment = await self.assign_job(job, printer_id)
                assignments.append(assignment)

        return assignments
```

### Queue Optimization

```python
class QueueOptimizer:
    """
    Optimize job queue with material batching and priority sorting.

    Optimization goals:
    1. Deadlines - Jobs with approaching deadlines first
    2. Material batching - Group same material to reduce swaps
    3. Priority - High-priority jobs first
    4. Build volume - Large jobs to Elegoo, small to Bamboo
    """

    async def get_next_job(
        self,
        printer_id: str,
        current_material: Optional[str] = None
    ) -> Optional[PrintJob]:
        # Get all queued jobs
        queued_jobs = await self.db.query(
            """
            SELECT * FROM print_jobs
            WHERE status = 'queued'
            ORDER BY
                -- Deadline priority (urgent jobs first)
                CASE
                    WHEN deadline_at IS NOT NULL
                    AND deadline_at < NOW() + INTERVAL '24 hours'
                    THEN 1 ELSE 2
                END,
                -- Material match priority (reduce swaps)
                CASE
                    WHEN material_id = %s THEN 1 ELSE 2
                END,
                -- User priority
                priority ASC,
                -- FIFO for same priority
                created_at ASC
            """,
            (current_material,)
        )

        # Filter jobs that fit printer's build volume
        printer_caps = PrinterSelector.PRINTERS[printer_id]
        max_dimension = min(printer_caps.build_volume)

        for job in queued_jobs:
            dimensions = await self.analyzer.analyze(job.stl_path)
            if dimensions.max_dimension <= max_dimension:
                return job

        return None
```

---

## RabbitMQ Integration

### Exchanges & Queues

```python
# Exchanges
FABRICATION_EXCHANGE = "fabrication"  # Topic exchange

# Queues (per printer)
BAMBOO_QUEUE = "fabrication.jobs.bamboo_h2d"
ELEGOO_QUEUE = "fabrication.jobs.elegoo_giga"
SNAPMAKER_QUEUE = "fabrication.jobs.snapmaker_artisan"

# Dead letter queue (failed jobs)
DLQ = "fabrication.jobs.dlq"

# Events
STATUS_EXCHANGE = "fabrication.status"  # Fanout exchange
```

### Message Format

```json
{
  "job_id": "uuid",
  "job_name": "bracket_v2",
  "stl_path": "/path/to/model.stl",
  "gcode_path": "/path/to/sliced.gcode",
  "material_id": "pla_black_esun",
  "print_settings": {
    "nozzle_temp": 210,
    "bed_temp": 60,
    "layer_height": 0.2,
    "infill": 20,
    "speed": 50
  },
  "estimated_duration_hours": 2.5,
  "priority": 5,
  "deadline_at": "2025-11-20T14:00:00Z",
  "retry_count": 0,
  "max_retries": 2
}
```

### Publisher

```python
async def publish_job_to_printer(job: PrintJob, printer_id: str):
    """Publish job to printer-specific queue."""
    queue_map = {
        "bamboo_h2d": BAMBOO_QUEUE,
        "elegoo_giga": ELEGOO_QUEUE,
        "snapmaker_artisan": SNAPMAKER_QUEUE,
    }

    message = {
        "job_id": str(job.id),
        "job_name": job.job_name,
        "stl_path": job.stl_path,
        "gcode_path": job.gcode_path,
        "material_id": job.material_id,
        "print_settings": job.print_settings,
        "estimated_duration_hours": float(job.estimated_duration_hours),
        "priority": job.priority,
        "deadline_at": job.deadline_at.isoformat() if job.deadline_at else None,
        "retry_count": job.retry_count,
        "max_retries": job.max_retries,
    }

    await rabbitmq_client.publish(
        exchange=FABRICATION_EXCHANGE,
        routing_key=queue_map[printer_id],
        message=message,
        properties={"delivery_mode": 2}  # Persistent
    )
```

---

## API Endpoints

### Submit Job

```http
POST /api/fabrication/jobs
Content-Type: application/json

{
  "job_name": "hex_box_v1",
  "stl_path": "/Users/Shared/KITT/artifacts/cad/hex_box.stl",
  "material_id": "pla_black_esun",
  "print_settings": {
    "nozzle_temp": 210,
    "bed_temp": 60,
    "layer_height": 0.2,
    "infill": 20,
    "speed": 50
  },
  "priority": 5,
  "deadline_at": "2025-11-20T14:00:00Z",
  "force_printer": null
}

Response:
{
  "job_id": "uuid",
  "status": "queued",
  "queue_position": 3,
  "estimated_start_time": "2025-11-17T16:30:00Z"
}
```

### Get Queue Status

```http
GET /api/fabrication/queue?status=queued&printer_id=bamboo_h2d

Response:
{
  "total_jobs": 5,
  "queued": 3,
  "printing": 2,
  "jobs": [
    {
      "job_id": "uuid",
      "job_name": "bracket_v2",
      "status": "queued",
      "priority": 3,
      "estimated_duration_hours": 2.5,
      "queue_position": 1,
      "material_id": "pla_black_esun"
    }
  ]
}
```

### Trigger Scheduling

```http
POST /api/fabrication/schedule

Response:
{
  "scheduled_jobs": 2,
  "assignments": [
    {
      "job_id": "uuid",
      "printer_id": "bamboo_h2d",
      "status": "scheduled"
    },
    {
      "job_id": "uuid2",
      "printer_id": "elegoo_giga",
      "status": "scheduled"
    }
  ]
}
```

### Cancel Job

```http
DELETE /api/fabrication/jobs/{job_id}

Response:
{
  "job_id": "uuid",
  "status": "cancelled",
  "cancellation_time": "2025-11-17T14:00:00Z"
}
```

---

## Implementation Plan

### Phase 1: Database & Models (Days 1-2)
- ✅ Create database migration for print_jobs table
- ✅ Create SQLAlchemy models
- ✅ Add database indexes
- ✅ Create seed data for testing

### Phase 2: Queue Optimizer (Days 3-4)
- ✅ Implement QueueOptimizer class
- ✅ Material batching logic
- ✅ Priority sorting algorithm
- ✅ Build volume filtering
- ✅ Unit tests

### Phase 3: Scheduler (Days 5-7)
- ✅ Implement ParallelJobScheduler class
- ✅ Idle printer detection
- ✅ Job assignment logic
- ✅ Distributed locking integration
- ✅ Scheduler daemon (background task)

### Phase 4: RabbitMQ Integration (Days 8-10)
- ✅ Create printer-specific queues
- ✅ Implement job publisher
- ✅ Implement job consumer (printer agents)
- ✅ Dead letter queue handling
- ✅ Status event publishing

### Phase 5: API Endpoints (Days 11-13)
- ✅ POST /api/fabrication/jobs (submit)
- ✅ GET /api/fabrication/queue (status)
- ✅ POST /api/fabrication/schedule (manual trigger)
- ✅ DELETE /api/fabrication/jobs/{id} (cancel)
- ✅ PATCH /api/fabrication/jobs/{id}/priority (update)

### Phase 6: Testing & Documentation (Days 14-15)
- ✅ Integration tests
- ✅ Load testing (concurrent jobs)
- ✅ Documentation
- ✅ Example workflows

---

## Success Metrics

### Performance
- **Throughput**: 2-3x increase in daily print capacity
- **Material swaps**: 50% reduction via batching
- **Printer utilization**: >80% during peak hours

### Reliability
- **Failed job retry**: <5% jobs require manual intervention
- **Queue persistence**: 100% jobs survive service restarts
- **Deadline compliance**: >95% of deadline jobs complete on time

### User Experience
- **Queue visibility**: Real-time status via Web UI
- **ETA accuracy**: ±15 minutes for estimated start times
- **Manual override**: Force printer selection when needed

---

## Future Enhancements (P3+)

### Advanced Queue Optimization
1. **ML-based time estimation** - Learn actual print times from outcomes
2. **Cost optimization** - Minimize material waste and electricity
3. **Predictive scheduling** - Pre-slice jobs during idle time

### Multi-Site Coordination
1. **Remote printer support** - Coordinate across multiple locations
2. **Load balancing** - Distribute jobs across sites based on availability

### Advanced Features
1. **Job dependencies** - Sequential jobs (print part A, then part B)
2. **Batch printing** - Multiple copies of same model
3. **Auto-retry with different settings** - If failure detected, retry with slower speed

---

## References

- **RabbitMQ Docs**: `docs/MESSAGE_QUEUE.md`
- **Material Inventory**: `docs/MATERIAL_INVENTORY_DASHBOARD.md`
- **Print Outcomes**: `docs/PRINT_INTELLIGENCE_DASHBOARD.md`
- **Distributed Locking**: `KITT_SYSTEM_ANALYSIS_MASTER.md` (P1 #6)
