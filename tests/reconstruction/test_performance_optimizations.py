"""Test performance optimizations for event replayer."""

import pytest
import polars as pl
import time
from loguru import logger

from rlx_datapipe.reconstruction import ChronologicalEventReplay


def generate_test_events(num_events: int) -> pl.DataFrame:
    """Generate test events for performance testing."""
    events = []
    
    # Start with a snapshot
    events.append({
        "event_type": "BOOK_SNAPSHOT",
        "origin_time": 1000000000,
        "bids": [[50000.0 - i, 1.0 + i * 0.1] for i in range(20)],
        "asks": [[50001.0 + i, 1.0 + i * 0.1] for i in range(20)],
        "is_snapshot": True
    })
    
    # Generate mixed events
    for i in range(1, num_events):
        if i % 1000 == 0:  # Periodic snapshot
            events.append({
                "event_type": "BOOK_SNAPSHOT",
                "origin_time": 1000000000 + i,
                "bids": [[50000.0 - j + (i/1000), 1.0 + j * 0.1] for j in range(20)],
                "asks": [[50001.0 + j + (i/1000), 1.0 + j * 0.1] for j in range(20)],
                "is_snapshot": True
            })
        elif i % 3 == 0:  # Trade
            events.append({
                "event_type": "TRADE",
                "origin_time": 1000000000 + i,
                "trade_id": i,
                "trade_price": 50000.0 + (i % 100) * 0.1,
                "trade_quantity": 0.1 + (i % 10) * 0.1,
                "trade_side": "BUY" if i % 2 == 0 else "SELL"
            })
        else:  # Delta
            events.append({
                "event_type": "BOOK_DELTA",
                "origin_time": 1000000000 + i,
                "delta_side": "BID" if i % 2 == 0 else "ASK",
                "delta_price": 50000.0 + (i % 50) * 0.1,
                "delta_quantity": 0.5 + (i % 5) * 0.1
            })
    
    return pl.DataFrame(events)


def test_baseline_performance():
    """Test baseline performance without optimizations."""
    # Generate 10K events for quick test
    events_df = generate_test_events(10_000)
    
    replayer = ChronologicalEventReplay()
    
    start_time = time.time()
    result_df = replayer.execute(events_df)
    elapsed_time = time.time() - start_time
    
    events_per_second = len(events_df) / elapsed_time
    
    logger.info(f"Processed {len(events_df)} events in {elapsed_time:.3f}s")
    logger.info(f"Throughput: {events_per_second:,.0f} events/second")
    
    # Basic performance check - should process at least 50K events/second
    assert events_per_second > 50_000
    assert len(result_df) == len(events_df)


def test_micro_batching_performance():
    """Test performance with micro-batching."""
    # Generate 100K events
    all_events = generate_test_events(100_000)
    
    # Process in micro-batches
    batch_size = 1000
    replayer = ChronologicalEventReplay()
    
    start_time = time.time()
    total_processed = 0
    
    # Process in chunks
    for i in range(0, len(all_events), batch_size):
        batch = all_events[i:i + batch_size]
        result = replayer.execute(batch)
        total_processed += len(result)
    
    elapsed_time = time.time() - start_time
    events_per_second = total_processed / elapsed_time
    
    logger.info(f"Processed {total_processed} events in {batch_size}-event batches")
    logger.info(f"Total time: {elapsed_time:.3f}s")
    logger.info(f"Throughput: {events_per_second:,.0f} events/second")
    
    # Should maintain good performance with batching
    assert events_per_second > 100_000
    assert total_processed == len(all_events)


def test_memory_efficiency():
    """Test memory usage remains bounded."""
    import gc
    import psutil
    import os
    
    # Get process
    process = psutil.Process(os.getpid())
    
    # Force garbage collection and get baseline memory
    gc.collect()
    baseline_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    # Process large dataset
    events_df = generate_test_events(50_000)
    replayer = ChronologicalEventReplay(max_levels=20)
    
    result_df = replayer.execute(events_df)
    
    # Get peak memory
    peak_memory = process.memory_info().rss / 1024 / 1024  # MB
    memory_increase = peak_memory - baseline_memory
    
    logger.info(f"Baseline memory: {baseline_memory:.1f} MB")
    logger.info(f"Peak memory: {peak_memory:.1f} MB")
    logger.info(f"Memory increase: {memory_increase:.1f} MB")
    
    # Memory increase should be well under 500MB
    assert memory_increase < 500
    
    # Clean up
    del events_df
    del result_df
    gc.collect()


def test_zero_copy_operations():
    """Test that operations minimize data copying."""
    # Create events with large book data
    events = []
    for i in range(100):
        events.append({
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000000 + i,
            "bids": [[50000.0 - j, 1.0] for j in range(100)],  # 100 levels
            "asks": [[50001.0 + j, 1.0] for j in range(100)],
            "is_snapshot": True
        })
    
    events_df = pl.DataFrame(events)
    replayer = ChronologicalEventReplay(max_levels=20)  # Only keep top 20
    
    # Measure time for operations that should be zero-copy
    start_time = time.time()
    
    # These operations should be fast due to zero-copy
    sorted_df = replayer._sort_events(events_df)
    labeled_df = replayer._label_event_types(sorted_df)
    
    prep_time = time.time() - start_time
    
    # Preparation should be very fast (< 10ms for 100 events)
    assert prep_time < 0.01
    
    # Full execution
    start_time = time.time()
    result_df = replayer.execute(events_df)
    exec_time = time.time() - start_time
    
    logger.info(f"Preparation time: {prep_time*1000:.2f}ms")
    logger.info(f"Execution time: {exec_time*1000:.2f}ms")
    
    assert len(result_df) == len(events_df)


def test_optimization_flags():
    """Test that optimization flags work correctly."""
    events_df = generate_test_events(1000)
    
    # Test with different configurations
    configs = [
        {"max_levels": 5},   # Minimal memory
        {"max_levels": 20},  # Default
        {"max_levels": 50},  # More memory
    ]
    
    for config in configs:
        replayer = ChronologicalEventReplay(**config)
        
        start_time = time.time()
        result_df = replayer.execute(events_df)
        elapsed_time = time.time() - start_time
        
        logger.info(
            f"Config {config}: {elapsed_time*1000:.2f}ms for {len(events_df)} events"
        )
        
        # All configs should complete successfully
        assert len(result_df) == len(events_df)
        
        # Verify max_levels is respected
        for row in result_df.filter(pl.col("book_state").is_not_null()).iter_rows(named=True):
            book_state = row["book_state"]
            if book_state:
                bids, asks = book_state
                # Check we don't exceed max_levels
                assert len(bids) <= config.get("max_levels", 20)
                assert len(asks) <= config.get("max_levels", 20)


def test_hybrid_data_structure_performance():
    """Test that hybrid data structure provides expected performance."""
    # The OrderBookState already uses hybrid structure:
    # - Arrays for top levels (fast access)
    # - Hash map for deep levels
    
    events = []
    
    # Create snapshot with many levels
    deep_bids = [[50000.0 - i * 0.1, 1.0] for i in range(100)]
    deep_asks = [[50001.0 + i * 0.1, 1.0] for i in range(100)]
    
    events.append({
        "event_type": "BOOK_SNAPSHOT",
        "origin_time": 1000000000,
        "bids": deep_bids,
        "asks": deep_asks,
        "is_snapshot": True
    })
    
    # Add many updates to different price levels
    for i in range(1000):
        events.append({
            "event_type": "BOOK_DELTA",
            "origin_time": 1000000001 + i,
            "delta_side": "BID" if i % 2 == 0 else "ASK",
            "delta_price": 50000.0 + (i % 200 - 100) * 0.1,
            "delta_quantity": 0.5 + (i % 5) * 0.1
        })
    
    events_df = pl.DataFrame(events)
    replayer = ChronologicalEventReplay(max_levels=20)
    
    start_time = time.time()
    result_df = replayer.execute(events_df)
    elapsed_time = time.time() - start_time
    
    updates_per_second = 1000 / elapsed_time
    
    logger.info(f"Processed 1000 updates to deep book in {elapsed_time:.3f}s")
    logger.info(f"Update rate: {updates_per_second:,.0f} updates/second")
    
    # Should handle deep book updates efficiently
    assert updates_per_second > 50_000