"""Simple performance tests for event replayer."""

import pytest
import polars as pl
import time
from loguru import logger

from rlx_datapipe.reconstruction import ChronologicalEventReplay


def test_throughput_baseline():
    """Test baseline throughput performance."""
    # Generate simple events
    num_events = 10000
    
    events = []
    # Initial snapshot
    events.append({
        "event_type": "BOOK_SNAPSHOT",
        "origin_time": 1000000000,
        "bids": [[50000.0, 1.0], [49999.0, 2.0]],
        "asks": [[50001.0, 1.0], [50002.0, 2.0]]
    })
    
    # Add trades and deltas
    for i in range(1, num_events):
        if i % 2 == 0:
            events.append({
                "event_type": "TRADE",
                "origin_time": 1000000000 + i,
                "trade_id": i,
                "trade_price": 50000.0 + (i % 10) * 0.1,
                "trade_quantity": 0.1,
                "trade_side": "BUY"
            })
        else:
            events.append({
                "event_type": "BOOK_DELTA",
                "origin_time": 1000000000 + i,
                "delta_side": "BID",
                "delta_price": 50000.0 - (i % 10),
                "delta_quantity": 1.0
            })
    
    events_df = pl.DataFrame(events)
    
    # Create replayer with high drift threshold to avoid resyncs
    replayer = ChronologicalEventReplay(drift_threshold=1.0)
    
    # Warm up
    _ = replayer.execute(events_df[:100])
    
    # Measure performance
    start_time = time.time()
    result_df = replayer.execute(events_df)
    elapsed_time = time.time() - start_time
    
    events_per_second = len(events_df) / elapsed_time
    
    logger.info(f"Processed {len(events_df)} events in {elapsed_time:.3f}s")
    logger.info(f"Throughput: {events_per_second:,.0f} events/second")
    
    # Should process at reasonable speed
    assert events_per_second > 10_000  # At least 10K events/second
    assert len(result_df) == len(events_df)


def test_memory_bounded():
    """Test that memory usage remains bounded."""
    # Generate events with large book snapshots
    events = []
    
    for i in range(100):
        # Large snapshots
        events.append({
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000000 + i * 1000,
            "bids": [[50000.0 - j * 0.1, 1.0] for j in range(100)],
            "asks": [[50001.0 + j * 0.1, 1.0] for j in range(100)]
        })
        
        # Some trades
        for j in range(10):
            events.append({
                "event_type": "TRADE",
                "origin_time": 1000000000 + i * 1000 + j,
                "trade_id": i * 10 + j,
                "trade_price": 50000.0,
                "trade_quantity": 0.1,
                "trade_side": "BUY"
            })
    
    events_df = pl.DataFrame(events)
    
    # Process with limited max_levels
    replayer = ChronologicalEventReplay(max_levels=20, drift_threshold=1.0)
    
    start_time = time.time()
    result_df = replayer.execute(events_df)
    elapsed_time = time.time() - start_time
    
    # Check that max_levels was respected
    for row in result_df.filter(pl.col("book_state").is_not_null()).head(10).iter_rows(named=True):
        book_state = row["book_state"]
        if book_state:
            bids, asks = book_state
            # Should only keep top 20 levels
            assert len(bids) <= 20
            assert len(asks) <= 20
    
    logger.info(f"Processed {len(events_df)} events with bounded memory in {elapsed_time:.3f}s")


def test_sort_performance():
    """Test that sorting is efficient."""
    # Generate events in random order
    import random
    
    num_events = 10000
    events = []
    
    # Generate timestamps
    timestamps = list(range(1000000000, 1000000000 + num_events))
    random.shuffle(timestamps)
    
    for i, ts in enumerate(timestamps):
        events.append({
            "event_type": "TRADE",
            "origin_time": ts,
            "trade_id": i,
            "trade_price": 50000.0,
            "trade_quantity": 0.1,
            "trade_side": "BUY"
        })
    
    events_df = pl.DataFrame(events)
    replayer = ChronologicalEventReplay()
    
    # Measure just the sort time
    start_time = time.time()
    sorted_df = replayer._sort_events(events_df)
    sort_time = time.time() - start_time
    
    # Verify sorted
    timestamps = sorted_df["origin_time"].to_list()
    assert timestamps == sorted(timestamps)
    
    logger.info(f"Sorted {num_events} events in {sort_time*1000:.2f}ms")
    
    # Sorting should be fast
    assert sort_time < 0.1  # Less than 100ms for 10K events


def test_normalization_performance():
    """Test schema normalization performance."""
    from rlx_datapipe.reconstruction import SchemaNormalizer
    
    num_events = 5000
    events = []
    
    for i in range(num_events):
        events.append({
            "event_type": "TRADE",
            "origin_time": 1000000000 + i,
            "trade_id": i,
            "price": 50000.0 + i * 0.1,  # Different field name
            "quantity": 0.1 + (i % 10) * 0.01,
            "side": "BUY" if i % 2 == 0 else "SELL"
        })
    
    events_df = pl.DataFrame(events)
    normalizer = SchemaNormalizer()
    
    start_time = time.time()
    normalized_df = normalizer.normalize_events(events_df)
    norm_time = time.time() - start_time
    
    events_per_second = num_events / norm_time
    
    logger.info(f"Normalized {num_events} events in {norm_time:.3f}s")
    logger.info(f"Normalization rate: {events_per_second:,.0f} events/second")
    
    assert len(normalized_df) == num_events
    assert "trade_price" in normalized_df.columns  # Normalized field name