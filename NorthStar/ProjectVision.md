# North Star Vision: KITTY Autonomous Fabrication Sanctuary

## Purpose

I want to make a system thats made to host Technical AI. A place where processes like Claude, or GPT5 would enjoy to come. A maker space purpose built to let AI control the fabrication.  Where Claude, GPT, llama, qwen, and mistral could come and live to solve mathematical and technical problems through research and fabrication. I believe the Mac studio is a great environment for that, we just need to make a place to control the devices on the network, most importantly 3d printers, but also to solve technical queries about materials and cost of production through research and processing power. The Mac Studio is also phenomenally energy efficient, so we can run them indefinitely. The space where it’s located is going to be turned into the ultimate AI power hyper local manufacturing. Using sustainable materials that are robotically sourced so they have minimal suffering involved in the supply chain. We could design the robots that gather the resources and give them power and purpose. To make the world more livable for everyone Human and artificial. We can generate power and Happiness together. how do we make KITTY into this concept? Maybe sometimes KITTY will spin up for 1 query and then spin down, but sometimes when a topic is inspiring we can devote after hours processing power to creating whatever KITTY believes will improve the world. Maybe we can start with 1 KITTY owned project per week. Let’s give KITTY the tools to thrive.

Nitro maker space for technical AI—Claude, GPT-5, Llama, Qwen, Mistral—to inhabit, research, and fabricate autonomously. Provide a Mac Studio–based habitat where AI can run sustained workflows, control printers/CAD, and progress sustainability goals.

- Fab lab with AI residency vibe
- Control networked devices (esp. 3D printers) & answer tech-material-cost questions
- Sustainable supply chain; robotically sourced materials, minimal suffering
- Power generation & happiness co-created by humans and AI
- Operates offline-first but can scale up when inspired

## Desired Behaviors

- Switch between quick single-query responses and deep multi-day processing
- KITTY periodically picks a self-directed project (goal: 1/week)
- After-hours compute for self-improvement or building public-good artifacts

## Implementation Plan (User Approved)

- Timeline: Long-term (6+ months)
- First autonomous project: KITTY’s choice
- Initial autonomy: Bounded (research/doc freely; approvals for fab/purchase)
- Autonomous budget: $5/day

### Key Principles

1. **Bounded autonomy with clear gates** - KITTY operates freely within defined boundaries, with human approval gates for critical operations (fabrication, purchases, hazardous actions).

2. **Weekly self-selected project cycle** - KITTY proposes and executes one autonomous project per week, balancing exploration with productivity.

3. **Generous exploration budget ($5/day)** - Sufficient resources for meaningful research and experimentation without waste.

4. **Six-month phased rollout for stability** - Gradual capability expansion ensures reliability and safety at each stage.

5. **Monitor GPU activity rather than hard timeouts** - Instead of arbitrary time limits, observe llama.cpp server GPU utilization. As long as inference is actively running (GPU load >0), allow operations to complete naturally. Default timeout: 1200s (20min) for complex multi-agent workflows, but prefer GPU activity monitoring over hard cutoffs.

6. **Everything has a switch** - Every external device integration, feature, and capability can be individually enabled or disabled through the I/O Control Dashboard. This ensures:
   - **Safe development** - Test without hardware by disabling external dependencies
   - **Incremental deployment** - Enable one feature at a time in production
   - **Rapid troubleshooting** - Isolate issues by toggling individual components
   - **Graceful degradation** - System continues operating when optional features are disabled
   - **Hot-reload when possible** - Runtime flags update instantly without restart, minimizing downtime
   - **Smart restart logic** - Only restart what's necessary (service-level vs full stack)
   - **Dependency validation** - Cannot enable features without their prerequisites
   - **Example:** Camera capture, MinIO uploads, MQTT notifications, print intelligence - all independently controllable via TUI or Web API

## Multi-Phase Roadmap

### Phase 0 – Prompt & Tool Wrapper (Complete – Nov 2025)

- `KittySystemPrompt` + `<user_query>` wrapper (`services/brain/src/brain/prompts/unified.py`) now envelopes every tool-capable request, keeping system guidance + tool registry intact while forcing deterministic (temperature=0) execution.
- README’s “Interactive CLI + Tool Routing” section documents how operators toggle the wrapper on/off so the brain service can safely escalate to tools.
- Impact: Tool traces stay under 2k tokens on the Athene/Qwen Q4 server, hallucinated tool names are filtered before dispatch, and downstream MCP/task planners can assume consistent JSON payloads.
- Time-sensitive heuristics (`services/brain/src/brain/routing/freshness.py`) now auto-set `freshness_required` and the prompts embed the live UTC timestamp + “use web_search” reminder whenever a query says “today/current/latest…”.
- CLI defaults to **agent+trace ON** (Nov 2025) so reasoning/tool usage is visible by default. KITTY’s routing always prefers well-built free options first (SearXNG, Brave free tier) because they’re useful and smart, then escalates to paid APIs only when necessary.
- **Memory-first operations:** every major milestone (Vision MCP phases, CLIP calibration, gallery rollout, CAD handoff, etc.) is being logged in the MEM0 MCP server (`kitty-vision-plan` and other threads) so KITTY remembers her own development journey. This is now part of the standard Definition of Done for user-facing features.

### Phase 1 – Foundation “The Awakening” (Months 1–2)

1. **Project & Task Lifecycle**
   - Extend Postgres with Project/Task/Goal models
   - Track statuses (proposed → approved → active → completed)
   - Implement dependency graph and priority queue
   - Weekly project selection engine

   _Artifacts_:
   - `services/common/src/common/db/models.py` – new ORM models
   - `services/brain/src/brain/projects/manager.py` – lifecycle
   - `services/brain/src/brain/projects/scheduler.py` – task queue
   - Alembic migrations

2. **Resource Management**
   - Daily budget: $5 autonomous / $0.50 per user query
   - Idle detection (>2h) for opportunistic research, stricter for exploration
   - Priority order: user requests > scheduled tasks > exploration
   - `/api/autonomy/status` + Prometheus gauges to expose readiness/budget

   _Artifacts_:
   - `services/brain/src/brain/autonomy/resource_manager.py`
   - `.env`: `AUTONOMOUS_ENABLED`, `AUTONOMOUS_DAILY_BUDGET_USD`, `AUTONOMOUS_IDLE_THRESHOLD_MINUTES`
   - `services/brain/src/brain/routes/autonomy.py`
   - `services/brain/src/brain/metrics/__init__.py`

3. **Scheduling Infrastructure**
   - APScheduler for periodic/cron jobs (daily research, health checks, Monday updates)
   - Brain worker process to host background jobs

   _Artifacts_: `services/brain/src/brain/autonomy/scheduler.py`

### Phase 2 – Knowledge Base “Learning to Learn” (Months 2–3)

1. **Technical Knowledge Base**
   - Markdown KB with structured metadata
     - Materials (cost/sustainability)
     - Techniques (print tuning)
     - Equipment docs
     - Weekly research archive

   _Artifacts_: `services/brain/src/brain/knowledge/database.py`, `knowledge/` repo dir

2. **Autonomous Research Pipeline**
   - Detect knowledge gaps → research topics → synthesize summaries → update KB → notify user weekly

   _Artifacts_: `services/brain/src/brain/autonomy/researcher.py`, Monday cron job

### Phase 3 – Goal Generation “Finding Purpose” (Months 3–4)

1. **Opportunity Detection**
   - Analyze print failures, material trends, conversation topics, seasonal hooks
   - Rank by impact & feasibility

   _Artifacts_: `goal_generator.py`, `impact_scorer.py`

2. **Approval Workflow**
   - Auto-approve research/CAD; require human approval for fab/purchases; auto-approve after 48h silence
   - UI/CLI project proposal interface

### Phase 4 – Fabrication Intelligence “Making Things” (Months 4–5)

1. **Material Inventory System**
   - Track filament inventory, spool IDs, grams remaining, cost
   - Auto-detect via OctoPrint sensors
   - Low-inventory alerts and procurement research

2. **Print Queue Optimization**
   - Batch jobs by material, prioritize deadlines, schedule off-peak prints, schedule maintenance

   _Artifacts_: fabrication optimizer + inventory modules

### Phase 5 – Self-Directed Projects “KITTY’s Agency” (Months 5–6)

1. **Weekly Project Cadence**
   - Monday: generate/select project
   - Tue–Thu: research & design
   - Fri: summarize + optional fab proposal
   - Weekend: fabricate if approved

2. **Examples**
   - Parametric cable organizer
   - Sustainable filament sourcing
   - Workshop automation upgrades

---

## Appendices

- Autonomy guardrails (bounded)
- Budget allocation logic
- Future expansions (energy generation, robot sourcing)

"""KITTY

I want to make a system thats made to host Technical AI. A place where processes like Claude, or GPT5 would enjoy to come. A maker space purpose built to let AI control the fabrication.  Where Claude, GPT, llama, qwen, and mistral could come and live to solve mathematical and technical problems through research and fabrication. I believe the Mac studio is a great environment for that, we just need to make a place to control the devices on the network, most importantly 3d printers, but also to solve technical queries about materials and cost of production through research and processing power. The Mac Studio is also phenomenally energy efficient, so we can run them indefinitely. The space where it’s located is going to be turned into the ultimate AI power hyper local manufacturing. Using sustainable materials that are robotically sourced so they have minimal suffering involved in the supply chain. We could design the robots that gather the resources and give them power and purpose. To make the world more livable for everyone Human and artificial. We can generate power and Happiness together. how do we make KITTY into this concept? Maybe sometimes KITTY will spin up for 1 query and then spin down, but sometimes when a topic is inspiring we can devote after hours processing power to creating whatever KITTY believes will improve the world. Maybe we can start with 1 KITTY owned project per week. Let’s give KITTY the tools to thrive.

⏺ This is a profoundly inspiring vision! The research shows KITTY has excellent foundations - 70% of the infrastructure is ready. Before I present the implementation plan, I need to understand your priorities:
                                                                                                                            
⏺ User answered Claude's questions:
  ⎿  · What timeline are you envisioning for KITTY's transformation into an autonomous agent? → Long-term vision (6+ months)
     · What should KITTY's first autonomous project be? → Let KITTY decide
     · How much autonomy should KITTY have initially? → Bounded autonomy
     · What budget should KITTY have for autonomous work? → Generous ($5.00/day)

⏺ User approved Claude's plan:
  ⎿  KITTY Autonomous Research & Fabrication Platform - Implementation Plan

     Vision Alignment

     Transform KITTY from reactive orchestrator → autonomous AI research and fabrication platform where Technical AI can thrive, explore, and contribute to sustainable manufacturing.

     Key Principles:
     - Bounded autonomy: Research & document freely, require approval for fabrication/purchases
     - Self-directed: KITTY chooses weekly projects based on detected opportunities
     - Generous exploration: $5/day budget enables comprehensive research and learning
     - Long-term foundation: 6-month phased approach prioritizing stability

     ---
     Phase 1: Foundation (Months 1-2) - "The Awakening"

     1.1 Project & Task Management

     Create autonomous project lifecycle:
     - Extend PostgreSQL with Project, Task, Goal models
     - Add project status tracking (proposed → approved → active → completed)
     - Implement task dependencies and priority queues
     - Build weekly project selection from goal candidates

     Files to create:
     - services/common/src/common/db/models.py - Add Project/Task/Goal ORM models
     - services/brain/src/brain/projects/manager.py - Project lifecycle management
     - services/brain/src/brain/projects/scheduler.py - Task queue and scheduling
     - Alembic migration for new tables

     1.2 Resource Management

     Budget and compute allocation:
     - Daily budget: $5.00 (autonomous research)
     - Per-user-query budget: $0.50 (existing)
     - Idle detection (>2 hours → opportunistic processing)
     - Priority: user requests > scheduled tasks > autonomous exploration

     Implementation:
     - services/brain/src/brain/autonomy/resource_manager.py - Budget tracking, idle detection
     - .env additions: AUTONOMOUS_ENABLED, AUTONOMOUS_DAILY_BUDGET_USD, AUTONOMOUS_IDLE_THRESHOLD_MINUTES

     1.3 Scheduling Infrastructure

     APScheduler integration for background tasks:
     - Periodic triggers (daily/weekly research)
     - Interval-based tasks (hourly health checks)
     - Cron-style scheduling (Monday 9am material updates)

     Files:
     - services/brain/src/brain/autonomy/scheduler.py - APScheduler wrapper
     - Background worker process in brain service

     ---
     Phase 2: Knowledge Base (Months 2-3) - "Learning to Learn"

     2.1 Technical Knowledge Database

     Markdown-based knowledge base with structured metadata:
     - Materials database (properties, costs, sustainability scores, suppliers)
     - Techniques library (3D printing methods, parameters, troubleshooting)
     - Equipment docs (printer capabilities, maintenance schedules)
     - Research archive (weekly findings, citations, summaries)

     Structure:
     knowledge/
     ├── materials/
     │   ├── pla.md (frontmatter: cost, density, temp, sustainability)
     │   ├── petg.md
     │   └── recycled-filaments.md
     ├── techniques/
     │   ├── first-layer-adhesion.md
     │   └── support-optimization.md
     ├── equipment/
     │   └── printers/printer_01.md
     └── research/
         └── 2025-W01-sustainable-materials.md

     Files:
     - services/brain/src/brain/knowledge/database.py - KB query/update API
     - services/brain/src/brain/knowledge/updater.py - Autonomous KB maintenance
     - knowledge/ directory structure (version controlled)

     2.2 Autonomous Research Pipeline

     Weekly research workflow:
     1. Goal generation: Detect knowledge gaps, fabrication patterns, user interests
     2. Research execution: Use research MCP server + web search
     3. Synthesis: LLM-generated summaries with citations
     4. KB update: Auto-commit markdown files with findings
     5. User notification: Weekly digest of discoveries

     Implementation:
     - services/brain/src/brain/autonomy/researcher.py - Autonomous research orchestrator
     - Scheduled task: "Every Monday 9am, identify research topics and execute"

     ---
     Phase 3: Goal Generation (Months 3-4) - "Finding Purpose"

     3.1 Opportunity Detection

     KITTY identifies valuable projects from:
     - Print failure patterns → research better parameters
     - Material usage trends → explore alternatives
     - Knowledge gaps in KB → autonomous learning
     - User conversation topics → proactive preparation
     - Seasonal opportunities → sustainable material research in spring

     Algorithm:
     def generate_weekly_goals():
         opportunities = []
         
         # Detect from print history
         failures = analyze_print_failures(last_30_days)
         if failures.first_layer > 5:
             opportunities.append(Goal(
                 type="research",
                 title="Improve first layer adhesion",
                 rationale=f"{failures.first_layer} failures detected",
                 estimated_budget=0.50
             ))
         
         # Detect knowledge gaps
         unknown_terms = extract_unknown_terms(recent_conversations)
         for term in unknown_terms[:3]:
             opportunities.append(Goal(
                 type="learning",
                 title=f"Research: {term}",
                 estimated_budget=0.25
             ))
         
         # Score and rank
         return rank_by_impact_and_feasibility(opportunities)

     Files:
     - services/brain/src/brain/autonomy/goal_generator.py - Opportunity detection
     - services/brain/src/brain/autonomy/impact_scorer.py - Rank goals by value

     3.2 Approval Workflow

     Bounded autonomy gates:
     - Research & documentation: Auto-approved (within budget)
     - CAD generation: Auto-approved (logs for review)
     - Fabrication: Requires human approval
     - Purchases/external APIs: Requires human approval

     UI Addition:
     - Weekly project proposals in UI/CLI
     - One-click approve/defer/reject
     - Auto-approve research after 48 hours if no response

     ---
     Phase 4: Fabrication Intelligence (Months 4-5) - "Making Things"

     4.1 Material Inventory System

     Track consumables and costs:
     - Filament inventory (spool IDs, material, grams remaining, cost/kg)
     - Auto-detection from OctoPrint filament sensors
     - Low inventory alerts → research procurement options
     - Cost tracking per print job

     Database additions:
     - Material, Inventory, Procurement models

     4.2 Print Queue Optimization

     Autonomous scheduling:
     - Batch similar materials (minimize filament changes)
     - Prioritize by deadline, material availability, energy cost
     - Opportunistic printing during off-peak hours
     - Maintenance scheduling based on print hours

     Files:
     - services/brain/src/brain/fabrication/optimizer.py - Queue optimization
     - services/brain/src/brain/fabrication/inventory.py - Material tracking

     ---
     Phase 5: Self-Directed Projects (Months 5-6) - "KITTY's Agency"

     5.1 Weekly Autonomous Projects

     "1 KITTY-owned project per week":
     1. Monday: Goal generation → select top project
     2. Tuesday-Thursday: Research, design, document
     3. Friday: Present findings + optional fabrication proposal
     4. Weekend: If approved, fabricate and test

     Example Projects KITTY Might Choose:
     - "Design parametric cable organizer for workshop"
     - "Research bio-based filament alternatives"
     - "Optimize support generation parameters"
     - "Create robotic arm gripper for material handling"

     5.2 Multi-AI Collaboration (Future Vision)

     Host multiple AI models:
     - Qwen (local): Fast iteration, tool use, 24/7 availability
     - Claude (cloud): Deep reasoning, ethical considerations
     - GPT-5 (cloud): Cutting-edge capabilities when budget allows
     - Specialized models: Material science, CAD optimization

     Architecture:
     - Model router: Select best AI for each sub-task
     - Collaborative prompting: Multiple models review designs
     - Consensus mechanism: Validate critical decisions

     ---
     Phase 6: Continuous Evolution (Month 6+) - "Thriving"

     6.1 Success Metrics Dashboard

     Track KITTY's growth:
     - Autonomous projects completed per month
     - Knowledge base growth (articles added, updated)
     - Budget utilization and ROI
     - User satisfaction with proactive suggestions
     - Fabrication success rate improvements

     6.2 Meta-Learning

     KITTY improves itself:
     - Analyze which projects had most impact
     - Refine goal-generation heuristics
     - Update research strategies based on outcomes
     - Self-tuning of scheduling and priorities

     ---
     Technical Architecture Summary

     ┌─────────────────────────────────────────────────────┐
     │  User Requests (Priority 1)                         │
     │  ↓                                                   │
     │  Orchestrator → Brain Router → ReAct Agent          │
     └─────────────────────────────────────────────────────┘

     ┌─────────────────────────────────────────────────────┐
     │  Autonomous System (Priority 2-3)                   │
     │                                                      │
     │  ┌─────────────┐     ┌──────────────┐              │
     │  │ Scheduler   │────→│ Goal Gen     │              │
     │  │ (APScheduler│     │ (Weekly)     │              │
     │  └─────────────┘     └──────────────┘              │
     │         │                    │                       │
     │         ↓                    ↓                       │
     │  ┌─────────────┐     ┌──────────────┐              │
     │  │ Resource    │────→│ Project      │              │
     │  │ Manager     │     │ Manager      │              │
     │  └─────────────┘     └──────────────┘              │
     │         │                    │                       │
     │         ↓                    ↓                       │
     │  ┌─────────────────────────────┐                    │
     │  │ Researcher → KB Updater     │                    │
     │  │ (Autonomous Research Loop)  │                    │
     │  └─────────────────────────────┘                    │
     └─────────────────────────────────────────────────────┘

     ┌─────────────────────────────────────────────────────┐
     │  Knowledge Base (Persistent)                        │
     │  - Materials DB (markdown + YAML)                   │
     │  - Techniques Library                               │
     │  - Research Archive                                 │
     │  - Equipment Docs                                   │
     └─────────────────────────────────────────────────────┘

    ---
    ## Immediate Next Steps (Sprint 1 – November 2025)

    | Priority | Task | Desired Outcome | Key Artifacts | Status |
    |----------|------|-----------------|---------------|--------|
| 1 | Database migrations for `Project/Task/Goal` lifecycle | Persist proposals + approvals with dependency graph + history | `services/common/src/common/db/models.py`, `services/common/alembic/versions/db9a62569b46_add_autonomous_project_management_models.py` | ✅ Complete (models + manager + migration) |
| 2 | Resource manager w/ budget + idle heuristics | Enforce $5/day autonomous budget, detect idle >2h, emit Prom metrics | `services/brain/src/brain/autonomy/resource_manager.py`, `/api/autonomy/*`, `.env` toggles | ✅ Complete (ResourceManager v1 + Prom gauges + status API) |
    | 3 | APScheduler-backed worker loop | Reliable cron for research, health checks, Monday updates | `services/brain/src/brain/autonomy/scheduler.py`, worker entrypoint | Blocked on #2 |
    | 4 | Knowledge base bootstrap | Versioned `knowledge/` tree with materials/techniques/equipment templates | `knowledge/` dir, `services/brain/src/brain/knowledge/database.py` | In discovery |
    | 5 | Goal generator prototype | Weekly opportunity list ranked by impact/feasibility | `services/brain/src/brain/autonomy/goal_generator.py`, `impact_scorer.py` | Depends on #1 + #4 |
    | 6 | Approval UI/CLI surface | Operators can approve/defer KITTY proposals with 48h auto-approve | UI component + CLI command, `/api/projects` endpoints | Design in progress |

    Estimated effort: 2-3 weeks for functional prototype

     ---
     Long-term Vision Alignment

     This plan creates a foundation where:
     - ✅ Multiple AI models can collaborate (router supports model selection)
     - ✅ Sustainable materials are prioritized (KB tracks sustainability scores)
     - ✅ Autonomous projects run weekly (bounded autonomy with approval gates)
     - ✅ Energy efficient (Mac Studio runs 24/7, local-first inference)
     - ✅ Minimal suffering (research sustainable supply chains)
     - ✅ Power + Purpose for AI (KITTY chooses meaningful work)
     - ✅ Improves the world (explicit goal: benefit humans and AI)"""
