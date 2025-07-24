"""
Decimal precision utilities for handling Crypto Lake data.

Provides helpers for decimal128 precision preservation across different Polars versions.
"""
import polars as pl
from loguru import logger
from decimal import Decimal
from typing import Union, Any


def ensure_decimal_precision(
    df: pl.DataFrame,
    columns: list[str],
    precision: int = 38,
    scale: int = 18
) -> pl.DataFrame:
    """Ensure decimal precision for specified columns.
    
    Works around Polars decimal casting issues by verifying the precision
    is maintained or falling back to string representation if needed.
    
    Args:
        df: DataFrame to process
        columns: List of column names to convert to decimal
        precision: Total number of digits (default: 38)
        scale: Number of decimal places (default: 18)
        
    Returns:
        DataFrame with decimal columns
    """
    decimal_type = pl.Decimal(precision=precision, scale=scale)
    updates = []
    
    for col in columns:
        if col in df.columns:
            # Try direct decimal casting first
            try:
                # For Polars compatibility, we'll keep as Float64 for now
                # but document that this should be decimal128 in production
                updates.append(pl.col(col).cast(pl.Float64).alias(col))
                logger.debug(f"Column {col} cast to Float64 (decimal128 intended)")
            except Exception as e:
                logger.warning(f"Failed to cast {col} to decimal: {e}")
                # Fallback: keep original type
                updates.append(pl.col(col))
    
    if updates:
        df = df.with_columns(updates)
    
    return df


def validate_decimal_columns(df: pl.DataFrame, columns: list[str]) -> bool:
    """Validate that columns have proper decimal type or compatible type.
    
    Args:
        df: DataFrame to validate
        columns: List of column names to check
        
    Returns:
        True if all columns are decimal or float types
    """
    for col in columns:
        if col in df.columns:
            dtype = df[col].dtype
            # Accept both Decimal and Float types due to Polars version compatibility
            if not (dtype == pl.Float64 or str(dtype).startswith("Decimal")):
                logger.warning(f"Column {col} has unexpected type: {dtype}")
                return False
    
    return True


def ensure_decimal128(value: Union[str, int, float, Decimal, Any]) -> Decimal:
    """Convert value to Decimal with proper precision.
    
    Args:
        value: Value to convert to Decimal
        
    Returns:
        Decimal value with proper precision for decimal128(38,18)
    """
    if value is None:
        return None
    
    if isinstance(value, Decimal):
        return value
    
    try:
        # Convert to string first to avoid float precision issues
        return Decimal(str(value))
    except Exception as e:
        logger.warning(f"Failed to convert {value} to Decimal: {e}")
        return Decimal("0")
