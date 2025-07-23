"""Test stateful replay logic with order book maintenance."""

import pytest
import polars as pl
from decimal import Decimal

from rlx_datapipe.reconstruction import ChronologicalEventReplay


def test_snapshot_initialization():
    """Test order book initialization from snapshot."""
    replayer = ChronologicalEventReplay()
    
    events_data = [
        {
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000001,
            "bids": [[49999.0, 1.0], [49998.0, 2.0], [49997.0, 3.0]],
            "asks": [[50001.0, 1.0], [50002.0, 2.0], [50003.0, 3.0]],
            "is_snapshot": True
        }
    ]
    
    events_df = pl.DataFrame(events_data)
    result_df = replayer.execute(events_df)
    
    # Check book state was properly initialized
    book_state = result_df[0]["book_state"].to_list()[0]
    assert len(book_state) == 2  # [bids, asks]
    
    bids, asks = book_state
    assert len(bids) == 3
    assert len(asks) == 3
    
    # Check top of book
    top_bid = result_df[0]["top_bid"].to_list()[0]
    top_ask = result_df[0]["top_ask"].to_list()[0]
    
    assert top_bid[0] == 49999.0
    assert top_ask[0] == 50001.0
    
    # Check spread
    spread = result_df[0]["spread"].to_list()[0]
    assert spread == 2.0


def test_trade_liquidity_consumption():
    """Test that trades consume liquidity from the book."""
    replayer = ChronologicalEventReplay()
    
    events_data = [
        {
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000001,
            "bids": [[49999.0, 2.0], [49998.0, 3.0]],
            "asks": [[50001.0, 2.0], [50002.0, 3.0]],
            "is_snapshot": True
        },
        {
            "event_type": "TRADE",
            "origin_time": 1000000002,
            "trade_id": 123,
            "trade_price": 50001.0,
            "trade_quantity": 1.0,
            "trade_side": "BUY"  # Buy trade consumes ask liquidity
        }
    ]
    
    events_df = pl.DataFrame(events_data)
    result_df = replayer.execute(events_df)
    
    # Check that ask liquidity was reduced
    second_event_asks = result_df[1]["book_state"].to_list()[0][1]  # asks
    
    # First ask level should have reduced quantity (2.0 - 1.0 = 1.0)
    assert second_event_asks[0][1] == 100000000  # 1.0 scaled to int


def test_book_delta_application():
    """Test application of book delta updates."""
    replayer = ChronologicalEventReplay()
    
    events_data = [
        {
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000001,
            "bids": [[49999.0, 1.0], [49998.0, 2.0]],
            "asks": [[50001.0, 1.0], [50002.0, 2.0]],
            "is_snapshot": True
        },
        {
            "event_type": "BOOK_DELTA",
            "origin_time": 1000000002,
            "delta_side": "BID",
            "delta_price": 49997.0,
            "delta_quantity": 3.0
        },
        {
            "event_type": "BOOK_DELTA",
            "origin_time": 1000000003,
            "delta_side": "ASK",
            "delta_price": 50001.0,
            "delta_quantity": 0.0  # Remove level
        }
    ]
    
    events_df = pl.DataFrame(events_data)
    result_df = replayer.execute(events_df)
    
    # After first delta: new bid level added
    bids_after_delta1 = result_df[1]["book_state"].to_list()[0][0]
    assert len(bids_after_delta1) == 3  # Added one level
    
    # After second delta: ask level removed
    asks_after_delta2 = result_df[2]["book_state"].to_list()[0][1]
    assert len(asks_after_delta2) == 1  # Removed one level
    
    # Check top ask changed
    top_ask_after_removal = result_df[2]["top_ask"].to_list()[0]
    assert top_ask_after_removal[0] == 50002.0  # Next level became top


def test_drift_tracking_and_resync():
    """Test drift tracking between snapshots and resynchronization."""
    replayer = ChronologicalEventReplay(
        drift_threshold=0.001,
        resync_on_drift=True
    )
    
    events_data = [
        {
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000001,
            "bids": [[49999.0, 1.0]],
            "asks": [[50001.0, 1.0]],
            "is_snapshot": True
        },
        # Apply some deltas
        {
            "event_type": "BOOK_DELTA",
            "origin_time": 1000000002,
            "delta_side": "BID",
            "delta_price": 49998.0,
            "delta_quantity": 2.0
        },
        # Second snapshot - should calculate drift
        {
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000003,
            "bids": [[49999.0, 1.0], [49998.0, 2.1]],  # Slightly different quantity
            "asks": [[50001.0, 1.0]],
            "is_snapshot": True
        }
    ]
    
    events_df = pl.DataFrame(events_data)
    result_df = replayer.execute(events_df)
    
    # Check drift metrics were calculated for second snapshot
    second_snapshot = result_df[2]
    drift_metrics = second_snapshot["drift_metrics"].to_list()[0]
    
    assert drift_metrics is not None
    assert "rms_error" in drift_metrics
    assert "max_deviation" in drift_metrics
    assert drift_metrics["snapshot_number"] == 1  # First snapshot with drift calculation
    assert drift_metrics["exceeds_threshold"] is True  # Should exceed threshold due to quantity difference
    assert drift_metrics["rms_error"] > 0.001  # Should have detected the drift


def test_event_enrichment():
    """Test that all events are enriched with book state."""
    replayer = ChronologicalEventReplay()
    
    events_data = [
        {
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000001,
            "bids": [[49999.0, 1.0]],
            "asks": [[50001.0, 1.0]],
            "is_snapshot": True
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
    result_df = replayer.execute(events_df)
    
    # Check all events have book state fields
    for i in range(len(result_df)):
        row = result_df[i]
        assert "book_state" in row
        assert "top_bid" in row
        assert "top_ask" in row
        assert "spread" in row
        
        # All should have values after initialization
        assert row["book_state"][0] is not None
        assert row["top_bid"][0] is not None
        assert row["top_ask"][0] is not None
        assert row["spread"][0] is not None


def test_uninitialized_book_handling():
    """Test handling of events before book initialization."""
    replayer = ChronologicalEventReplay()
    
    events_data = [
        # Trade before any snapshot
        {
            "event_type": "TRADE",
            "origin_time": 1000000001,
            "trade_id": 123,
            "trade_price": 50000.0,
            "trade_quantity": 0.5,
            "trade_side": "BUY"
        },
        # Delta before snapshot
        {
            "event_type": "BOOK_DELTA",
            "origin_time": 1000000002,
            "delta_side": "BID",
            "delta_price": 49999.0,
            "delta_quantity": 1.0
        },
        # Finally a snapshot
        {
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000003,
            "bids": [[49999.0, 1.0]],
            "asks": [[50001.0, 1.0]],
            "is_snapshot": True
        }
    ]
    
    events_df = pl.DataFrame(events_data)
    result_df = replayer.execute(events_df)
    
    # First two events should have None for book state
    assert result_df[0]["top_bid"][0] is None
    assert result_df[0]["top_ask"][0] is None
    assert result_df[1]["top_bid"][0] is None
    assert result_df[1]["top_ask"][0] is None
    
    # Third event (snapshot) should initialize the book
    assert result_df[2]["top_bid"][0] is not None
    assert result_df[2]["top_ask"][0] is not None


def test_multiple_snapshots():
    """Test handling multiple snapshots with resynchronization."""
    replayer = ChronologicalEventReplay()
    
    events_data = [
        {
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000001,
            "bids": [[49999.0, 1.0]],
            "asks": [[50001.0, 1.0]],
            "is_snapshot": True
        },
        {
            "event_type": "BOOK_DELTA",
            "origin_time": 1000000002,
            "delta_side": "BID",
            "delta_price": 49998.0,
            "delta_quantity": 2.0
        },
        # New snapshot with different state
        {
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000003,
            "bids": [[50000.0, 3.0], [49999.0, 4.0]],
            "asks": [[50001.0, 2.0], [50002.0, 3.0]],
            "is_snapshot": True
        }
    ]
    
    events_df = pl.DataFrame(events_data)
    result_df = replayer.execute(events_df)
    
    # After second snapshot, book should be completely replaced
    final_book = result_df[2]["book_state"].to_list()[0]
    final_bids = final_book[0]
    
    # Check new bid levels
    assert len(final_bids) == 2
    assert final_bids[0][0] == 5000000000000  # 50000.0 scaled
    
    # Top bid should be updated
    final_top_bid = result_df[2]["top_bid"].to_list()[0]
    assert final_top_bid[0] == 50000.0


def test_sell_trade_consumes_bids():
    """Test that sell trades consume bid liquidity."""
    replayer = ChronologicalEventReplay()
    
    events_data = [
        {
            "event_type": "BOOK_SNAPSHOT",
            "origin_time": 1000000001,
            "bids": [[49999.0, 3.0], [49998.0, 2.0]],
            "asks": [[50001.0, 3.0], [50002.0, 2.0]],
            "is_snapshot": True
        },
        {
            "event_type": "TRADE",
            "origin_time": 1000000002,
            "trade_id": 124,
            "trade_price": 49999.0,
            "trade_quantity": 2.0,
            "trade_side": "SELL"  # Sell trade consumes bid liquidity
        }
    ]
    
    events_df = pl.DataFrame(events_data)
    result_df = replayer.execute(events_df)
    
    # Check that bid liquidity was reduced
    second_event_bids = result_df[1]["book_state"].to_list()[0][0]  # bids
    
    # First bid level should have reduced quantity (3.0 - 2.0 = 1.0)
    assert second_event_bids[0][1] == 100000000  # 1.0 scaled to int