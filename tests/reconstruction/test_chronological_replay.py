"""Test ChronologicalEventReplay algorithm."""

import pytest
import polars as pl
from decimal import Decimal

from rlx_datapipe.reconstruction import ChronologicalEventReplay


def test_event_sorting():
    """Test stable sort by origin_time and update_id."""
    replayer = ChronologicalEventReplay()
    
    # Create test events with mixed timestamps
    events_data = [
        {"origin_time": 1000000003, "update_id": 2, "event_type": "TRADE", "data": "C2"},
        {"origin_time": 1000000001, "update_id": 1, "event_type": "BOOK_SNAPSHOT", "data": "A"},
        {"origin_time": 1000000002, "update_id": 1, "event_type": "BOOK_DELTA", "data": "B1"},
        {"origin_time": 1000000003, "update_id": 1, "event_type": "TRADE", "data": "C1"},
        {"origin_time": 1000000002, "update_id": 2, "event_type": "BOOK_DELTA", "data": "B2"},
    ]
    
    events_df = pl.DataFrame(events_data)
    
    # Sort events
    sorted_df = replayer._sort_events(events_df)
    
    # Verify order
    expected_order = ["A", "B1", "B2", "C1", "C2"]
    actual_order = sorted_df["data"].to_list()
    
    assert actual_order == expected_order
    
    # Verify stable sort maintains order for equal timestamps
    assert sorted_df.filter(pl.col("origin_time") == 1000000002)["data"].to_list() == ["B1", "B2"]
    assert sorted_df.filter(pl.col("origin_time") == 1000000003)["data"].to_list() == ["C1", "C2"]


def test_event_type_labeling():
    """Test automatic event type labeling."""
    replayer = ChronologicalEventReplay()
    
    # Test with missing event_type column
    events_data = [
        {"origin_time": 1000000001, "trade_id": 123, "price": 50000},
        {"origin_time": 1000000002, "bids": [[49999, 1]], "asks": [[50001, 1]]},
        {"origin_time": 1000000003, "side": "BID", "price": 49998, "quantity": 2},
    ]
    
    events_df = pl.DataFrame(events_data)
    
    # Label events
    labeled_df = replayer._label_event_types(events_df)
    
    # Verify labels
    assert labeled_df["event_type"].to_list() == ["TRADE", "BOOK_SNAPSHOT", "BOOK_DELTA"]


def test_event_type_labeling_with_is_snapshot():
    """Test event type labeling with is_snapshot flag."""
    replayer = ChronologicalEventReplay()
    
    events_data = [
        {"origin_time": 1000000001, "is_snapshot": True, "bids": [[49999, 1]], "asks": [[50001, 1]]},
        {"origin_time": 1000000002, "is_snapshot": False, "side": "BID", "price": 49998},
    ]
    
    events_df = pl.DataFrame(events_data)
    labeled_df = replayer._label_event_types(events_df)
    
    assert labeled_df["event_type"].to_list() == ["BOOK_SNAPSHOT", "BOOK_DELTA"]


def test_execute_basic_flow():
    """Test basic execute flow with minimal data."""
    replayer = ChronologicalEventReplay()
    
    # Create simple test data
    events_data = [
        {
            "origin_time": 1000000001,
            "event_type": "BOOK_SNAPSHOT",
            "bids": [[49999.0, 1.0], [49998.0, 2.0]],
            "asks": [[50001.0, 1.0], [50002.0, 2.0]],
            "is_snapshot": True
        },
        {
            "origin_time": 1000000002,
            "event_type": "TRADE",
            "trade_id": 123,
            "trade_price": 50000.0,
            "trade_quantity": 0.5,
            "trade_side": "BUY"
        },
        {
            "origin_time": 1000000003,
            "event_type": "BOOK_DELTA",
            "delta_side": "BID",
            "delta_price": 49997.0,
            "delta_quantity": 3.0
        }
    ]
    
    events_df = pl.DataFrame(events_data)
    
    # Execute replay
    result_df = replayer.execute(events_df)
    
    # Verify basic properties
    assert len(result_df) == 3
    assert "book_state" in result_df.columns
    assert "top_bid" in result_df.columns
    assert "top_ask" in result_df.columns
    assert "spread" in result_df.columns
    
    # Verify events are in chronological order
    timestamps = result_df["event_timestamp"].to_list()
    assert timestamps == sorted(timestamps)


def test_initialization_from_first_snapshot():
    """Test that order book initializes from first snapshot."""
    replayer = ChronologicalEventReplay()
    
    events_data = [
        {
            "origin_time": 1000000002,
            "event_type": "TRADE",
            "trade_id": 123,
            "trade_price": 50000.0,
            "trade_quantity": 0.5,
            "trade_side": "BUY"
        },
        {
            "origin_time": 1000000001,  # Earlier timestamp
            "event_type": "BOOK_SNAPSHOT",
            "bids": [[49999.0, 1.0]],
            "asks": [[50001.0, 1.0]],
            "is_snapshot": True
        }
    ]
    
    events_df = pl.DataFrame(events_data)
    result_df = replayer.execute(events_df)
    
    # After sorting, snapshot should be first
    first_event = result_df[0]
    assert first_event["event_type"].item() == "BOOK_SNAPSHOT"
    
    # Book state should be initialized for both events
    # Extract the top_bid value from the Series
    top_bid_data = first_event["top_bid"].to_list()[0]
    assert top_bid_data is not None
    assert isinstance(top_bid_data, list)
    assert len(top_bid_data) == 2
    assert top_bid_data[0] == 49999.0  # Price
    assert top_bid_data[1] == 1.0      # Quantity
    
    # Second event should also have book state
    second_event_top_bid = result_df[1]["top_bid"].to_list()[0]
    assert second_event_top_bid is not None


def test_update_id_addition():
    """Test that update_id is added if missing."""
    replayer = ChronologicalEventReplay()
    
    events_data = [
        {"origin_time": 1000000001, "event_type": "TRADE"},
        {"origin_time": 1000000002, "event_type": "BOOK_DELTA"},
    ]
    
    events_df = pl.DataFrame(events_data)
    sorted_df = replayer._sort_events(events_df)
    
    # Verify update_id column was added
    assert "update_id" in sorted_df.columns
    assert sorted_df["update_id"].to_list() == [0, 0]