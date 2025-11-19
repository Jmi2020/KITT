# KITT Research Pipeline Architecture

**Date**: 2025-11-18
**Status**: Documentation of current system architecture and execution flow

## Table of Contents
1. [System Overview](#system-overview)
2. [Execution Flow](#execution-flow)
3. [Key Components](#key-components)
4. [Code Locations](#code-locations)
5. [Data Flow](#data-flow)
6. [Known Issues](#known-issues)

---

## System Overview

The KITT Research Pipeline is an autonomous research system that uses LangGraph to orchestrate multi-step research workflows. It combines web search, webpage fetching, and LLM-based analysis to answer research questions.

### Architecture Stack
- **Framework**: LangGraph (state machine orchestration)
- **Backend**: FastAPI + Python 3.13
- **LLM Integration**: llama.cpp via OpenAI-compatible API
- **Deployment**: Docker Compose
- **Database**: PostgreSQL (for persistence)

### Key Design Principles
1. **Autonomous**: Executes multi-iteration research without human intervention
2. **Iterative**: Breaks down complex questions into sub-questions
3. **Source-Aware**: Tracks citations and source attribution
4. **Claim-Based**: Extracts factual claims from content for verification

---

## Execution Flow

### High-Level Flow
```
User Query → Research Session → Graph Execution → Findings/Claims → Synthesis
```

### Detailed Step-by-Step Execution

#### 1. **Session Creation**
- **Entry Point**: `POST /api/research/sessions` (routes/research.py)
- **Function**: `create_research_session()`
- **Creates**: Database record with session_id, query, status="created"

#### 2. **Graph Initialization**
- **File**: `services/brain/src/brain/research/graph/graph.py`
- **Class**: `ResearchGraph`
- **Method**: `build_graph()`
- **Nodes Created**:
  - `initialize` - Sets up initial state
  - `plan` - Generates research plan and sub-questions
  - `execute_search` - Performs web searches
  - `extract_claims` - Extracts factual claims from content
  - `synthesize` - Generates final synthesis
  - `finalize` - Cleanup and persistence

#### 3. **Planning Phase**
- **Node**: `_planning_node()` in nodes.py
- **Input**: User's original query
- **Process**:
  - LLM generates research strategy
  - Creates 3-5 sub-questions
  - Sets max_iterations (default: 3)
- **Output**: Updates state with sub_questions list

#### 4. **Execution Phase** (Iterative)
For each iteration (up to max_iterations):

##### 4a. Search Execution
- **Node**: `_search_execution_node()` in nodes.py:~700-900
- **Location**: `/Users/Shared/Coding/KITT/services/brain/src/brain/research/graph/nodes.py`
- **Process**:
  1. Selects next sub-question from queue
  2. Calls web_search tool (DuckDuckGo)
  3. Gets 5-10 search results
  4. For each result, calls fetch_webpage
  5. Combines all fetched content
  6. Creates "finding" object with combined content

##### 4b. Claim Extraction
- **Location in nodes.py**: Lines 840-895
- **Trigger**: After finding is added to state
- **Process**:
  ```python
  # Line 846: Log start
  logger.info(f"🔬 Starting claim extraction for finding {finding.get('id')}")

  # Lines 847-849: Debug checkpoints (currently not executing)
  print("PRINT: Line 847 executing", flush=True)
  logger.info("DEBUG_CLAIM_1")

  # Line 852: Get source info
  source_id = finding.get("id", f"source_{state['current_iteration']}")

  # Line 862-872: Call extraction function
  claims = await extract_claims_from_content(
      content=content_for_extraction,
      source_id=source_id,
      source_url=source_url,
      source_title=source_title,
      session_id=state["session_id"],
      query=state["query"],
      sub_question_id=sq_id,
      model_coordinator=components.model_coordinator,
      current_iteration=state["current_iteration"]
  )
  ```

##### 4c. Claim Extraction Function
- **File**: `services/brain/src/brain/research/extraction.py`
- **Function**: `extract_claims_from_content()` (lines 64-230)
- **Location**: `/Users/Shared/Coding/KITT/services/brain/src/brain/research/extraction.py`
- **Process**:
  1. Validates content (lines 86-88)
  2. Truncates if too long (lines 90-101)
  3. Builds prompt with content and query context
  4. Calls LLM via model_coordinator.consult()
  5. Parses JSON response for claims
  6. Returns list of claim objects

**Current Issue**: This function never executes despite being called (see Known Issues)

##### 4d. State Update
- Updates state with:
  - `findings`: List of finding objects
  - `sources`: List of source objects (URL, title, content)
  - `claims`: List of extracted claims (currently empty)
  - `current_iteration`: Increments

##### 4e. Routing Decision
- **Node**: `_should_continue()` routing function
- **Checks**:
  - Have we reached max_iterations?
  - Are there more sub-questions?
  - Do we have enough findings?
- **Routes to**: Either `execute_search` (continue) or `synthesize` (done)

#### 5. **Synthesis Phase**
- **Node**: `_synthesis_node()` in nodes.py
- **Input**: All findings, claims, sources from state
- **Process**:
  1. Aggregates all research findings
  2. LLM generates comprehensive answer
  3. Includes source citations
  4. Formats in markdown
- **Output**: Final synthesis text

#### 6. **Persistence Phase**
- **Node**: `_finalization_node()` in nodes.py
- **Database Operations**:
  - Persist findings to `research_findings` table
  - Persist sources to `research_sources` table
  - Persist claims to `research_claims` table (currently 0 claims)
  - Update session status to "completed"

#### 7. **Response to User**
- **Format**: JSON response with:
  - `session_id`
  - `query`
  - `synthesis` (final answer)
  - `sources` (list of URLs and titles)
  - `metadata` (iterations, findings count, claims count)

---

## Key Components

### 1. **ResearchGraph** (`graph/graph.py`)
Main orchestrator that defines the LangGraph state machine.

**Key Methods**:
- `build_graph()` - Constructs the node graph
- `run()` - Executes the graph for a session

**State Schema**:
```python
{
    "session_id": str,
    "query": str,
    "sub_questions": List[str],
    "current_iteration": int,
    "max_iterations": int,
    "findings": List[dict],
    "sources": List[dict],
    "claims": List[dict],
    "synthesis": str,
    "status": str
}
```

### 2. **Nodes** (`graph/nodes.py`)
Contains all graph node implementations.

**Important Functions**:
- `_planning_node()` (lines ~150-250)
- `_search_execution_node()` (lines ~700-900)
- `_synthesis_node()` (lines ~500-600)
- `_finalization_node()` (lines ~950-1050)

### 3. **Tools** (`tools/`)
External tools available to the research system.

**Available Tools**:
- `web_search` - DuckDuckGo search (tool_web_search.py)
- `fetch_webpage` - Jina Reader or native fetcher (tool_fetch_webpage.py)
- `research_deep` - Recursive deep research (not used in main flow)

### 4. **Model Coordinator** (`model_coordinator.py`)
Manages LLM interactions across different models.

**Key Method**:
- `consult(prompt, system_message, response_format)` - Sends prompts to LLM
- Routes to different llama.cpp servers based on model alias

### 5. **Extraction Module** (`extraction.py`)
Handles claim extraction from research content.

**Key Function**:
- `extract_claims_from_content()` (lines 64-230)

**Prompt Template** (lines 105-140):
```
You are a research assistant extracting factual claims from web content.

Original Research Query: {query}
Content from: {source_title}

Extract verifiable factual claims from the following content:
{content}

Return ONLY a JSON object with this structure:
{
  "claims": [
    {
      "claim": "The specific factual claim",
      "evidence": "Direct quote or evidence from content",
      "confidence": "high|medium|low"
    }
  ]
}
```

---

## Code Locations

### Docker Container Structure
```
/app/
├── services/
│   └── brain/
│       ├── src/
│       │   └── brain/
│       │       ├── app.py                    # FastAPI entry point
│       │       ├── orchestrator.py           # Request routing
│       │       ├── research/
│       │       │   ├── graph/
│       │       │   │   ├── graph.py          # ResearchGraph class
│       │       │   │   └── nodes.py          # Node implementations
│       │       │   ├── extraction.py         # Claim extraction
│       │       │   └── tools/                # Research tools
│       │       ├── routing/
│       │       │   ├── router.py
│       │       │   ├── model_coordinator.py
│       │       │   └── llama_cpp_client.py
│       │       └── routes/
│       │           └── research.py           # API endpoints
│       └── Dockerfile                        # Python 3.13-slim
└── .logs/
    └── reasoning.log                         # Main log file
```

### Host Filesystem (Bind Mount)
```
/Users/Shared/Coding/KITT/
├── services/brain/                           # Mounted to /app/services/brain
├── Research/                                 # Investigation docs
│   ├── claim_extraction_investigation_session2.md
│   └── research_pipeline_architecture.md (this file)
└── infra/compose/
    └── docker-compose.yml                    # Container orchestration
```

### Important File Paths

#### In Container:
- Graph: `/app/services/brain/src/brain/research/graph/nodes.py`
- Extraction: `/app/services/brain/src/brain/research/extraction.py`
- Logs: `/app/.logs/reasoning.log`

#### On Host:
- Graph: `/Users/Shared/Coding/KITT/services/brain/src/brain/research/graph/nodes.py`
- Extraction: `/Users/Shared/Coding/KITT/services/brain/src/brain/research/extraction.py`
- Docker Compose: `/Users/Shared/Coding/KITT/infra/compose/docker-compose.yml`

---

## Data Flow

### Object Schemas

#### Finding Object
```python
{
    "id": "finding_1_{session_id}_{tool_name}_{iteration}",
    "content": "Combined content from all fetched webpages",
    "tool": "web_search",
    "iteration": 1,
    "sub_question_id": "sq_1"
}
```

#### Source Object
```python
{
    "id": "source_{iteration}_{index}",
    "url": "https://example.com/article",
    "title": "Article Title",
    "content": "Fetched webpage content in markdown",
    "tool": "web_search",
    "relevance": 0.85,
    "iteration": 1
}
```

#### Claim Object (Expected)
```python
{
    "id": "claim_{session_id}_{index}",
    "claim": "Specific factual statement",
    "evidence": "Supporting quote from source",
    "confidence": "high",
    "source_id": "source_1_0",
    "source_url": "https://example.com/article",
    "source_title": "Article Title",
    "sub_question_id": "sq_1"
}
```

### Database Schema

#### research_sessions
```sql
session_id          UUID PRIMARY KEY
query               TEXT
status              VARCHAR(50)
created_at          TIMESTAMP
completed_at        TIMESTAMP
synthesis           TEXT
metadata            JSONB
```

#### research_findings
```sql
id                  UUID PRIMARY KEY
session_id          UUID REFERENCES research_sessions
content             TEXT
tool                VARCHAR(100)
iteration           INTEGER
sub_question_id     VARCHAR(200)
```

#### research_sources
```sql
id                  UUID PRIMARY KEY
session_id          UUID REFERENCES research_sessions
url                 TEXT
title               VARCHAR(500)
content             TEXT
relevance           FLOAT
tool                VARCHAR(100)
```

#### research_claims
```sql
id                  UUID PRIMARY KEY
session_id          UUID REFERENCES research_sessions
claim               TEXT
evidence            TEXT
confidence          VARCHAR(20)
source_id           VARCHAR(500)
source_url          TEXT
source_title        VARCHAR(500)
```

---

## Known Issues

### 1. **Claim Extraction Not Executing** ❌ CRITICAL

**Symptom**: Research sessions complete with 0 claims extracted despite fetching 7,000+ chars of content.

**Evidence**:
```
[INFO] 🔬 Starting claim extraction for finding finding_1_...        ✅ Line 846 executes
[DEBUG] DEBUG_CLAIM_2: source_id = finding_1_...                     ✅ Line 853 executes

MISSING:
- Line 847: print("PRINT: Line 847 executing", flush=True)            ❌ Never appears
- Line 848: logger.info("DEBUG_CLAIM_1")                              ❌ Never appears
- Line 849: logger.info("DEBUG_CLAIM_1b")                             ❌ Never appears
- Lines 857-897: All subsequent DEBUG_CLAIM logs                      ❌ Never appear
```

**Investigation Status**:
- ✅ Python 3.13 upgrade completed (Session 2)
- ✅ Bytecode files deleted (all `__pycache__` removed)
- ✅ Container restarted (started at 2025-11-18T20:34:04)
- ✅ Code verified in both host and container
- ❌ **Still broken** - execution jumps from line 846 → 853

**Root Cause**: Unknown. Physically impossible code execution pattern.

**Hypotheses**:
1. **Uvicorn worker caching** - 2 workers may have stale module cache
2. **Python import caching** - sys.modules cache despite no bytecode
3. **Hidden exception** - Something raising between 846-847 but caught silently
4. **Code patching** - Some decorator or metaclass modifying execution
5. **Bind mount issue** - Container not seeing latest file changes

**Next Steps**:
- Try reducing to single uvicorn worker (remove `--workers 2`)
- Force complete rebuild: `docker compose build --no-cache brain`
- Add module reload: `importlib.reload(nodes)`
- Check for decorators on the function containing this code

### 2. **Database Varchar Truncation** ⚠️ NON-CRITICAL

**Error**: `value too long for type character varying(200)`

**Impact**: Titles/fields truncated in database

**Fix**: Increase VARCHAR limits or use TEXT type

### 3. **Jina Reader Disabled** ℹ️ CONFIGURED

**Config**: `JINA_READER_DISABLED=true` in .env

**Reason**: Using native webpage fetcher instead

**Impact**: None (fallback working correctly)

---

## Environment Configuration

### Docker Container Settings
```yaml
# docker-compose.yml
services:
  brain:
    image: compose-brain:latest
    build:
      context: ../../services/brain
      dockerfile: Dockerfile
    command: python -m uvicorn brain.app:app --host 0.0.0.0 --port 8000 --workers 2
    environment:
      - PYTHONDONTWRITEBYTECODE=1
      - PYTHONUNBUFFERED=1
      - JINA_READER_DISABLED=true
    volumes:
      - ../../services/brain:/app/services/brain
    ports:
      - "8000:8000"
```

### Python Version
- **Container**: Python 3.13.9 (`python:3.13-slim`)
- **Host**: Python 3.13.3

### LLM Servers
- **Primary**: http://host.docker.internal:8082 (Q4 quantized model)
- **F16**: http://host.docker.internal:8083 (FP16 model)
- **Tool Calling**: Enabled on port 8083

---

## Testing Commands

### Run Research Session
```bash
# Via CLI
kitty-cli research "What are the benefits of green tea?" --no-config

# Via API
curl -X POST http://localhost:8000/api/research/sessions \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the benefits of green tea?", "max_iterations": 3}'
```

### Monitor Logs
```bash
# Container logs (stdout)
docker logs -f compose-brain-1

# Application logs (reasoning.log)
docker exec compose-brain-1 tail -f .logs/reasoning.log

# Search for specific session
docker exec compose-brain-1 grep "SESSION_ID" .logs/reasoning.log
```

### Check Claim Extraction
```bash
# Check if claims were extracted for session
docker exec compose-brain-1 grep "SESSION_ID" .logs/reasoning.log | grep -E "(🔬|claim|DEBUG_CLAIM)"

# Check database
psql -h localhost -U postgres -d kitt -c "SELECT COUNT(*) FROM research_claims WHERE session_id = 'SESSION_ID';"
```

### Verify Code in Container
```bash
# Check specific lines
docker exec compose-brain-1 sed -n '845,860p' /app/services/brain/src/brain/research/graph/nodes.py

# Verify no bytecode
docker exec compose-brain-1 find /app/services/brain -name "*.pyc"
```

### Restart Brain Service
```bash
# Restart only
docker compose -f /Users/Shared/Coding/KITT/infra/compose/docker-compose.yml restart brain

# Rebuild and restart
docker compose -f /Users/Shared/Coding/KITT/infra/compose/docker-compose.yml up -d --build brain

# Full rebuild (no cache)
docker compose -f /Users/Shared/Coding/KITT/infra/compose/docker-compose.yml build --no-cache brain
```

---

## References

### Related Documentation
- `/Users/Shared/Coding/KITT/Research/claim_extraction_investigation_session2.md` - Python 3.13 upgrade and debugging
- `/Users/Shared/Coding/KITT/Research/webpage_fetching_WORKING.md` - Webpage fetching works correctly
- `/Users/Shared/Coding/KITT/Research/KITT_Research_System_Fixes.md` - Original issues document

### Key GitHub Issues
- Claim extraction returning 0 claims (unresolved)
- Python bytecode caching with bind mounts (resolved)

---

## Appendix: Function Call Chain

**Complete execution path for a research query:**

```
1. POST /api/research/sessions
   └─> create_research_session() in routes/research.py
       └─> ResearchGraph.run() in graph/graph.py
           └─> graph.ainvoke(initial_state)
               ├─> _planning_node()
               │   └─> model_coordinator.consult()
               │       └─> llama.cpp /v1/chat/completions
               │
               ├─> _search_execution_node() [LOOP: max_iterations]
               │   ├─> web_search(query)
               │   │   └─> DuckDuckGo API
               │   ├─> fetch_webpage(url) [LOOP: per result]
               │   │   └─> Native fetcher (Jina disabled)
               │   └─> extract_claims_from_content() [❌ NOT EXECUTING]
               │       └─> model_coordinator.consult()
               │           └─> llama.cpp /v1/chat/completions
               │
               ├─> _synthesis_node()
               │   └─> model_coordinator.consult()
               │       └─> llama.cpp /v1/chat/completions
               │
               └─> _finalization_node()
                   └─> Database persistence
                       ├─> INSERT INTO research_findings
                       ├─> INSERT INTO research_sources
                       └─> INSERT INTO research_claims [0 rows]
```

---

**Document Version**: 1.0
**Last Updated**: 2025-11-18
**Next Review**: After claim extraction fix is implemented
