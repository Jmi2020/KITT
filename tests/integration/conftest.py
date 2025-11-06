"""Pytest configuration and fixtures for integration tests."""

import pytest
from pathlib import Path
import tempfile


@pytest.fixture
def tmp_path():
    """Provide a temporary directory for test artifacts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing."""
    test_env = {
        "CAD_SERVICE_URL": "http://localhost:8200",
        "BRAIN_SERVICE_URL": "http://localhost:8000",
        "GATEWAY_URL": "http://localhost:8080",
        "ZOO_API_BASE": "https://api.zoo.dev",
        "ZOO_API_KEY": "test-key",
        "TRIPO_API_BASE": "https://api.tripo.ai",
        "TRIPO_API_KEY": "test-key",
        "MINIO_ENDPOINT": "http://localhost:9000",
        "MINIO_BUCKET": "test-artifacts",
        "MINIO_ACCESS_KEY": "minioadmin",
        "MINIO_SECRET_KEY": "minioadmin",
    }

    for key, value in test_env.items():
        monkeypatch.setenv(key, value)

    return test_env


@pytest.fixture
def sample_cad_prompt():
    """Provide a sample CAD generation prompt."""
    return "Design a mounting bracket with 4x M3 holes, 60mm x 40mm x 3mm"


@pytest.fixture
def sample_image_url():
    """Provide a sample image URL for testing."""
    return "https://example.com/test-image.png"


@pytest.fixture
def sample_conversation_id():
    """Provide a sample conversation ID."""
    return "test-conv-12345"
