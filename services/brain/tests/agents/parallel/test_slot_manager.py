"""
Tests for SlotManager: slot acquisition, release, fallback, and health checks.
"""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from brain.agents.parallel.types import ModelTier
from brain.agents.parallel.slot_manager import (
    SlotManager,
    get_slot_manager,
    reset_slot_manager,
)


class TestSlotManagerInit:
    """Tests for SlotManager initialization."""

    def test_init_with_defaults(self, mock_endpoints):
        """Should initialize with provided endpoints."""
        manager = SlotManager(endpoints=mock_endpoints)

        assert manager._endpoints == mock_endpoints
        assert manager._health_timeout == 5.0

    def test_init_custom_timeout(self, mock_endpoints):
        """Should accept custom health check timeout."""
        manager = SlotManager(endpoints=mock_endpoints, health_check_timeout=10.0)

        assert manager._health_timeout == 10.0


class TestSlotAcquisition:
    """Tests for slot acquisition."""

    @pytest.mark.asyncio
    async def test_acquire_slot_success(self, mock_endpoints):
        """Should acquire slot on available endpoint."""
        manager = SlotManager(endpoints=mock_endpoints)

        tier, acquired = await manager.acquire_slot(ModelTier.Q4_TOOLS)

        assert acquired is True
        assert tier == ModelTier.Q4_TOOLS
        assert mock_endpoints[ModelTier.Q4_TOOLS].active_slots == 1

    @pytest.mark.asyncio
    async def test_acquire_slot_unknown_tier(self, mock_endpoints):
        """Should fail for unknown tier."""
        manager = SlotManager(endpoints=mock_endpoints)

        tier, acquired = await manager.acquire_slot(ModelTier.MCP_EXTERNAL)

        assert acquired is False
        assert tier == ModelTier.MCP_EXTERNAL

    @pytest.mark.asyncio
    async def test_acquire_slot_with_fallback(self, mock_endpoints):
        """Should use fallback when primary is exhausted."""
        manager = SlotManager(endpoints=mock_endpoints)

        # Exhaust Q4 slots
        q4 = mock_endpoints[ModelTier.Q4_TOOLS]
        for _ in range(q4.max_slots):
            await q4.acquire_slot()

        # Try to acquire with fallback
        tier, acquired = await manager.acquire_slot(
            ModelTier.Q4_TOOLS,
            allow_fallback=True,
            fallback_tier=ModelTier.CODER,
            max_retries=1,  # Quick failure
            timeout=0.5,
        )

        assert acquired is True
        assert tier == ModelTier.CODER

    @pytest.mark.asyncio
    async def test_acquire_slot_no_fallback(self, mock_endpoints):
        """Should fail without fallback when primary exhausted."""
        manager = SlotManager(endpoints=mock_endpoints)

        # Exhaust Q4 slots
        q4 = mock_endpoints[ModelTier.Q4_TOOLS]
        for _ in range(q4.max_slots):
            await q4.acquire_slot()

        # Try without fallback
        tier, acquired = await manager.acquire_slot(
            ModelTier.Q4_TOOLS,
            allow_fallback=False,
            max_retries=1,
            timeout=0.5,
        )

        assert acquired is False
        assert tier == ModelTier.Q4_TOOLS

    @pytest.mark.asyncio
    async def test_acquire_slot_timeout(self, mock_endpoints):
        """Should respect timeout."""
        manager = SlotManager(endpoints=mock_endpoints)

        # Exhaust all slots
        q4 = mock_endpoints[ModelTier.Q4_TOOLS]
        for _ in range(q4.max_slots):
            await q4.acquire_slot()

        # Short timeout should fail quickly
        start = asyncio.get_event_loop().time()
        tier, acquired = await manager.acquire_slot(
            ModelTier.Q4_TOOLS,
            timeout=0.1,
            allow_fallback=False,
            max_retries=10,
        )
        elapsed = asyncio.get_event_loop().time() - start

        assert acquired is False
        assert elapsed < 1.0  # Should timeout quickly


class TestSlotRelease:
    """Tests for slot release."""

    @pytest.mark.asyncio
    async def test_release_slot_success(self, mock_endpoints):
        """Should release slot correctly."""
        manager = SlotManager(endpoints=mock_endpoints)

        await manager.acquire_slot(ModelTier.Q4_TOOLS)
        assert mock_endpoints[ModelTier.Q4_TOOLS].active_slots == 1

        await manager.release_slot(ModelTier.Q4_TOOLS)

        assert mock_endpoints[ModelTier.Q4_TOOLS].active_slots == 0

    @pytest.mark.asyncio
    async def test_release_slot_unknown_tier(self, mock_endpoints):
        """Should handle unknown tier gracefully."""
        manager = SlotManager(endpoints=mock_endpoints)

        # Should not raise
        await manager.release_slot(ModelTier.MCP_EXTERNAL)


class TestHealthCheck:
    """Tests for health checking."""

    @pytest.mark.asyncio
    async def test_check_health_healthy(self, mock_endpoints, mock_httpx_client):
        """Should return True for healthy endpoint."""
        manager = SlotManager(endpoints=mock_endpoints)
        manager._http_client = mock_httpx_client

        result = await manager.check_health(ModelTier.Q4_TOOLS)

        assert result is True

    @pytest.mark.asyncio
    async def test_check_health_unhealthy(self, mock_endpoints, mock_httpx_error_client):
        """Should return False for unhealthy endpoint."""
        manager = SlotManager(endpoints=mock_endpoints)
        manager._http_client = mock_httpx_error_client

        result = await manager.check_health(ModelTier.Q4_TOOLS)

        assert result is False

    @pytest.mark.asyncio
    async def test_check_health_unknown_tier(self, mock_endpoints):
        """Should return False for unknown tier."""
        manager = SlotManager(endpoints=mock_endpoints)

        result = await manager.check_health(ModelTier.MCP_EXTERNAL)

        assert result is False

    @pytest.mark.asyncio
    async def test_check_all_health(self, mock_endpoints, mock_httpx_client):
        """Should check all endpoints concurrently."""
        manager = SlotManager(endpoints=mock_endpoints)
        manager._http_client = mock_httpx_client

        results = await manager.check_all_health()

        assert len(results) == len(mock_endpoints)
        for tier_name, healthy in results.items():
            assert isinstance(healthy, bool)


class TestSlotStatus:
    """Tests for status reporting."""

    def test_get_status(self, mock_endpoints):
        """Should return status for all endpoints."""
        manager = SlotManager(endpoints=mock_endpoints)

        status = manager.get_status()

        assert len(status) == len(mock_endpoints)
        for tier_name, info in status.items():
            assert "active" in info
            assert "max" in info
            assert "available" in info

    def test_get_available_slots(self, mock_endpoints):
        """Should return available slots for tier."""
        manager = SlotManager(endpoints=mock_endpoints)

        available = manager.get_available_slots(ModelTier.Q4_TOOLS)

        assert available == mock_endpoints[ModelTier.Q4_TOOLS].max_slots

    def test_get_available_slots_unknown_tier(self, mock_endpoints):
        """Should return 0 for unknown tier."""
        manager = SlotManager(endpoints=mock_endpoints)

        available = manager.get_available_slots(ModelTier.MCP_EXTERNAL)

        assert available == 0

    def test_total_capacity(self, mock_endpoints):
        """Should sum all max slots."""
        manager = SlotManager(endpoints=mock_endpoints)

        capacity = manager.total_capacity()

        expected = sum(e.max_slots for e in mock_endpoints.values())
        assert capacity == expected

    @pytest.mark.asyncio
    async def test_total_active(self, mock_endpoints):
        """Should sum all active slots."""
        manager = SlotManager(endpoints=mock_endpoints)

        # Acquire some slots
        await manager.acquire_slot(ModelTier.Q4_TOOLS)
        await manager.acquire_slot(ModelTier.CODER)

        active = manager.total_active()

        assert active == 2

    def test_total_available(self, mock_endpoints):
        """Should calculate total available."""
        manager = SlotManager(endpoints=mock_endpoints)

        available = manager.total_available()

        expected = sum(e.available_slots for e in mock_endpoints.values())
        assert available == expected


class TestConcurrentAcquisition:
    """Tests for concurrent slot acquisition."""

    @pytest.mark.asyncio
    async def test_10_concurrent_acquires(self, mock_endpoints):
        """Should handle 10 concurrent acquisition attempts safely."""
        manager = SlotManager(endpoints=mock_endpoints)
        q4 = mock_endpoints[ModelTier.Q4_TOOLS]

        # Launch 10 concurrent acquisitions (Q4 has 6 slots)
        tasks = [
            manager.acquire_slot(ModelTier.Q4_TOOLS, timeout=1.0, max_retries=1)
            for _ in range(10)
        ]
        results = await asyncio.gather(*tasks)

        # Count successes
        successes = sum(1 for tier, acquired in results if acquired)

        # Should only succeed up to max_slots
        assert successes == q4.max_slots
        assert q4.active_slots == q4.max_slots

    @pytest.mark.asyncio
    async def test_acquire_release_cycle(self, mock_endpoints):
        """Should handle rapid acquire/release cycles."""
        manager = SlotManager(endpoints=mock_endpoints)

        async def acquire_release():
            tier, acquired = await manager.acquire_slot(ModelTier.Q4_TOOLS, timeout=5.0)
            if acquired:
                await asyncio.sleep(0.01)
                await manager.release_slot(tier)
            return acquired

        # Run 20 cycles concurrently
        tasks = [acquire_release() for _ in range(20)]
        results = await asyncio.gather(*tasks)

        # Most should succeed (some may fail due to timing)
        successes = sum(results)
        assert successes >= 10

        # All slots should be released
        assert mock_endpoints[ModelTier.Q4_TOOLS].active_slots == 0


class TestSingleton:
    """Tests for singleton pattern."""

    @pytest.mark.asyncio
    async def test_get_slot_manager_singleton(self):
        """get_slot_manager should return same instance."""
        await reset_slot_manager()

        m1 = get_slot_manager()
        m2 = get_slot_manager()

        assert m1 is m2

    @pytest.mark.asyncio
    async def test_reset_slot_manager(self):
        """reset_slot_manager should create new instance."""
        m1 = get_slot_manager()

        await reset_slot_manager()

        m2 = get_slot_manager()
        assert m1 is not m2


class TestCleanup:
    """Tests for resource cleanup."""

    @pytest.mark.asyncio
    async def test_close_http_client(self, mock_endpoints, mock_httpx_client):
        """close() should close HTTP client."""
        manager = SlotManager(endpoints=mock_endpoints)
        manager._http_client = mock_httpx_client

        await manager.close()

        mock_httpx_client.aclose.assert_called_once()
        assert manager._http_client is None
