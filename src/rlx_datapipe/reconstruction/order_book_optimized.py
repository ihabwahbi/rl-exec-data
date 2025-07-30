"""Optimized order book operations using numba JIT compilation."""

import numpy as np
from numba import boolean, int64, jit


@jit(nopython=True)
def find_insert_position_bid(prices: np.ndarray, count: int, new_price: int64) -> int:
    """
    Find insertion position for bid (descending order).

    Args:
        prices: Array of bid prices (descending)
        count: Number of valid prices
        new_price: Price to insert

    Returns:
        Insertion position
    """
    for i in range(count):
        if new_price > prices[i]:
            return i
    return count


@jit(nopython=True)
def find_insert_position_ask(prices: np.ndarray, count: int, new_price: int64) -> int:
    """
    Find insertion position for ask (ascending order).

    Args:
        prices: Array of ask prices (ascending)
        count: Number of valid prices
        new_price: Price to insert

    Returns:
        Insertion position
    """
    for i in range(count):
        if new_price < prices[i]:
            return i
    return count


@jit(nopython=True)
def update_bounded_levels(
    prices: np.ndarray,
    quantities: np.ndarray,
    count: int,
    max_levels: int,
    price: int64,
    quantity: int64,
    is_bid: boolean,
) -> tuple[int, boolean]:
    """
    Update bounded price levels with JIT optimization.

    Args:
        prices: Price array
        quantities: Quantity array
        count: Current number of levels
        max_levels: Maximum levels allowed
        price: Price to update
        quantity: New quantity (0 to remove)
        is_bid: True for bid side

    Returns:
        Tuple of (new_count, was_updated)
    """
    # Handle removal
    if quantity == 0:
        for i in range(count):
            if prices[i] == price:
                # Shift remaining levels
                for j in range(i, count - 1):
                    prices[j] = prices[j + 1]
                    quantities[j] = quantities[j + 1]
                return count - 1, True
        return count, False

    # Check if price exists
    for i in range(count):
        if prices[i] == price:
            quantities[i] = quantity
            return count, True

    # Find insertion position
    if is_bid:
        insert_pos = find_insert_position_bid(prices, count, price)
    else:
        insert_pos = find_insert_position_ask(prices, count, price)

    # Check if it should be in top levels
    if count < max_levels:
        # Shift elements to make room
        for i in range(count, insert_pos, -1):
            prices[i] = prices[i - 1]
            quantities[i] = quantities[i - 1]

        # Insert new level
        prices[insert_pos] = price
        quantities[insert_pos] = quantity
        return count + 1, True

    # Check if it belongs in top levels when full
    if is_bid and insert_pos < max_levels or not is_bid and insert_pos < max_levels:
        # Shift elements, losing the worst
        for i in range(max_levels - 1, insert_pos, -1):
            prices[i] = prices[i - 1]
            quantities[i] = quantities[i - 1]

        prices[insert_pos] = price
        quantities[insert_pos] = quantity
        return count, True

    return count, False


@jit(nopython=True)
def calculate_book_metrics(
    bid_prices: np.ndarray,
    bid_quantities: np.ndarray,
    bid_count: int,
    ask_prices: np.ndarray,
    ask_quantities: np.ndarray,
    ask_count: int,
) -> tuple[int64, int64, int64, int64, int64]:
    """
    Calculate book metrics with JIT optimization.

    Returns:
        Tuple of (spread, mid_price, bid_depth, ask_depth, total_bid_volume)
    """
    if bid_count == 0 or ask_count == 0:
        return 0, 0, bid_count, ask_count, 0

    best_bid = bid_prices[0]
    best_ask = ask_prices[0]

    spread = best_ask - best_bid
    mid_price = (best_bid + best_ask) // 2

    # Calculate total bid volume
    total_bid_volume = int64(0)
    for i in range(bid_count):
        total_bid_volume += bid_quantities[i]

    return spread, mid_price, bid_count, ask_count, total_bid_volume


@jit(nopython=True)
def apply_delta_batch_optimized(
    bid_prices: np.ndarray,
    bid_quantities: np.ndarray,
    bid_count: int,
    ask_prices: np.ndarray,
    ask_quantities: np.ndarray,
    ask_count: int,
    max_levels: int,
    delta_prices: np.ndarray,
    delta_quantities: np.ndarray,
    delta_sides: np.ndarray,  # 0 for BID, 1 for ASK
    num_deltas: int,
) -> tuple[int, int, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Apply batch of deltas with JIT optimization.

    Returns:
        Tuple of (new_bid_count, new_ask_count, bid_top_prices, bid_top_quantities,
                 ask_top_prices, ask_top_quantities)
    """
    # Pre-allocate output arrays
    bid_top_prices = np.zeros(num_deltas, dtype=int64)
    bid_top_quantities = np.zeros(num_deltas, dtype=int64)
    ask_top_prices = np.zeros(num_deltas, dtype=int64)
    ask_top_quantities = np.zeros(num_deltas, dtype=int64)

    for i in range(num_deltas):
        price = delta_prices[i]
        quantity = delta_quantities[i]
        is_bid = delta_sides[i] == 0

        if is_bid:
            bid_count, _ = update_bounded_levels(
                bid_prices, bid_quantities, bid_count, max_levels, price, quantity, True
            )
        else:
            ask_count, _ = update_bounded_levels(
                ask_prices,
                ask_quantities,
                ask_count,
                max_levels,
                price,
                quantity,
                False,
            )

        # Record top of book
        if bid_count > 0:
            bid_top_prices[i] = bid_prices[0]
            bid_top_quantities[i] = bid_quantities[0]

        if ask_count > 0:
            ask_top_prices[i] = ask_prices[0]
            ask_top_quantities[i] = ask_quantities[0]

    return (
        bid_count,
        ask_count,
        bid_top_prices,
        bid_top_quantities,
        ask_top_prices,
        ask_top_quantities,
    )


@jit(nopython=True)
def validate_monotonic_sequence(update_ids: np.ndarray) -> tuple[int, int, int]:
    """
    Validate monotonic sequence with JIT optimization.

    Args:
        update_ids: Array of update IDs

    Returns:
        Tuple of (num_gaps, max_gap_size, first_gap_position)
    """
    if len(update_ids) == 0:
        return 0, 0, -1

    num_gaps = 0
    max_gap_size = 0
    first_gap_position = -1

    for i in range(1, len(update_ids)):
        expected = update_ids[i - 1] + 1
        actual = update_ids[i]

        if actual != expected:
            gap_size = actual - expected
            num_gaps += 1
            max_gap_size = max(max_gap_size, gap_size)

            if first_gap_position == -1:
                first_gap_position = i

    return num_gaps, max_gap_size, first_gap_position


@jit(nopython=True)
def calculate_drift_metrics(
    current_bid_prices: np.ndarray,
    current_bid_quantities: np.ndarray,
    current_bid_count: int,
    snapshot_bid_prices: np.ndarray,
    snapshot_bid_quantities: np.ndarray,
    snapshot_bid_count: int,
) -> tuple[int64, int64]:
    """
    Calculate drift between current state and snapshot.

    Returns:
        Tuple of (price_drift, quantity_drift)
    """
    price_drift = int64(0)
    quantity_drift = int64(0)

    min_count = min(current_bid_count, snapshot_bid_count)

    for i in range(min_count):
        price_drift += abs(current_bid_prices[i] - snapshot_bid_prices[i])
        quantity_drift += abs(current_bid_quantities[i] - snapshot_bid_quantities[i])

    return price_drift, quantity_drift
