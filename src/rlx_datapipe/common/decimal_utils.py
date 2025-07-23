"""Decimal precision utilities using scaled int64 arithmetic."""

import numpy as np
import pyarrow as pa
from numba import jit
from typing import Union


# Scaling factor for int64 representation (8 decimal places)
PRICE_SCALE = 100_000_000  # 10^8
QUANTITY_SCALE = 100_000_000  # 10^8


@jit(nopython=True)
def float_to_scaled_int64(value: float, scale: int = PRICE_SCALE) -> np.int64:
    """
    Convert float to scaled int64.
    
    Args:
        value: Float value to convert
        scale: Scaling factor (default 10^8)
        
    Returns:
        Scaled int64 value
    """
    return np.int64(np.round(value * scale))


@jit(nopython=True)
def scaled_int64_to_float(value: np.int64, scale: int = PRICE_SCALE) -> float:
    """
    Convert scaled int64 back to float.
    
    Args:
        value: Scaled int64 value
        scale: Scaling factor (default 10^8)
        
    Returns:
        Float value
    """
    return float(value) / scale


def scaled_to_decimal128(value: Union[int, np.int64], scale: int = 8):
    """
    Convert scaled int64 to PyArrow Decimal128.
    
    Args:
        value: Scaled int64 value
        scale: Number of decimal places (default 8)
        
    Returns:
        PyArrow Decimal128 scalar
    """
    # Decimal128 type with precision 38, scale 8
    decimal_type = pa.decimal128(38, scale)
    return pa.scalar(value, type=decimal_type)


def decimal128_to_scaled(decimal_value) -> np.int64:
    """
    Convert PyArrow Decimal128 to scaled int64.
    
    Args:
        decimal_value: PyArrow Decimal128 value
        
    Returns:
        Scaled int64 value
    """
    # Extract the integer representation
    return np.int64(decimal_value.as_py())


@jit(nopython=True)
def calculate_mid_price(
    bid_price: np.int64,
    ask_price: np.int64,
) -> np.int64:
    """
    Calculate mid price from scaled bid/ask.
    
    Args:
        bid_price: Best bid price (scaled)
        ask_price: Best ask price (scaled)
        
    Returns:
        Mid price (scaled)
    """
    return (bid_price + ask_price) // 2


@jit(nopython=True)
def calculate_spread(
    bid_price: np.int64,
    ask_price: np.int64,
) -> np.int64:
    """
    Calculate spread from scaled bid/ask.
    
    Args:
        bid_price: Best bid price (scaled)
        ask_price: Best ask price (scaled)
        
    Returns:
        Spread (scaled)
    """
    return ask_price - bid_price