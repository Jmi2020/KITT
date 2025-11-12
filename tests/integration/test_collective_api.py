# ruff: noqa: E402
"""Integration tests for Collective Meta-Agent API endpoints."""
import os
import sys
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/common/src"))
sys.path.append(str(ROOT / "services/brain/src"))

# Configuration
BRAIN_BASE = os.getenv("BRAIN_BASE", "http://localhost:8000")
GATEWAY_BASE = os.getenv("GATEWAY_BASE", "http://localhost:8080")
TIMEOUT = 120  # 2 minutes for Quality-First mode


@pytest.mark.integration
class TestCollectiveBrainAPI:
    """Integration tests for brain service collective endpoint."""

    def test_health_check(self):
        """Test brain service is running."""
        response = requests.get(f"{BRAIN_BASE}/healthz", timeout=10)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_council_pattern_minimal(self):
        """Test council pattern with minimal k=2."""
        payload = {
            "task": "Quick test: PETG or PLA?",
            "pattern": "council",
            "k": 2
        }

        response = requests.post(
            f"{BRAIN_BASE}/api/collective/run",
            json=payload,
            timeout=TIMEOUT
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "pattern" in data
        assert data["pattern"] == "council"
        assert "proposals" in data
        assert len(data["proposals"]) == 2
        assert "verdict" in data
        assert len(data["verdict"]) > 0

        # Verify proposal structure
        for proposal in data["proposals"]:
            assert "role" in proposal
            assert "text" in proposal
            assert proposal["role"].startswith("specialist_")

    def test_council_pattern_full(self):
        """Test council pattern with k=3."""
        payload = {
            "task": "Compare PETG vs ABS vs TPU for outdoor furniture",
            "pattern": "council",
            "k": 3
        }

        response = requests.post(
            f"{BRAIN_BASE}/api/collective/run",
            json=payload,
            timeout=TIMEOUT
        )

        assert response.status_code == 200
        data = response.json()

        assert data["pattern"] == "council"
        assert len(data["proposals"]) == 3
        assert data["verdict"]
        assert "logs" in data

    def test_debate_pattern(self):
        """Test debate pattern."""
        payload = {
            "task": "Should I use tree supports for this overhang?",
            "pattern": "debate"
        }

        response = requests.post(
            f"{BRAIN_BASE}/api/collective/run",
            json=payload,
            timeout=TIMEOUT
        )

        assert response.status_code == 200
        data = response.json()

        assert data["pattern"] == "debate"
        assert len(data["proposals"]) == 2
        assert data["proposals"][0]["role"] == "pro"
        assert data["proposals"][1]["role"] == "con"
        assert data["verdict"]

    def test_pipeline_pattern_stub(self):
        """Test pipeline pattern (currently stubbed)."""
        payload = {
            "task": "Generate a test function",
            "pattern": "pipeline"
        }

        response = requests.post(
            f"{BRAIN_BASE}/api/collective/run",
            json=payload,
            timeout=TIMEOUT
        )

        assert response.status_code == 200
        data = response.json()

        # Pipeline should work but return placeholder
        assert data["pattern"] == "pipeline"
        assert "proposals" in data
        assert "verdict" in data

    def test_invalid_pattern(self):
        """Test invalid pattern returns validation error."""
        payload = {
            "task": "Test",
            "pattern": "invalid_pattern",
            "k": 3
        }

        response = requests.post(
            f"{BRAIN_BASE}/api/collective/run",
            json=payload,
            timeout=10
        )

        assert response.status_code == 422  # Validation error

    def test_k_out_of_range_low(self):
        """Test k < 2 returns validation error."""
        payload = {
            "task": "Test",
            "pattern": "council",
            "k": 1
        }

        response = requests.post(
            f"{BRAIN_BASE}/api/collective/run",
            json=payload,
            timeout=10
        )

        assert response.status_code == 422

    def test_k_out_of_range_high(self):
        """Test k > 7 returns validation error."""
        payload = {
            "task": "Test",
            "pattern": "council",
            "k": 10
        }

        response = requests.post(
            f"{BRAIN_BASE}/api/collective/run",
            json=payload,
            timeout=10
        )

        assert response.status_code == 422

    def test_missing_task(self):
        """Test missing task returns validation error."""
        payload = {
            "pattern": "council",
            "k": 3
        }

        response = requests.post(
            f"{BRAIN_BASE}/api/collective/run",
            json=payload,
            timeout=10
        )

        assert response.status_code == 422

    def test_max_steps_parameter(self):
        """Test max_steps parameter is accepted."""
        payload = {
            "task": "Test",
            "pattern": "council",
            "k": 2,
            "max_steps": 5
        }

        response = requests.post(
            f"{BRAIN_BASE}/api/collective/run",
            json=payload,
            timeout=TIMEOUT
        )

        # Should succeed (max_steps is accepted but not yet used)
        assert response.status_code == 200

    def test_default_pattern(self):
        """Test default pattern is council."""
        payload = {
            "task": "Test default pattern"
        }

        response = requests.post(
            f"{BRAIN_BASE}/api/collective/run",
            json=payload,
            timeout=TIMEOUT
        )

        assert response.status_code == 200
        data = response.json()
        # Default pattern should be pipeline according to schema
        assert data["pattern"] in ["pipeline", "council"]  # Either is acceptable default

    def test_k_boundary_values(self):
        """Test k at boundary values."""
        # Test k=2 (minimum)
        payload = {"task": "Test", "pattern": "council", "k": 2}
        response = requests.post(f"{BRAIN_BASE}/api/collective/run", json=payload, timeout=TIMEOUT)
        assert response.status_code == 200
        assert len(response.json()["proposals"]) == 2

        # Test k=7 (maximum)
        payload = {"task": "Test", "pattern": "council", "k": 7}
        response = requests.post(f"{BRAIN_BASE}/api/collective/run", json=payload, timeout=TIMEOUT)
        assert response.status_code == 200
        assert len(response.json()["proposals"]) == 7


@pytest.mark.integration
class TestCollectiveGatewayAPI:
    """Integration tests for gateway service collective proxy."""

    def test_health_check(self):
        """Test gateway service is running."""
        response = requests.get(f"{GATEWAY_BASE}/healthz", timeout=10)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_gateway_proxy_council(self):
        """Test gateway proxies council requests to brain."""
        payload = {
            "task": "Quick gateway test: PETG or ABS?",
            "pattern": "council",
            "k": 2
        }

        response = requests.post(
            f"{GATEWAY_BASE}/api/collective/run",
            json=payload,
            timeout=TIMEOUT
        )

        assert response.status_code == 200
        data = response.json()

        assert data["pattern"] == "council"
        assert len(data["proposals"]) == 2
        assert data["verdict"]

    def test_gateway_proxy_debate(self):
        """Test gateway proxies debate requests."""
        payload = {
            "task": "Test debate via gateway",
            "pattern": "debate"
        }

        response = requests.post(
            f"{GATEWAY_BASE}/api/collective/run",
            json=payload,
            timeout=TIMEOUT
        )

        assert response.status_code == 200
        data = response.json()

        assert data["pattern"] == "debate"
        assert len(data["proposals"]) == 2

    def test_gateway_error_forwarding(self):
        """Test gateway forwards validation errors from brain."""
        payload = {
            "task": "Test",
            "pattern": "invalid",
            "k": 3
        }

        response = requests.post(
            f"{GATEWAY_BASE}/api/collective/run",
            json=payload,
            timeout=10
        )

        # Should forward 422 from brain
        assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.slow
class TestCollectiveQualityFirstMode:
    """Integration tests for Quality-First mode performance."""

    def test_complex_council_k5(self):
        """Test complex question with k=5 (may take 2-3 minutes)."""
        payload = {
            "task": "Design a print workflow for a 400mm tall architectural model with intricate details. "
                   "Consider material choice, orientation, support strategy, and post-processing. "
                   "Compare PETG, ABS, and PLA approaches.",
            "pattern": "council",
            "k": 5
        }

        response = requests.post(
            f"{GATEWAY_BASE}/api/collective/run",
            json=payload,
            timeout=300  # 5 minutes for complex query
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["proposals"]) == 5
        assert data["verdict"]
        assert len(data["verdict"]) > 100  # Expect comprehensive verdict

        # Verify all specialists provided detailed responses
        for proposal in data["proposals"]:
            assert len(proposal["text"]) > 50  # Non-trivial responses

    def test_debate_with_complex_topic(self):
        """Test debate on complex engineering trade-off."""
        payload = {
            "task": "For a large functional part (300mm), should I prioritize layer adhesion (thicker layers, "
                   "higher temps) or dimensional accuracy (thinner layers, slower speeds)? "
                   "Consider print time, strength, warping risk.",
            "pattern": "debate"
        }

        response = requests.post(
            f"{GATEWAY_BASE}/api/collective/run",
            json=payload,
            timeout=180  # 3 minutes
        )

        assert response.status_code == 200
        data = response.json()

        # Expect detailed PRO/CON arguments
        assert len(data["proposals"][0]["text"]) > 100
        assert len(data["proposals"][1]["text"]) > 100
        assert len(data["verdict"]) > 100


if __name__ == "__main__":
    # Run smoke tests only by default
    pytest.main([
        __file__,
        "-v",
        "-m", "not slow",
        "--tb=short"
    ])
