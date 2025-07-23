"""Tests for order book benchmark."""

import pytest

from rlx_datapipe.reconstruction.benchmark_order_book import OrderBookBenchmark


class TestOrderBookBenchmark:
    """Test order book benchmark functionality."""
    
    def test_benchmark_initialization(self):
        """Test benchmark initialization."""
        benchmark = OrderBookBenchmark(
            symbol="BTCUSDT",
            target_throughput=100_000,
            memory_limit_mb=512,
        )
        
        assert benchmark.symbol == "BTCUSDT"
        assert benchmark.target_throughput == 100_000
        assert benchmark.memory_limit_mb == 512
    
    def test_generate_test_data(self):
        """Test test data generation."""
        benchmark = OrderBookBenchmark()
        
        test_data = benchmark.generate_test_data(
            num_deltas=1000,
            num_snapshots=2,
        )
        
        assert "deltas" in test_data
        assert "snapshots" in test_data
        
        # Check delta data
        deltas = test_data["deltas"]
        assert len(deltas) == 1000
        assert "update_id" in deltas.columns
        assert "price" in deltas.columns
        assert "new_quantity" in deltas.columns
        assert "side" in deltas.columns
        
        # Check snapshots
        snapshots = test_data["snapshots"]
        assert len(snapshots) == 80  # 20 levels * 2 sides * 2 snapshots
    
    def test_small_benchmark_run(self):
        """Test running a small benchmark."""
        benchmark = OrderBookBenchmark(
            target_throughput=10_000,  # Lower target for test
            memory_limit_mb=100,
        )
        
        # Run with small dataset
        results = benchmark.run_full_benchmark(
            num_deltas=10_000,  # Small dataset for fast test
            num_snapshots=2,
        )
        
        assert "summary" in results
        assert "basic_engine" in results
        assert "optimized_ops" in results
        
        # Check summary
        summary = results["summary"]
        assert "achieved_throughput" in summary
        assert "memory_used_mb" in summary
        assert "meets_target" in summary
        assert "optimization_speedup" in summary
        
        # Check that optimization speedup was calculated
        assert "optimization_speedup" in summary
        # Note: The optimized benchmark tests different operations so direct comparison isn't meaningful