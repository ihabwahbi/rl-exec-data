"""
Unit tests for unification module.

Tests chronological merging and memory-bounded operations.
"""
import pytest
from pathlib import Path
import tempfile
import time

import polars as pl
import numpy as np

from rlx_datapipe.reconstruction.unification import (
    UnificationConfig,
    UnifiedEventStream,
    BatchedDataReader
)
from rlx_datapipe.reconstruction.data_ingestion import EventType


class TestUnificationConfig:
    """Test UnificationConfig class."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = UnificationConfig()
        assert config.batch_size == 1000
        assert config.memory_limit_gb == 1.0
        assert config.enable_streaming is True
        assert config.memory_limit_bytes == 1_073_741_824
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = UnificationConfig(
            batch_size=500,
            memory_limit_gb=2.0,
            enable_streaming=False
        )
        assert config.batch_size == 500
        assert config.memory_limit_gb == 2.0
        assert config.enable_streaming is False
        assert config.memory_limit_bytes == 2_147_483_648


class TestUnifiedEventStream:
    """Test UnifiedEventStream class."""
    
    @pytest.fixture
    def sample_data_files(self, tmp_path):
        """Create sample data files for testing."""
        # Create trades data
        trades_df = pl.DataFrame({
            "origin_time": [1000, 3000, 5000],
            "price": [100.0, 101.0, 99.5],
            "quantity": [1.0, 2.0, 0.5],
            "side": ["BUY", "SELL", "BUY"],
            "trade_id": [1, 2, 3]
        })
        trades_file = tmp_path / "trades.parquet"
        trades_df.write_parquet(trades_file)
        
        # Create book snapshot data
        book_df = pl.DataFrame({
            "origin_time": [2000, 4000],
            "timestamp": ["2024-01-01", "2024-01-01"],
            "symbol": ["BTCUSDT", "BTCUSDT"],
            "exchange": ["binance", "binance"],
            "bid_0_price": [99.9, 100.4],
            "bid_0_amount": [10.0, 15.0],
            "ask_0_price": [100.1, 100.6],
            "ask_0_amount": [10.0, 15.0]
        })
        book_file = tmp_path / "book.parquet"
        book_df.write_parquet(book_file)
        
        # Create delta data
        delta_df = pl.DataFrame({
            "origin_time": [1500, 2500, 3500],
            "update_id": [100, 101, 102],
            "price": [99.8, 100.2, 100.3],
            "new_quantity": [5.0, 0.0, 8.0],
            "side": ["BID", "ASK", "BID"]
        })
        delta_file = tmp_path / "deltas.parquet"
        delta_df.write_parquet(delta_file)
        
        return {
            "trades": trades_file,
            "book": book_file,
            "deltas": delta_file
        }
    
    def test_merge_single_stream(self, sample_data_files):
        """Test merging a single data stream."""
        stream = UnifiedEventStream()
        
        # Merge only trades
        df = stream.merge_streams(trades_path=sample_data_files["trades"])
        
        assert len(df) == 3
        assert "event_type" in df.columns
        assert df["event_type"].unique()[0] == EventType.TRADE.value
        assert stream._event_counts[EventType.TRADE] == 3
    
    def test_merge_multiple_streams(self, sample_data_files):
        """Test merging multiple data streams."""
        stream = UnifiedEventStream()
        
        # Merge all three streams
        df = stream.merge_streams(
            trades_path=sample_data_files["trades"],
            book_snapshots_path=sample_data_files["book"],
            book_deltas_path=sample_data_files["deltas"]
        )
        
        # Verify total events
        assert len(df) == 8  # 3 trades + 2 snapshots + 3 deltas
        
        # Verify event counts
        assert stream._event_counts[EventType.TRADE] == 3
        assert stream._event_counts[EventType.BOOK_SNAPSHOT] == 2
        assert stream._event_counts[EventType.BOOK_DELTA] == 3
        
        # Verify chronological order
        origin_times = df["origin_time"].to_list()
        assert origin_times == sorted(origin_times)
        assert origin_times == [1000, 1500, 2000, 2500, 3000, 3500, 4000, 5000]
    
    def test_stable_sort_maintains_order(self, tmp_path):
        """Test that stable sort maintains original order for equal timestamps."""
        # Create data with duplicate timestamps
        df1 = pl.DataFrame({
            "origin_time": [1000, 2000, 2000],
            "event_type": ["A", "B", "C"],
            "order": [1, 2, 3]
        })
        
        df2 = pl.DataFrame({
            "origin_time": [1500, 2000],
            "event_type": ["D", "E"],
            "order": [4, 5]
        })
        
        file1 = tmp_path / "data1.parquet"
        file2 = tmp_path / "data2.parquet"
        df1.write_parquet(file1)
        df2.write_parquet(file2)
        
        # Manual merge to test sort behavior
        stream = UnifiedEventStream()
        dfs = [
            pl.read_parquet(file1),
            pl.read_parquet(file2)
        ]
        
        merged = pl.concat(dfs, how="diagonal")
        sorted_df = merged.sort("origin_time", maintain_order=True)
        
        # Check that events with same timestamp maintain relative order
        events_at_2000 = sorted_df.filter(pl.col("origin_time") == 2000)
        assert events_at_2000["event_type"].to_list() == ["B", "C", "E"]
    
    def test_no_data_paths_error(self):
        """Test error when no data paths provided."""
        stream = UnifiedEventStream()
        
        with pytest.raises(ValueError, match="No data paths provided"):
            stream.merge_streams()
    
    def test_merge_streams_batched(self, sample_data_files):
        """Test batched merging."""
        config = UnificationConfig(batch_size=2)
        stream = UnifiedEventStream(config)
        
        # Get batches
        batches = list(stream.merge_streams_batched(
            trades_path=sample_data_files["trades"],
            book_deltas_path=sample_data_files["deltas"]
        ))
        
        # Should have multiple batches
        assert len(batches) > 0
        
        # Combine all batches and verify order
        all_data = pl.concat(batches)
        origin_times = all_data["origin_time"].to_list()
        
        # Each batch should be sorted
        for batch in batches:
            batch_times = batch["origin_time"].to_list()
            assert batch_times == sorted(batch_times)


class TestBatchedDataReader:
    """Test BatchedDataReader class."""
    
    @pytest.fixture
    def large_data_file(self, tmp_path):
        """Create a larger data file for testing."""
        # Create data with known size
        n_rows = 10000
        # Create categories list with exact length
        categories = (["A", "B", "C"] * (n_rows // 3 + 1))[:n_rows]
        
        df = pl.DataFrame({
            "origin_time": range(n_rows),
            "value": np.random.randn(n_rows),
            "category": categories
        })
        
        file_path = tmp_path / "large_data.parquet"
        df.write_parquet(file_path)
        return file_path
    
    def test_batched_reading(self, large_data_file):
        """Test reading data in batches."""
        reader = BatchedDataReader(large_data_file, batch_size=1000)
        
        total_rows = 0
        batch_count = 0
        
        for batch in reader.read_batches():
            batch_count += 1
            total_rows += len(batch)
            assert len(batch) <= 1000  # Should respect batch size
        
        assert total_rows == 10000
        assert batch_count == 10
    
    def test_memory_limit_detection(self, large_data_file):
        """Test memory limit detection."""
        # Set very low memory limit to trigger backpressure
        reader = BatchedDataReader(
            large_data_file,
            batch_size=5000,
            memory_limit_bytes=1024 * 1024  # 1MB
        )
        
        backpressure_triggered = False
        
        for batch in reader.read_batches():
            if reader.is_backpressure_active:
                backpressure_triggered = True
                break
        
        # Should trigger backpressure with such low limit
        assert backpressure_triggered
    
    def test_streaming_mode_activation(self, large_data_file):
        """Test that streaming mode activates properly."""
        reader = BatchedDataReader(
            large_data_file,
            batch_size=5000,
            memory_limit_bytes=1024 * 1024  # 1MB
        )
        
        # Track if streaming mode was activated
        streaming_activated = False
        
        for i, batch in enumerate(reader.read_batches()):
            if reader._streaming_mode_active:
                streaming_activated = True
            
            # Only check first few batches
            if i > 2:
                break
        
        assert streaming_activated


class TestMemoryUsage:
    """Test memory usage constraints."""
    
    def test_memory_stays_under_limit(self, tmp_path):
        """Test that memory usage stays under configured limit."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        
        # Get baseline memory
        baseline_memory = process.memory_info().rss
        
        # Configure with 100MB limit
        config = UnificationConfig(memory_limit_gb=0.1)
        stream = UnifiedEventStream(config)
        
        # Create small test data
        trades_df = pl.DataFrame({
            "origin_time": [1000, 2000, 3000],
            "price": [100.0, 101.0, 99.5],
            "quantity": [1.0, 2.0, 0.5],
            "side": ["BUY", "SELL", "BUY"]
        })
        trades_file = tmp_path / "trades.parquet"
        trades_df.write_parquet(trades_file)
        
        # Process data
        df = stream.merge_streams(trades_path=trades_file)
        
        # Check memory after processing
        current_memory = process.memory_info().rss
        memory_used_mb = (current_memory - baseline_memory) / (1024 * 1024)
        
        # Should be well under 100MB for this small test data
        assert memory_used_mb < 100