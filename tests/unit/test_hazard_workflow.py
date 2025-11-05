import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/common/src"))
sys.path.append(str(ROOT / "services/safety/src"))

pytest.importorskip("pydantic_settings")
pytest.importorskip("httpx")

from common.config import settings  # type: ignore[import]
from safety.signing import sign_payload  # type: ignore[import]
from safety.workflows.hazard import HazardWorkflow  # type: ignore[import]


@pytest.mark.asyncio
async def test_hazard_allows_when_signature_valid(monkeypatch):
    monkeypatch.setenv("HAZARD_SIGNING_KEY", "secret")
    settings.hazard_signing_key = "secret"
    payload = "unlock:door1:zone1:user1"
    signature = sign_payload(payload, key="secret")

    workflow = HazardWorkflow(unifi_client=None)
    allowed, response = await workflow.process_device_intent(
        intent="unlock",
        device_id="door1",
        zone_id=None,
        user_id="user1",
        signature=signature,
    )
    assert allowed is True
    assert response["status"] == "approved"


@pytest.mark.asyncio
async def test_hazard_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv("HAZARD_SIGNING_KEY", "secret")
    settings.hazard_signing_key = "secret"
    workflow = HazardWorkflow(unifi_client=None)
    allowed, response = await workflow.process_device_intent(
        intent="unlock",
        device_id="door1",
        zone_id=None,
        user_id="user1",
        signature="bad",
    )
    assert not allowed
    assert response["status"] == "error"
