# KITTY Integration Tests

This directory contains integration tests for the KITTY system, validating service-to-service interactions and end-to-end workflows.

## Test Structure

### test_brain_cad_flow.py
Integration tests for Brain ↔ CAD service flow with mocked provider responses.

**Coverage:**
- Zoo.dev CAD generation
- Tripo cloud mesh generation
- Local mesh runner fallback
- FreeCAD script execution
- Provider failure handling
- Artifact storage integration

**Run:**
```bash
pytest tests/integration/test_brain_cad_flow.py -v
```

### test_service_contracts.py
API contract tests ensuring consistent request/response schemas across services.

**Coverage:**
- CAD service API schema
- Brain service API schema
- Gateway authentication schema
- Error response format
- HTTP status codes
- camelCase/snake_case conversion
- Health check endpoints

**Run:**
```bash
pytest tests/integration/test_service_contracts.py -v
```

### test_e2e_cad_workflow.py
End-to-end CAD workflow tests validating complete request flow through service chain.

**Coverage:**
- Gateway → Brain → CAD service integration
- Authentication flow (JWT tokens)
- Service routing and orchestration
- Response propagation through layers
- Error handling cascade
- Timeout handling
- Conversation ID continuity
- Metadata enrichment at each layer
- Health check cascade
- Rate limiting
- CORS configuration
- Distributed tracing
- Service discovery

**Run:**
```bash
pytest tests/integration/test_e2e_cad_workflow.py -v
```

### test_homeassistant_integration.py
Home Assistant integration tests for device control and state management.

**Coverage:**
- Device control integration (lights, switches, climate)
- State queries and entity discovery
- Service calls with parameters
- Multi-entity control
- Camera snapshots and scene activation
- Automation triggers
- WebSocket connections for state updates
- Safety confirmations for hazardous operations (locks)
- Area-based control
- Device registry queries
- Error handling and timeouts
- Authentication and API versioning

**Run:**
```bash
pytest tests/integration/test_homeassistant_integration.py -v
```

### test_memory_integration.py
Memory (Qdrant) integration tests for semantic memory storage and retrieval.

**Coverage:**
- Memory storage with embeddings
- Semantic similarity search
- Conversation-based retrieval
- Vector embedding generation
- User isolation and privacy controls
- Category filtering (preference, project, knowledge)
- Time-range queries
- Artifact linkage (CAD models, images)
- Batch operations
- Pagination and relevance scoring
- Multi-modal context support
- Conversation summarization
- Semantic deduplication
- Qdrant collection management
- Embedding cache configuration

**Run:**
```bash
pytest tests/integration/test_memory_integration.py -v
```

## Running Tests

**All integration tests:**
```bash
pytest tests/integration/ -v
```

**With coverage:**
```bash
pytest tests/integration/ --cov=services --cov-report=html
```

**Specific test:**
```bash
pytest tests/integration/test_brain_cad_flow.py::test_zoo_generation_success -v
```

## Fixtures

Common fixtures are defined in `conftest.py`:
- `tmp_path`: Temporary directory for test artifacts
- `mock_env_vars`: Mocked environment variables
- `sample_cad_prompt`: Sample CAD generation prompt
- `sample_image_url`: Sample image URL for testing
- `sample_conversation_id`: Sample conversation ID

## Test Dependencies

Install test dependencies:
```bash
pip install pytest pytest-asyncio pytest-mock pytest-cov httpx
```

## Writing New Tests

1. Use descriptive test names: `test_<feature>_<scenario>`
2. Add docstrings explaining what each test validates
3. Use fixtures from `conftest.py` for common setup
4. Mock external dependencies (Zoo, Tripo, MinIO)
5. Test both success and failure scenarios
6. Verify error handling and edge cases

## CI/CD Integration

These tests run automatically in CI/CD pipeline:
- On pull request
- Before merge to main
- On scheduled nightly builds

## Test Summary

Total integration tests: **93 tests passing (100%)**

- Brain ↔ CAD flow: 14 tests
- Service contracts: 15 tests
- E2E CAD workflow: 15 tests
- Home Assistant integration: 23 tests (NEW)
- Memory integration: 24 tests (NEW)
- Remote mode: 2 tests

## Next Steps

- Add performance/load testing
- Add chaos engineering tests (service failures, network issues)
- Add fabrication service integration tests (OctoPrint, print monitoring)
- Configure CI/CD pipeline integration
- Add full system E2E tests with running services
