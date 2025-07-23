"""Tests for order book state management."""

import numpy as np
import pytest

from rlx_datapipe.reconstruction.order_book_state import BoundedPriceLevel, OrderBookState


class TestBoundedPriceLevel:
    """Test bounded price level management."""
    
    def test_initialization(self):
        """Test initialization of bounded price levels."""
        # Test bid side
        bid_levels = BoundedPriceLevel(max_levels=5, is_bid_side=True)
        assert bid_levels.max_levels == 5
        assert bid_levels.is_bid_side is True
        assert bid_levels.top_count == 0
        assert len(bid_levels.deep_levels) == 0
        
        # Test ask side
        ask_levels = BoundedPriceLevel(max_levels=5, is_bid_side=False)
        assert ask_levels.max_levels == 5
        assert ask_levels.is_bid_side is False
        assert ask_levels.top_count == 0
        assert len(ask_levels.deep_levels) == 0
    
    def test_single_update(self):
        """Test single price level update."""
        levels = BoundedPriceLevel(max_levels=5, is_bid_side=True)
        
        # Add a level
        levels.update(100000000, 50000000)  # Price: 1.0, Quantity: 0.5
        
        assert levels.top_count == 1
        assert levels.top_prices[0] == 100000000
        assert levels.top_quantities[0] == 50000000
    
    def test_multiple_updates_bid_side(self):
        """Test multiple updates on bid side (descending order)."""
        levels = BoundedPriceLevel(max_levels=3, is_bid_side=True)
        
        # Add levels in random order
        levels.update(100000000, 10000000)  # 1.0
        levels.update(110000000, 20000000)  # 1.1
        levels.update(105000000, 15000000)  # 1.05
        
        # Check order is descending for bids
        assert levels.top_count == 3
        assert levels.top_prices[0] == 110000000  # 1.1
        assert levels.top_prices[1] == 105000000  # 1.05
        assert levels.top_prices[2] == 100000000  # 1.0
    
    def test_multiple_updates_ask_side(self):
        """Test multiple updates on ask side (ascending order)."""
        levels = BoundedPriceLevel(max_levels=3, is_bid_side=False)
        
        # Add levels in random order
        levels.update(100000000, 10000000)  # 1.0
        levels.update(110000000, 20000000)  # 1.1
        levels.update(105000000, 15000000)  # 1.05
        
        # Check order is ascending for asks
        assert levels.top_count == 3
        assert levels.top_prices[0] == 100000000  # 1.0
        assert levels.top_prices[1] == 105000000  # 1.05
        assert levels.top_prices[2] == 110000000  # 1.1
    
    def test_overflow_to_deep_levels(self):
        """Test overflow to deep levels when max_levels exceeded."""
        levels = BoundedPriceLevel(max_levels=2, is_bid_side=True)
        
        # Add more than max_levels
        levels.update(100000000, 10000000)  # 1.0
        levels.update(110000000, 20000000)  # 1.1
        levels.update(105000000, 15000000)  # 1.05
        levels.update(95000000, 5000000)    # 0.95
        
        # Top levels should have best 2 bids
        assert levels.top_count == 2
        assert levels.top_prices[0] == 110000000  # 1.1
        assert levels.top_prices[1] == 105000000  # 1.05
        
        # Worse bids should be in deep levels
        assert len(levels.deep_levels) == 2
        assert levels.deep_levels[100000000] == 10000000
        assert levels.deep_levels[95000000] == 5000000
    
    def test_remove_level(self):
        """Test removing a price level."""
        levels = BoundedPriceLevel(max_levels=3, is_bid_side=True)
        
        # Add levels
        levels.update(100000000, 10000000)
        levels.update(110000000, 20000000)
        levels.update(105000000, 15000000)
        
        # Remove middle level
        levels.update(105000000, 0)
        
        assert levels.top_count == 2
        assert levels.top_prices[0] == 110000000
        assert levels.top_prices[1] == 100000000
    
    def test_promote_from_deep(self):
        """Test promotion from deep levels when space available."""
        levels = BoundedPriceLevel(max_levels=2, is_bid_side=True)
        
        # Fill top levels and overflow to deep
        levels.update(100000000, 10000000)
        levels.update(110000000, 20000000)
        levels.update(105000000, 15000000)
        
        # Remove a top level
        levels.update(110000000, 0)
        
        # Best deep level should be promoted
        assert levels.top_count == 2
        assert levels.top_prices[0] == 105000000  # Promoted from deep
        assert levels.top_prices[1] == 100000000
        assert len(levels.deep_levels) == 0
    
    def test_update_existing_level(self):
        """Test updating quantity of existing level."""
        levels = BoundedPriceLevel(max_levels=3, is_bid_side=True)
        
        # Add level
        levels.update(100000000, 10000000)
        
        # Update same level
        levels.update(100000000, 25000000)
        
        assert levels.top_count == 1
        assert levels.top_prices[0] == 100000000
        assert levels.top_quantities[0] == 25000000


class TestOrderBookState:
    """Test full order book state management."""
    
    def test_initialization(self):
        """Test order book initialization."""
        book = OrderBookState("BTCUSDT", max_levels=20)
        
        assert book.symbol == "BTCUSDT"
        assert book.max_levels == 20
        assert book.last_update_id == 0
        assert book.bids.top_count == 0
        assert book.asks.top_count == 0
    
    def test_initialize_from_snapshot(self):
        """Test initializing from snapshot data."""
        book = OrderBookState("BTCUSDT", max_levels=5)
        
        # Create snapshot data
        bid_prices = np.array([110000000, 109000000, 108000000], dtype=np.int64)
        bid_quantities = np.array([10000000, 20000000, 30000000], dtype=np.int64)
        ask_prices = np.array([111000000, 112000000, 113000000], dtype=np.int64)
        ask_quantities = np.array([15000000, 25000000, 35000000], dtype=np.int64)
        
        book.initialize_from_snapshot(
            bid_prices=bid_prices,
            bid_quantities=bid_quantities,
            ask_prices=ask_prices,
            ask_quantities=ask_quantities,
            update_id=12345,
        )
        
        assert book.last_update_id == 12345
        assert book.bids.top_count == 3
        assert book.asks.top_count == 3
        
        # Check bid order
        assert book.bids.top_prices[0] == 110000000
        assert book.bids.top_prices[1] == 109000000
        assert book.bids.top_prices[2] == 108000000
        
        # Check ask order
        assert book.asks.top_prices[0] == 111000000
        assert book.asks.top_prices[1] == 112000000
        assert book.asks.top_prices[2] == 113000000
    
    def test_apply_delta(self):
        """Test applying delta updates."""
        book = OrderBookState("BTCUSDT", max_levels=5)
        
        # Apply bid delta
        book.apply_delta(
            price=100000000,
            quantity=50000000,
            side="BID",
            update_id=1001,
        )
        
        assert book.last_update_id == 1001
        assert book.bids.top_count == 1
        assert book.bids.top_prices[0] == 100000000
        
        # Apply ask delta
        book.apply_delta(
            price=101000000,
            quantity=40000000,
            side="ASK",
            update_id=1002,
        )
        
        assert book.last_update_id == 1002
        assert book.asks.top_count == 1
        assert book.asks.top_prices[0] == 101000000
    
    def test_get_top_of_book(self):
        """Test getting best bid and ask."""
        book = OrderBookState("BTCUSDT", max_levels=5)
        
        # Empty book
        best_bid, best_ask = book.get_top_of_book()
        assert best_bid is None
        assert best_ask is None
        
        # Add levels
        book.apply_delta(100000000, 50000000, "BID", 1)
        book.apply_delta(101000000, 40000000, "ASK", 2)
        
        best_bid, best_ask = book.get_top_of_book()
        assert best_bid == (100000000, 50000000)
        assert best_ask == (101000000, 40000000)
    
    def test_remove_level_with_zero_quantity(self):
        """Test removing level by setting quantity to 0."""
        book = OrderBookState("BTCUSDT", max_levels=5)
        
        # Add levels
        book.apply_delta(100000000, 50000000, "BID", 1)
        book.apply_delta(101000000, 40000000, "ASK", 2)
        
        # Remove bid level
        book.apply_delta(100000000, 0, "BID", 3)
        
        best_bid, best_ask = book.get_top_of_book()
        assert best_bid is None
        assert best_ask == (101000000, 40000000)
    
    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        book = OrderBookState("BTCUSDT", max_levels=5)
        
        # Add some data
        book.apply_delta(100000000, 50000000, "BID", 1)
        book.apply_delta(101000000, 40000000, "ASK", 2)
        book.last_origin_time = 1234567890
        
        # Serialize
        state_dict = book.to_dict()
        
        # Deserialize
        restored = OrderBookState.from_dict(state_dict)
        
        assert restored.symbol == "BTCUSDT"
        assert restored.max_levels == 5
        assert restored.last_update_id == 2
        assert restored.last_origin_time == 1234567890
        
        # Check book state
        best_bid, best_ask = restored.get_top_of_book()
        assert best_bid == (100000000, 50000000)
        assert best_ask == (101000000, 40000000)
    
    def test_invalid_side(self):
        """Test handling of invalid side parameter."""
        book = OrderBookState("BTCUSDT", max_levels=5)
        
        with pytest.raises(ValueError, match="Invalid side"):
            book.apply_delta(100000000, 50000000, "INVALID", 1)