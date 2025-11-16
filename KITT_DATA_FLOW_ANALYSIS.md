# KITT Data Flow and Orchestration Analysis

## 1. REQUEST FLOW ANALYSIS

### 1.1 CLI → Gateway → Brain → Response Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CLI Request Flow                                   │
└─────────────────────────────────────────────────────────────────────────────────┘

User (SSH Terminal)
        │
        │ typer command
        │ UUID: request_id
        │ Headers: auth tokens
        ▼
   ┌─────────────────┐
   │   CLI Service   │  (HTTP Client)
   │ :8000 endpoint  │  - Parses inline provider syntax (@openai: #gpt-4o:)
   │ main.py         │  - Detects model from name
   └────────┬────────┘
        │
        │ POST /api/query
        │ Body: {
        │   conversationId, userId, intent,
        │   prompt, payload, provider, model,
        │   freshnessRequired, useAgent, toolMode
        │ }
        ▼
   ┌──────────────────────┐
   │  GATEWAY Service     │  (Request Router)
   │  Port: 8080          │
   │  routes/routing.py   │
   └────────┬─────────────┘
        │
        │ HTTP Proxy/Forward
        │
        ▼
   ┌──────────────────────────────────────┐
   │   BRAIN Service                      │
   │   Port: 8000                         │
   │   routes/query.py → POST /api/query  │
   └────────┬─────────────────────────────┘
        │
        │ [1] Record user message (PostgreSQL)
        │ [2] Load conversation state (in-memory)
        │ [3] Check pending confirmations
        │ [4] Search memories (Qdrant via mem0-mcp)
        │ [5] Enrich prompt with context
        │
        ▼
   ┌──────────────────────────────────────┐
   │   orchestrator.generate_response()   │
   │   ├─ routing.router.route()          │
   │   ├─ Cache check (Redis Streams)     │
   │   ├─ Decision path selection:        │
   │   │  ├─ Agent mode (ReAct)           │
   │   │  ├─ Local (llama.cpp)            │
   │   │  ├─ MCP (Perplexity)             │
   │   │  └─ Frontier (OpenAI)            │
   │   └─ Store memories (Qdrant)         │
   └────────┬─────────────────────────────┘
        │
        ├─→ [Option A] Agent Routing
        │   ├─ langgraph integration
        │   ├─ Tool execution (ReAct agent)
        │   ├─ MCP server calls
        │   └─ Vision pipeline
        │
        ├─→ [Option B] Local Routing
        │   └─ llama.cpp Q4/F16 models
        │
        ├─→ [Option C] MCP Routing
        │   └─ Perplexity API (research_deep tool)
        │
        └─→ [Option D] Frontier Routing
            └─ OpenAI GPT-4o / Claude via providers
        │
        ▼
   ┌──────────────────────────────────────┐
   │   RoutingResult with metadata        │
   │   - output: str                      │
   │   - tier: RoutingTier (local/mcp/frontier)
   │   - confidence: float (0.0-1.0)      │
   │   - latency_ms: int                  │
   │   - cached: bool                     │
   │   - metadata: {...}                  │
   └────────┬─────────────────────────────┘
        │
        │ [1] Record assistant message (PostgreSQL)
        │ [2] Log routing decision (audit_store)
        │ [3] Update cost tracking (Redis)
        │
        ▼
   ┌──────────────────────────────────────┐
   │   QueryResponse returned to Client   │
   │   ├─ conversationId                  │
   │   ├─ result: {output, verbosity}     │
   │   ├─ routing: {tier, confidence, ...}│
   │   ├─ requiresConfirmation            │
   │   ├─ pendingTool (if hazard)         │
   │   └─ hazardClass (low/medium/high)   │
   └────────┬─────────────────────────────┘
        │
        ▼
    CLI Terminal
    Display response with formatting
```

### 1.2 UI → Gateway → Services Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           UI Request Flow                                       │
└─────────────────────────────────────────────────────────────────────────────────┘

Browser (Vite React)
        │
        │ WebSocket: ws://localhost:9002
        │ HTTP: http://localhost:8080
        │ MQTT: ws://localhost:9001
        │
        ├──→ POST /api/query (interactive queries)
        │    └─→ Brain service
        │
        ├──→ WebSocket MQTT subscriptions
        │    ├─ kitty/ctx/{conversationId} (context updates)
        │    ├─ kitty/device/* (device state)
        │    └─ kitty/autonomy/* (autonomy status)
        │
        ├──→ GET /api/devices (device discovery)
        │    └─→ Discovery service
        │
        ├──→ POST /api/fabrication (print jobs)
        │    └─→ Fabrication service
        │
        ├──→ POST /api/cad/generate (CAD generation)
        │    └─→ CAD service
        │
        └──→ GET /api/conversations (history)
             └─→ Brain service

        ▼
   ┌──────────────────────┐
   │  GATEWAY Service     │
   │  Port: 8080          │
   │  MQTT Bridge         │
   └────────┬─────────────┘
        │
        │ Routes:
        │ - routing.py (→ Brain)
        │ - devices.py (→ Discovery)
        │ - fabrication.py (→ Fabrication)
        │ - vision.py (→ Vision processing)
        │ - images.py (→ Image storage)
        │ - collective.py (→ Brain collective endpoints)
        │ - io_control.py (→ I/O Control)
        │
        ▼
   ┌──────────────────────────────────────┐
   │   Multiple Backend Services          │
   │                                      │
   │   ├─ Brain (8000) → Queries          │
   │   ├─ Discovery (8500) → Devices      │
   │   ├─ Fabrication (8300) → Printing  │
   │   ├─ CAD (8200) → Design            │
   │   ├─ Safety (8400) → Hazard control │
   │   └─ Broker (8777) → Commands       │
   └──────────────────────────────────────┘
```

### 1.3 Data Flow Through State Layers

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         State Management Architecture                           │
└─────────────────────────────────────────────────────────────────────────────────┘

Request arrives at Brain:

    ┌──────────────────────────────────────────────────────────────┐
    │ 1. IN-MEMORY STATE (Fast, ephemeral)                        │
    │    ConversationStateManager                                  │
    │    ├─ conversation_id → ConversationState                   │
    │    ├─ pending_confirmation (5min timeout)                   │
    │    ├─ history: List[AgentStep]                              │
    │    └─ metadata: Dict[str, Any]                              │
    │                                                               │
    │    Problem: Lost on service restart!                        │
    └──────────────────────────────────────────────────────────────┘
                             │
                             │ (sync via MQTT)
                             ▼
    ┌──────────────────────────────────────────────────────────────┐
    │ 2. MQTT CONTEXT STORE (Distributed state)                   │
    │    Topic: kitty/ctx/{conversation_id}                       │
    │    ├─ QoS: 1 (at least once)                                │
    │    ├─ Retained: true                                         │
    │    ├─ Payload: ConversationContext (JSON)                   │
    │    └─ Connected to: Mosquitto broker                        │
    │                                                               │
    │    Problem: Not durable! Lost if Mosquitto restarts         │
    └──────────────────────────────────────────────────────────────┘
                             │
                             │ (on request/response)
                             ▼
    ┌──────────────────────────────────────────────────────────────┐
    │ 3. POSTGRESQL DATABASE (Durable state)                      │
    │    ├─ conversations table                                    │
    │    ├─ conversation_messages table                            │
    │    ├─ routing_decisions table (audit)                        │
    │    ├─ projects table                                         │
    │    └─ tasks table                                            │
    │                                                               │
    │    Problem: Write lag, not real-time sync with in-memory    │
    └──────────────────────────────────────────────────────────────┘
                             │
                             │ (cache layer)
                             ▼
    ┌──────────────────────────────────────────────────────────────┐
    │ 4. REDIS (Cache & semantic search)                          │
    │    ├─ Streams: kitty:semantic-cache                         │
    │    │  ├─ Key: hash(prompt)                                   │
    │    │  └─ Value: {prompt, response, confidence}              │
    │    │                                                          │
    │    ├─ Strings: kitty:routing:* (cost tracking)             │
    │    └─ Sets: kitty:features:* (feature flags)               │
    │                                                               │
    │    Problem: TTL expirations, no persistence by default      │
    └──────────────────────────────────────────────────────────────┘
                             │
                             │ (vector search)
                             ▼
    ┌──────────────────────────────────────────────────────────────┐
    │ 5. QDRANT (Memory/knowledge store)                          │
    │    ├─ Collection: kitty_memory                              │
    │    ├─ Vectors: embedding model (BAAI/bge-small-en-v1.5)    │
    │    ├─ Metadata: conversation_id, user_id, timestamp         │
    │    └─ Accessed via: mem0-mcp service                        │
    │                                                               │
    │    Problem: Only memories, not conversation state           │
    └──────────────────────────────────────────────────────────────┘

State Consistency Issues:
────────────────────────────
1. IN-MEMORY (ConversationStateManager) is NEVER persisted
   - On brain restart, all pending confirmations lost
   - No recovery mechanism

2. MQTT is unreliable for confirmations
   - Depends on Mosquitto uptime
   - No durability if Mosquitto is down

3. PostgreSQL is slow path
   - Messages recorded after routing completes
   - Creates write-after-read ordering issues

4. No distributed transactions
   - Possible for confirmation to be cleared from memory
     but never recorded in DB

5. Cache invalidation
   - Semantic cache (Redis Streams) never cleared
   - Stale responses can be served indefinitely
```

---

## 2. AUTONOMOUS OPERATIONS ANALYSIS

### 2.1 Scheduled Jobs

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     Autonomous Jobs Schedule (4am-6am PST)                      │
└─────────────────────────────────────────────────────────────────────────────────┘

APScheduler Backend Scheduler (in-process)
├─ Timezone: UTC
├─ Storage: In-memory only
├─ Persistence: NONE (jobs lost on restart)
└─ Status: Only running if AUTONOMOUS_ENABLED=true

Time (PST)   │ Time (UTC) │ Job ID                      │ Schedule      │ Status
─────────────┼────────────┼─────────────────────────────┼───────────────┼─────────
 4:00 AM     │ 12:00 PM   │ daily_health_check          │ Cron: 12:00   │ ACTIVE
             │            │ (jobs.py::daily_health_check) │ daily UTC     │
             │            │                             │               │
 4:30 AM     │ 12:30 PM   │ project_generation_cycle    │ Cron: 12:30   │ ACTIVE
             │            │ (jobs.py)                   │ daily UTC     │
             │            │                             │               │
 5:00 AM     │ 1:00 PM    │ weekly_research_cycle       │ Cron: 13:00   │ ACTIVE
             │            │ (jobs.py)                   │ Mon UTC       │
             │            │                             │               │
 5:00 AM     │ 1:00 PM    │ printer_fleet_health_check  │ Interval:     │ ACTIVE
             │            │ (jobs.py)                   │ every 4 hours │
             │            │                             │               │
 6:00 AM     │ 2:00 PM    │ knowledge_base_update       │ Cron: 14:00   │ ACTIVE
             │            │ (jobs.py)                   │ Mon UTC       │
             │            │                             │               │
 6:00 AM     │ 2:00 PM    │ outcome_measurement_cycle   │ Cron: 14:00   │ ACTIVE
             │            │ (jobs.py::Phase 3)          │ daily UTC     │
             │            │                             │               │
Every 15 min │ Every 15m  │ task_execution_cycle        │ Interval:     │ ACTIVE
             │            │ (jobs.py)                   │ 15 minutes    │
             │            │                             │               │


Active Job Dependencies:
────────────────────────

daily_health_check (12:00 UTC)
├─ Reads: ResourceManager (CPU/memory/budget)
├─ Logs: reasoning.jsonl (struct logs)
├─ Checks: can_run_autonomous flag
└─ Problem: No persistent storage of health metrics

weekly_research_cycle (13:00 UTC, Monday only)
├─ Dependencies:
│  ├─ ResourceManager (budget check)
│  ├─ GoalGenerator (opportunity detection)
│  ├─ FeedbackLoop (learning from past cycles)
│  └─ Database write: goals table
├─ Status: "identified" (awaiting approval)
├─ Scope: 30-day lookback, 3+ failures, 50+ impact score
└─ Problem: Approval mechanism not clear

project_generation_cycle (12:30 UTC, daily)
├─ Requires: Approved goals
├─ Generates: Project objects
├─ Persistence: PostgreSQL projects table
└─ Problem: No coordination with task execution

task_execution_cycle (Every 15 min)
├─ Reads: Ready tasks from DB
├─ Executes: TaskExecutor
├─ Problem: Can run 96 times/day independently
└─ Issue: No mutual exclusion with manual tasks

printer_fleet_health_check (Every 4 hours)
├─ Pings: Connected printers via fabrication service
├─ Updates: Device health status
└─ Problem: Blocking or async? Not clear.

knowledge_base_update (14:00 UTC, Monday)
├─ Refreshes: RAG knowledge base
├─ Source: External APIs
└─ Problem: May conflict with research requests

outcome_measurement_cycle (14:00 UTC, daily)
└─ Problem: Run twice daily (also at 2:00 PM UTC)
```

### 2.2 Job Execution Coordination Issues

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      Autonomy Coordination Problems                             │
└─────────────────────────────────────────────────────────────────────────────────┘

1. SCHEDULER PERSISTENCE
   Problem:  APScheduler stores jobs in memory only
   Impact:   All scheduled jobs lost on brain service restart
   Risk:     No recovery of weekly_research_cycle if brain crashes
   Status:   ❌ CRITICAL

2. RESOURCE CONTENTION
   Scenario: task_execution_cycle (every 15 min) runs while...
            weekly_research_cycle (Monday) generates new tasks
            AND project_generation_cycle generates projects
   Result:   Race condition on projects/tasks tables
   Locking:  No distributed locking mechanism
   Status:   ❌ HIGH RISK

3. BUDGET ALLOCATION
   System:   Separate budgets for "scheduled" vs "exploration" workloads
   Problem:  Not enforced at scheduler level
   Issue:    weekly_research_cycle might exhaust budget
   Impact:   Task execution blocked mid-cycle
   Status:   ⚠️ MEDIUM RISK

4. TASK EXECUTION CONCURRENCY
   Design:   task_execution_cycle runs every 15 minutes
   Problem:  Can execute 96 different tasks per day
   Risk:     Multiple tasks executing in parallel
   Mutex:    No coordination mechanism
   Status:   ❌ HIGH RISK

5. GOAL APPROVAL WORKFLOW
   Flow:     Goals created by weekly_research_cycle with status="identified"
   Problem:  "Awaiting approval" but how?
   Missing:  No UI endpoint shown, no approval callback
   Risk:     Goals might age out or never get approved
   Status:   ❌ UNKNOWN

6. FAILURE RECOVERY
   Current:  Jobs log errors to struct_logger
   Problem:  No retry mechanism
   Result:   Failed weekly_research_cycle is never retried
   Recovery: Manual intervention required
   Status:   ❌ NO RECOVERY
```

### 2.3 Actual Running Status Check

```
In services/brain/src/brain/app.py lifespan:

if autonomous_enabled:
    scheduler = get_scheduler()
    scheduler.start()
    
    # 7 jobs registered
    - daily_health_check
    - weekly_research_cycle
    - knowledge_base_update
    - printer_fleet_health_check
    - project_generation_cycle
    - task_execution_cycle
    - outcome_measurement_cycle
else:
    logger.info("Autonomous mode disabled")

Key Questions:
──────────────
1. Is AUTONOMOUS_ENABLED=true in production? ← UNKNOWN
2. Are jobs actually being triggered? ← NO MONITORING
3. What happens if a job fails? ← LOGGED ONLY
4. Are logs being captured? ← reasoning.jsonl
5. Can jobs be manually triggered? ← NO ENDPOINTS VISIBLE
```

---

## 3. STATE MANAGEMENT DEEP DIVE

### 3.1 State Storage Topology

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          State Storage Matrix                                   │
└─────────────────────────────────────────────────────────────────────────────────┘

┌──────────────┬──────────────┬─────────────┬────────────────┬──────────────────┐
│ Storage      │ Content Type │ Persistence │ Real-Time Sync │ Consistency      │
├──────────────┼──────────────┼─────────────┼────────────────┼──────────────────┤
│ In-Memory    │ Conversation │ NO          │ N/A            │ Single instance  │
│ (Brain)      │ State        │ (ephemeral) │                │ only             │
├──────────────┼──────────────┼─────────────┼────────────────┼──────────────────┤
│ MQTT         │ Context JSON │ MAYBE*      │ YES (QoS=1)    │ Last-write-wins  │
│ (Mosquitto)  │ (retained)   │ *if retain  │ (unreliable)   │ (lossy)          │
│              │              │ disabled    │                │                  │
├──────────────┼──────────────┼─────────────┼────────────────┼──────────────────┤
│ PostgreSQL   │ Messages     │ YES         │ NO (async)     │ ACID (single DB) │
│ (Main DB)    │ Decisions    │ (durable)   │ 100ms+ latency │ isolation=       │
│              │ Conversations│              │                │ read_committed   │
├──────────────┼──────────────┼─────────────┼────────────────┼──────────────────┤
│ Redis        │ Prompt cache │ CONFIGURABLE│ YES (if watch) │ No transactions  │
│ Streams      │ Cost tracking│ (default:no)│                │ (key-based only) │
├──────────────┼──────────────┼─────────────┼────────────────┼──────────────────┤
│ Qdrant       │ Embeddings   │ YES         │ Single insert  │ Atomic writes    │
│ (Vector DB)  │ Memories     │ (persisted) │                │ (vector level)   │
└──────────────┴──────────────┴─────────────┴────────────────┴──────────────────┘

* Mosquitto doesn't persist retained messages to disk by default


Critical State Synchronization Gaps:
────────────────────────────────────

┌─ Pending Confirmations
│  Location: In-memory only (ConversationStateManager._states)
│  TTL: 5 minutes
│  Problem: If brain crashes during confirmation window,
│           confirmation is lost and user sees new prompt
│  Risk: Double-execution of hazard operations
│
├─ Conversation History
│  Location: PostgreSQL (async write)
│  Gap: Message recorded AFTER routing completes
│  Problem: Network partition could lose the message
│  Ordering: Last-written message may not be last-executed
│
├─ Routing Decisions
│  Location: audit_store (PostgreSQL)
│  Gap: Recorded asynchronously
│  Problem: Audit trail may be incomplete
│  Latency: 100ms+ behind actual execution
│
├─ Cost Tracking
│  Location: Redis (ephemeral, no replication)
│  Problem: Cost data lost if Redis crashes
│  Impact: Budget enforcement becomes incorrect
│  Recovery: Manual audit required
│
└─ Goal Status
   Location: PostgreSQL only
   Problem: Goals cached in-memory
   Risk: Status changes not propagated to other services
   Sync: Manual refresh required
```

### 3.2 Consistency Issues Timeline

```
Scenario: User requests hazardous operation (unlock door)

Time Event                              State in Memory  State in DB   State in MQTT
──── ─────────────────────────────────── ──────────────── ──────────── ──────────────
T0   Request arrives                     [empty]          [empty]      [empty]
T1   Orchestrator creates confirmation   CONFIRMED        [async wait]  [async wait]
T2   Response sent to client             CONFIRMED        [pending]     [async wait]
     "Say 'unlock' to confirm"
T3   Brain service crashes               ❌ LOST          [pending]     [pending]
T4   Brain service restarts              [empty]          PENDING       PENDING
T5   User says "unlock door"             [never checked]  PENDING       PENDING
     User confused why it didn't work    
     Or executes again thinking not sent
T6   Brain processes new request         NEW CONFIRMATION PENDING       PENDING
     Creates NEW confirmation
T7   DOUBLE CONFIRMATION ISSUED          ⚠️  HAZARD        PENDING       PENDING
```

---

## 4. MESSAGE PASSING & ASYNC OPERATIONS

### 4.1 Communication Patterns

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     Service-to-Service Communication                            │
└─────────────────────────────────────────────────────────────────────────────────┘

Brain Service Communications:
────────────────────────────

Brain ──HTTP──> Broker (8777)
   ├─ POST /exec (command execution)
   ├─ Audit logging
   └─ Allow-list enforcement

Brain ──HTTP──> Discovery (8500)
   ├─ GET /devices (device list)
   └─ Device status

Brain ──HTTP──> Fabrication (8300)
   ├─ POST /print (submit print job)
   └─ GET /status (print status)

Brain ──HTTP──> CAD (8200)
   ├─ POST /generate (CAD generation)
   └─ GET /status (generation status)

Brain ──MQTT──> Mosquitto (1883)
   ├─ Pub: kitty/ctx/{conversation_id}
   ├─ Sub: kitty/device/* (device state)
   └─ Sub: kitty/autonomy/* (autonomy commands)

Brain ──gRPC──> mem0-mcp (8765)
   └─ Memory operations (search, add, update)

Brain ──TCP──> Qdrant (6333)
   └─ Vector storage

Brain ──TCP──> Redis (6379)
   └─ Cache operations

Brain ──PostgreSQL──> postgres:5432
   └─ Conversation history, audit logs

Gateway ──HTTP──> Brain (8000)
   └─ All client requests forwarded

UI ──WebSocket──> Mosquitto (9001)
   └─ MQTT over WebSocket


No Explicit Message Queue/Broker:
─────────────────────────────────
❌ No RabbitMQ, Kafka, AWS SQS, etc.
✓  MQTT provides pub/sub for real-time updates
❌ MQTT is NOT reliable for critical messages
   (no durability guarantees by default)

Problems:
─────────
1. Task execution is HTTP-based, synchronous
2. No guaranteed delivery for autonomous operations
3. No deadletter queue for failed async operations
4. No event sourcing or change data capture
5. No request tracking across services
```

### 4.2 Async Pattern: task_execution_cycle

```
Brain Service (task_execution_cycle every 15 min):

1. Read:  SELECT * FROM tasks WHERE status='ready' LIMIT 10
2. For each task:
   └─ 3. Call:  TaskExecutor.execute(task)
       ├─ HTTP request to service (Fabrication, CAD, etc.)
       ├─ Await response (BLOCKING)
       └─ Store result in DB
4. Update: UPDATE tasks SET status='completed'
5. Next cycle in 15 minutes

Problems:
─────────
❌ Blocking: If one service is slow, others are blocked
❌ No timeout: Service hang blocks all tasks
❌ No retry: Failed request → task stuck forever
❌ No observability: No logs of what task ran
❌ No deduplication: Same task can run twice if cycle overlaps
```

---

## 5. BOTTLENECK IDENTIFICATION

### 5.1 Critical Bottlenecks

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          Identified Bottlenecks                                 │
└─────────────────────────────────────────────────────────────────────────────────┘

🔴 CRITICAL:

1. Brain Service Lifespan Initialization
   Location: services/brain/src/brain/app.py (lifespan)
   Problem:  Sequential initialization of 10+ components
   Duration: ~5-10 seconds (estimated)
   Impact:   All requests blocked during startup
   Risk:     Kubernetes liveness probe timeout
   ─────────────────────────────────────────────
   Init Order:
   └─ PostgreSQL connection pool (~500ms)
      └─ Checkpointer init (~1000ms)
         └─ Redis init (~100ms)
            └─ Budget manager (~100ms)
               └─ Permission gate (~100ms)
                  └─ MCP servers (research, memory) (~2000ms)
                     └─ Tool executor (~100ms)
                        └─ Model coordinator (~100ms)
                           └─ Research graph build (~3000ms)
                              └─ Session manager (~100ms)

2. Conversation State Serialization (MQTT)
   Location: brain/state/mqtt_context_store.py
   Problem:  Every message publishes full context as JSON
   Size:     Context object can be 10KB+ for long conversations
   Latency:  Network roundtrip for each request/response
   Impact:   O(N) with conversation length
   ─────────────────────────────────────────────
   Timeline:
   └─ Generate response (~2000ms)
      └─ Serialize context (~50ms)
         └─ Publish to MQTT (~100ms)

3. Semantic Cache Lookup (Redis Streams)
   Location: brain/routing/router.py
   Problem:  xrevrange(count=50) for every uncached prompt
   Complexity: O(N) where N = stream length
   Stream Size: Unbounded growth, no eviction policy
   ─────────────────────────────────────────────
   Timeline:
   └─ Hash prompt (~5ms)
      └─ Fetch from Redis Streams (~50-500ms depending on size)
         └─ Parse JSON (~10ms)

4. In-Memory Conversation State (No Eviction)
   Location: brain/conversation/state.py:ConversationStateManager
   Problem:  Stores ALL conversation states indefinitely
   Memory Growth: Linear with active conversations
   Cleanup: cleanup_expired() runs manually, never auto
   ─────────────────────────────────────────────
   Impact:
   └─ After 1000 conversations: ~50MB
      After 10,000 conversations: ~500MB (likely OOM)
      Cleanup needed: hourly or conversation-based

5. Database Async Writes (Race Condition)
   Location: brain/routes/query.py (record_conversation_message)
   Problem:  Fire-and-forget writes, no await
   Scenario: Network partition during write
   Result:   Message lost, audit trail incomplete
   ─────────────────────────────────────────────
   Code:
   └─ try:
         record_conversation_message(...)  # Async, no await!
      except Exception:
         pass  # Silently ignore failures

6. Task Execution Blocking (Every 15 minutes)
   Location: brain/autonomous/task_executor.py
   Problem:  HTTP calls are blocking, sequential
   Max Tasks: If 10 tasks ready, executes sequentially
   Duration: Each could take 30-60 seconds
   Impact:   Next cycle waits for previous to complete
   ─────────────────────────────────────────────
   Worst Case:
   └─ 10 tasks × 60s each = 600s per cycle
      Next cycle starts at T=15min but task still running

🟡 HIGH PRIORITY:

7. Memory MCP Service Performance
   Location: mem0-mcp:8765
   Problem:  Embedding model runs inference for every memory operation
   Model:    BAAI/bge-small-en-v1.5 (~125M params)
   Latency:  ~100-500ms per embedding
   Calls:    Every query + every response = 2 calls/request
   ─────────────────────────────────────────────

8. Research Graph Execution
   Location: brain/research/graph.py
   Problem:  LangGraph runs sequentially through nodes
   Checkpoints: Database writes at each step
   Latency:  500ms-2000ms per research operation
   ─────────────────────────────────────────────

9. Gateway Service (Single Proxy)
   Problem:  All client requests go through gateway
   Load:     Cannot shard or scale independently
   Status:   No load balancer visible in compose
   ─────────────────────────────────────────────

10. PostgreSQL Connection Pool
    Config:  Not visible in code, using default pool size
    Default: SQLAlchemy pool_size=5, max_overflow=10
    Risk:    Only 15 concurrent connections total
    Impact:  Queue formation at 16+ concurrent requests
    ─────────────────────────────────────────────
```

### 5.2 Bottleneck Impact Matrix

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    Bottleneck Severity vs Impact                                │
└─────────────────────────────────────────────────────────────────────────────────┘

Bottleneck                          Severity  Impact Level  Fix Complexity
───────────────────────────────────────────────────────────────────────────────
Brain startup initialization         HIGH      ALL          Medium
Semantic cache lookup                MEDIUM    Single req   Medium
Conversation state serialization     MEDIUM    Every req    Easy
In-memory state growth               MEDIUM    Long-term    Easy
DB async writes (no await)          CRITICAL  Correctness  Easy
Task execution blocking              HIGH      Autonomy     Hard
Memory MCP latency                  MEDIUM    Every query  Hard (model)
Research graph sequential           MEDIUM    Complex ops  Hard
Gateway as SPOF                     MEDIUM    Availability Easy
PostgreSQL pool size                LOW       High load    Easy


P99 Latency Breakdown (estimated):
──────────────────────────────────
Prompt arrival                                 T+0ms
└─ Gateway forward to Brain                    T+10ms
   └─ Record user message (async)              T+15ms
      └─ Load conversation state               T+20ms (in-memory)
         └─ Check cache (Redis Streams)        T+100ms
            └─ Route decision (local/MCP/frontier) T+500-2000ms
               └─ Serialize and publish MQTT   T+2100ms
                  └─ Record response (async)   T+2110ms
                     └─ Return response        T+2150ms

Response received at client: ~2150ms P99
Actual work: ~1500ms
Overhead: ~650ms (30%)
```

---

## 6. ISSUES AND RECOMMENDATIONS

### 6.1 Critical Issues

```
Issue #1: CONVERSATION STATE LOST ON RESTART
─────────────────────────────────────────────
Severity: CRITICAL
Component: ConversationStateManager (in-memory)
Impact: Loss of pending confirmations → possible double-execution

Problem:
  - All in-memory conversation state lost on brain service restart
  - No persistence layer
  - No cache warmup on startup
  
Scenario:
  1. User requests "unlock door"
  2. Brain creates confirmation state in memory
  3. Response: "Say 'unlock' to confirm unlock"
  4. Brain service crashes (OOM, deployment, etc.)
  5. Brain restarts, no state loaded
  6. User says "unlock"
  7. Brain treats it as NEW request, creates NEW confirmation
  8. User confused, may say unlock again
  9. Actual unlock occurs TWICE

Recommendations:
  1. Persist conversation state to PostgreSQL
  2. Load conversation state on startup (warm cache)
  3. Add TTL-based eviction (300s) for in-memory cache
  4. Add cache hit/miss metrics for monitoring

Estimate: 2-3 days to implement


Issue #2: SEMANTIC CACHE IS UNBOUNDED AND NEVER INVALIDATED
─────────────────────────────────────────────────────────────
Severity: CRITICAL
Component: SemanticCache (Redis Streams)
Impact: Stale responses served indefinitely, memory exhaustion

Problem:
  - Redis Streams grow without bound
  - hit_ratio() only counts entries, doesn't implement actual ratio
  - No TTL on cache entries
  - No cache invalidation mechanism
  - Search scans all entries: xrevrange(count=50)

Timeline to Issues:
  - 1000 requests → 100KB stream
  - 10,000 requests → 1MB stream  
  - 100,000 requests → 10MB stream (hours at peak load)
  - Redis maxmemory-policy: allkeys-lfu (may evict important keys)

Recommendations:
  1. Add EXPIRE TTL to cache entries (12 hours?)
  2. Implement proper cache hit ratio metric
  3. Add cache invalidation endpoints
  4. Use sorted set with scores for efficient eviction
  5. Add observability: cache_hit_rate, cache_size_bytes

Estimate: 1 day to implement


Issue #3: AUTONOMOUS JOBS NOT PERSISTED (IN-PROCESS SCHEDULER)
──────────────────────────────────────────────────────────────
Severity: CRITICAL
Component: APScheduler (BackgroundScheduler)
Impact: Job schedules lost on restart, autonomy stops

Problem:
  - Jobs stored in process memory only
  - No persistent job store configured
  - Weekly_research_cycle may not run if brain restarts
  - No observability: is job running or not?

Consequences:
  - If brain crashes Sunday night, Monday research cycle skipped
  - No alerting that jobs are missing
  - Manual intervention required

Solution Options:
  A. Add PostgreSQL job store (better)
  B. Use distributed scheduler (Celery + Redis) (best)
  C. Use Kubernetes CronJobs (simplest)

Recommendations:
  1. Migrate to apscheduler APScheduler with SQLAlchemy backend
  2. Or: Use Kubernetes CronJobs for critical jobs
  3. Add health checks: /healthz returns job count + next run times
  4. Add observability: scheduled_jobs_total, job_last_run timestamp

Estimate: 2-3 days for PostgreSQL, 1 day for K8s


Issue #4: NO DISTRIBUTED LOCKING FOR CONCURRENT EXECUTION
──────────────────────────────────────────────────────────
Severity: CRITICAL
Component: Autonomy orchestration
Impact: Race conditions, double-execution, inconsistent state

Problem:
  - Multiple jobs may run simultaneously:
    - task_execution_cycle (every 15 min)
    - project_generation_cycle (daily)
    - outcome_measurement_cycle (daily)
  - All access same tables: projects, tasks, goals
  - No mutex/locks to prevent concurrent writes
  - PostgreSQL isolation = read_committed (insufficient)

Race Condition Example:
  Time  job_A (task_exec)          job_B (project_gen)
  ────  ──────────────────────     ──────────────────────
  T0    SELECT projects
        WHERE status='ready'        -
  T1    -                           INSERT new project
  T2    UPDATE tasks               -
  T3    -                           UPDATE projects
  T4    COMMIT                      COMMIT
  Result: Inconsistent state, task references deleted project

Recommendations:
  1. Add database-level locks (SELECT ... FOR UPDATE)
  2. Or: Use distributed lock (Redis, Zookeeper)
  3. Implement job mutual exclusion at scheduler level
  4. Add transaction logging for audit trail

Estimate: 1-2 days


Issue #5: DATABASE ASYNC WRITES WITHOUT AWAIT (SILENT FAILURES)
────────────────────────────────────────────────────────────────
Severity: CRITICAL
Component: brain/routes/query.py
Impact: Audit trail incomplete, data loss

Problem:
  record_conversation_message(...) is called but NOT awaited
  Failures are silently caught and logged
  Result: Message lost, no indication to user

Code:
  try:
      record_conversation_message(...)  # ← NOT AWAITED!
  except Exception:
      logger.warning("Failed to record")  # ← Swallowed

Consequences:
  - Audit trail incomplete
  - User cannot retrieve conversation history
  - Cost tracking is inaccurate
  - Compliance issues (missing audit logs)

Recommendations:
  1. Await all database writes
  2. Raise exception if write fails (fail fast)
  3. Return 202 Accepted + background write (explicit async)
  4. Add write queue with dead-letter queue for failed writes

Estimate: 2 hours


Issue #6: NO PENDING CONFIRMATION STATE RECOVERY
─────────────────────────────────────────────────
Severity: HIGH
Component: Confirmation workflow
Impact: Confirmations expire unexpectedly

Problem:
  - Confirmation state is in-memory only
  - TTL = 300 seconds (5 minutes)
  - No way to query current confirmation status
  - No way to explicitly clear confirmation
  - If user steps away, confirmation expires silently

Scenario:
  1. User: "unlock the door"
  2. Brain: "Say 'unlock door now' to confirm"
  3. User steps away for 6 minutes
  4. Confirmation expires
  5. User returns, says "unlock door now"
  6. Brain: "Invalid confirmation, no pending action"

Recommendations:
  1. Add GET /api/confirmation/{conversation_id} endpoint
  2. Add DELETE /api/confirmation/{conversation_id} endpoint
  3. Persist confirmation to PostgreSQL
  4. Add expiration cleanup job
  5. Add notifications before expiration (at 4 min)

Estimate: 1 day
```

### 6.2 High-Priority Issues

```
Issue #7: TASK EXECUTION BLOCKING AND UNOBSERVABLE
──────────────────────────────────────────────────
Severity: HIGH
Impact: Autonomy operations are slow and opaque

Problem:
  - TaskExecutor.execute() makes HTTP calls sequentially
  - Timeouts not configured (relies on default httpx timeout)
  - If one service hangs, all subsequent tasks wait
  - No observability: which task is running?

Timeline:
  Task 1 (Fabrication): 30s
  └─ Task 2 (CAD): waits... 30s
     └─ Task 3 (Discovery): waits... 30s
  Total: 90s for 3 tasks that could run in 30s

Recommendations:
  1. Make task execution concurrent (asyncio.gather)
  2. Set per-service timeouts (fabrication: 60s, cad: 120s)
  3. Add observability:
     - task_execution_duration_seconds
     - task_execution_status (running, failed, etc)
  4. Add retry logic with exponential backoff
  5. Add dead-letter queue for failed tasks

Estimate: 2-3 days


Issue #8: GATEWAY IS SINGLE POINT OF FAILURE
─────────────────────────────────────────────
Severity: MEDIUM
Impact: All client requests blocked if gateway down

Problem:
  - All UI requests go through gateway:8080
  - Gateway is single instance (no replication)
  - No load balancer in front
  - Docker Compose has single gateway service

Compose:
  gateway:
    ports:
      - "8080:8080"  ← Single port, single instance

Recommendations:
  1. Add load balancer (nginx, HAProxy)
  2. Run multiple gateway instances
  3. Use Docker Compose service scaling
  4. Add health checks to load balancer

Estimate: 1 day


Issue #9: POSTGRESQL POOL TOO SMALL
──────────────────────────────────
Severity: MEDIUM
Impact: Connection queue at peak load

Problem:
  - SessionLocal uses default pool size
  - Default: pool_size=5, max_overflow=10
  - Only 15 concurrent connections available
  - System likely has 20-30 concurrent requests

Recommendations:
  1. Increase pool_size to 20
  2. Set max_overflow to 40
  3. Add connection pool monitoring
  4. Add slow query logging

Estimate: 30 minutes


Issue #10: MEMORY MCP LATENCY ON EVERY QUERY
────────────────────────────────────────────
Severity: MEDIUM
Impact: Adds 100-500ms to every request

Problem:
  - Search memories: embed + search + rerank
  - Add memories: embed + store
  - Called on every request → every response
  - Model: BAAI/bge-small-en-v1.5 is slow (125M params)

Timeline:
  Every request = search (300ms) + response embed (300ms) = 600ms overhead

Recommendations:
  1. Cache embeddings for recent conversations
  2. Use smaller/faster model (BAAI/bge-tiny-en-v1.5)
  3. Batch embedding operations
  4. Add async embedding pipeline
  5. Conditional memory search (only for complex queries)

Estimate: 3-5 days
```

### 6.3 Design Improvements

```
Recommended Architecture Changes:
─────────────────────────────────

1. Persistent Job Store
   Current:  APScheduler in-process memory
   Proposed: APScheduler + PostgreSQL backend
   
   Benefits:
   ✓ Jobs persist across restarts
   ✓ Distributed execution possible (future)
   ✓ Job history/audit trail
   ✓ Can manually trigger jobs
   
2. Distributed State Management
   Current:  In-memory + MQTT + PostgreSQL (async)
   Proposed: PostgreSQL (sync) + Redis (cache layer)
   
   Benefits:
   ✓ Strong consistency
   ✓ State recoverable on restart
   ✓ No message loss from crashes
   ✓ Better audit trail
   
3. Message Queue for Async Operations
   Current:  HTTP + no queue
   Proposed: Kafka/RabbitMQ or Redis Streams
   
   Benefits:
   ✓ Reliable task delivery
   ✓ Decoupled services
   ✓ Retry mechanism built-in
   ✓ Observability (consumer lag)
   
4. Distributed Locking
   Current:  None
   Proposed: Redis Locks or PostgreSQL Advisory Locks
   
   Benefits:
   ✓ Prevent concurrent execution
   ✓ Mutual exclusion enforced
   ✓ Deadlock detection possible
   
5. State Checkpointing for Autonomy
   Current:  Projects/tasks in DB, in-memory tracking
   Proposed: LangGraph checkpointing model
   
   Benefits:
   ✓ Resumable workflows
   ✓ Replay capability
   ✓ Failure recovery
   
6. Observability
   Current:  Prometheus metrics, no request tracing
   Proposed: Add distributed tracing (Jaeger, Tempo)
   
   Benefits:
   ✓ End-to-end request tracking
   ✓ Bottleneck identification
   ✓ Service dependency graph
```

---

## APPENDIX: FILES ANALYZED

```
Gateway Service:
  - services/gateway/src/gateway/app.py (42 lines)
  - services/gateway/src/gateway/routes/routing.py
  - Multiple route handlers (vision, token, devices, etc.)

Brain Service:
  - services/brain/src/brain/app.py (318 lines)
  - services/brain/src/brain/orchestrator.py (320 lines)
  - services/brain/src/brain/routes/query.py (266 lines)
  - services/brain/src/brain/routing/router.py (150+ lines)
  - services/brain/src/brain/conversation/state.py (171 lines)
  - services/brain/src/brain/state/mqtt_context_store.py (46 lines)

Autonomous Operations:
  - services/brain/src/brain/autonomous/scheduler.py (150+ lines)
  - services/brain/src/brain/autonomous/jobs.py (150+ lines)
  - services/brain/src/brain/autonomous/task_executor.py
  - services/brain/src/brain/autonomous/resource_manager.py
  - services/brain/src/brain/autonomous/goal_generator.py
  - services/brain/src/brain/autonomous/outcome_tracker.py

State Management:
  - services/common/src/common/cache.py (57 lines)
  - services/common/src/common/db/models.py (100+ lines)

Broker Service:
  - services/broker/src/broker/app.py (185 lines)
  - services/broker/src/broker/executor.py
  - services/broker/src/broker/audit.py

Infrastructure:
  - infra/compose/docker-compose.yml (489 lines)
```

