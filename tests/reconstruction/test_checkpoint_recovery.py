"""Integration tests for checkpoint and recovery functionality."""

import asyncio
import json
import os
import signal
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import Mock, patch

import pytest
from loguru import logger

from rlx_datapipe.reconstruction.checkpoint_manager import CheckpointManager
from rlx_datapipe.reconstruction.order_book_engine import OrderBookEngine
from rlx_datapipe.reconstruction.pipeline_integration import RecoverablePipeline
from rlx_datapipe.reconstruction.pipeline_state_provider import PipelineStateProvider
from rlx_datapipe.reconstruction.recovery_manager import RecoveryManager
from rlx_datapipe.reconstruction.seekable_file_reader import SeekableFileReader
from rlx_datapipe.reconstruction.symbol_worker import SymbolWorker
from rlx_datapipe.reconstruction.unified_market_event import UnifiedMarketEvent


@pytest.fixture
def temp_output_dir():
    """Create temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_events():
    """Generate sample market events."""
    events = []
    
    # Book snapshot
    events.append({
        "event_type": "BOOK_SNAPSHOT",
        "update_id": 1000,
        "origin_time": int(time.time() * 1e9),
        "bids": [[100.0, 1.0], [99.0, 2.0], [98.0, 3.0]],
        "asks": [[101.0, 1.0], [102.0, 2.0], [103.0, 3.0]],
    })
    
    # Book deltas
    for i in range(1001, 1100):
        events.append({
            "event_type": "BOOK_DELTA",
            "update_id": i,
            "origin_time": int(time.time() * 1e9),
            "side": "BID" if i % 2 == 0 else "ASK",
            "price": 100.0 + (i % 10) * 0.1,
            "new_quantity": (i % 5) * 0.5,
        })
    
    # Trades
    for i in range(1100, 1150):
        events.append({
            "event_type": "TRADE",
            "update_id": i,
            "origin_time": int(time.time() * 1e9),
            "trade_id": f"trade_{i}",
            "price": 100.5,
            "quantity": 0.1,
            "side": "BUY" if i % 2 == 0 else "SELL",
        })
    
    return events


@pytest.fixture
def sample_data_file(temp_output_dir, sample_events):
    """Create a sample data file."""
    data_file = temp_output_dir / "sample_data.jsonl"
    
    with open(data_file, "w") as f:
        for event in sample_events:
            f.write(json.dumps(event) + "\n")
    
    return data_file


@pytest.mark.asyncio
async def test_full_checkpoint_recovery_cycle(temp_output_dir, sample_events):
    """Test complete checkpoint and recovery cycle."""
    symbol = "BTCUSDT"
    checkpoint_dir = temp_output_dir / "checkpoints"
    
    # Phase 1: Process events with checkpointing
    engine = OrderBookEngine(
        symbol=symbol,
        checkpoint_dir=checkpoint_dir,
    )
    
    # Load checkpoint manager
    assert engine.checkpoint_manager is not None
    
    # Process first half of events
    for event in sample_events[:75]:
        if event["event_type"] == "BOOK_SNAPSHOT":
            # Simplified snapshot processing
            engine.last_update_id = event["update_id"]
            engine.updates_processed += 1
        elif event["event_type"] == "BOOK_DELTA":
            engine.last_update_id = event["update_id"]
            engine.updates_processed += 1
    
    # Save checkpoint
    engine._save_checkpoint()
    
    # Verify checkpoint was created
    checkpoint_files = list(checkpoint_dir.glob("*.parquet"))
    assert len(checkpoint_files) == 1
    
    # Phase 2: Simulate crash and recovery
    last_update_before_crash = engine.last_update_id
    events_before_crash = engine.updates_processed
    
    # Create new engine instance (simulating restart)
    new_engine = OrderBookEngine(
        symbol=symbol,
        checkpoint_dir=checkpoint_dir,
    )
    
    # Load checkpoint
    success = new_engine.load_checkpoint()
    assert success is True
    assert new_engine.last_update_id == last_update_before_crash
    assert new_engine.updates_processed == events_before_crash
    
    # Continue processing from checkpoint
    for event in sample_events[75:]:
        if event["event_type"] in ["BOOK_DELTA", "TRADE"]:
            new_engine.last_update_id = event["update_id"]
            new_engine.updates_processed += 1
    
    # Verify all events processed
    assert new_engine.last_update_id == 1149
    assert new_engine.updates_processed == len(sample_events) - 1  # -1 for snapshot


@pytest.mark.asyncio
async def test_recoverable_pipeline(temp_output_dir, sample_data_file):
    """Test RecoverablePipeline with checkpoint and recovery."""
    symbol = "BTCUSDT"
    
    # Phase 1: Initial pipeline run
    pipeline = RecoverablePipeline(
        output_dir=temp_output_dir,
        symbol=symbol,
        enable_recovery=True,
    )
    
    # Initialize pipeline
    data_sink, event_queue = await pipeline.initialize()
    
    # No recovery on first run
    assert pipeline.recovery_successful is False
    assert pipeline.get_last_update_id() is None
    
    # Process some events
    with open(sample_data_file, "r") as f:
        for i, line in enumerate(f):
            if i >= 50:  # Process first 50 events
                break
            
            event_data = json.loads(line)
            # Simulate event processing and checkpoint
            if i == 25:
                # Create manual checkpoint
                checkpoint_manager = CheckpointManager(
                    checkpoint_dir=pipeline.checkpoint_dir,
                    symbol=symbol,
                )
                
                state_data = {
                    "book_state": {},
                    "last_update_id": event_data.get("update_id", 0),
                    "updates_processed": i,
                    "gap_stats": {},
                    "drift_metrics": {},
                    "current_file": str(sample_data_file),
                    "file_offset": f.tell(),
                }
                
                checkpoint_manager.save_checkpoint(
                    state_data,
                    event_data.get("update_id", 0)
                )
    
    # Phase 2: Recovery
    pipeline2 = RecoverablePipeline(
        output_dir=temp_output_dir,
        symbol=symbol,
        enable_recovery=True,
    )
    
    # Initialize with recovery
    data_sink2, event_queue2 = await pipeline2.initialize()
    
    # Should have recovered
    assert pipeline2.recovery_successful is True
    assert pipeline2.get_last_update_id() is not None
    
    # Get resume position
    resume_file, resume_offset = pipeline2.get_resume_position()
    assert resume_file == str(sample_data_file)
    assert resume_offset > 0


@pytest.mark.asyncio
async def test_data_continuity_validation(temp_output_dir):
    """Test data continuity validation after recovery."""
    symbol = "BTCUSDT"
    checkpoint_dir = temp_output_dir / "checkpoints"
    
    # Create recovery manager
    recovery_manager = RecoveryManager(checkpoint_dir, symbol)
    
    # Create checkpoint
    checkpoint_manager = CheckpointManager(
        checkpoint_dir=checkpoint_dir,
        symbol=symbol,
    )
    
    state_data = {
        "book_state": {},
        "last_update_id": 5000,
        "updates_processed": 1000,
        "gap_stats": {},
        "drift_metrics": {},
    }
    
    checkpoint_manager.save_checkpoint(state_data, 5000)
    
    # Test recovery
    success = await recovery_manager.attempt_recovery()
    assert success is True
    
    # Test continuity validation
    
    # Case 1: Perfect continuity
    valid = await recovery_manager.validate_continuity(5001, int(time.time() * 1e9))
    assert valid is True
    
    # Case 2: Small gap (acceptable)
    valid = await recovery_manager.validate_continuity(5100, int(time.time() * 1e9))
    assert valid is True
    
    # Case 3: Large gap (unacceptable)
    valid = await recovery_manager.validate_continuity(7000, int(time.time() * 1e9))
    assert valid is False
    
    # Case 4: Duplicate processing warning
    valid = await recovery_manager.validate_continuity(4999, int(time.time() * 1e9))
    assert valid is True  # Still valid but should log warning


def test_seekable_file_reader(sample_data_file):
    """Test seekable file reader for recovery."""
    reader = SeekableFileReader(sample_data_file)
    
    with reader:
        # Read first few lines
        lines_read = 0
        initial_offset = 0
        
        for i in range(10):
            line = reader.read_line()
            assert line is not None
            lines_read += 1
        
        # Get position
        filename, offset, line_num = reader.get_position()
        assert filename == str(sample_data_file)
        assert offset > initial_offset
        assert line_num == 10
        
        # Seek back to beginning
        success = reader.seek(0)
        assert success is True
        
        # Read first line again
        first_line = reader.read_line()
        assert first_line is not None
        data = json.loads(first_line)
        assert data["update_id"] == 1000
        
        # Test finding specific update_id
        reader.seek(0)
        found = reader.find_update_id(1050)
        assert found is True
        
        # Next line should have update_id > 1050
        next_line = reader.read_line()
        next_data = json.loads(next_line)
        assert next_data["update_id"] > 1050


@pytest.mark.asyncio
async def test_crash_simulation_with_wal(temp_output_dir):
    """Test crash recovery using WAL."""
    symbol = "BTCUSDT"
    checkpoint_dir = temp_output_dir / "checkpoints"
    
    # Create checkpoint manager with WAL
    checkpoint_manager = CheckpointManager(
        checkpoint_dir=checkpoint_dir,
        symbol=symbol,
    )
    
    # Save initial checkpoint
    state_data = {
        "book_state": {},
        "last_update_id": 1000,
        "updates_processed": 100,
        "gap_stats": {},
        "drift_metrics": {},
    }
    checkpoint_manager.save_checkpoint(state_data, 1000)
    
    # Log events to WAL (simulating events after checkpoint)
    for i in range(1001, 1051):
        event_data = {
            "update_id": i,
            "event_type": "BOOK_DELTA",
            "price": 100.0 + i * 0.01,
            "quantity": 1.0,
        }
        checkpoint_manager.log_event_to_wal(event_data)
    
    # Simulate crash (WAL not flushed)
    # In real scenario, WAL would be partially written
    
    # Flush WAL for test
    checkpoint_manager.wal_manager.flush()
    
    # Create new checkpoint manager (simulating restart)
    new_checkpoint_manager = CheckpointManager(
        checkpoint_dir=checkpoint_dir,
        symbol=symbol,
    )
    
    # Load checkpoint
    recovered_state = new_checkpoint_manager.load_latest_checkpoint()
    assert recovered_state["last_update_id"] == 1000
    
    # Recover from WAL
    wal_events = await new_checkpoint_manager.recover_from_wal()
    assert wal_events == 50  # Events 1001-1050


@pytest.mark.asyncio
async def test_performance_impact_monitoring(temp_output_dir):
    """Test checkpoint performance impact is <1%."""
    symbol = "BTCUSDT"
    checkpoint_dir = temp_output_dir / "checkpoints"
    
    # Create checkpoint manager
    checkpoint_manager = CheckpointManager(
        checkpoint_dir=checkpoint_dir,
        symbol=symbol,
        enable_time_trigger=False,
    )
    
    # Mock state provider
    mock_provider = Mock()
    mock_provider.get_checkpoint_state.return_value = {
        "book_state": {"test": "data"},
        "last_update_id": 1000,
        "gap_stats": {},
        "updates_processed": 1000,
        "snapshot_count": 1,
        "drift_metrics": {},
        "processing_rate": 100000.0,
    }
    checkpoint_manager.set_state_provider(mock_provider)
    
    await checkpoint_manager.start()
    
    try:
        # Simulate high-throughput event processing
        start_time = time.time()
        events_processed = 0
        
        # Process events for 2 seconds
        while time.time() - start_time < 2.0:
            # Record batch of events
            await checkpoint_manager.record_events(1000)
            events_processed += 1000
            
            # Trigger checkpoint every 100k events
            if events_processed % 100000 == 0:
                await checkpoint_manager._async_checkpoint_callback()
            
            # Small delay to simulate processing
            await asyncio.sleep(0.001)
        
        # Get performance metrics
        metrics = checkpoint_manager.checkpoint_monitor.get_metrics()
        
        # Check throughput impact
        assert metrics["throughput_degradation_percent"] < 1.0
        
        # Check checkpoint time
        assert metrics["avg_checkpoint_time_ms"] < 100
        
    finally:
        await checkpoint_manager.stop()


def test_secure_checkpoint_files(temp_output_dir):
    """Test checkpoint file security."""
    symbol = "BTCUSDT"
    checkpoint_dir = temp_output_dir / "checkpoints"
    
    checkpoint_manager = CheckpointManager(
        checkpoint_dir=checkpoint_dir,
        symbol=symbol,
    )
    
    # Save checkpoint
    state_data = {
        "book_state": {"sensitive": "data"},
        "last_update_id": 1000,
        "updates_processed": 100,
        "gap_stats": {},
        "drift_metrics": {},
    }
    
    checkpoint_path = checkpoint_manager.save_checkpoint(state_data, 1000)
    
    # Verify file permissions
    stat_info = checkpoint_path.stat()
    file_perms = oct(stat_info.st_mode)[-3:]
    assert file_perms == "600"  # Owner read/write only
    
    # Verify directory permissions
    dir_stat = checkpoint_dir.stat()
    dir_perms = oct(dir_stat.st_mode)[-3:]
    assert dir_perms == "700"  # Owner full access only
    
    # Verify WAL directory permissions
    wal_dir = checkpoint_dir / "wal"
    if wal_dir.exists():
        wal_stat = wal_dir.stat()
        wal_perms = oct(wal_stat.st_mode)[-3:]
        assert wal_perms == "700"


@pytest.mark.asyncio
async def test_memory_leak_detection(temp_output_dir):
    """Test for memory leaks during extended operation."""
    import gc
    import sys
    
    symbol = "BTCUSDT"
    checkpoint_dir = temp_output_dir / "checkpoints"
    
    checkpoint_manager = CheckpointManager(
        checkpoint_dir=checkpoint_dir,
        symbol=symbol,
        enable_time_trigger=False,
    )
    
    # Mock state provider
    mock_provider = Mock()
    mock_provider.get_checkpoint_state.return_value = {
        "book_state": {"test": "data" * 100},  # Larger state
        "last_update_id": 1000,
        "gap_stats": {},
        "updates_processed": 1000,
        "snapshot_count": 1,
        "drift_metrics": {},
        "processing_rate": 100000.0,
    }
    checkpoint_manager.set_state_provider(mock_provider)
    
    await checkpoint_manager.start()
    
    try:
        # Record initial memory
        gc.collect()
        initial_objects = len(gc.get_objects())
        
        # Perform many checkpoint cycles
        for i in range(100):
            # Trigger checkpoint
            await checkpoint_manager._async_checkpoint_callback()
            
            # Record events
            await checkpoint_manager.record_events(1000)
            
            # Small delay
            await asyncio.sleep(0.01)
        
        # Force garbage collection
        gc.collect()
        final_objects = len(gc.get_objects())
        
        # Check for excessive object growth
        object_growth = final_objects - initial_objects
        growth_percentage = (object_growth / initial_objects) * 100
        
        # Allow some growth but flag potential leaks
        assert growth_percentage < 10.0, f"Potential memory leak: {growth_percentage:.1f}% object growth"
        
    finally:
        await checkpoint_manager.stop()