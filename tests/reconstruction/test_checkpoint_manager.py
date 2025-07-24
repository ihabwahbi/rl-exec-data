"""Unit tests for CheckpointManager."""

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

import pytest
from loguru import logger

from rlx_datapipe.reconstruction.checkpoint_manager import CheckpointManager


class MockStateProvider:
    """Mock state provider for testing."""
    
    def __init__(self):
        self.state_counter = 0
        self.events_processed = 0
    
    def get_checkpoint_state(self) -> Dict[str, Any]:
        """Get mock checkpoint state."""
        self.state_counter += 1
        return {
            "book_state": {
                "bids": [[100.0, 1.0], [99.0, 2.0]],
                "asks": [[101.0, 1.0], [102.0, 2.0]],
            },
            "last_update_id": self.state_counter * 1000,
            "gap_stats": {"total_gaps": 5, "max_gap_size": 10},
            "updates_processed": self.events_processed,
            "snapshot_count": 1,
            "drift_metrics": {"total_drift": 0.1},
            "processing_rate": 1000.0,
            "current_file": f"test_file_{self.state_counter}.jsonl",
            "file_offset": self.state_counter * 1024,
        }


@pytest.fixture
def temp_checkpoint_dir():
    """Create a temporary checkpoint directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def checkpoint_manager(temp_checkpoint_dir):
    """Create a CheckpointManager instance."""
    return CheckpointManager(
        checkpoint_dir=temp_checkpoint_dir,
        symbol="BTCUSDT",
        max_checkpoints=3,
        enable_time_trigger=False,  # Disable for unit tests
    )


@pytest.fixture
def checkpoint_manager_with_time_trigger(temp_checkpoint_dir):
    """Create a CheckpointManager with time triggers enabled."""
    return CheckpointManager(
        checkpoint_dir=temp_checkpoint_dir,
        symbol="BTCUSDT",
        max_checkpoints=3,
        enable_time_trigger=True,
        time_interval=0.5,  # 500ms for testing
    )


def test_checkpoint_manager_initialization(checkpoint_manager, temp_checkpoint_dir):
    """Test CheckpointManager initialization."""
    assert checkpoint_manager.symbol == "BTCUSDT"
    assert checkpoint_manager.checkpoint_dir == temp_checkpoint_dir
    assert checkpoint_manager.max_checkpoints == 3
    assert checkpoint_manager.prefer_parquet is True
    
    # Check directory permissions
    assert temp_checkpoint_dir.exists()
    stat_info = temp_checkpoint_dir.stat()
    assert oct(stat_info.st_mode)[-3:] == "700"


def test_save_checkpoint_parquet(checkpoint_manager):
    """Test saving checkpoint in Parquet format."""
    state_data = {
        "book_state": {"test": "data"},
        "last_update_id": 12345,
        "updates_processed": 100,
        "gap_stats": {},
        "drift_metrics": {},
    }
    
    # Save checkpoint
    checkpoint_path = checkpoint_manager.save_checkpoint(state_data, 12345)
    
    assert checkpoint_path.exists()
    assert checkpoint_path.suffix == ".parquet"
    assert "BTCUSDT_checkpoint_12345" in checkpoint_path.name
    
    # Check file permissions
    stat_info = checkpoint_path.stat()
    assert oct(stat_info.st_mode)[-3:] == "600"


def test_load_latest_checkpoint_parquet(checkpoint_manager):
    """Test loading latest Parquet checkpoint."""
    # Save multiple checkpoints
    for i in range(3):
        state_data = {
            "book_state": {"version": i},
            "last_update_id": i * 1000,
            "updates_processed": i * 100,
            "gap_stats": {},
            "drift_metrics": {},
        }
        time.sleep(0.01)  # Ensure different timestamps
        checkpoint_manager.save_checkpoint(state_data, i * 1000)
    
    # Load latest
    loaded_state = checkpoint_manager.load_latest_checkpoint()
    
    assert loaded_state is not None
    assert loaded_state["last_update_id"] == 2000
    assert loaded_state["book_state"]["version"] == 2


def test_checkpoint_cleanup(checkpoint_manager):
    """Test old checkpoint cleanup."""
    # Save more than max_checkpoints
    for i in range(5):
        state_data = {
            "book_state": {"version": i},
            "last_update_id": i * 1000,
            "updates_processed": i * 100,
            "gap_stats": {},
            "drift_metrics": {},
        }
        time.sleep(0.01)
        checkpoint_manager.save_checkpoint(state_data, i * 1000)
    
    # Check only max_checkpoints remain
    checkpoint_files = list(checkpoint_manager.checkpoint_dir.glob("*.parquet"))
    assert len(checkpoint_files) == 3
    
    # Verify oldest were removed
    loaded_state = checkpoint_manager.load_latest_checkpoint()
    assert loaded_state["last_update_id"] == 4000  # Latest


@pytest.mark.asyncio
async def test_async_checkpoint_with_state_provider(checkpoint_manager):
    """Test async checkpoint with state provider."""
    mock_provider = MockStateProvider()
    checkpoint_manager.set_state_provider(mock_provider)
    
    # Start checkpoint manager
    await checkpoint_manager.start()
    
    try:
        # Trigger manual checkpoint
        task = await checkpoint_manager._async_checkpoint_callback()
        if task:
            await task
        
        # Verify checkpoint was created
        checkpoint_files = list(checkpoint_manager.checkpoint_dir.glob("*.parquet"))
        assert len(checkpoint_files) == 1
        
        # Load and verify
        loaded_state = checkpoint_manager.load_latest_checkpoint()
        assert loaded_state is not None
        assert loaded_state["last_update_id"] == 1000
        
    finally:
        await checkpoint_manager.stop()


@pytest.mark.asyncio
async def test_time_based_triggers(checkpoint_manager_with_time_trigger):
    """Test time-based checkpoint triggers."""
    mock_provider = MockStateProvider()
    checkpoint_manager_with_time_trigger.set_state_provider(mock_provider)
    
    # Start checkpoint manager
    await checkpoint_manager_with_time_trigger.start()
    
    try:
        # Wait for time-based trigger
        await asyncio.sleep(0.6)
        
        # Verify checkpoint was created
        checkpoint_files = list(
            checkpoint_manager_with_time_trigger.checkpoint_dir.glob("*.parquet")
        )
        assert len(checkpoint_files) >= 1
        
    finally:
        await checkpoint_manager_with_time_trigger.stop()


@pytest.mark.asyncio
async def test_event_based_triggers(checkpoint_manager):
    """Test event-based checkpoint triggers."""
    mock_provider = MockStateProvider()
    checkpoint_manager.set_state_provider(mock_provider)
    
    # Configure for smaller event interval
    checkpoint_manager.checkpoint_trigger.config.event_interval = 100
    
    await checkpoint_manager.start()
    
    try:
        # Record events
        for i in range(10):
            await checkpoint_manager.record_events(20)
            mock_provider.events_processed += 20
        
        # Wait for async checkpoint
        await asyncio.sleep(0.1)
        
        # Verify checkpoint was created
        checkpoint_files = list(checkpoint_manager.checkpoint_dir.glob("*.parquet"))
        assert len(checkpoint_files) >= 1
        
    finally:
        await checkpoint_manager.stop()


def test_wal_integration(checkpoint_manager):
    """Test WAL manager integration."""
    assert checkpoint_manager.wal_enabled is True
    assert checkpoint_manager.wal_manager is not None
    
    # Log events to WAL
    for i in range(100):
        event_data = {
            "update_id": i,
            "event_type": "test",
            "data": f"event_{i}",
        }
        checkpoint_manager.log_event_to_wal(event_data)
    
    # Check WAL stats
    wal_stats = checkpoint_manager.wal_manager.get_stats()
    assert wal_stats["current_buffer_size"] == 100


@pytest.mark.asyncio
async def test_recovery_from_wal(checkpoint_manager):
    """Test recovery from WAL after checkpoint."""
    # Save initial checkpoint
    state_data = {
        "book_state": {"version": 1},
        "last_update_id": 1000,
        "updates_processed": 100,
        "gap_stats": {},
        "drift_metrics": {},
    }
    checkpoint_manager.save_checkpoint(state_data, 1000)
    
    # Log events to WAL after checkpoint
    for i in range(1001, 1101):
        event_data = {
            "update_id": i,
            "event_type": "test",
            "data": f"event_{i}",
        }
        checkpoint_manager.log_event_to_wal(event_data)
    
    # Flush WAL
    checkpoint_manager.wal_manager.flush()
    
    # Recover from WAL
    recovered_count = await checkpoint_manager.recover_from_wal()
    assert recovered_count == 100


def test_checkpoint_monitor_metrics(checkpoint_manager):
    """Test checkpoint performance monitoring."""
    # Record some events
    checkpoint_manager.checkpoint_monitor.record_events(1000)
    
    # Simulate checkpoint
    checkpoint_manager.checkpoint_monitor.checkpoint_started()
    time.sleep(0.05)  # 50ms checkpoint
    checkpoint_manager.checkpoint_monitor.checkpoint_completed()
    
    # Get metrics
    metrics = checkpoint_manager.checkpoint_monitor.get_metrics()
    
    assert metrics["checkpoint_count"] == 1
    assert metrics["avg_checkpoint_time_ms"] >= 50
    assert metrics["events_processed"] == 1000


def test_state_snapshot_cow_performance(checkpoint_manager):
    """Test copy-on-write snapshot performance."""
    mock_provider = MockStateProvider()
    
    # Time snapshot creation
    start_time = time.time()
    
    # Create snapshot (should be fast due to COW)
    snapshot = asyncio.run(
        checkpoint_manager.state_snapshot.create_snapshot(mock_provider)
    )
    
    snapshot_time_ms = (time.time() - start_time) * 1000
    
    assert snapshot is not None
    assert snapshot.last_update_id == 1000
    assert snapshot_time_ms < 100  # Should complete in <100ms


def test_clear_all_checkpoints(checkpoint_manager):
    """Test clearing all checkpoints."""
    # Create some checkpoints
    for i in range(3):
        state_data = {
            "book_state": {"version": i},
            "last_update_id": i * 1000,
            "updates_processed": i * 100,
            "gap_stats": {},
            "drift_metrics": {},
        }
        checkpoint_manager.save_checkpoint(state_data, i * 1000)
    
    # Verify checkpoints exist
    checkpoint_files = list(checkpoint_manager.checkpoint_dir.glob("*.parquet"))
    assert len(checkpoint_files) == 3
    
    # Clear all
    checkpoint_manager.clear_all_checkpoints()
    
    # Verify all cleared
    checkpoint_files = list(checkpoint_manager.checkpoint_dir.glob("*.parquet"))
    assert len(checkpoint_files) == 0