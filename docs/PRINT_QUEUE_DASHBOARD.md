# Print Queue Dashboard - P3 #20

**Status:** Complete
**Access:** `http://localhost:8300/queue`

---

## Overview

Standalone web dashboard for real-time print queue monitoring and job management. Provides visual interface for operators to monitor all 3 printers and manage the print queue.

---

## Features

### 📊 **Queue Statistics**
- Total jobs in system
- Jobs by status (queued, scheduled, printing)
- Urgent jobs (approaching deadline)
- Real-time updates every 10 seconds

### 🖨️ **Printer Status Panel**
- Live status for all 3 printers:
  - **Bamboo H2D** - FDM (250x250x250mm)
  - **Elegoo OrangeStorm Giga** - FDM (800x800x1000mm)
  - **Snapmaker Artisan** - FDM/CNC/Laser
- Current job and progress
- Online/offline detection
- Idle/printing state

### 📋 **Job Queue View**
- Jobs sorted by priority and queue position
- Visual priority indicators (red=high, yellow=medium, blue=low)
- Job metadata:
  - Queue position
  - Status badge
  - Priority level
  - Material type
  - Estimated duration
  - Estimated cost
  - Assigned printer (if scheduled)
  - Deadline warnings
- Actions:
  - **Cancel** - Remove job from queue
  - **Change Priority** - Update job priority (1-10)

### ⚠️ **Deadline Alerts**
- **Yellow badge** - Deadline within 24 hours
- **Red badge** - Overdue job (URGENT)

---

## Access Methods

### 1. Web Dashboard (Recommended)
```bash
# Open in browser
open http://localhost:8300/queue

# Or use curl to check if available
curl http://localhost:8300/queue
```

**Features:**
- Visual job cards with color-coded priorities
- Real-time auto-refresh (every 10 seconds)
- Interactive job management (cancel, priority)
- Responsive design (works on tablets/phones)

### 2. CLI Helper Script
```bash
# List queue
./scripts/queue-cli.sh list

# Show statistics
./scripts/queue-cli.sh status

# Submit job
./scripts/queue-cli.sh submit /path/to/model.stl "bracket_v2" pla_black_esun 3

# Cancel job
./scripts/queue-cli.sh cancel job_20251116_123456_abc123

# Watch queue (live updates)
./scripts/queue-cli.sh watch

# Update priority
./scripts/queue-cli.sh priority job_20251116_123456_abc123 1

# Show help
./scripts/queue-cli.sh help
```

### 3. Direct API Calls
```bash
# Get queue status
curl http://localhost:8300/api/fabrication/queue | jq

# Get statistics
curl http://localhost:8300/api/fabrication/queue/statistics | jq

# Cancel job
curl -X DELETE http://localhost:8300/api/fabrication/jobs/JOB_ID

# Update priority
curl -X PATCH http://localhost:8300/api/fabrication/jobs/JOB_ID/priority \
  -H "Content-Type: application/json" \
  -d '{"priority": 1}'
```

---

## Queue Management

### Job Priority System

**Priority Levels (1-10):**
- **1-3** = HIGH (red border, urgent)
- **4-6** = MEDIUM (yellow border, normal)
- **7-10** = LOW (blue border, background tasks)

**Priority Scoring Algorithm:**
```
Score = Deadline Urgency (0-1000)
      + User Priority (0-100)
      + Material Match Bonus (0-50)
      + FIFO Tie-breaker (0-10)
```

**Deadline Urgency:**
- Overdue → 1000 points (highest)
- <24h → 0-500 points (scaled)
- >24h → 0 points

### Job Lifecycle

```
1. Queued       → Job submitted, waiting for scheduling
2. Scheduled    → Assigned to printer, in RabbitMQ queue
3. Slicing      → Generating G-code
4. Uploading    → Transferring to printer
5. Printing     → Currently printing
6. Completed    → Print finished successfully
7. Failed       → Print failed (reason logged)
8. Cancelled    → User cancelled
```

### Material Batching

The scheduler automatically batches jobs with the same material to reduce filament swaps:
- Jobs with matching material get +50 priority points
- Reduces downtime and material waste
- Configurable material batch bonus in optimizer

---

## User Workflows

### Workflow 1: Submit Job via Web UI
1. Use existing research UI to generate STL
2. Submit job via API or CLI script
3. Open queue dashboard to monitor: `http://localhost:8300/queue`
4. Adjust priority if needed
5. Job auto-schedules to idle printer

### Workflow 2: CLI-Only Workflow
```bash
# 1. Submit job
./scripts/queue-cli.sh submit /path/model.stl "my_part" pla_black_esun 5

# 2. Watch queue
./scripts/queue-cli.sh watch

# 3. If urgent, boost priority
./scripts/queue-cli.sh priority job_20251116_123456 1

# 4. Check printer status
./scripts/queue-cli.sh printers
```

### Workflow 3: Operator Monitoring
1. Open dashboard on dedicated monitor: `http://localhost:8300/queue`
2. Dashboard auto-refreshes every 10 seconds
3. Red badges indicate urgent jobs
4. Cancel/reprioritize as needed
5. Monitor all 3 printers simultaneously

---

## Technical Details

### Frontend
- **Technology**: Vanilla JavaScript (no build required)
- **Styling**: Embedded CSS, dark theme
- **Auto-refresh**: 10-second interval
- **Responsive**: Works on desktop, tablet, mobile

### API Endpoints Used
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/fabrication/queue` | GET | Get queue status |
| `/api/fabrication/queue/statistics` | GET | Get queue stats |
| `/api/fabrication/printer_status` | GET | Get printer status |
| `/api/fabrication/jobs/{id}` | DELETE | Cancel job |
| `/api/fabrication/jobs/{id}/priority` | PATCH | Update priority |

### File Structure
```
services/fabrication/
├── static/
│   └── queue.html          # Standalone dashboard
├── src/fabrication/
│   └── app.py              # FastAPI app with /queue route
└── scripts/
    └── queue-cli.sh        # CLI helper
```

---

## Configuration

### Environment Variables
```bash
# Fabrication service URL (for CLI script)
export FABRICATION_URL="http://localhost:8300"

# RabbitMQ URL (for job distribution)
export RABBITMQ_URL="amqp://guest:guest@localhost:5672/"
```

### Auto-Refresh Interval
To change refresh rate, edit `queue.html`:
```javascript
// Change from 10 seconds to 5 seconds
setInterval(loadDashboard, 5000);
```

---

## Troubleshooting

### Dashboard Not Loading
```bash
# 1. Check fabrication service is running
curl http://localhost:8300/healthz

# 2. Check static directory exists
ls /home/user/KITT/services/fabrication/static/

# 3. Restart fabrication service
cd services/fabrication
python -m fabrication.app
```

### Queue Empty
```bash
# Submit test job
./scripts/queue-cli.sh submit /path/to/test.stl "test_job"

# Verify job in database
psql kitt -c "SELECT job_id, status FROM print_queue;"
```

### Jobs Not Scheduling
```bash
# 1. Check RabbitMQ is running
docker ps | grep rabbitmq

# 2. Check printer status
./scripts/queue-cli.sh printers

# 3. Manually trigger scheduler
curl -X POST http://localhost:8300/api/fabrication/schedule
```

---

## Future Enhancements

### Phase 1 (Current)
- ✅ Visual queue dashboard
- ✅ Real-time updates
- ✅ Job cancellation
- ✅ Priority updates
- ✅ Printer status
- ✅ CLI helper script

### Phase 2 (Planned)
- [ ] STL thumbnail previews (Three.js integration)
- [ ] WebSocket for push updates (replace polling)
- [ ] Drag-and-drop priority reordering
- [ ] Queue ETA calculator
- [ ] Material usage forecast chart
- [ ] Print history timeline

### Phase 3 (Future)
- [ ] Mobile app (PWA)
- [ ] Printer camera live feed integration
- [ ] Voice alerts for urgent jobs
- [ ] Slack/Discord notifications
- [ ] Queue optimization suggestions
- [ ] Batch job submission

---

## Related Documentation

- **Multi-Printer Coordination**: `docs/MULTI_PRINTER_COORDINATION.md`
- **API Reference**: `http://localhost:8300/docs` (FastAPI auto-docs)
- **Material Inventory**: `docs/MATERIAL_INVENTORY_DASHBOARD.md`
- **Print Intelligence**: `docs/PRINT_INTELLIGENCE_DASHBOARD.md`

---

## Support

**Web UI:** `http://localhost:8300/queue`
**API Docs:** `http://localhost:8300/docs`
**CLI Help:** `./scripts/queue-cli.sh help`
