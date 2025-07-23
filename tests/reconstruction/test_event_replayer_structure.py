"""Test module structure for event replayer components."""

import pytest
from decimal import Decimal


def test_imports():
    """Test that all modules can be imported."""
    from rlx_datapipe.reconstruction import (
        ChronologicalEventReplay,
        SchemaNormalizer,
        DriftTracker,
        OrderBookState,
        OrderBookEngine
    )
    
    # Verify classes exist
    assert ChronologicalEventReplay is not None
    assert SchemaNormalizer is not None
    assert DriftTracker is not None
    assert OrderBookState is not None
    assert OrderBookEngine is not None


def test_chronological_event_replay_init():
    """Test ChronologicalEventReplay initialization."""
    from rlx_datapipe.reconstruction import ChronologicalEventReplay
    
    replayer = ChronologicalEventReplay(
        drift_threshold=0.001,
        max_levels=20,
        resync_on_drift=True
    )
    
    assert replayer.drift_threshold == 0.001
    assert replayer.max_levels == 20
    assert replayer.resync_on_drift is True
    assert replayer.normalizer is not None
    assert replayer.drift_tracker is not None


def test_schema_normalizer_init():
    """Test SchemaNormalizer initialization."""
    from rlx_datapipe.reconstruction import SchemaNormalizer
    
    normalizer = SchemaNormalizer()
    assert normalizer.pending_queue == []


def test_drift_tracker_init():
    """Test DriftTracker initialization."""
    from rlx_datapipe.reconstruction import DriftTracker
    
    tracker = DriftTracker(drift_threshold=0.001)
    assert tracker.drift_threshold == 0.001
    assert tracker.drift_history == []
    assert tracker.total_snapshots == 0
    assert tracker.total_resyncs == 0


def test_order_book_state_extended():
    """Test extended OrderBookState functionality."""
    from rlx_datapipe.reconstruction import OrderBookState
    
    book = OrderBookState(symbol="BTCUSDT", max_levels=20)
    
    # Test initial state
    assert book.symbol == "BTCUSDT"
    assert book.max_levels == 20
    assert book.initialized is False
    
    # Test new methods exist
    assert hasattr(book, 'get_best_bid')
    assert hasattr(book, 'get_best_ask')
    assert hasattr(book, 'get_spread')
    assert hasattr(book, 'get_bid_levels')
    assert hasattr(book, 'get_ask_levels')
    assert hasattr(book, 'apply_trade')
    assert hasattr(book, 'resynchronize')
    
    # Test initialization from snapshot
    snapshot = {
        "bids": [[50000.0, 1.0], [49999.0, 2.0]],
        "asks": [[50001.0, 1.5], [50002.0, 2.5]]
    }
    
    book.initialize_from_snapshot(snapshot)
    assert book.initialized is True
    
    # Test best bid/ask
    best_bid = book.get_best_bid()
    best_ask = book.get_best_ask()
    
    assert best_bid is not None
    assert best_ask is not None
    assert best_bid[0] == 50000.0
    assert best_ask[0] == 50001.0
    
    # Test spread
    spread = book.get_spread()
    assert spread == 1.0


def test_decimal_utils():
    """Test decimal utility functions."""
    from rlx_datapipe.reconstruction.decimal_utils import ensure_decimal128
    
    # Test various input types
    assert ensure_decimal128("123.456") == Decimal("123.456")
    assert ensure_decimal128(123.456) == Decimal("123.456")
    assert ensure_decimal128(123) == Decimal("123")
    assert ensure_decimal128(Decimal("123.456")) == Decimal("123.456")
    assert ensure_decimal128(None) is None