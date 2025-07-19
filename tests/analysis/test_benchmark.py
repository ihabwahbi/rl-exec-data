"""
Tests for performance benchmark harness.
"""

import pytest
import tempfile
import json
from pathlib import Path
import polars as pl

from rlx_datapipe.analysis.delta_analyzer import create_sample_delta_data
from scripts.bench_replay import PerformanceHarness, PerformanceMetrics, OrderBookEngine


class TestOrderBookEngine:
    """Test the OrderBookEngine class."""
    
    def test_order_book_initialization(self):
        """Test order book initialization."""
        engine = OrderBookEngine(max_levels=10)
        
        assert engine.max_levels == 10
        assert engine.update_count == 0
        assert engine.last_update_id == 0
        assert len(engine.bids) == 0
        assert len(engine.asks) == 0
    
    def test_order_book_update(self):
        """Test order book updates."""
        engine = OrderBookEngine(max_levels=10)
        
        # Add bid
        success = engine.update(price=100.0, quantity=1.0, side="bid", update_id=1)
        assert success
        assert engine.update_count == 1
        assert engine.last_update_id == 1
        assert 100.0 in engine.bids
        assert engine.bids[100.0] == 1.0
        
        # Add ask
        success = engine.update(price=101.0, quantity=2.0, side="ask", update_id=2)
        assert success
        assert engine.update_count == 2
        assert engine.last_update_id == 2
        assert 101.0 in engine.asks
        assert engine.asks[101.0] == 2.0
    
    def test_order_book_remove(self):
        """Test order book level removal."""
        engine = OrderBookEngine(max_levels=10)
        
        # Add and remove bid
        engine.update(price=100.0, quantity=1.0, side="bid", update_id=1)
        assert 100.0 in engine.bids
        
        engine.update(price=100.0, quantity=0.0, side="bid", update_id=2)
        assert 100.0 not in engine.bids
    
    def test_order_book_max_levels(self):
        """Test max levels constraint."""
        engine = OrderBookEngine(max_levels=5)
        
        # Add more bids than max levels
        for i in range(10):
            engine.update(price=100.0 + i, quantity=1.0, side="bid", update_id=i+1)
        
        # Should only keep top 5 bids
        assert len(engine.bids) == 5
        assert max(engine.bids.keys()) == 109.0  # Highest bid
        assert min(engine.bids.keys()) == 105.0  # 5th highest bid
    
    def test_best_bid_ask(self):
        """Test best bid/ask calculation."""
        engine = OrderBookEngine(max_levels=10)
        
        # Empty book
        best_bid, best_ask = engine.get_best_bid_ask()
        assert best_bid is None
        assert best_ask is None
        
        # Add some levels
        engine.update(price=100.0, quantity=1.0, side="bid", update_id=1)
        engine.update(price=99.0, quantity=1.0, side="bid", update_id=2)
        engine.update(price=101.0, quantity=1.0, side="ask", update_id=3)
        engine.update(price=102.0, quantity=1.0, side="ask", update_id=4)
        
        best_bid, best_ask = engine.get_best_bid_ask()
        assert best_bid == 100.0
        assert best_ask == 101.0
    
    def test_sequence_gap_detection(self):
        """Test sequence gap detection."""
        engine = OrderBookEngine(max_levels=10)
        
        # Normal sequence
        success = engine.update(price=100.0, quantity=1.0, side="bid", update_id=1)
        assert success
        
        success = engine.update(price=101.0, quantity=1.0, side="ask", update_id=2)
        assert success
        
        # Gap in sequence (should still return True but log warning)
        success = engine.update(price=102.0, quantity=1.0, side="ask", update_id=5)
        assert success
        assert engine.last_update_id == 5


class TestPerformanceMetrics:
    """Test the PerformanceMetrics class."""
    
    def test_metrics_initialization(self):
        """Test metrics initialization."""
        metrics = PerformanceMetrics()
        
        assert metrics.events_processed == 0
        assert metrics.throughput_eps == 0.0
        assert metrics.memory_usage_gb == 0.0
    
    def test_opentelemetry_export(self):
        """Test OpenTelemetry export."""
        metrics = PerformanceMetrics(
            events_processed=1000,
            throughput_eps=500.0,
            memory_usage_gb=2.5
        )
        
        otel_metrics = metrics.to_opentelemetry()
        
        assert otel_metrics["pipeline.events.processed"] == 1000
        assert otel_metrics["pipeline.throughput.eps"] == 500.0
        assert otel_metrics["pipeline.memory.usage_gb"] == 2.5


class TestPerformanceHarness:
    """Test the PerformanceHarness class."""
    
    def test_harness_initialization(self):
        """Test harness initialization."""
        harness = PerformanceHarness(memory_limit_gb=8.0)
        
        assert harness.memory_limit_gb == 8.0
        assert harness.memory_profiler.limit_gb == 8.0
        assert harness.order_book is not None
        assert harness.metrics is not None
    
    def test_parse_events(self):
        """Test event parsing."""
        harness = PerformanceHarness()
        
        # Create sample data
        df = create_sample_delta_data(100)
        
        # Parse events
        parsed_df = harness.parse_events(df)
        
        # Check columns exist
        assert "price" in parsed_df.columns
        assert "quantity" in parsed_df.columns
        assert "update_id" in parsed_df.columns
        assert "notional" in parsed_df.columns
        assert "event_time" in parsed_df.columns
        
        # Check data types
        assert parsed_df["price"].dtype == pl.Float64
        assert parsed_df["quantity"].dtype == pl.Float64
        assert parsed_df["update_id"].dtype == pl.Int64
        
        # Check parse times were recorded
        assert len(harness.parse_times) > 0
    
    def test_update_order_book(self):
        """Test order book updates."""
        harness = PerformanceHarness()
        
        # Create sample data
        df = create_sample_delta_data(100)
        parsed_df = harness.parse_events(df)
        
        # Update order book
        harness.update_order_book(parsed_df)
        
        # Check order book was updated
        assert harness.order_book.update_count == 100
        assert harness.order_book.get_depth() > 0
        
        # Check update times were recorded
        assert len(harness.order_book_update_times) > 0
    
    def test_write_to_disk(self):
        """Test disk writing."""
        harness = PerformanceHarness()
        
        # Create sample data
        df = create_sample_delta_data(100)
        parsed_df = harness.parse_events(df)
        
        # Write to disk
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "test_output.parquet"
            harness.write_to_disk(parsed_df, output_path)
            
            # Check file was created
            assert output_path.exists()
            
            # Check file can be read back
            read_df = pl.read_parquet(output_path)
            assert len(read_df) == 100
        
        # Check write times were recorded
        assert len(harness.disk_write_times) > 0
    
    def test_profiling_start_stop(self):
        """Test profiling start/stop."""
        harness = PerformanceHarness()
        
        # Start profiling
        harness.start_profiling()
        
        # Process some events
        df = create_sample_delta_data(1000)
        parsed_df = harness.parse_events(df)
        harness.update_order_book(parsed_df)
        harness.throughput_analyzer.record_processing(1000)
        
        # Record memory usage so we have samples
        harness.memory_profiler.record_memory()
        harness.memory_profiler.record_memory()
        
        # Stop profiling
        harness.stop_profiling()
        
        # Check metrics were calculated
        assert harness.metrics.events_processed == 0  # Not set by stop_profiling
        assert harness.metrics.throughput_eps >= 0
        assert harness.metrics.parse_rate_eps > 0
        assert harness.metrics.order_book_update_rate_eps > 0
        assert harness.metrics.peak_memory_gb > 0
        assert harness.metrics.p95_memory_gb > 0
    
    def test_small_benchmark(self):
        """Test running a small benchmark."""
        harness = PerformanceHarness()
        
        # Run small benchmark
        metrics = harness.run_benchmark(num_events=1000, batch_size=100)
        
        # Check metrics
        assert metrics.events_processed == 1000
        assert metrics.throughput_eps > 0
        assert metrics.peak_memory_gb > 0
        assert metrics.p95_memory_gb > 0
        assert metrics.order_book_update_rate_eps > 0
        assert metrics.parse_rate_eps > 0
    
    def test_benchmark_with_memory_limit(self):
        """Test benchmark with memory limit."""
        # Very low memory limit to trigger warning
        harness = PerformanceHarness(memory_limit_gb=0.1)
        
        # Should complete without crashing
        metrics = harness.run_benchmark(num_events=500, batch_size=100)
        
        assert metrics.events_processed > 0