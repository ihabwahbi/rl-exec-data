"""
Data ingestion module for loading Crypto Lake data formats.

Handles reading trades, book snapshots, and book deltas with proper schema validation
and decimal precision preservation.
"""
from collections.abc import Iterator
from enum import Enum
from pathlib import Path
from typing import ClassVar

import polars as pl
import pyarrow.parquet as pq
from loguru import logger

from .decimal_utils import ensure_decimal_precision


class EventType(Enum):
    """Market event types."""
    TRADE = "TRADE"
    BOOK_SNAPSHOT = "BOOK_SNAPSHOT"
    BOOK_DELTA = "BOOK_DELTA"


class DataIngestion:
    """Base class for data ingestion with common functionality."""

    def __init__(self, data_path: str | Path):
        """Initialize data ingestion.

        Args:
            data_path: Path to the data file or directory
        """
        self.data_path = Path(data_path)
        if not self.data_path.exists():
            raise ValueError(f"Data path does not exist: {self.data_path}")

    def _validate_required_columns(
        self, df: pl.DataFrame, required_columns: list[str]
    ) -> None:
        """Validate that DataFrame contains required columns.

        Args:
            df: DataFrame to validate
            required_columns: List of required column names

        Raises:
            ValueError: If required columns are missing
        """
        missing_columns = set(required_columns) - set(df.columns)
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")


class TradesReader(DataIngestion):
    """Reader for Crypto Lake trades data."""

    REQUIRED_COLUMNS: ClassVar[list[str]] = ["origin_time", "price", "quantity", "side"]
    OPTIONAL_COLUMNS: ClassVar[list[str]] = [
        "trade_id", "timestamp", "symbol", "exchange"
    ]

    def read(
        self, batch_size: int | None = None
    ) -> pl.DataFrame | Iterator[pl.DataFrame]:
        """Read trades data with schema validation.

        Args:
            batch_size: If provided, returns an iterator of batches

        Returns:
            DataFrame or iterator of DataFrames with trades data
        """
        logger.info(f"Reading trades data from {self.data_path}")

        if batch_size:
            return self._read_batched(batch_size)
        return self._read_all()

    def _read_all(self) -> pl.DataFrame:
        """Read all trades data at once."""
        df = pl.read_parquet(self.data_path)
        self._validate_required_columns(df, self.REQUIRED_COLUMNS)

        # Convert price and quantity to decimal128(38,18) for precision
        df = ensure_decimal_precision(df, ["price", "quantity"])
        df = df.with_columns(pl.lit(EventType.TRADE.value).alias("event_type"))

        logger.info(f"Read {len(df)} trade records")
        return df

    def _read_batched(self, batch_size: int) -> Iterator[pl.DataFrame]:
        """Read trades data in batches."""
        parquet_file = pq.ParquetFile(self.data_path)

        for batch in parquet_file.iter_batches(batch_size=batch_size):
            df = pl.from_arrow(batch)
            self._validate_required_columns(df, self.REQUIRED_COLUMNS)

            # Convert price and quantity to decimal128(38,18) for precision
            df = ensure_decimal_precision(df, ["price", "quantity"])
            df = df.with_columns(pl.lit(EventType.TRADE.value).alias("event_type"))

            yield df


class BookSnapshotReader(DataIngestion):
    """Reader for Crypto Lake book snapshot data."""

    REQUIRED_COLUMNS: ClassVar[list[str]] = [
        "origin_time", "timestamp", "symbol", "exchange"
    ]

    def read(
        self, batch_size: int | None = None
    ) -> pl.DataFrame | Iterator[pl.DataFrame]:
        """Read book snapshot data with schema validation.

        Args:
            batch_size: If provided, returns an iterator of batches

        Returns:
            DataFrame or iterator of DataFrames with book snapshot data
        """
        logger.info(f"Reading book snapshot data from {self.data_path}")

        if batch_size:
            return self._read_batched(batch_size)
        return self._read_all()

    def _read_all(self) -> pl.DataFrame:
        """Read all book snapshot data at once."""
        df = pl.read_parquet(self.data_path)
        self._validate_required_columns(df, self.REQUIRED_COLUMNS)

        # Convert all bid/ask price and quantity columns to decimal128(38,18)
        decimal_cols = []
        for i in range(20):  # 0-19 levels
            for col_type in ["bid", "ask"]:
                for suffix in ["price", "amount"]:
                    col_name = f"{col_type}_{i}_{suffix}"
                    if col_name in df.columns:
                        decimal_cols.append(col_name)
        
        df = ensure_decimal_precision(df, decimal_cols)
        df = df.with_columns(pl.lit(EventType.BOOK_SNAPSHOT.value).alias("event_type"))

        logger.info(f"Read {len(df)} book snapshot records")
        return df

    def _read_batched(self, batch_size: int) -> Iterator[pl.DataFrame]:
        """Read book snapshot data in batches."""
        parquet_file = pq.ParquetFile(self.data_path)

        for batch in parquet_file.iter_batches(batch_size=batch_size):
            df = pl.from_arrow(batch)
            self._validate_required_columns(df, self.REQUIRED_COLUMNS)

            # Convert all bid/ask price and quantity columns to decimal128(38,18)
            decimal_cols = []
            for i in range(20):  # 0-19 levels
                for col_type in ["bid", "ask"]:
                    for suffix in ["price", "amount"]:
                        col_name = f"{col_type}_{i}_{suffix}"
                        if col_name in df.columns:
                            decimal_cols.append(col_name)
            
            df = ensure_decimal_precision(df, decimal_cols)
            df = df.with_columns(pl.lit(EventType.BOOK_SNAPSHOT.value).alias("event_type"))

            yield df


class BookDeltaV2Reader(DataIngestion):
    """Reader for Crypto Lake book delta v2 data."""

    REQUIRED_COLUMNS: ClassVar[list[str]] = [
        "origin_time", "update_id", "price", "new_quantity", "side"
    ]

    def read(
        self, batch_size: int | None = None
    ) -> pl.DataFrame | Iterator[pl.DataFrame]:
        """Read book delta v2 data with schema validation.

        Args:
            batch_size: If provided, returns an iterator of batches

        Returns:
            DataFrame or iterator of DataFrames with book delta data
        """
        logger.info(f"Reading book delta v2 data from {self.data_path}")

        if batch_size:
            return self._read_batched(batch_size)
        return self._read_all()

    def _read_all(self) -> pl.DataFrame:
        """Read all book delta data at once."""
        df = pl.read_parquet(self.data_path)
        self._validate_required_columns(df, self.REQUIRED_COLUMNS)

        # Convert price and new_quantity to decimal128(38,18) for precision
        df = ensure_decimal_precision(df, ["price", "new_quantity"])
        df = df.with_columns(pl.lit(EventType.BOOK_DELTA.value).alias("event_type"))

        logger.info(f"Read {len(df)} book delta records")
        return df

    def _read_batched(self, batch_size: int) -> Iterator[pl.DataFrame]:
        """Read book delta data in batches."""
        parquet_file = pq.ParquetFile(self.data_path)

        for batch in parquet_file.iter_batches(batch_size=batch_size):
            df = pl.from_arrow(batch)
            self._validate_required_columns(df, self.REQUIRED_COLUMNS)

            # Convert price and new_quantity to decimal128(38,18) for precision
            df = ensure_decimal_precision(df, ["price", "new_quantity"])
            df = df.with_columns(pl.lit(EventType.BOOK_DELTA.value).alias("event_type"))

            yield df
