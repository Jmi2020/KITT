"""
Tests for IdleReaper background task.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brain.agents.parallel.types import ModelTier
from brain.agents.parallel.registry import ModelEndpoint
from brain.agents.parallel.slot_manager import SlotManager
from brain.agents.parallel.idle_reaper import IdleReaper


@pytest.fixture
def mock_endpoints():
    """Create mock endpoints with different idle settings."""
    return {
        ModelTier.Q4_TOOLS: ModelEndpoint(
            name="Q4",
            base_url="http://localhost:8083",
            max_slots=6,
            context_length=131072,
            model_id="kitty-q4",
            idle_shutdown_seconds=60,  # 1 minute for testing
            port=8083,
        ),
        ModelTier.CODER: ModelEndpoint(
            name="Coder",
            base_url="http://localhost:8087",
            max_slots=4,
            context_length=32768,
            model_id="kitty-coder",
            idle_shutdown_seconds=120,  # 2 minutes
            port=8087,
        ),
        ModelTier.GPTOSS_REASON: ModelEndpoint(
            name="Ollama",
            base_url="http://localhost:11434",
            max_slots=2,
            context_length=65536,
            model_id="gpt-oss-120b-judge",
            idle_shutdown_seconds=0,  # Never auto-shutdown
            port=11434,
        ),
    }


@pytest.fixture
def slot_manager(mock_endpoints):
    """Create a slot manager with mock endpoints."""
    return SlotManager(endpoints=mock_endpoints, auto_restart=False)


class TestIdleReaperInit:
    """Tests for IdleReaper initialization."""

    def test_init_default(self, slot_manager, mock_endpoints):
        """Test default initialization."""
        reaper = IdleReaper(slot_manager=slot_manager, endpoints=mock_endpoints)
        assert reaper._slot_manager is slot_manager
        assert reaper._shutdown_callback is None
        assert not reaper.is_running

    def test_init_with_callback(self, slot_manager, mock_endpoints):
        """Test initialization with shutdown callback."""
        callback = AsyncMock()
        reaper = IdleReaper(
            slot_manager=slot_manager,
            shutdown_callback=callback,
            endpoints=mock_endpoints,
        )
        assert reaper._shutdown_callback is callback


class TestCheckAndShutdownIdle:
    """Tests for idle checking and shutdown."""

    @pytest.mark.asyncio
    async def test_no_shutdown_when_active(self, slot_manager, mock_endpoints):
        """Should not shutdown when slots are active."""
        # Acquire a slot (makes endpoint active)
        tier, success = await slot_manager.acquire_slot(ModelTier.Q4_TOOLS)
        assert success

        callback = AsyncMock()
        reaper = IdleReaper(
            slot_manager=slot_manager,
            shutdown_callback=callback,
            endpoints=mock_endpoints,
        )

        results = await reaper.check_and_shutdown_idle()

        # No shutdown because Q4 has active slots
        assert results.get(ModelTier.Q4_TOOLS, False) is False
        callback.assert_not_called()

        # Cleanup
        await slot_manager.release_slot(tier)

    @pytest.mark.asyncio
    async def test_no_shutdown_when_never_used(self, slot_manager, mock_endpoints):
        """Should not shutdown if endpoint was never used."""
        callback = AsyncMock()
        reaper = IdleReaper(
            slot_manager=slot_manager,
            shutdown_callback=callback,
            endpoints=mock_endpoints,
        )

        # Never used, so no shutdown
        results = await reaper.check_and_shutdown_idle()
        assert results.get(ModelTier.Q4_TOOLS, False) is False
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_shutdown_when_idle_past_threshold(self, slot_manager, mock_endpoints):
        """Should shutdown when idle longer than threshold."""
        # Simulate past usage
        async with slot_manager._last_used_lock:
            # Set last used to 2 minutes ago (longer than Q4's 60s threshold)
            from datetime import timedelta
            slot_manager._last_used[ModelTier.Q4_TOOLS] = (
                datetime.now(timezone.utc) - timedelta(seconds=120)
            )

        callback = AsyncMock()
        reaper = IdleReaper(
            slot_manager=slot_manager,
            shutdown_callback=callback,
            endpoints=mock_endpoints,
        )

        results = await reaper.check_and_shutdown_idle()

        # Q4 should be shut down
        assert results.get(ModelTier.Q4_TOOLS) is True
        callback.assert_called_once_with(ModelTier.Q4_TOOLS)

    @pytest.mark.asyncio
    async def test_no_shutdown_for_zero_threshold(self, slot_manager, mock_endpoints):
        """Should never shutdown endpoints with 0 threshold (like Ollama)."""
        # Set last used to a long time ago
        async with slot_manager._last_used_lock:
            from datetime import timedelta
            slot_manager._last_used[ModelTier.GPTOSS_REASON] = (
                datetime.now(timezone.utc) - timedelta(hours=24)
            )

        callback = AsyncMock()
        reaper = IdleReaper(
            slot_manager=slot_manager,
            shutdown_callback=callback,
            endpoints=mock_endpoints,
        )

        results = await reaper.check_and_shutdown_idle()

        # GPTOSS should NOT be shut down (idle_shutdown_seconds=0)
        assert ModelTier.GPTOSS_REASON not in results
        callback.assert_not_called()


class TestBackgroundTask:
    """Tests for background task management."""

    @pytest.mark.asyncio
    async def test_start_and_stop(self, slot_manager, mock_endpoints):
        """Test starting and stopping the background task."""
        reaper = IdleReaper(
            slot_manager=slot_manager,
            endpoints=mock_endpoints,
        )

        assert not reaper.is_running

        # Start the reaper
        await reaper.start(interval=0.1)  # Short interval for testing
        assert reaper.is_running

        # Let it run briefly
        await asyncio.sleep(0.05)

        # Stop it
        await reaper.stop()
        assert not reaper.is_running

    @pytest.mark.asyncio
    async def test_double_start_warning(self, slot_manager, mock_endpoints):
        """Test that double start logs warning."""
        reaper = IdleReaper(
            slot_manager=slot_manager,
            endpoints=mock_endpoints,
        )

        await reaper.start(interval=0.1)
        # Second start should be a no-op with warning
        await reaper.start(interval=0.1)

        assert reaper.is_running

        # Cleanup
        await reaper.stop()


class TestGetStatus:
    """Tests for status reporting."""

    def test_get_status_not_running(self, slot_manager, mock_endpoints):
        """Test status when not running."""
        reaper = IdleReaper(
            slot_manager=slot_manager,
            endpoints=mock_endpoints,
        )

        status = reaper.get_status()
        assert status["running"] is False
        assert status["endpoints_monitored"] == 2  # Q4 and CODER (not GPTOSS)

    @pytest.mark.asyncio
    async def test_get_status_running(self, slot_manager, mock_endpoints):
        """Test status when running."""
        reaper = IdleReaper(
            slot_manager=slot_manager,
            endpoints=mock_endpoints,
        )

        await reaper.start(interval=30.0)
        status = reaper.get_status()

        assert status["running"] is True
        assert status["check_interval"] == 30.0

        await reaper.stop()
