# KITT Documentation

Welcome to the KITT documentation. This folder contains comprehensive documentation for developers and users.

## Documentation Structure

```
docs/
├── README.md                           # This file
├── architecture/                       # System architecture & design
│   ├── overview.md                    # High-level system overview
│   ├── research-system.md             # Research pipeline architecture
│   ├── hierarchical-research.md       # Hierarchical research deep-dive
│   └── database-schema.md             # Database design
├── user-guides/                       # End-user documentation
│   ├── getting-started.md             # Quick start guide
│   ├── research-modes.md              # Flat vs Hierarchical research
│   ├── configuration.md               # Configuration options
│   └── results-viewing.md             # Viewing and following up on results
├── api/                               # API documentation
│   ├── research-api.md                # Research endpoints
│   ├── gateway-api.md                 # Gateway routing
│   └── models.md                      # Request/response models
└── development/                       # Developer documentation
    ├── setup.md                       # Development environment setup
    ├── contributing.md                # Contribution guidelines
    ├── testing.md                     # Testing procedures
    └── deployment.md                  # Deployment guide
```

## Quick Links

### For Users
- [Getting Started](user-guides/getting-started.md) - Start here
- [Research Modes](user-guides/research-modes.md) - Understanding flat vs hierarchical research
- [Configuration Guide](user-guides/configuration.md) - Customize your research sessions

### For Developers
- [System Architecture](architecture/overview.md) - How KITT works
- [Hierarchical Research](architecture/hierarchical-research.md) - Multi-stage research system
- [Development Setup](development/setup.md) - Set up your dev environment
- [API Reference](api/research-api.md) - REST API documentation

### Planning Documents
- [Hierarchical Research Architecture](/plans/hierarchical-research-architecture.md) - Detailed implementation plan

## Key Features

### Autonomous Research System
- **Intelligent query decomposition** - Breaks complex questions into focused sub-questions
- **Multi-stage synthesis** - Dedicated analysis per aspect, integrated final answer
- **Budget-aware execution** - Cost and iteration limits with priority-based allocation
- **Quality metrics** - RAGAS evaluation, confidence scoring, saturation detection
- **Source attribution** - Full source tracking with snippets and relevance

### Research Modes

#### Flat Research (Default)
- Single-stage research and synthesis
- Suitable for straightforward queries
- Lower iteration requirements
- Faster execution

#### Hierarchical Research (Opt-in)
- LLM-based query decomposition
- Priority-weighted sub-question research
- Per-sub-question synthesis
- Meta-synthesis integrating all findings
- Best for complex, multi-faceted questions

## System Components

- **Brain Service** - Research orchestration and LangGraph pipeline
- **Gateway Service** - API routing and load balancing
- **UI Service** - React-based web interface
- **Database** - PostgreSQL with research sessions, findings, and sources
- **Model Coordinator** - Tiered model selection (local/external)
- **Tool Executor** - MCP integration for web search and research tools

## Configuration

Key configuration options for research sessions:

```python
{
    "enable_hierarchical": False,        # Enable hierarchical mode
    "max_iterations": 15,                # Total iteration budget
    "max_total_cost_usd": 2.0,          # Budget limit
    "max_external_calls": 10,            # External API call limit
    "min_quality_score": 0.7,           # Quality threshold
    "min_ragas_score": 0.75,            # RAGAS threshold

    # Hierarchical-specific
    "min_sub_questions": 2,             # Min decomposition
    "max_sub_questions": 5,             # Max decomposition
    "sub_question_min_iterations": 2,   # Min per sub-question
    "sub_question_max_iterations": 5,   # Max per sub-question
}
```

## Recent Updates

### 2025-11-17: Hierarchical Research System
- ✅ Complete hierarchical research implementation (Phases 1-8)
- ✅ LLM-based query decomposition
- ✅ Priority-weighted sub-question research
- ✅ Multi-stage synthesis (sub-question + meta)
- ✅ Hierarchical-aware stopping criteria
- ✅ Graph routing with new nodes

### Previous Updates
- 2025-11-16: Results viewing UI with synthesis generation
- 2025-11-15: Source analysis and metadata tracking
- 2025-11-14: Research pipeline Phase 6 completion

## Contributing

See [development/contributing.md](development/contributing.md) for contribution guidelines.

## Support

For issues or questions:
- GitHub Issues: https://github.com/anthropics/claude-code/issues
- Internal documentation: Check `/plans` directory for detailed planning docs
