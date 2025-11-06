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

## Next Steps

- Add end-to-end CAD workflow tests (UI → Gateway → Brain → CAD)
- Add Home Assistant integration tests
- Add Memory (Qdrant/Mem0) integration tests
- Add performance/load testing
- Add chaos engineering tests (service failures, network issues)
