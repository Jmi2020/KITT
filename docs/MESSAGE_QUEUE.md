# Message Queue & Async Event Bus - Developer Guide

## Overview

KITT's message queue infrastructure provides asynchronous messaging capabilities using RabbitMQ, enabling decoupled service communication, task distribution, and event sourcing across the distributed system.

**Status**: ✅ **Production Ready** (P2 #15 Implementation Complete)

**Technology**: RabbitMQ 3.12 with Management Plugin + Prometheus Metrics

**Patterns Supported**:
- **Event Bus**: Pub/Sub for service events
- **Task Queues**: Work distribution with priorities and retries
- **RPC**: Request/Reply for synchronous calls
- **Dead Letter Queues**: Failed message handling

---

## Architecture

### RabbitMQ Topology

```
┌─────────────────────────────────────────────────────────────────────┐
│  RabbitMQ Broker                                                     │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Exchanges (Routing Logic)                                    │  │
│  │                                                               │  │
│  │  kitty.events (topic)    →  Routing by pattern match        │  │
│  │  kitty.tasks (direct)    →  Routing by exact queue name     │  │
│  │  kitty.rpc (direct)      →  Request/Reply routing           │  │
│  │  dlx (topic)             →  Dead letter routing             │  │
│  └───────────────────────────┬──────────────────────────────────┘  │
│                               │                                     │
│  ┌────────────────────────────┴──────────────────────────────────┐  │
│  │  Queues (Message Storage)                                     │  │
│  │                                                               │  │
│  │  fabrication.events    (100k max, durable)                   │  │
│  │  research.tasks        (10k max, priority queue)             │  │
│  │  cad.tasks             (5k max, priority queue)              │  │
│  │  brain.commands        (durable, no limit)                   │  │
│  │  notifications         (50k max)                             │  │
│  │  audit.events          (1M max, 30-day TTL)                  │  │
│  │  dlx.queue             (dead letter collection)              │  │
│  │  retry.fabrication     (5-min TTL, auto-retry)               │  │
│  └───────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### Messaging Patterns

#### 1. Event Bus (Pub/Sub)

**Use Case**: Service-to-service event notifications

```
Publisher                Exchange              Subscribers
────────                ────────              ───────────

[Fabrication]  ──┐
                  ├──> kitty.events ──┬──> [Audit Service]
[CAD Service]  ──┘    (topic)        ├──> [Notification Service]
                                      └──> [Analytics Service]

Routing Keys: service.entity.action
Examples:
  - fabrication.print.started
  - fabrication.print.completed
  - cad.model.generated
  - research.task.completed
```

#### 2. Task Queue (Work Distribution)

**Use Case**: Background job processing with load balancing

```
Producer               Exchange              Workers
────────              ────────              ───────

[Brain API]  ───> kitty.tasks ───> research.tasks ──┬──> [Worker 1]
                   (direct)                         ├──> [Worker 2]
                                                     └──> [Worker 3]

Features:
  - Priority: 0-10 (higher = processed first)
  - Fair dispatch: One task per worker at a time
  - Retry: 3 attempts with exponential backoff
  - DLX: Failed tasks go to dead letter queue
```

#### 3. RPC (Request/Reply)

**Use Case**: Synchronous inter-service calls

```
Client                  Server
──────                  ──────

[Service A] ──request──> [Service B]
            <─response─┘

Features:
  - Temporary reply queue per client
  - Correlation ID for matching request/response
  - Timeout: 30 seconds default
  - Blocking operation (use sparingly)
```

---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.10+ (for Python clients)
- `pika` library installed: `pip install pika`

### 1. Start RabbitMQ

```bash
cd /home/user/KITT

docker compose \
  -f infra/compose/docker-compose.yml \
  -f infra/compose/docker-compose.message-queue.yml \
  up -d rabbitmq
```

### 2. Verify RabbitMQ is Running

```bash
# Check container
docker ps | grep rabbitmq

# Check health
docker exec -it $(docker ps -q -f name=rabbitmq) rabbitmq-diagnostics ping

# Access Management UI
open http://localhost:15672
# Login: kitty / changeme
```

### 3. Python Usage Examples

**Event Bus (Pub/Sub)**:
```python
from common.messaging import EventBus

# Publisher
bus = EventBus("amqp://kitty:changeme@localhost:5672/", source="fabrication-service")
bus.connect()
bus.publish("fabrication.print.started", {
    "job_id": "print_123",
    "printer_id": "bamboo_h2d",
    "material_id": "pla_black_esun",
})
bus.disconnect()

# Subscriber
def handle_print_started(event):
    print(f"Print started: {event.data['job_id']}")

bus = EventBus("amqp://kitty:changeme@localhost:5672/", source="audit-service")
bus.connect()
bus.subscribe("fabrication.print.#", handle_print_started)
bus.start_consuming()  # Blocking
```

**Task Queue (Work Distribution)**:
```python
from common.messaging import TaskQueue

# Producer
queue = TaskQueue("amqp://kitty:changeme@localhost:5672/", "research.tasks")
queue.connect()
task_id = queue.submit(
    task_type="research_paper",
    data={"query": "3D printing failure detection"},
    priority=7,  # 0-10 scale
    max_retries=3,
)
print(f"Submitted task: {task_id}")
queue.disconnect()

# Worker
def process_research(task):
    print(f"Researching: {task.data['query']}")
    # ... do research ...
    return {"results": [...]}

queue = TaskQueue("amqp://kitty:changeme@localhost:5672/", "research.tasks")
queue.connect()
queue.register_handler("research_paper", process_research)
queue.start_worker(prefetch_count=2)  # Blocking, process 2 tasks in parallel
```

**RPC (Request/Reply)**:
```python
from common.messaging import RPCClient, RPCServer

# RPC Server
def handle_add(request):
    return {"result": request["a"] + request["b"]}

server = RPCServer("amqp://kitty:changeme@localhost:5672/", "math.rpc")
server.connect()
server.register_handler(handle_add)
server.start()  # Blocking

# RPC Client
client = RPCClient("amqp://kitty:changeme@localhost:5672/")
client.connect()
result = client.call("math.rpc", {"a": 5, "b": 3}, timeout=30)
print(result)  # {"result": 8}
client.disconnect()
```

---

## Configuration

### Environment Variables

All message queue configuration in `.env`:

```bash
# RabbitMQ credentials
RABBITMQ_USER=kitty
RABBITMQ_PASSWORD=changeme
RABBITMQ_VHOST=/

# Connection URL
RABBITMQ_URL=amqp://kitty:changeme@rabbitmq:5672/

# Clustering cookie (for multi-node setups)
RABBITMQ_ERLANG_COOKIE=kitty_secret_cookie_change_me
```

### Queue Policies

Policies are auto-configured via `definitions.json`:

**High Availability**:
- All queues replicated across nodes (future clustering)
- Pattern: `.*`

**Dead Letter Exchange**:
- Failed messages routed to `dlx` exchange
- Pattern: All queues except `*.dlx$`

**TTL (Time-To-Live)**:
- Retry queues expire after 5 minutes
- Pattern: `retry.*`

### Queue Limits

| Queue | Max Length | TTL | Use Case |
|-------|------------|-----|----------|
| fabrication.events | 100,000 | None | Fabrication events |
| research.tasks | 10,000 | None | Research tasks |
| cad.tasks | 5,000 | None | CAD generation tasks |
| brain.commands | Unlimited | None | Brain commands |
| notifications | 50,000 | None | User notifications |
| audit.events | 1,000,000 | 30 days | Audit logs |
| dlx.queue | Unlimited | None | Failed messages |

---

## Usage Patterns

### Pattern 1: Event-Driven Architecture

**Scenario**: Fabrication service publishes print events, multiple services react

```python
# Fabrication Service (Publisher)
from common.messaging import EventBus

bus = EventBus(RABBITMQ_URL, source="fabrication-service")
bus.connect()

# Publish when print starts
bus.publish("fabrication.print.started", {
    "job_id": job_id,
    "printer_id": printer_id,
    "started_at": datetime.now().isoformat(),
})

# Publish when print completes
bus.publish("fabrication.print.completed", {
    "job_id": job_id,
    "success": True,
    "duration_hours": 3.5,
})
```

```python
# Audit Service (Subscriber)
def log_fabrication_event(event):
    print(f"Audit: {event.event_type} at {event.timestamp}")
    # Store in audit log database

bus = EventBus(RABBITMQ_URL, source="audit-service")
bus.connect()
bus.subscribe("fabrication.#", log_fabrication_event)
bus.start_consuming()
```

```python
# Notification Service (Subscriber)
def notify_user(event):
    if event.event_type == "fabrication.print.completed":
        send_notification(f"Print {event.data['job_id']} completed!")

bus = EventBus(RABBITMQ_URL, source="notification-service")
bus.connect()
bus.subscribe("fabrication.print.completed", notify_user)
bus.start_consuming()
```

### Pattern 2: Background Task Processing

**Scenario**: Brain API submits research tasks, workers process them

```python
# Brain API (Producer)
from common.messaging import TaskQueue

queue = TaskQueue(RABBITMQ_URL, "research.tasks")
queue.connect()

task_id = queue.submit(
    task_type="research_paper",
    data={
        "query": "autonomous 3D printing failure detection",
        "max_results": 10,
    },
    priority=8,  # High priority
)

print(f"Task submitted: {task_id}")
```

```python
# Research Worker (Consumer)
from common.messaging import TaskQueue
import time

def process_research(task):
    print(f"Processing research task: {task.task_id}")
    
    # Simulate research
    time.sleep(5)
    
    results = {
        "papers": [...],
        "summary": "...",
    }
    
    return results

queue = TaskQueue(RABBITMQ_URL, "research.tasks")
queue.connect()
queue.register_handler("research_paper", process_research)
queue.start_worker(prefetch_count=3)  # Process 3 tasks concurrently
```

### Pattern 3: Request/Reply (RPC)

**Scenario**: Service A needs synchronous result from Service B

```python
# Service B (RPC Server)
from common.messaging import RPCServer

def estimate_print_cost(request):
    stl_volume = request["volume_cm3"]
    material_id = request["material_id"]
    
    # Calculate cost
    cost_usd = calculate_cost(stl_volume, material_id)
    
    return {
        "cost_usd": cost_usd,
        "material_grams": stl_volume * density,
    }

server = RPCServer(RABBITMQ_URL, "fabrication.estimate.rpc")
server.connect()
server.register_handler(estimate_print_cost)
server.start()
```

```python
# Service A (RPC Client)
from common.messaging import RPCClient

client = RPCClient(RABBITMQ_URL)
client.connect()

result = client.call(
    "fabrication.estimate.rpc",
    {
        "volume_cm3": 125.5,
        "material_id": "pla_black_esun",
    },
    timeout=10,
)

print(f"Estimated cost: ${result['cost_usd']}")
client.disconnect()
```

---

## Monitoring & Management

### RabbitMQ Management UI

**URL**: http://localhost:15672  
**Login**: `kitty` / `changeme`

**Features**:
- Queue/exchange/binding visualization
- Message browsing and manual publishing
- Consumer monitoring
- Connection and channel statistics
- Performance metrics (message rates, memory usage)

**Common Tasks**:
```
# Purge queue
Queues → [queue name] → Purge

# Manually publish message
Exchanges → [exchange name] → Publish message

# View bindings
Exchanges → [exchange name] → Bindings

# Monitor consumers
Queues → [queue name] → Consumers
```

### Prometheus Metrics

**URL**: http://localhost:15692/metrics

**Key Metrics**:
```
# Message rates
rabbitmq_global_messages_published_total
rabbitmq_global_messages_delivered_total
rabbitmq_global_messages_acknowledged_total

# Queue metrics
rabbitmq_queue_messages{queue="research.tasks"}
rabbitmq_queue_consumers{queue="research.tasks"}

# Connection metrics
rabbitmq_connections
rabbitmq_channels

# Resource usage
rabbitmq_process_resident_memory_bytes
rabbitmq_disk_space_available_bytes
```

### Health Checks

**Manual health check**:
```bash
# Check RabbitMQ status
docker exec -it $(docker ps -q -f name=rabbitmq) rabbitmq-diagnostics status

# Check node health
docker exec -it $(docker ps -q -f name=rabbitmq) rabbitmq-diagnostics ping

# List queues
docker exec -it $(docker ps -q -f name=rabbitmq) rabbitmqctl list_queues name messages consumers

# List exchanges
docker exec -it $(docker ps -q -f name=rabbitmq) rabbitmqctl list_exchanges name type
```

---

## Error Handling & Retries

### Retry Mechanism

Task queues implement automatic retry with exponential backoff:

```python
# Task configuration
queue.submit(
    task_type="research_paper",
    data={...},
    max_retries=3,  # Retry up to 3 times
)

# Worker handles retries automatically
# Retry 1: Immediately (requeue)
# Retry 2: Immediately (requeue)
# Retry 3: Immediately (requeue)
# After 3 failures: Sent to dead letter queue
```

**Custom Retry Logic**:
```python
def process_with_retry(task):
    try:
        # Process task
        result = do_work(task.data)
        return result
    except RetryableError as e:
        if task.retry_count < task.max_retries:
            # Requeue for retry
            raise
        else:
            # Give up, send to DLX
            raise PermanentError("Max retries exceeded")
    except PermanentError as e:
        # Don't retry, send to DLX immediately
        raise
```

### Dead Letter Queue

Failed messages automatically route to `dlx.queue`:

**View failed messages**:
```bash
# Via Management UI
http://localhost:15672/#/queues/%2F/dlx.queue

# Via CLI
docker exec -it $(docker ps -q -f name=rabbitmq) \
  rabbitmqctl list_queues name messages | grep dlx
```

**Reprocess failed messages**:
```python
# Move messages from DLX back to original queue
# (manual operation via Management UI or custom script)
```

---

## Best Practices

### 1. Message Design

**Good message structure**:
```python
{
    "event_id": "uuid",
    "event_type": "fabrication.print.started",
    "timestamp": "2025-11-16T12:00:00Z",
    "source": "fabrication-service",
    "correlation_id": "request-uuid",  # For tracing
    "data": {
        "job_id": "print_123",
        "printer_id": "bamboo_h2d",
        "material_id": "pla_black_esun",
    }
}
```

**Guidelines**:
- Include `event_id` for deduplication
- Add `correlation_id` for request tracing
- Keep data payload small (<1MB recommended)
- Use ISO 8601 for timestamps
- Version your event schemas

### 2. Idempotency

**Problem**: Messages can be delivered multiple times

**Solution**: Make handlers idempotent
```python
def handle_print_started(event):
    job_id = event.data["job_id"]
    
    # Check if already processed
    if db.exists(job_id):
        logger.info(f"Duplicate event for {job_id}, skipping")
        return
    
    # Process event
    db.insert(job_id, event.data)
```

### 3. Connection Management

**Use context managers**:
```python
with EventBus(RABBITMQ_URL, source="my-service") as bus:
    bus.publish("event.type", {"data": "..."})
# Automatically disconnects
```

**Avoid**:
```python
# DON'T: Open new connection per message
for i in range(1000):
    bus = EventBus(RABBITMQ_URL)
    bus.connect()
    bus.publish("event", {})
    bus.disconnect()  # Very inefficient!
```

**Do**:
```python
# DO: Reuse connection
bus = EventBus(RABBITMQ_URL, source="my-service")
bus.connect()
for i in range(1000):
    bus.publish("event", {"index": i})
bus.disconnect()
```

### 4. Consumer Performance

**Prefetch count tuning**:
```python
# Slow tasks (CPU-intensive)
queue.start_worker(prefetch_count=1)  # Process one at a time

# Fast tasks (I/O-bound)
queue.start_worker(prefetch_count=10)  # Process 10 in parallel
```

### 5. Message Persistence

**Durable queues + persistent messages**:
```python
# Queues are durable by default
queue.declare_queue("my.queue", durable=True)

# Messages are persistent by default (delivery_mode=2)
bus.publish("event.type", data, properties=pika.BasicProperties(
    delivery_mode=2  # Persistent
))
```

---

## Troubleshooting

### Issue: Messages not being consumed

**Diagnosis**:
```bash
# Check if consumers are running
docker exec -it $(docker ps -q -f name=rabbitmq) \
  rabbitmqctl list_queues name consumers

# Should show consumers > 0
```

**Solutions**:
1. Verify worker is running and connected
2. Check worker logs for errors
3. Verify queue binding to exchange
4. Check if queue has messages: `list_queues name messages`

### Issue: Messages piling up in queue

**Diagnosis**:
```bash
# Check queue depth
docker exec -it $(docker ps -q -f name=rabbitmq) \
  rabbitmqctl list_queues name messages

# Check consumer count
docker exec -it $(docker ps -q -f name=rabbitmq) \
  rabbitmqctl list_queues name consumers
```

**Solutions**:
1. **Scale workers**: Increase `prefetch_count` or add more workers
2. **Optimize handlers**: Profile and optimize slow task handlers
3. **Add queue limits**: Prevent unbounded growth
4. **Check for blocking**: Ensure workers aren't stuck

### Issue: High memory usage

**Diagnosis**:
```bash
# Check RabbitMQ memory usage
docker stats $(docker ps -q -f name=rabbitmq)

# Check per-queue memory
# Via Management UI: http://localhost:15672/#/queues
```

**Solutions**:
1. **Increase memory limit** in docker-compose:
   ```yaml
   rabbitmq:
     environment:
       RABBITMQ_VM_MEMORY_HIGH_WATERMARK: 0.6  # 60% of RAM
   ```
2. **Purge old messages**: Delete messages from queues
3. **Enable lazy queues**: Move messages to disk
4. **Reduce message size**: Compress or reference data instead of embedding

### Issue: Connection failures

**Diagnosis**:
```python
# Check if RabbitMQ is running
docker ps | grep rabbitmq

# Check logs
docker logs $(docker ps -q -f name=rabbitmq)
```

**Solutions**:
1. Verify `RABBITMQ_URL` is correct
2. Check firewall rules (port 5672)
3. Verify credentials (user/password)
4. Check RabbitMQ disk space (needs 2GB free minimum)

---

## Production Deployment

### 1. Clustering (Future Enhancement)

For production, deploy RabbitMQ cluster with 3+ nodes:

```yaml
# docker-compose.message-queue-cluster.yml (future)
rabbitmq-1:
  image: rabbitmq:3.12-management-alpine
  environment:
    RABBITMQ_ERLANG_COOKIE: shared_secret_cookie

rabbitmq-2:
  image: rabbitmq:3.12-management-alpine
  environment:
    RABBITMQ_ERLANG_COOKIE: shared_secret_cookie
    RABBITMQ_CLUSTER_WITH: rabbitmq-1

rabbitmq-3:
  image: rabbitmq:3.12-management-alpine
  environment:
    RABBITMQ_ERLANG_COOKIE: shared_secret_cookie
    RABBITMQ_CLUSTER_WITH: rabbitmq-1
```

### 2. Security Hardening

```bash
# Use strong passwords
RABBITMQ_PASSWORD=<randomly-generated-64-char-password>

# Enable TLS
RABBITMQ_SSL_CERTFILE=/certs/server.crt
RABBITMQ_SSL_KEYFILE=/certs/server.key
RABBITMQ_SSL_CACERTFILE=/certs/ca.crt

# Disable guest user
rabbitmqctl delete_user guest
```

### 3. Monitoring & Alerting

**Critical alerts**:
- Queue depth > 10,000 messages
- Consumer count = 0 for critical queues
- Memory usage > 80%
- Disk space < 5GB

**Prometheus alerts**:
```yaml
# infra/prometheus/alerts/rabbitmq.yml
- alert: RabbitMQQueueBacklog
  expr: rabbitmq_queue_messages{queue="research.tasks"} > 10000
  annotations:
    summary: "RabbitMQ queue backlog is high"
```

### 4. Backup & Recovery

**Backup definitions**:
```bash
# Export definitions
docker exec -it $(docker ps -q -f name=rabbitmq) \
  rabbitmqctl export_definitions /tmp/definitions.json

docker cp $(docker ps -q -f name=rabbitmq):/tmp/definitions.json ./backup/
```

**Restore definitions**:
```bash
# Import definitions
docker cp ./backup/definitions.json $(docker ps -q -f name=rabbitmq):/tmp/

docker exec -it $(docker ps -q -f name=rabbitmq) \
  rabbitmqctl import_definitions /tmp/definitions.json
```

---

## Related Documentation

- **Docker Compose Configuration**: `infra/compose/docker-compose.message-queue.yml`
- **RabbitMQ Configuration**: `infra/compose/rabbitmq/rabbitmq.conf`
- **Queue Definitions**: `infra/compose/rabbitmq/definitions.json`
- **Python Client Library**: `services/common/src/common/messaging/`
- **Environment Configuration**: `.env.example` (Section 15)

---

## Support

For questions or issues:
1. Check Management UI: http://localhost:15672
2. Review logs: `docker logs $(docker ps -q -f name=rabbitmq)`
3. Check queue stats: `rabbitmqctl list_queues`
4. File issue: https://github.com/Jmi2020/KITT/issues

---

**Message Queue Infrastructure**: Production-ready async messaging for distributed services! 🐰📨
