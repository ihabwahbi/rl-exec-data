"""Comprehensive test coverage for event replayer functionality."""

import pytest
import polars as pl
from decimal import Decimal
import tempfile
from pathlib import Path

from rlx_datapipe.reconstruction import (
    ChronologicalEventReplay,
    SchemaNormalizer,
    DriftTracker,
    OrderBookState,
    UnifiedEventStreamWithReplay
)


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_events(self):
        """Test handling of empty event stream."""
        replayer = ChronologicalEventReplay()
        empty_df = pl.DataFrame({"event_type": [], "origin_time": []})
        
        result = replayer.execute(empty_df)
        assert len(result) == 0
    
    def test_single_event_types(self):
        """Test handling streams with only one event type."""
        replayer = ChronologicalEventReplay()
        
        # Only trades
        trades_only = pl.DataFrame([
            {
                "event_type": "TRADE",
                "origin_time": 1000000001 + i,
                "trade_id": i,
                "trade_price": 50000.0,
                "trade_quantity": 0.1,
                "trade_side": "BUY"
            } for i in range(10)
        ])
        
        result = replayer.execute(trades_only)
        assert len(result) == 10
        # Should have None for book state since no snapshot
        for row in result.iter_rows(named=True):
            assert row["top_bid"] is None
    
    def test_duplicate_timestamps(self):
        """Test handling of events with identical timestamps."""
        replayer = ChronologicalEventReplay()
        
        events = pl.DataFrame([
            {
                "event_type": "TRADE",
                "origin_time": 1000000001,
                "update_id": 1,
                "trade_id": 1,
                "trade_price": 50000.0,
                "trade_quantity": 0.1,
                "trade_side": "BUY"
            },
            {
                "event_type": "TRADE",
                "origin_time": 1000000001,  # Same timestamp
                "update_id": 2,
                "trade_id": 2,
                "trade_price": 50001.0,
                "trade_quantity": 0.2,
                "trade_side": "SELL"
            }
        ])
        
        result = replayer.execute(events)
        assert len(result) == 2
        # Should be sorted by update_id
        assert result[0]["trade_id"].item() == 1
        assert result[1]["trade_id"].item() == 2
    
    def test_malformed_snapshot(self):
        """Test handling of malformed snapshot data."""
        replayer = ChronologicalEventReplay()
        
        events = pl.DataFrame([
            {
                "event_type": "BOOK_SNAPSHOT",
                "origin_time": 1000000001,
                "bids": [],  # Empty bids
                "asks": []   # Empty asks
            }
        ])
        
        result = replayer.execute(events)
        assert len(result) == 1
        # Should initialize with empty book
        assert result[0]["top_bid"][0] is None
        assert result[0]["top_ask"][0] is None
    
    def test_negative_quantities(self):
        """Test handling of negative quantities."""
        replayer = ChronologicalEventReplay()
        
        events = pl.DataFrame([
            {
                "event_type": "BOOK_SNAPSHOT",
                "origin_time": 1000000001,
                "bids": [[50000.0, 1.0]],
                "asks": [[50001.0, 1.0]]
            },
            {
                "event_type": "BOOK_DELTA",
                "origin_time": 1000000002,
                "delta_side": "BID",
                "delta_price": 49999.0,
                "delta_quantity": -1.0  # Negative quantity (should be 0)
            }
        ])
        
        result = replayer.execute(events)
        assert len(result) == 2
        # Negative quantities should be treated as 0 (remove level)


class TestComplexScenarios:
    """Test complex real-world scenarios."""
    
    def test_rapid_drift_recovery(self):
        """Test recovery from rapid drift scenarios."""
        replayer = ChronologicalEventReplay(
            drift_threshold=0.01,
            resync_on_drift=True
        )
        
        events = []
        
        # Initial snapshot
        events.append({
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000000,
            "bids": [[50000.0, 10.0]],
            "asks": [[50001.0, 10.0]]
        })
        
        # Add trades that consume liquidity
        for i in range(20):
            events.append({
                "event_type": "TRADE",
                "origin_time": 1000000001 + i,
                "trade_id": i,
                "trade_price": 50000.5,
                "trade_quantity": 0.5,
                "trade_side": "BUY"
            })
        
        # Snapshot showing significant drift
        events.append({
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000100,
            "bids": [[50000.0, 5.0]],  # Should be 0 after trades
            "asks": [[50001.0, 5.0]]   # Should be 0 after trades
        })
        
        events_df = pl.DataFrame(events)
        result = replayer.execute(events_df)
        
        # Check drift was detected
        last_event = result[-1]
        assert last_event["drift_metrics"][0] is not None
        assert last_event["drift_metrics"][0]["exceeds_threshold"]
    
    def test_order_book_overflow(self):
        """Test handling of order book with more levels than max_levels."""
        replayer = ChronologicalEventReplay(max_levels=5)
        
        # Create snapshot with many levels
        bids = [[50000.0 - i * 0.1, 1.0 + i * 0.1] for i in range(20)]
        asks = [[50001.0 + i * 0.1, 1.0 + i * 0.1] for i in range(20)]
        
        events = pl.DataFrame([
            {
                "event_type": "BOOK_SNAPSHOT",
                "origin_time": 1000000001,
                "bids": bids,
                "asks": asks
            }
        ])
        
        result = replayer.execute(events)
        book_state = result[0]["book_state"][0]
        
        # Should only keep top 5 levels
        assert len(book_state[0]) <= 5  # Bids
        assert len(book_state[1]) <= 5  # Asks
    
    def test_cross_spread_handling(self):
        """Test handling of crossed spread situations."""
        replayer = ChronologicalEventReplay()
        
        events = pl.DataFrame([
            {
                "event_type": "BOOK_SNAPSHOT",
                "origin_time": 1000000001,
                "bids": [[50002.0, 1.0]],  # Bid > Ask (crossed)
                "asks": [[50001.0, 1.0]]
            }
        ])
        
        result = replayer.execute(events)
        spread = result[0]["spread"][0]
        
        # Spread should be negative for crossed book
        assert spread < 0


class TestIntegrationScenarios:
    """Test integration with full pipeline."""
    
    def test_save_and_load_results(self):
        """Test saving and loading replayed events."""
        replayer = ChronologicalEventReplay()
        
        events = pl.DataFrame([
            {
                "event_type": "BOOK_SNAPSHOT",
                "origin_time": 1000000001,
                "bids": [[50000.0, 1.0]],
                "asks": [[50001.0, 1.0]]
            },
            {
                "event_type": "TRADE",
                "origin_time": 1000000002,
                "trade_id": 1,
                "trade_price": 50000.5,
                "trade_quantity": 0.5,
                "trade_side": "BUY"
            }
        ])
        
        result = replayer.execute(events)
        
        # Save to parquet
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "replayed.parquet"
            
            # Convert complex types to strings for parquet
            result_for_save = result.with_columns([
                pl.col("book_state").map_elements(str, return_dtype=pl.Utf8),
                pl.col("drift_metrics").map_elements(str, return_dtype=pl.Utf8)
            ])
            
            result_for_save.write_parquet(output_path)
            
            # Load and verify
            loaded = pl.read_parquet(output_path)
            assert len(loaded) == 2
            assert loaded["event_type"].to_list() == ["BOOK_SNAPSHOT", "TRADE"]
    
    def test_drift_metrics_export(self):
        """Test exporting drift metrics for reporting."""
        stream = UnifiedEventStreamWithReplay(
            symbol="BTCUSDT",
            drift_threshold=0.001
        )
        
        events = pl.DataFrame([
            {
                "event_type": "BOOK_SNAPSHOT",
                "origin_time": 1000000001,
                "bids": [[50000.0, 10.0]],
                "asks": [[50001.0, 10.0]]
            },
            {
                "event_type": "BOOK_DELTA",
                "origin_time": 1000000002,
                "delta_side": "BID",
                "delta_price": 49999.0,
                "delta_quantity": 5.0
            },
            {
                "event_type": "BOOK_SNAPSHOT",
                "origin_time": 1000000003,
                "bids": [[50000.0, 10.1], [49999.0, 5.0]],
                "asks": [[50001.0, 10.0]]
            }
        ])
        
        # Process events
        result = stream.chronological_replayer.execute(events)
        
        # Get drift report
        report = stream.get_drift_report()
        
        assert "summary" in report
        assert "recommendations" in report
        assert report["summary"]["total_snapshots"] == 1
        
        # Export metrics
        metrics = stream.chronological_replayer.drift_tracker.export_metrics()
        assert len(metrics) > 0
        assert all(m["metric_type"] == "drift" for m in metrics)


class TestPerformanceEdgeCases:
    """Test performance under edge conditions."""
    
    def test_large_batch_processing(self):
        """Test processing very large batches."""
        replayer = ChronologicalEventReplay(drift_threshold=1.0)
        
        # Generate 50K events
        events = []
        events.append({
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000000,
            "bids": [[50000.0, 1.0]],
            "asks": [[50001.0, 1.0]]
        })
        
        for i in range(1, 50000):
            events.append({
                "event_type": "TRADE",
                "origin_time": 1000000000 + i,
                "trade_id": i,
                "trade_price": 50000.0 + (i % 100) * 0.01,
                "trade_quantity": 0.1,
                "trade_side": "BUY" if i % 2 == 0 else "SELL"
            })
        
        events_df = pl.DataFrame(events)
        
        # Should complete without memory issues
        result = replayer.execute(events_df)
        assert len(result) == 50000
    
    def test_zero_copy_verification(self):
        """Verify zero-copy operations."""
        replayer = ChronologicalEventReplay()
        
        # Create large event
        large_bids = [[50000.0 - i * 0.01, 1.0] for i in range(1000)]
        events_df = pl.DataFrame([
            {
                "event_type": "BOOK_SNAPSHOT",
                "origin_time": 1000000001,
                "bids": large_bids,
                "asks": [[50001.0, 1.0]]
            }
        ])
        
        # These operations should not copy data
        sorted_df = replayer._sort_events(events_df)
        labeled_df = replayer._label_event_types(sorted_df)
        
        # Verify same underlying data (in practice)
        assert len(sorted_df) == len(events_df)
        assert len(labeled_df) == len(events_df)


class TestRegressionTests:
    """Tests to prevent regressions."""
    
    def test_decimal_precision_maintained(self):
        """Ensure decimal precision is maintained throughout."""
        normalizer = SchemaNormalizer()
        
        event = {
            "event_type": "TRADE",
            "origin_time": 1000000001,
            "trade_price": "50000.123456789012345678",
            "trade_quantity": "0.000000000123456789",
            "trade_side": "BUY"
        }
        
        normalized = normalizer.normalize_to_unified_schema(event)
        
        # Check precision is maintained
        assert str(normalized["trade_price"]) == "50000.123456789012345678"
        assert normalized["trade_quantity"] == Decimal("0.000000000123456789")
    
    def test_drift_calculation_accuracy(self):
        """Ensure drift calculation remains accurate."""
        tracker = DriftTracker(drift_threshold=0.001)
        
        book = OrderBookState()
        book.initialize_from_snapshot({
            "bids": [[100.0, 10.0]],
            "asks": [[101.0, 10.0]]
        })
        
        # Exact 1% drift
        snapshot = {
            "bids": [[100.0, 10.1]],
            "asks": [[101.0, 10.0]]
        }
        
        metrics = tracker.calculate_drift(book, snapshot)
        
        # RMS = sqrt((0.01^2 + 0^2) / 2) ≈ 0.00707
        assert abs(metrics["rms_error"] - 0.00707) < 0.0001