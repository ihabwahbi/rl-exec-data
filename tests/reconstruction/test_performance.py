"""
Performance tests for the reconstruction pipeline.

Tests throughput, memory usage, and performance baselines.
"""
import pytest
from pathlib import Path
import time
import tempfile

import polars as pl
import numpy as np

from rlx_datapipe.reconstruction.data_ingestion import TradesReader
from rlx_datapipe.reconstruction.unification import UnifiedEventStream
from rlx_datapipe.reconstruction.performance import PerformanceBenchmark
from rlx_datapipe.reconstruction.optimized_readers import OptimizedTradesReader


class TestPerformanceBenchmarks:
    """Test performance against established baselines."""
    
    @pytest.fixture
    def large_trades_file(self, tmp_path):
        """Create a large trades file for performance testing."""
        # Create 1M trades (similar to validated baseline)
        n_trades = 1_000_000
        base_time = 1700000000000000000
        
        # Generate data in chunks to avoid memory issues
        chunk_size = 100_000
        chunks = []
        
        for i in range(0, n_trades, chunk_size):
            chunk_end = min(i + chunk_size, n_trades)
            chunk_df = pl.DataFrame({
                "origin_time": [base_time + j * 1000000 for j in range(i, chunk_end)],
                "price": np.random.uniform(40000, 41000, chunk_end - i),
                "quantity": np.random.exponential(0.5, chunk_end - i),
                "side": np.random.choice(["BUY", "SELL"], chunk_end - i),
                "trade_id": range(i + 1, chunk_end + 1)
            })
            chunks.append(chunk_df)
        
        # Combine and write
        trades_df = pl.concat(chunks)
        trades_file = tmp_path / "large_trades.parquet"
        trades_df.write_parquet(trades_file)
        
        return trades_file
    
    def test_reader_throughput(self, large_trades_file):
        """Test that reader meets throughput baseline."""
        benchmark = PerformanceBenchmark()
        reader = TradesReader(large_trades_file)
        
        # Benchmark the reader
        results = benchmark.benchmark_reader(
            reader.read,
            large_trades_file
        )
        
        # Log results
        benchmark.log_results(results, "TradesReader Throughput Test")
        
        # Verify performance
        assert results["total_rows"] == 1_000_000
        assert results["meets_baseline_read_speed"]
        
        # Throughput might be lower due to decimal conversion
        # but should still be reasonable
        assert results["throughput_messages_per_second"] > 100_000
    
    def test_batched_reader_memory(self, large_trades_file):
        """Test that batched reading stays within memory limits."""
        benchmark = PerformanceBenchmark()
        reader = TradesReader(large_trades_file)
        
        # Benchmark batched reading
        results = benchmark.benchmark_reader(
            reader.read,
            large_trades_file,
            batch_size=10_000
        )
        
        # Log results
        benchmark.log_results(results, "Batched Reader Memory Test")
        
        # Verify memory usage
        assert results["meets_memory_limit"]
        assert results["memory_peak_gb"] < 1.0
    
    def test_optimized_reader_performance(self, large_trades_file):
        """Test optimized reader performance."""
        benchmark = PerformanceBenchmark()
        reader = OptimizedTradesReader(large_trades_file)
        
        # Time the optimized reader
        start_time = time.perf_counter()
        total_rows = 0
        
        for batch in reader.read_zero_copy(batch_size=50_000):
            total_rows += len(batch)
        
        end_time = time.perf_counter()
        duration = end_time - start_time
        
        throughput = total_rows / duration
        
        # Should be significantly faster than baseline
        assert throughput > 336_000  # Baseline throughput
        assert total_rows == 1_000_000
    
    @pytest.mark.slow
    def test_sustained_throughput(self, tmp_path):
        """Test sustained throughput over extended period."""
        # Create smaller file for sustained test
        n_trades = 100_000
        base_time = 1700000000000000000
        
        trades_df = pl.DataFrame({
            "origin_time": [base_time + i * 1000000 for i in range(n_trades)],
            "price": np.random.uniform(40000, 41000, n_trades),
            "quantity": np.random.exponential(0.5, n_trades),
            "side": np.random.choice(["BUY", "SELL"], n_trades)
        })
        
        trades_file = tmp_path / "sustained_trades.parquet"
        trades_df.write_parquet(trades_file)
        
        # Run multiple iterations
        benchmark = PerformanceBenchmark()
        throughputs = []
        
        for i in range(5):
            reader = TradesReader(trades_file)
            results = benchmark.benchmark_reader(
                reader.read,
                trades_file
            )
            throughputs.append(results["throughput_messages_per_second"])
        
        # Throughput should be consistent
        avg_throughput = np.mean(throughputs)
        std_throughput = np.std(throughputs)
        cv = std_throughput / avg_throughput  # Coefficient of variation
        
        assert cv < 0.1  # Less than 10% variation
        assert avg_throughput > 100_000
    
    def test_memory_leak_detection(self, tmp_path):
        """Test for memory leaks in repeated processing."""
        import psutil
        import os
        import gc
        
        # Create test data
        trades_df = pl.DataFrame({
            "origin_time": range(10_000),
            "price": np.random.uniform(40000, 41000, 10_000),
            "quantity": np.random.exponential(0.5, 10_000),
            "side": np.random.choice(["BUY", "SELL"], 10_000)
        })
        
        trades_file = tmp_path / "memory_test_trades.parquet"
        trades_df.write_parquet(trades_file)
        
        process = psutil.Process(os.getpid())
        
        # Get baseline after forcing garbage collection
        gc.collect()
        baseline_memory = process.memory_info().rss / (1024 * 1024)  # MB
        
        # Run multiple iterations
        memory_readings = []
        
        for i in range(10):
            reader = TradesReader(trades_file)
            df = reader.read()
            
            # Force cleanup
            del df
            del reader
            gc.collect()
            
            current_memory = process.memory_info().rss / (1024 * 1024)
            memory_readings.append(current_memory)
        
        # Memory should not continuously increase
        memory_increase = memory_readings[-1] - baseline_memory
        assert memory_increase < 50  # Less than 50MB increase
        
        # Check for monotonic increase (indicates leak)
        increasing_count = sum(
            1 for i in range(1, len(memory_readings))
            if memory_readings[i] > memory_readings[i-1]
        )
        
        # Should not continuously increase
        assert increasing_count < len(memory_readings) * 0.7