"""Simple integration test for event replayer."""

import pytest
import polars as pl
from pathlib import Path
import tempfile

from rlx_datapipe.reconstruction import ChronologicalEventReplay, UnifiedEventStreamWithReplay
from rlx_datapipe.reconstruction.unified_stream_enhanced import EnhancedUnificationConfig


def test_direct_chronological_replay_integration():
    """Test direct integration of ChronologicalEventReplay."""
    # Create mixed event data
    events_data = [
        # First snapshot
        {
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000001,
            "bids": [[49999.0, 1.0], [49998.0, 2.0]],
            "asks": [[50001.0, 1.0], [50002.0, 2.0]],
            "is_snapshot": True
        },
        # Trade
        {
            "event_type": "TRADE", 
            "origin_time": 1000000002,
            "trade_id": 123,
            "trade_price": 50000.0,
            "trade_quantity": 0.5,
            "trade_side": "BUY"
        },
        # Delta
        {
            "event_type": "BOOK_DELTA",
            "origin_time": 1000000003,
            "delta_side": "BID",
            "delta_price": 49997.0,
            "delta_quantity": 3.0
        },
        # Another trade
        {
            "event_type": "TRADE",
            "origin_time": 1000000004,
            "trade_id": 124,
            "trade_price": 50001.0,
            "trade_quantity": 0.3,
            "trade_side": "SELL"
        },
        # Second snapshot for drift check
        {
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000005,
            "bids": [[49999.0, 1.0], [49998.0, 2.0], [49997.0, 3.1]],  # Slight drift
            "asks": [[50001.0, 0.7], [50002.0, 2.0]],  # Trade impact
            "is_snapshot": True
        }
    ]
    
    events_df = pl.DataFrame(events_data)
    
    # Create replayer
    replayer = ChronologicalEventReplay(
        drift_threshold=0.001,
        max_levels=20,
        resync_on_drift=True
    )
    
    # Execute replay
    result_df = replayer.execute(events_df)
    
    # Verify results
    assert len(result_df) == 5
    
    # Check chronological order maintained
    timestamps = result_df["event_timestamp"].to_list()
    assert timestamps == sorted(timestamps)
    
    # Check all events have required fields
    assert all(col in result_df.columns for col in [
        "event_timestamp", "event_type", "book_state", 
        "top_bid", "top_ask", "spread"
    ])
    
    # Check book initialization
    first_event = result_df[0]
    assert first_event["event_type"].item() == "BOOK_SNAPSHOT"
    assert first_event["top_bid"][0] is not None
    
    # Check drift was detected
    last_snapshot = result_df[4]
    assert last_snapshot["drift_metrics"][0] is not None
    assert "rms_error" in last_snapshot["drift_metrics"][0]
    
    # Check statistics
    drift_stats = replayer.drift_tracker.get_statistics()
    assert drift_stats["total_snapshots"] == 1  # Only second snapshot calculates drift
    assert drift_stats["total_resyncs"] >= 0
    
    # Save to parquet and reload to test serialization
    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir) / "replayed_events.parquet"
        result_df.write_parquet(output_path)
        
        # Reload and verify
        reloaded_df = pl.read_parquet(output_path)
        assert len(reloaded_df) == 5
        assert reloaded_df["event_type"].to_list() == result_df["event_type"].to_list()


def test_configuration_and_metrics():
    """Test configuration options and metric tracking."""
    config = EnhancedUnificationConfig(
        max_book_levels=5,  # Small for testing
        enable_drift_tracking=True
    )
    
    # Create stream with custom config
    stream = UnifiedEventStreamWithReplay(
        symbol="BTCUSDT",
        config=config,
        drift_threshold=0.05,  # 5% threshold
        resync_on_drift=False  # Don't resync
    )
    
    # Create simple test events
    events = pl.DataFrame([
        {
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000001,
            "bids": [[100.0, 10.0]] * 10,  # More than max_levels
            "asks": [[101.0, 10.0]] * 10
        }
    ])
    
    # Process directly through replayer
    result = stream.chronological_replayer.execute(events)
    
    # Check configuration was applied
    assert stream.chronological_replayer.max_levels == 5
    assert stream.chronological_replayer.drift_threshold == 0.05
    assert stream.chronological_replayer.resync_on_drift is False
    
    # Get drift report
    report = stream.get_drift_report()
    assert "summary" in report
    assert "thresholds" in report
    assert report["thresholds"]["configured_threshold"] == 0.05
    assert report["thresholds"]["resync_enabled"] is False


def test_drift_export_for_fidelity_reporter():
    """Test exporting drift metrics for FidelityReporter."""
    replayer = ChronologicalEventReplay(drift_threshold=0.001)
    
    # Create events that will generate drift
    events = pl.DataFrame([
        {
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000001,
            "bids": [[100.0, 10.0]],
            "asks": [[101.0, 10.0]]
        },
        {
            "event_type": "BOOK_DELTA",
            "origin_time": 1000000002,
            "delta_side": "BID",
            "delta_price": 99.0,
            "delta_quantity": 5.0
        },
        {
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000003,
            "bids": [[100.0, 10.1], [99.0, 5.0]],  # Slight drift
            "asks": [[101.0, 10.0]]
        },
        {
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000004,
            "bids": [[100.0, 11.0], [99.0, 5.5]],  # More drift
            "asks": [[101.0, 10.0]]
        }
    ])
    
    # Process events
    result = replayer.execute(events)
    
    # Export drift metrics
    exported_metrics = replayer.drift_tracker.export_metrics()
    
    # Verify export format
    assert len(exported_metrics) == 2  # Two snapshots with drift calculations
    
    for metric in exported_metrics:
        assert metric["metric_type"] == "drift"
        assert metric["threshold"] == 0.001
        assert "rms_error" in metric
        assert "max_deviation" in metric
        assert "snapshot_number" in metric
        assert "exceeds_threshold" in metric
    
    # Test that metrics can be saved to DataFrame
    metrics_df = pl.DataFrame(exported_metrics)
    assert len(metrics_df) == 2
    assert "metric_type" in metrics_df.columns
    assert metrics_df["metric_type"].unique().to_list() == ["drift"]