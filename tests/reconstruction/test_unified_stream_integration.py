"""Test integration with unified stream components."""

import pytest
import polars as pl
from pathlib import Path
import tempfile

from rlx_datapipe.reconstruction.unified_stream_with_replay import UnifiedEventStreamWithReplay
from rlx_datapipe.reconstruction.unified_stream_enhanced import EnhancedUnificationConfig


def test_unified_stream_with_replay_init():
    """Test initialization of integrated stream."""
    config = EnhancedUnificationConfig(
        enable_order_book=True,
        max_book_levels=20,
        enable_drift_tracking=True
    )
    
    stream = UnifiedEventStreamWithReplay(
        symbol="BTCUSDT",
        config=config,
        drift_threshold=0.001,
        resync_on_drift=True
    )
    
    assert stream.symbol == "BTCUSDT"
    assert stream.chronological_replayer is not None
    assert stream.chronological_replayer.drift_threshold == 0.001


def test_batch_processing_integration():
    """Test batch processing with chronological replay."""
    # Create test data with required columns
    trades_data = pl.DataFrame({
        "symbol": ["BTCUSDT"] * 3,
        "origin_time": [1000000002, 1000000004, 1000000006],
        "timestamp": [1000000002, 1000000004, 1000000006],  # Required
        "exchange": ["binance"] * 3,  # Required
        "event_type": ["TRADE"] * 3,
        "trade_id": [1, 2, 3],
        "price": [50000.0, 50001.0, 50002.0],
        "quantity": [0.5, 0.6, 0.7],
        "side": ["BUY", "SELL", "BUY"]
    })
    
    snapshots_data = pl.DataFrame({
        "symbol": ["BTCUSDT"] * 2,
        "origin_time": [1000000001, 1000000005],
        "timestamp": [1000000001, 1000000005],  # Required
        "exchange": ["binance"] * 2,  # Required
        "event_type": ["BOOK_SNAPSHOT"] * 2,
        # Add bid/ask columns in expected format
        "bid_price_0": [49999.0, 50000.0],
        "bid_quantity_0": [1.0, 1.1],
        "bid_price_1": [49998.0, 49999.0],
        "bid_quantity_1": [2.0, 2.1],
        "ask_price_0": [50001.0, 50002.0],
        "ask_quantity_0": [1.0, 1.1],
        "ask_price_1": [50002.0, 50003.0],
        "ask_quantity_1": [2.0, 2.1],
        "is_snapshot": [True, True]
    })
    
    deltas_data = pl.DataFrame({
        "symbol": ["BTCUSDT"] * 2,
        "origin_time": [1000000003, 1000000007],
        "timestamp": [1000000003, 1000000007],  # Required
        "exchange": ["binance"] * 2,  # Required
        "update_id": [1, 2],  # Required
        "event_type": ["BOOK_DELTA"] * 2,
        "side": ["BID", "ASK"],
        "price": [49997.0, 50004.0],
        "new_quantity": [3.0, 0.0]
    })
    
    # Use temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Save test data
        trades_path = temp_path / "trades.parquet"
        snapshots_path = temp_path / "snapshots.parquet"
        deltas_path = temp_path / "deltas.parquet"
        output_path = temp_path / "output"
        
        trades_data.write_parquet(trades_path)
        snapshots_data.write_parquet(snapshots_path)
        deltas_data.write_parquet(deltas_path)
        
        # Process with integrated stream
        stream = UnifiedEventStreamWithReplay(
            symbol="BTCUSDT",
            drift_threshold=0.001
        )
        
        stats = stream.process_unified_stream(
            trades_path=trades_path,
            book_snapshots_path=snapshots_path,
            book_deltas_path=deltas_path,
            output_path=output_path,
            use_streaming=False  # Use batch mode for test
        )
        
        # Check statistics
        assert stats["total_events"] == 7  # 3 trades + 2 snapshots + 2 deltas
        assert stats["trades_processed"] == 3
        assert stats["snapshots_processed"] == 2
        assert stats["deltas_processed"] == 2
        assert stats["events_with_book_state"] >= 6  # All but first trade
        
        # Check drift metrics
        assert "drift_metrics" in stats
        assert stats["drift_metrics"]["total_snapshots"] == 1  # Second snapshot calculates drift
        
        # Check output files
        assert (output_path / "chronological_events_enriched.parquet").exists()
        
        # Load and verify enriched data
        enriched_df = pl.read_parquet(output_path / "chronological_events_enriched.parquet")
        assert len(enriched_df) == 7
        
        # Verify chronological order
        timestamps = enriched_df["event_timestamp"].to_list()
        assert timestamps == sorted(timestamps)
        
        # Verify book state enrichment
        assert enriched_df.filter(pl.col("top_bid").is_not_null()).height >= 6


def test_drift_report():
    """Test drift report generation."""
    stream = UnifiedEventStreamWithReplay(
        symbol="BTCUSDT",
        drift_threshold=0.001
    )
    
    # Generate some drift data
    snapshot1 = pl.DataFrame({
        "event_type": ["BOOK_SNAPSHOT"],
        "origin_time": [1000000001],
        "bids": [[[100.0, 10.0]]],
        "asks": [[[101.0, 10.0]]]
    })
    
    delta = pl.DataFrame({
        "event_type": ["BOOK_DELTA"],
        "origin_time": [1000000002],
        "delta_side": ["BID"],
        "delta_price": [99.0],
        "delta_quantity": [5.0]
    })
    
    snapshot2 = pl.DataFrame({
        "event_type": ["BOOK_SNAPSHOT"],
        "origin_time": [1000000003],
        "bids": [[[100.0, 10.5], [99.0, 5.0]]],  # Drift on first level
        "asks": [[[101.0, 10.0]]]
    })
    
    # Process events
    events_df = pl.concat([snapshot1, delta, snapshot2])
    stream.chronological_replayer.execute(events_df)
    
    # Get drift report
    report = stream.get_drift_report()
    
    assert "summary" in report
    assert "thresholds" in report
    assert "recommendations" in report
    
    assert report["summary"]["total_snapshots"] == 1
    assert report["thresholds"]["configured_threshold"] == 0.001
    assert report["thresholds"]["resync_enabled"] is True


def test_configuration_propagation():
    """Test that configuration is properly propagated."""
    config = EnhancedUnificationConfig(
        max_book_levels=10,
        enable_drift_tracking=True,
        use_memory_mapping=False,
        pending_queue_size=500
    )
    
    stream = UnifiedEventStreamWithReplay(
        symbol="BTCUSDT",
        config=config,
        drift_threshold=0.005
    )
    
    # Check configuration propagation
    assert stream.config.max_book_levels == 10
    assert stream.config.enable_drift_tracking is True
    assert stream.config.use_memory_mapping is False
    assert stream.config.pending_queue_size == 500
    
    # Check replayer configuration
    assert stream.chronological_replayer.max_levels == 10
    assert stream.chronological_replayer.drift_threshold == 0.005


def test_empty_data_handling():
    """Test handling of empty or missing data."""
    stream = UnifiedEventStreamWithReplay(symbol="BTCUSDT")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        output_path = temp_path / "output"
        
        # Process with no data files
        stats = stream.process_unified_stream(
            output_path=output_path,
            use_streaming=False
        )
        
        # Should handle gracefully
        assert stats["total_events"] == 0
        assert stats["trades_processed"] == 0
        assert stats["snapshots_processed"] == 0
        assert stats["deltas_processed"] == 0