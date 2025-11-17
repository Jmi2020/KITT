# Documentation TODO

This file tracks documentation updates needed as features are finalized.

## 🚨 Important

**These docs must be updated as features are finalized and implementation changes.**

## Pending Documentation Updates

### High Priority

- [ ] **Results Viewing UI** - Document the Results page functionality
  - File: `docs/user-guides/results-viewing.md`
  - Status: UI complete, docs not yet created
  - Features to document:
    - Session grid view
    - Results modal with synthesis
    - Generate synthesis button
    - Finding cards with sources
    - Follow-up research capability

- [ ] **Research Configuration** - Complete configuration guide
  - File: `docs/user-guides/configuration.md`
  - Status: Partial (hierarchical config documented, need full reference)
  - Need to document:
    - All ResearchConfig options
    - Strategy selection (breadth/depth/hybrid/task-decomposition)
    - Quality thresholds
    - Budget settings
    - Model preferences

- [ ] **API Documentation** - Create REST API reference
  - File: `docs/api/research-api.md`
  - Status: Not created
  - Endpoints to document:
    - POST /api/research/sessions
    - GET /api/research/sessions/{id}
    - GET /api/research/sessions/{id}/results
    - GET /api/research/sessions/{id}/findings
    - POST /api/research/sessions/{id}/followup
    - POST /api/research/sessions/{id}/generate-synthesis

### Medium Priority

- [ ] **System Architecture Overview** - High-level system diagram
  - File: `docs/architecture/overview.md`
  - Status: Not created
  - Should include:
    - Service architecture (Brain, Gateway, UI, DB)
    - Data flow diagrams
    - Component interactions
    - Technology stack

- [ ] **Database Schema** - Document research DB schema
  - File: `docs/architecture/database-schema.md`
  - Status: Not created
  - Tables to document:
    - research_sessions
    - research_findings
    - Migration history

- [ ] **Development Setup** - Dev environment guide
  - File: `docs/development/setup.md`
  - Status: Not created
  - Should cover:
    - Prerequisites
    - Docker setup
    - Service configuration
    - Local model setup
    - Database initialization

### Low Priority

- [ ] **Testing Guide** - Testing procedures and examples
  - File: `docs/development/testing.md`
  - Status: Not created

- [ ] **Deployment Guide** - Production deployment
  - File: `docs/development/deployment.md`
  - Status: Not created

- [ ] **Contributing Guidelines** - Contribution workflow
  - File: `docs/development/contributing.md`
  - Status: Not created

## Recently Completed

- [x] **Hierarchical Research User Guide** (2025-11-17)
  - File: `docs/user-guides/hierarchical-research.md`
  - Status: Complete ✅

- [x] **Hierarchical Research Architecture** (2025-11-17)
  - File: `docs/architecture/hierarchical-research.md`
  - Status: Complete ✅

- [x] **Implementation Planning Document** (2025-11-17)
  - File: `plans/hierarchical-research-architecture.md`
  - Status: Complete ✅

## Documentation Sync Checklist

When implementing new features, ensure documentation is updated:

### Before Feature Development
- [ ] Review existing documentation for related features
- [ ] Note documentation sections that will need updates
- [ ] Create TODO items in this file

### During Development
- [ ] Update technical documentation as architecture changes
- [ ] Document new configuration options
- [ ] Add code examples for new APIs

### After Feature Completion
- [ ] Update user guides with new features
- [ ] Add API documentation for new endpoints
- [ ] Update architecture docs if structure changed
- [ ] Add examples and screenshots
- [ ] Review and update README.md
- [ ] Remove completed items from this TODO

### Before Release
- [ ] Review all documentation for accuracy
- [ ] Test all examples and code snippets
- [ ] Ensure configuration examples are current
- [ ] Update version/date information
- [ ] Check all internal links work

## Documentation Standards

### User Guides Should Include:
- Clear description of feature/concept
- When to use it
- Step-by-step examples
- Configuration options
- Best practices
- Troubleshooting
- Related documentation links

### Architecture Docs Should Include:
- Technical overview
- Component diagrams
- Implementation details
- Code examples
- Performance characteristics
- Testing strategy
- Future enhancements

### API Docs Should Include:
- Endpoint description
- Request/response schemas
- Example requests (curl, JavaScript, Python)
- Error responses
- Rate limits/constraints
- Authentication requirements

## Maintenance Schedule

- **Weekly**: Review TODO list, prioritize items
- **Per Feature**: Update docs immediately after feature completion
- **Monthly**: Comprehensive doc review for accuracy
- **Pre-Release**: Full documentation audit

## Contact

For documentation questions or contributions:
- Review existing docs in `/docs`
- Check planning docs in `/plans`
- Follow structure defined in `/docs/README.md`
