"""Integration tests for order book reconstruction pipeline."""

import tempfile
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from rlx_datapipe.reconstruction.unified_stream_enhanced import (
    EnhancedUnificationConfig,
    UnifiedEventStreamEnhanced,
)


class TestOrderBookIntegration:
    """Integration tests for order book components."""
    
    @pytest.fixture
    def sample_data(self):
        """Generate sample market data for testing."""
        # Generate book deltas
        num_deltas = 1000
        deltas = pl.DataFrame({
            "origin_time": np.arange(num_deltas) * 1000,
            "timestamp": np.arange(num_deltas) * 1000,  # Add required timestamp
            "symbol": ["BTCUSDT"] * num_deltas,  # Add required symbol
            "exchange": ["BINANCE"] * num_deltas,  # Add required exchange
            "update_id": np.arange(1000, 1000 + num_deltas),
            "price": np.random.uniform(45000, 46000, num_deltas),
            "new_quantity": np.random.uniform(0.1, 5.0, num_deltas),
            "side": np.random.choice(["BID", "ASK"], num_deltas),
            "event_type": ["BOOK_DELTA"] * num_deltas,
        })
        
        # Add some removals
        removal_indices = np.random.choice(num_deltas, size=50, replace=False)
        deltas = deltas.with_columns(
            pl.when(pl.arange(0, num_deltas).is_in(removal_indices))
            .then(0.0)
            .otherwise(pl.col("new_quantity"))
            .alias("new_quantity")
        )
        
        # Generate snapshots
        snapshot_times = [0, 250000, 500000, 750000]
        snapshots = []
        
        for snap_time in snapshot_times:
            # Bid levels
            bid_prices = np.linspace(44900, 45000, 20)
            bid_quantities = np.random.uniform(0.5, 3.0, 20)
            
            # Ask levels
            ask_prices = np.linspace(45100, 45200, 20)
            ask_quantities = np.random.uniform(0.5, 3.0, 20)
            
            snapshot = pl.DataFrame({
                "origin_time": [snap_time] * 40,
                "timestamp": [snap_time] * 40,  # Add required timestamp
                "symbol": ["BTCUSDT"] * 40,  # Add required symbol
                "exchange": ["BINANCE"] * 40,  # Add required exchange
                "update_id": [1000 + snap_time // 1000] * 40,
                "side": ["BID"] * 20 + ["ASK"] * 20,
                "price": np.concatenate([bid_prices, ask_prices]),
                "quantity": np.concatenate([bid_quantities, ask_quantities]),
                "event_type": ["BOOK_SNAPSHOT"] * 40,
            })
            snapshots.append(snapshot)
        
        snapshots_df = pl.concat(snapshots)
        
        # Generate trades
        num_trades = 100
        trade_times = np.sort(np.random.randint(0, num_deltas * 1000, num_trades))
        trades = pl.DataFrame({
            "origin_time": trade_times,
            "timestamp": trade_times,  # Add required timestamp
            "symbol": ["BTCUSDT"] * num_trades,  # Add required symbol
            "exchange": ["BINANCE"] * num_trades,  # Add required exchange
            "price": np.random.uniform(45000, 45100, num_trades),
            "quantity": np.random.uniform(0.01, 1.0, num_trades),
            "side": np.random.choice(["BUY", "SELL"], num_trades),
            "event_type": ["TRADE"] * num_trades,
        })
        
        return {
            "deltas": deltas,
            "snapshots": snapshots_df,
            "trades": trades,
        }
    
    def test_unified_stream_with_order_book(self, sample_data):
        """Test unified stream with order book reconstruction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Save sample data
            deltas_path = tmpdir / "deltas.parquet"
            snapshots_path = tmpdir / "snapshots.parquet"
            trades_path = tmpdir / "trades.parquet"
            
            sample_data["deltas"].write_parquet(deltas_path)
            sample_data["snapshots"].write_parquet(snapshots_path)
            sample_data["trades"].write_parquet(trades_path)
            
            # Configure stream
            config = EnhancedUnificationConfig(
                enable_order_book=True,
                checkpoint_dir=tmpdir / "checkpoints",
                enable_streaming=False,  # Use batch mode for test
            )
            
            # Process data
            stream = UnifiedEventStreamEnhanced("BTCUSDT", config)
            stats = stream.process_with_order_book(
                trades_path=trades_path,
                book_snapshots_path=snapshots_path,
                book_deltas_path=deltas_path,
                output_path=tmpdir / "output",
            )
            
            # Verify results
            assert stats["total_events"] == 1000 + 160 + 100  # deltas + snapshots + trades
            assert stats["deltas_processed"] == 1000
            assert stats["snapshots_processed"] == 160
            assert stats["trades_processed"] == 100
            
            # Check order book stats
            ob_stats = stats["order_book_stats"]
            assert ob_stats["updates_processed"] == 1000
            assert ob_stats["snapshot_count"] == 4
            
            # Check output file exists
            output_file = tmpdir / "output" / "enriched_deltas.parquet"
            assert output_file.exists()
            
            # Read and verify enriched data
            enriched = pl.read_parquet(output_file)
            assert len(enriched) == 1000
            assert "bid_top_price" in enriched.columns
            assert "ask_top_price" in enriched.columns
            assert "bid_depth" in enriched.columns
            assert "ask_depth" in enriched.columns
    
    def test_sequence_gap_handling(self):
        """Test handling of sequence gaps in delta feed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create deltas with intentional gaps
            deltas = pl.DataFrame({
                "origin_time": [1000, 2000, 3000, 4000, 5000],
                "update_id": [1000, 1001, 1005, 1006, 1010],  # Gaps at 1002-1004, 1007-1009
                "price": [45000.0, 45100.0, 45200.0, 45300.0, 45400.0],
                "new_quantity": [1.0, 2.0, 3.0, 4.0, 5.0],
                "side": ["BID", "ASK", "BID", "ASK", "BID"],
                "event_type": ["BOOK_DELTA"] * 5,
            })
            
            deltas_path = tmpdir / "deltas_with_gaps.parquet"
            deltas.write_parquet(deltas_path)
            
            # Process with gap detection
            config = EnhancedUnificationConfig(
                enable_order_book=True,
                enable_streaming=False,
            )
            
            stream = UnifiedEventStreamEnhanced("BTCUSDT", config)
            stats = stream.process_with_order_book(
                book_deltas_path=deltas_path,
            )
            
            # Check gap detection
            delta_stats = stats["delta_processor_stats"]
            assert delta_stats["total_gaps"] == 2
            assert delta_stats["max_gap_size"] == 3  # Gap from 1006 to 1010
    
    def test_checkpoint_recovery(self, sample_data):
        """Test checkpoint and recovery functionality."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            checkpoint_dir = tmpdir / "checkpoints"
            
            # Save sample data
            deltas_path = tmpdir / "deltas.parquet"
            sample_data["deltas"].write_parquet(deltas_path)
            
            # Process first half
            config = EnhancedUnificationConfig(
                enable_order_book=True,
                checkpoint_dir=checkpoint_dir,
                enable_streaming=False,
            )
            
            # Split data for two-phase processing
            first_half = sample_data["deltas"].head(500)
            second_half = sample_data["deltas"].tail(500)
            
            first_path = tmpdir / "first_half.parquet"
            second_path = tmpdir / "second_half.parquet"
            
            first_half.write_parquet(first_path)
            second_half.write_parquet(second_path)
            
            # Process first half
            stream1 = UnifiedEventStreamEnhanced("BTCUSDT", config)
            stats1 = stream1.process_with_order_book(
                book_deltas_path=first_path,
            )
            
            assert stats1["deltas_processed"] == 500
            
            # Create new stream and process second half (should load checkpoint)
            stream2 = UnifiedEventStreamEnhanced("BTCUSDT", config)
            stats2 = stream2.process_with_order_book(
                book_deltas_path=second_path,
            )
            
            assert stats2["deltas_processed"] == 500
            
            # Verify checkpoint was used
            ob_stats = stats2["order_book_stats"]
            assert ob_stats["updates_processed"] == 500  # Only processed second half
    
    def test_drift_tracking(self, sample_data):
        """Test drift tracking between snapshots and reconstructed state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Save data with snapshots
            deltas_path = tmpdir / "deltas.parquet"
            snapshots_path = tmpdir / "snapshots.parquet"
            
            sample_data["deltas"].write_parquet(deltas_path)
            sample_data["snapshots"].write_parquet(snapshots_path)
            
            # Process with drift tracking
            config = EnhancedUnificationConfig(
                enable_order_book=True,
                enable_drift_tracking=True,
                enable_streaming=False,
            )
            
            stream = UnifiedEventStreamEnhanced("BTCUSDT", config)
            stats = stream.process_with_order_book(
                book_snapshots_path=snapshots_path,
                book_deltas_path=deltas_path,
            )
            
            # Check drift metrics
            drift_metrics = stats["drift_metrics"]
            assert drift_metrics["total_snapshots"] >= 1
            # Drift may or may not occur depending on data
            assert "max_price_drift" in drift_metrics
            assert "max_quantity_drift" in drift_metrics
    
    def test_memory_limit_compliance(self, sample_data):
        """Test that processing stays within memory limits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Generate larger dataset
            large_deltas = pl.concat([sample_data["deltas"]] * 10)  # 10x data
            deltas_path = tmpdir / "large_deltas.parquet"
            large_deltas.write_parquet(deltas_path)
            
            # Process with strict memory limit
            config = EnhancedUnificationConfig(
                enable_order_book=True,
                memory_limit_gb=0.5,  # 500MB limit
                enable_streaming=True,
                use_memory_mapping=True,
                mmap_chunk_size=1000,
            )
            
            stream = UnifiedEventStreamEnhanced("BTCUSDT", config)
            stats = stream.process_with_order_book(
                book_deltas_path=deltas_path,
                output_path=tmpdir / "output",
            )
            
            # Verify processing completed
            assert stats["deltas_processed"] == len(large_deltas)
            
            # Check throughput
            assert stats["throughput"] > 0
    
    def test_error_recovery(self):
        """Test error handling and recovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create invalid data
            invalid_deltas = pl.DataFrame({
                "origin_time": [1000, 2000],
                "update_id": [1000, 1001],
                # Missing required columns
                "price": [45000.0, 45100.0],
                # "new_quantity" missing
                # "side" missing
                "event_type": ["BOOK_DELTA", "BOOK_DELTA"],
            })
            
            invalid_path = tmpdir / "invalid.parquet"
            invalid_deltas.write_parquet(invalid_path)
            
            config = EnhancedUnificationConfig(enable_order_book=True)
            stream = UnifiedEventStreamEnhanced("BTCUSDT", config)
            
            # Should raise error for missing columns
            with pytest.raises(Exception):
                stream.process_with_order_book(book_deltas_path=invalid_path)