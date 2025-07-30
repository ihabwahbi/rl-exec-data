"""Order book state management with bounded levels."""

import numpy as np


class BoundedPriceLevel:
    """Manages bounded price levels for one side of the book."""

    def __init__(self, max_levels: int, is_bid_side: bool):
        """
        Initialize bounded price level container.

        Args:
            max_levels: Maximum number of levels to track
            is_bid_side: True for bid side, False for ask side
        """
        self.max_levels = max_levels
        self.is_bid_side = is_bid_side

        # Use contiguous arrays for top levels (optimized access)
        self.top_prices = np.zeros(max_levels, dtype=np.int64)
        self.top_quantities = np.zeros(max_levels, dtype=np.int64)
        self.top_count = 0

        # Hash map for deep levels beyond max_levels
        self.deep_levels: dict[int, int] = {}

    def update(self, price: int, quantity: int) -> None:
        """
        Update a price level.

        Args:
            price: Price in scaled int64 format
            quantity: Quantity (0 means remove level)
        """
        if quantity == 0:
            self._remove_level(price)
        else:
            self._update_level(price, quantity)

    def _update_level(self, price: int, quantity: int) -> None:
        """Update or insert a price level."""
        # Check if price already exists in top levels
        for i in range(self.top_count):
            if self.top_prices[i] == price:
                self.top_quantities[i] = quantity
                return

        # Check if it belongs in top levels
        if self._should_be_in_top(price):
            self._insert_in_top(price, quantity)
        else:
            # Store in deep levels
            self.deep_levels[price] = quantity

    def _remove_level(self, price: int) -> None:
        """Remove a price level."""
        # Check top levels
        for i in range(self.top_count):
            if self.top_prices[i] == price:
                # Shift remaining levels
                for j in range(i, self.top_count - 1):
                    self.top_prices[j] = self.top_prices[j + 1]
                    self.top_quantities[j] = self.top_quantities[j + 1]

                self.top_count -= 1

                # Try to promote from deep levels
                self._promote_from_deep()
                return

        # Remove from deep levels if exists
        self.deep_levels.pop(price, None)

    def _should_be_in_top(self, price: int) -> bool:
        """Check if price should be in top levels."""
        if self.top_count < self.max_levels:
            return True

        if self.is_bid_side:
            # For bids, check if price is higher than lowest top bid
            return price > self.top_prices[self.top_count - 1]
        else:
            # For asks, check if price is lower than highest top ask
            return price < self.top_prices[self.top_count - 1]

    def _insert_in_top(self, price: int, quantity: int) -> None:
        """Insert price level in top levels maintaining order."""
        # Find insertion position
        insert_pos = self.top_count

        if self.is_bid_side:
            # Bids are sorted descending
            for i in range(self.top_count):
                if price > self.top_prices[i]:
                    insert_pos = i
                    break
        else:
            # Asks are sorted ascending
            for i in range(self.top_count):
                if price < self.top_prices[i]:
                    insert_pos = i
                    break

        # If we're at max capacity, move last to deep
        if self.top_count == self.max_levels:
            last_price = self.top_prices[self.max_levels - 1]
            last_quantity = self.top_quantities[self.max_levels - 1]
            self.deep_levels[last_price] = last_quantity
            self.top_count = self.max_levels - 1

        # Shift elements to make room
        for i in range(self.top_count, insert_pos, -1):
            self.top_prices[i] = self.top_prices[i - 1]
            self.top_quantities[i] = self.top_quantities[i - 1]

        # Insert new level
        self.top_prices[insert_pos] = price
        self.top_quantities[insert_pos] = quantity
        self.top_count += 1

    def _promote_from_deep(self) -> None:
        """Promote best level from deep to top if space available."""
        if self.top_count >= self.max_levels or not self.deep_levels:
            return

        # Find best deep level efficiently
        try:
            if self.is_bid_side:
                best_price = max(self.deep_levels.keys())
            else:
                best_price = min(self.deep_levels.keys())

            best_quantity = self.deep_levels.pop(best_price)
            self._insert_in_top(best_price, best_quantity)
        except ValueError:
            # Handle case where deep_levels becomes empty during operation
            pass

    def get_levels(self) -> list[tuple[int, int]]:
        """Get all top levels as list of (price, quantity) tuples."""
        levels = []
        for i in range(self.top_count):
            levels.append((self.top_prices[i], self.top_quantities[i]))
        return levels

    def get_depth(self) -> int:
        """Get total number of levels (top + deep)."""
        return self.top_count + len(self.deep_levels)

    def clear(self) -> None:
        """Clear all levels."""
        self.top_prices.fill(0)
        self.top_quantities.fill(0)
        self.top_count = 0
        self.deep_levels.clear()


class OrderBookState:
    """Manages full order book state with bid and ask sides."""

    def __init__(self, symbol: str = "BTCUSDT", max_levels: int = 20):
        """
        Initialize order book state.

        Args:
            symbol: Trading symbol
            max_levels: Maximum levels per side
        """
        self.symbol = symbol
        self.max_levels = max_levels

        # Bid and ask sides
        self.bids = BoundedPriceLevel(max_levels, is_bid_side=True)
        self.asks = BoundedPriceLevel(max_levels, is_bid_side=False)

        # Last update tracking
        self.last_update_id = 0
        self.last_origin_time = 0

        # Track initialization state
        self.initialized = False

    def initialize_from_snapshot(
        self,
        snapshot: dict,
        update_id: int | None = None,
    ) -> None:
        """
        Initialize book state from snapshot data.

        Args:
            snapshot: Dict with 'bids' and 'asks' lists or arrays
            update_id: Optional snapshot update ID
        """
        # Handle both dict format and array format
        if isinstance(snapshot, dict):
            # Clear existing state
            self.bids.clear()
            self.asks.clear()

            # Load bid levels
            if "bids" in snapshot and snapshot["bids"] is not None:
                for level in snapshot["bids"]:
                    if isinstance(level, list) and len(level) >= 2:
                        # Handle Decimal objects properly
                        if hasattr(level[0], "__float__"):
                            price = float(level[0]) * 1e8
                            quantity = float(level[1]) * 1e8
                        else:
                            price = float(level[0]) * 1e8
                            quantity = float(level[1]) * 1e8
                        if quantity > 0:
                            self.bids.update(int(price), int(quantity))

            # Load ask levels
            if "asks" in snapshot and snapshot["asks"] is not None:
                for level in snapshot["asks"]:
                    if isinstance(level, list) and len(level) >= 2:
                        # Handle Decimal objects properly
                        if hasattr(level[0], "__float__"):
                            price = float(level[0]) * 1e8
                            quantity = float(level[1]) * 1e8
                        else:
                            price = float(level[0]) * 1e8
                            quantity = float(level[1]) * 1e8
                        if quantity > 0:
                            self.asks.update(int(price), int(quantity))

            self.initialized = True

        else:
            # Legacy array format support
            bid_prices = snapshot
            bid_quantities = update_id  # This was the second param
            # We don't have ask data in this format, so skip
            for price, quantity in zip(bid_prices, bid_quantities, strict=False):
                if quantity > 0:
                    self.bids.update(int(price), int(quantity))

        if update_id is not None and isinstance(update_id, int):
            self.last_update_id = update_id

    def apply_delta(
        self,
        price: int,
        quantity: int,
        side: str,
        update_id: int,
    ) -> None:
        """
        Apply a delta update to the book.

        Args:
            price: Price level (scaled int64)
            quantity: New quantity (0 means remove)
            side: "BID" or "ASK"
            update_id: Update ID for sequencing
        """
        if side == "BID":
            self.bids.update(price, quantity)
        elif side == "ASK":
            self.asks.update(price, quantity)
        else:
            raise ValueError(f"Invalid side: {side}")

        self.last_update_id = update_id

    def get_top_of_book(self) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
        """
        Get best bid and ask.

        Returns:
            Tuple of (best_bid, best_ask) where each is (price, quantity) or None
        """
        best_bid: tuple[int, int] | None = None
        if self.bids.top_count > 0:
            best_bid = (int(self.bids.top_prices[0]), int(self.bids.top_quantities[0]))

        best_ask: tuple[int, int] | None = None
        if self.asks.top_count > 0:
            best_ask = (int(self.asks.top_prices[0]), int(self.asks.top_quantities[0]))

        return best_bid, best_ask

    def get_current_state(self) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
        """
        Get current book state.

        Returns:
            Tuple of (bid_levels, ask_levels)
        """
        return self.bids.get_levels(), self.asks.get_levels()

    def get_book_depth(self) -> tuple[int, int]:
        """
        Get depth of both sides.

        Returns:
            Tuple of (bid_depth, ask_depth)
        """
        return self.bids.get_depth(), self.asks.get_depth()

    def to_dict(self) -> dict:
        """Convert state to dictionary for checkpointing."""
        return {
            "symbol": self.symbol,
            "max_levels": self.max_levels,
            "last_update_id": self.last_update_id,
            "last_origin_time": self.last_origin_time,
            "bids": {
                "top_prices": self.bids.top_prices.tolist(),
                "top_quantities": self.bids.top_quantities.tolist(),
                "top_count": self.bids.top_count,
                "deep_levels": dict(self.bids.deep_levels),
            },
            "asks": {
                "top_prices": self.asks.top_prices.tolist(),
                "top_quantities": self.asks.top_quantities.tolist(),
                "top_count": self.asks.top_count,
                "deep_levels": dict(self.asks.deep_levels),
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OrderBookState":
        """Create instance from dictionary."""
        state = cls(data["symbol"], data["max_levels"])
        state.last_update_id = data["last_update_id"]
        state.last_origin_time = data["last_origin_time"]

        # Restore bid side
        bid_data = data["bids"]
        state.bids.top_prices = np.array(bid_data["top_prices"], dtype=np.int64)
        state.bids.top_quantities = np.array(bid_data["top_quantities"], dtype=np.int64)
        state.bids.top_count = bid_data["top_count"]
        state.bids.deep_levels = dict(bid_data["deep_levels"])

        # Restore ask side
        ask_data = data["asks"]
        state.asks.top_prices = np.array(ask_data["top_prices"], dtype=np.int64)
        state.asks.top_quantities = np.array(ask_data["top_quantities"], dtype=np.int64)
        state.asks.top_count = ask_data["top_count"]
        state.asks.deep_levels = dict(ask_data["deep_levels"])

        return state

    def get_best_bid(self) -> tuple[float, float] | None:
        """Get best bid price and quantity.

        Returns:
            Tuple of (price, quantity) or None if no bids
        """
        if self.bids.top_count > 0:
            # Convert from scaled int to float
            price = float(self.bids.top_prices[0]) / 1e8
            quantity = float(self.bids.top_quantities[0]) / 1e8
            return (price, quantity)
        return None

    def get_best_ask(self) -> tuple[float, float] | None:
        """Get best ask price and quantity.

        Returns:
            Tuple of (price, quantity) or None if no asks
        """
        if self.asks.top_count > 0:
            # Convert from scaled int to float
            price = float(self.asks.top_prices[0]) / 1e8
            quantity = float(self.asks.top_quantities[0]) / 1e8
            return (price, quantity)
        return None

    def get_spread(self) -> float | None:
        """Get bid-ask spread.

        Returns:
            Spread amount or None if either side is empty
        """
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()

        if best_bid and best_ask:
            return best_ask[0] - best_bid[0]
        return None

    def get_bid_levels(self) -> list[tuple[float, float]]:
        """Get all bid levels as (price, quantity) tuples.

        Returns:
            List of bid levels with prices and quantities as floats
        """
        levels = []
        for price_int, qty_int in self.bids.get_levels():
            price = float(price_int) / 1e8
            quantity = float(qty_int) / 1e8
            levels.append((price, quantity))
        return levels

    def get_ask_levels(self) -> list[tuple[float, float]]:
        """Get all ask levels as (price, quantity) tuples.

        Returns:
            List of ask levels with prices and quantities as floats
        """
        levels = []
        for price_int, qty_int in self.asks.get_levels():
            price = float(price_int) / 1e8
            quantity = float(qty_int) / 1e8
            levels.append((price, quantity))
        return levels

    def apply_trade(self, trade: dict) -> None:
        """Apply trade event to order book (liquidity consumption).

        Args:
            trade: Trade event with price, quantity, and side
        """
        price = float(trade["price"])
        quantity = float(trade["quantity"])
        side = trade["side"]

        # Convert to scaled int
        price_int = int(price * 1e8)
        quantity_int = int(quantity * 1e8)

        if side == "BUY":
            # Buy trade consumes ask liquidity
            # For simplicity, we reduce quantity at best ask
            if self.asks.top_count > 0 and self.asks.top_prices[0] <= price_int:
                remaining = self.asks.top_quantities[0] - quantity_int
                if remaining > 0:
                    self.asks.top_quantities[0] = remaining
                else:
                    # Remove level if fully consumed
                    self.asks._remove_level(self.asks.top_prices[0])

        elif side == "SELL":
            # Sell trade consumes bid liquidity
            # For simplicity, we reduce quantity at best bid
            if self.bids.top_count > 0 and self.bids.top_prices[0] >= price_int:
                remaining = self.bids.top_quantities[0] - quantity_int
                if remaining > 0:
                    self.bids.top_quantities[0] = remaining
                else:
                    # Remove level if fully consumed
                    self.bids._remove_level(self.bids.top_prices[0])

    def resynchronize(self, snapshot: dict) -> None:
        """Resynchronize book state from snapshot.

        Args:
            snapshot: Snapshot event with bids and asks
        """
        # Clear existing state
        self.bids.clear()
        self.asks.clear()

        # Load new state from snapshot
        if snapshot.get("bids"):
            for level in snapshot["bids"]:
                if isinstance(level, list) and len(level) >= 2:
                    price = float(level[0]) * 1e8
                    quantity = float(level[1]) * 1e8
                    self.bids.update(int(price), int(quantity))

        if snapshot.get("asks"):
            for level in snapshot["asks"]:
                if isinstance(level, list) and len(level) >= 2:
                    price = float(level[0]) * 1e8
                    quantity = float(level[1]) * 1e8
                    self.asks.update(int(price), int(quantity))

        self.initialized = True
