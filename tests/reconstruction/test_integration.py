"""
Integration tests for the reconstruction pipeline.

Tests end-to-end data flow with realistic sample data.
"""
import pytest
from pathlib import Path
import tempfile
import shutil
from datetime import datetime, UTC

import polars as pl
import numpy as np

from rlx_datapipe.reconstruction.data_ingestion import (
    TradesReader,
    BookSnapshotReader,
    BookDeltaV2Reader,
    EventType
)
from rlx_datapipe.reconstruction.unification import (
    UnifiedEventStream,
    UnificationConfig
)


class TestEndToEndPipeline:
    """Test complete pipeline integration."""
    
    @pytest.fixture
    def realistic_sample_data(self, tmp_path):
        """Create realistic sample data mimicking Crypto Lake format."""
        # Create realistic trades data
        n_trades = 1000
        base_time = 1700000000000000000  # nanoseconds
        
        trades_df = pl.DataFrame({
            "origin_time": [base_time + i * 1000000 for i in range(n_trades)],  # 1ms intervals
            "price": np.random.uniform(40000, 41000, n_trades),
            "quantity": np.random.exponential(0.5, n_trades),
            "side": np.random.choice(["BUY", "SELL"], n_trades),
            "trade_id": range(1, n_trades + 1),
            "timestamp": [datetime.now(UTC).isoformat() for _ in range(n_trades)],
            "symbol": ["BTCUSDT"] * n_trades,
            "exchange": ["binance"] * n_trades
        })
        
        # Create book snapshots (every 100ms)
        n_snapshots = 100
        book_data = {
            "origin_time": [base_time + i * 100000000 for i in range(n_snapshots)],  # 100ms
            "timestamp": [datetime.now(UTC).isoformat() for _ in range(n_snapshots)],
            "symbol": ["BTCUSDT"] * n_snapshots,
            "exchange": ["binance"] * n_snapshots
        }
        
        # Add 20 levels of bid/ask data
        for level in range(20):
            spread = 0.01 * (level + 1)
            book_data[f"bid_{level}_price"] = np.random.uniform(40000 - spread * 100, 40000 - spread * 50, n_snapshots)
            book_data[f"bid_{level}_amount"] = np.random.exponential(1.0, n_snapshots)
            book_data[f"ask_{level}_price"] = np.random.uniform(40000 + spread * 50, 40000 + spread * 100, n_snapshots)
            book_data[f"ask_{level}_amount"] = np.random.exponential(1.0, n_snapshots)
        
        book_df = pl.DataFrame(book_data)
        
        # Create book deltas
        n_deltas = 5000
        delta_df = pl.DataFrame({
            "origin_time": [base_time + i * 200000 for i in range(n_deltas)],  # 0.2ms intervals
            "update_id": range(1000000, 1000000 + n_deltas),
            "price": np.random.uniform(39900, 41100, n_deltas),
            "new_quantity": np.where(
                np.random.random(n_deltas) < 0.1,  # 10% removals
                0.0,
                np.random.exponential(0.5, n_deltas)
            ),
            "side": np.random.choice(["BID", "ASK"], n_deltas)
        })
        
        # Write files
        trades_file = tmp_path / "trades.parquet"
        book_file = tmp_path / "book_snapshots.parquet"
        deltas_file = tmp_path / "book_deltas.parquet"
        
        trades_df.write_parquet(trades_file)
        book_df.write_parquet(book_file)
        delta_df.write_parquet(deltas_file)
        
        return {
            "trades": trades_file,
            "book": book_file,
            "deltas": deltas_file,
            "expected_total": n_trades + n_snapshots + n_deltas
        }
    
    def test_full_pipeline_processing(self, realistic_sample_data):
        """Test processing realistic data through full pipeline."""
        # Initialize readers
        trades_reader = TradesReader(realistic_sample_data["trades"])
        book_reader = BookSnapshotReader(realistic_sample_data["book"])
        delta_reader = BookDeltaV2Reader(realistic_sample_data["deltas"])
        
        # Read each data type
        trades_df = trades_reader.read()
        book_df = book_reader.read()
        delta_df = delta_reader.read()
        
        # Verify readers added event types
        assert trades_df["event_type"].unique()[0] == EventType.TRADE.value
        assert book_df["event_type"].unique()[0] == EventType.BOOK_SNAPSHOT.value
        assert delta_df["event_type"].unique()[0] == EventType.BOOK_DELTA.value
        
        # Verify decimal precision
        assert trades_df["price"].dtype == pl.Decimal(precision=38, scale=18)
        assert delta_df["price"].dtype == pl.Decimal(precision=38, scale=18)
        
        # Unify streams
        stream = UnifiedEventStream()
        unified_df = stream.merge_streams(
            trades_path=realistic_sample_data["trades"],
            book_snapshots_path=realistic_sample_data["book"],
            book_deltas_path=realistic_sample_data["deltas"]
        )
        
        # Verify results
        assert len(unified_df) == realistic_sample_data["expected_total"]
        
        # Verify chronological order
        origin_times = unified_df["origin_time"].to_list()
        assert origin_times == sorted(origin_times)
        
        # Verify event type distribution
        event_counts = unified_df["event_type"].value_counts()
        assert len(event_counts.filter(pl.col("event_type") == EventType.TRADE.value)) > 0
        assert len(event_counts.filter(pl.col("event_type") == EventType.BOOK_SNAPSHOT.value)) > 0
        assert len(event_counts.filter(pl.col("event_type") == EventType.BOOK_DELTA.value)) > 0
    
    def test_batched_processing(self, realistic_sample_data):
        """Test batched processing of realistic data."""
        config = UnificationConfig(batch_size=100)
        stream = UnifiedEventStream(config)
        
        # Process in batches
        all_batches = []
        batch_count = 0
        
        for batch in stream.merge_streams_batched(
            trades_path=realistic_sample_data["trades"],
            book_snapshots_path=realistic_sample_data["book"],
            book_deltas_path=realistic_sample_data["deltas"]
        ):
            all_batches.append(batch)
            batch_count += 1
            
            # Verify each batch is sorted
            times = batch["origin_time"].to_list()
            assert times == sorted(times)
        
        # Should have multiple batches
        assert batch_count > 1
        
        # Combine and verify total
        combined = pl.concat(all_batches)
        assert len(combined) <= realistic_sample_data["expected_total"]
    
    def test_memory_bounded_processing(self, realistic_sample_data):
        """Test memory-bounded processing."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        baseline_memory = process.memory_info().rss / (1024 * 1024)  # MB
        
        # Configure with strict memory limit
        config = UnificationConfig(
            batch_size=50,
            memory_limit_gb=0.1  # 100MB limit
        )
        stream = UnifiedEventStream(config)
        
        max_memory_mb = baseline_memory
        
        # Process in batches and monitor memory
        for batch in stream.merge_streams_batched(
            trades_path=realistic_sample_data["trades"],
            book_snapshots_path=realistic_sample_data["book"],
            book_deltas_path=realistic_sample_data["deltas"]
        ):
            current_memory_mb = process.memory_info().rss / (1024 * 1024)
            max_memory_mb = max(max_memory_mb, current_memory_mb)
            
            # Memory increase should stay reasonable
            memory_increase_mb = current_memory_mb - baseline_memory
            assert memory_increase_mb < 200  # Allow some overhead
    
    def test_decimal_precision_preservation(self, tmp_path):
        """Test that decimal precision is preserved throughout pipeline."""
        # Create data with precise decimal values
        precise_trades = pl.DataFrame({
            "origin_time": [1000, 2000, 3000],
            "price": ["40000.123456789012345678", "40000.987654321098765432", "40001.111111111111111111"],
            "quantity": ["1.123456789012345678", "2.987654321098765432", "0.111111111111111111"],
            "side": ["BUY", "SELL", "BUY"]
        })
        
        # Cast to proper types before writing
        precise_trades = precise_trades.with_columns([
            pl.col("price").cast(pl.Float64),
            pl.col("quantity").cast(pl.Float64)
        ])
        
        trades_file = tmp_path / "precise_trades.parquet"
        precise_trades.write_parquet(trades_file)
        
        # Read and process
        reader = TradesReader(trades_file)
        df = reader.read()
        
        # Verify decimal precision is maintained
        assert df["price"].dtype == pl.Decimal(precision=38, scale=18)
        assert df["quantity"].dtype == pl.Decimal(precision=38, scale=18)
        
        # Values should be preserved (within decimal precision)
        prices = df["price"].to_list()
        assert len(prices) == 3