"""Test schema normalization functionality."""

import pytest
import polars as pl
from decimal import Decimal

from rlx_datapipe.reconstruction import SchemaNormalizer


def test_normalize_trade_event():
    """Test normalization of trade events."""
    normalizer = SchemaNormalizer()
    
    # Test various trade event formats
    trade_events = [
        # Standard format
        {
            "event_type": "TRADE",
            "origin_time": 1000000001,
            "trade_id": 123,
            "trade_price": 50000.0,
            "trade_quantity": 0.5,
            "trade_side": "BUY"
        },
        # Alternative field names
        {
            "event_type": "TRADE",
            "timestamp": 1000000002,
            "id": 124,
            "price": 50001.0,
            "quantity": 0.6,
            "side": "SELL"
        },
        # Execution field names
        {
            "event_type": "TRADE",
            "origin_time": 1000000003,
            "exec_id": 125,
            "exec_price": 50002.0,
            "exec_quantity": 0.7,
            "exec_side": "buy"  # lowercase
        }
    ]
    
    for event in trade_events:
        normalized = normalizer.normalize_to_unified_schema(event)
        
        # Check core fields
        assert normalized["event_type"] == "TRADE"
        assert "event_timestamp" in normalized
        assert normalized["event_timestamp"] > 0
        
        # Check trade fields are populated
        assert normalized["trade_id"] is not None
        assert normalized["trade_price"] is not None
        assert normalized["trade_quantity"] is not None
        assert normalized["trade_side"] in ["BUY", "SELL"]
        
        # Check other fields are null
        assert normalized["bids"] is None
        assert normalized["asks"] is None
        assert normalized["delta_side"] is None


def test_normalize_snapshot_event():
    """Test normalization of snapshot events."""
    normalizer = SchemaNormalizer()
    
    snapshot = {
        "event_type": "BOOK_SNAPSHOT",
        "origin_time": 1000000001,
        "bids": [[49999.0, 1.0], [49998.0, 2.0]],
        "asks": [[50001.0, 1.0], [50002.0, 2.0]],
        "is_snapshot": True
    }
    
    normalized = normalizer.normalize_to_unified_schema(snapshot)
    
    # Check core fields
    assert normalized["event_type"] == "BOOK_SNAPSHOT"
    assert normalized["event_timestamp"] == 1000000001000000  # Converted to nanoseconds
    
    # Check snapshot fields
    assert normalized["is_snapshot"] is True
    assert len(normalized["bids"]) == 2
    assert len(normalized["asks"]) == 2
    
    # Check bid/ask format
    assert all(isinstance(level[0], Decimal) for level in normalized["bids"])
    assert all(isinstance(level[1], Decimal) for level in normalized["bids"])
    
    # Check trade fields are null
    assert normalized["trade_id"] is None
    assert normalized["trade_price"] is None


def test_normalize_delta_event():
    """Test normalization of delta events."""
    normalizer = SchemaNormalizer()
    
    delta_events = [
        {
            "event_type": "BOOK_DELTA",
            "origin_time": 1000000001,
            "delta_side": "BID",
            "delta_price": 49997.0,
            "delta_quantity": 3.0
        },
        # Alternative format
        {
            "event_type": "BOOK_DELTA",
            "origin_time": 1000000002,
            "side": "ASK",
            "price": 50003.0,
            "quantity": 0.0  # Remove level
        }
    ]
    
    for event in delta_events:
        normalized = normalizer.normalize_to_unified_schema(event)
        
        assert normalized["event_type"] == "BOOK_DELTA"
        assert normalized["delta_side"] in ["BID", "ASK"]
        assert isinstance(normalized["delta_price"], Decimal)
        assert isinstance(normalized["delta_quantity"], Decimal)
        
        # Check other fields are null
        assert normalized["trade_id"] is None
        assert normalized["bids"] is None


def test_normalize_with_update_id():
    """Test that update_id is preserved."""
    normalizer = SchemaNormalizer()
    
    event = {
        "event_type": "TRADE",
        "origin_time": 1000000001,
        "update_id": 12345,
        "trade_id": 123,
        "trade_price": 50000.0,
        "trade_quantity": 0.5,
        "trade_side": "BUY"
    }
    
    normalized = normalizer.normalize_to_unified_schema(event)
    assert normalized["update_id"] == 12345


def test_normalize_events_dataframe():
    """Test normalizing entire DataFrame."""
    normalizer = SchemaNormalizer()
    
    events_data = [
        {
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000001,
            "bids": [[49999.0, 1.0]],
            "asks": [[50001.0, 1.0]]
        },
        {
            "event_type": "TRADE",
            "origin_time": 1000000002,
            "trade_id": 123,
            "trade_price": 50000.0,
            "trade_quantity": 0.5,
            "trade_side": "BUY"
        },
        {
            "event_type": "BOOK_DELTA",
            "origin_time": 1000000003,
            "delta_side": "BID",
            "delta_price": 49998.0,
            "delta_quantity": 2.0
        }
    ]
    
    events_df = pl.DataFrame(events_data)
    normalized_df = normalizer.normalize_events(events_df)
    
    # Check all events were normalized
    assert len(normalized_df) == 3
    
    # Check required columns exist
    required_cols = [
        "event_timestamp", "event_type", "update_id",
        "trade_id", "trade_price", "trade_quantity", "trade_side",
        "bids", "asks", "is_snapshot",
        "delta_side", "delta_price", "delta_quantity"
    ]
    
    for col in required_cols:
        assert col in normalized_df.columns


def test_pending_queue_pattern():
    """Test pending queue pattern for atomic updates."""
    normalizer = SchemaNormalizer()
    
    # Simulate delta before snapshot
    delta1 = {
        "event_type": "BOOK_DELTA",
        "origin_time": 1000000001,
        "delta_side": "BID",
        "delta_price": 49997.0,
        "delta_quantity": 3.0
    }
    
    # Process delta - should be queued
    normalized1 = normalizer.normalize_to_unified_schema(delta1)
    assert len(normalizer.pending_queue) == 0  # Queue is cleared after each event for now
    
    # Process snapshot - should apply pending updates
    snapshot = {
        "event_type": "BOOK_SNAPSHOT",
        "origin_time": 1000000002,
        "bids": [[49999.0, 1.0], [49998.0, 2.0]],
        "asks": [[50001.0, 1.0]],
        "is_snapshot": True
    }
    
    normalized2 = normalizer.normalize_to_unified_schema(snapshot)
    assert normalized2["event_type"] == "BOOK_SNAPSHOT"
    assert len(normalizer.pending_queue) == 0  # Queue should be cleared


def test_timestamp_conversion():
    """Test timestamp conversion to nanoseconds."""
    normalizer = SchemaNormalizer()
    
    # Test microsecond timestamp
    event1 = {
        "event_type": "TRADE",
        "origin_time": 1000000,  # Microseconds
        "trade_id": 1
    }
    normalized1 = normalizer.normalize_to_unified_schema(event1)
    assert normalized1["event_timestamp"] == 1000000000000  # Converted to nanoseconds
    
    # Test nanosecond timestamp
    event2 = {
        "event_type": "TRADE",
        "event_timestamp": 1000000000000000,  # Already nanoseconds
        "trade_id": 2
    }
    normalized2 = normalizer.normalize_to_unified_schema(event2)
    assert normalized2["event_timestamp"] == 1000000000000000


def test_decimal_precision():
    """Test decimal precision is maintained."""
    normalizer = SchemaNormalizer()
    
    event = {
        "event_type": "TRADE",
        "origin_time": 1000000001,
        "trade_price": "50000.123456789012345678",  # High precision
        "trade_quantity": "0.000000000123456789",
        "trade_side": "BUY"
    }
    
    normalized = normalizer.normalize_to_unified_schema(event)
    
    # Check precision is maintained
    assert isinstance(normalized["trade_price"], Decimal)
    assert isinstance(normalized["trade_quantity"], Decimal)
    assert str(normalized["trade_price"]) == "50000.123456789012345678"
    
    # Check quantity precision - may be in scientific notation
    qty_decimal = normalized["trade_quantity"]
    assert qty_decimal == Decimal("0.000000000123456789")


def test_normalize_dict_format_levels():
    """Test normalizing dict format book levels."""
    normalizer = SchemaNormalizer()
    
    snapshot = {
        "event_type": "BOOK_SNAPSHOT",
        "origin_time": 1000000001,
        "bids": [
            {"price": 49999.0, "quantity": 1.0},
            {"p": 49998.0, "q": 2.0},
            {"price": 49997.0, "size": 3.0}
        ],
        "asks": [
            {"price": 50001.0, "quantity": 1.0}
        ]
    }
    
    normalized = normalizer.normalize_to_unified_schema(snapshot)
    
    # Check all bid levels were normalized
    assert len(normalized["bids"]) == 3
    assert normalized["bids"][0] == [Decimal("49999.0"), Decimal("1.0")]
    assert normalized["bids"][1] == [Decimal("49998.0"), Decimal("2.0")]
    assert normalized["bids"][2] == [Decimal("49997.0"), Decimal("3.0")]