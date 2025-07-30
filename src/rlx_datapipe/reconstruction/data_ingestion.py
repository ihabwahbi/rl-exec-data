"""
Data ingestion module for loading Crypto Lake data formats.

Handles reading trades, book snapshots, and book deltas with proper schema validation
and decimal precision preservation.
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar

import polars as pl
import pyarrow.parquet as pq
from loguru import logger

from .decimal_utils import ensure_decimal_precision


class EventType(Enum):
    """Market event types."""

    TRADE = "TRADE"
    BOOK_SNAPSHOT = "BOOK_SNAPSHOT"
    BOOK_DELTA = "BOOK_DELTA"


class DataIngestionBase:
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


class TradesReader(DataIngestionBase):
    """Reader for Crypto Lake trades data."""

    REQUIRED_COLUMNS: ClassVar[list[str]] = ["origin_time", "price", "quantity", "side"]
    OPTIONAL_COLUMNS: ClassVar[list[str]] = [
        "trade_id",
        "timestamp",
        "symbol",
        "exchange",
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


class BookSnapshotsReader(DataIngestionBase):
    """Reader for Crypto Lake book snapshots data."""

    REQUIRED_COLUMNS: ClassVar[list[str]] = ["origin_time", "bids", "asks", "update_id"]
    OPTIONAL_COLUMNS: ClassVar[list[str]] = ["symbol", "exchange", "sequence"]

    def read(
        self, batch_size: int | None = None
    ) -> pl.DataFrame | Iterator[pl.DataFrame]:
        """Read book snapshots data with schema validation.

        Args:
            batch_size: If provided, returns an iterator of batches

        Returns:
            DataFrame or iterator of DataFrames with book snapshots data
        """
        logger.info(f"Reading book snapshots data from {self.data_path}")

        if batch_size:
            return self._read_batched(batch_size)
        return self._read_all()

    def _read_all(self) -> pl.DataFrame:
        """Read all book snapshots data at once."""
        df = pl.read_parquet(self.data_path)
        self._validate_required_columns(df, self.REQUIRED_COLUMNS)

        # Note: bids and asks are already arrays, no decimal conversion needed here
        df = df.with_columns(pl.lit(EventType.BOOK_SNAPSHOT.value).alias("event_type"))

        logger.info(f"Read {len(df)} book snapshot records")
        return df

    def _read_batched(self, batch_size: int) -> Iterator[pl.DataFrame]:
        """Read book snapshots data in batches."""
        parquet_file = pq.ParquetFile(self.data_path)

        for batch in parquet_file.iter_batches(batch_size=batch_size):
            df = pl.from_arrow(batch)
            self._validate_required_columns(df, self.REQUIRED_COLUMNS)

            # Note: bids and asks are already arrays, no decimal conversion needed here
            df = df.with_columns(
                pl.lit(EventType.BOOK_SNAPSHOT.value).alias("event_type")
            )

            yield df


class BookDeltasReader(DataIngestionBase):
    """Reader for Crypto Lake book deltas data."""

    REQUIRED_COLUMNS: ClassVar[list[str]] = [
        "origin_time",
        "update_id",
        "side",
        "price",
        "new_quantity",
    ]
    OPTIONAL_COLUMNS: ClassVar[list[str]] = ["symbol", "exchange", "sequence"]

    def read(
        self, batch_size: int | None = None
    ) -> pl.DataFrame | Iterator[pl.DataFrame]:
        """Read book deltas data with schema validation.

        Args:
            batch_size: If provided, returns an iterator of batches

        Returns:
            DataFrame or iterator of DataFrames with book deltas data
        """
        logger.info(f"Reading book deltas data from {self.data_path}")

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


class DataIngestion:
    """Unified data ingestion for streaming market data messages."""

    def __init__(self, input_path: Path, manifest_path: Path | None = None):
        """Initialize data ingestion.

        Args:
            input_path: Path to input data (file or directory)
            manifest_path: Optional manifest file specifying data files
        """
        self.input_path = Path(input_path)
        self.manifest_path = manifest_path
        self.current_file_index = 0
        self.data_files = self._discover_data_files()

    def _discover_data_files(self) -> list[Path]:
        """Discover data files to process."""
        files = []

        if self.manifest_path and self.manifest_path.exists():
            # Load files from manifest
            with open(self.manifest_path) as f:
                for line in f:
                    file_path = Path(line.strip())
                    if file_path.exists():
                        files.append(file_path)
        elif self.input_path.is_file():
            files.append(self.input_path)
        elif self.input_path.is_dir():
            # Find all parquet files
            files.extend(sorted(self.input_path.glob("**/*.parquet")))

        logger.info(f"Discovered {len(files)} data files to process")
        return files

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        """Read messages from data files in streaming fashion.

        Yields:
            Dictionary containing message data with event_type field
        """
        for data_file in self.data_files:
            logger.info(f"Processing file: {data_file}")

            # Determine file type from name or content
            if "trade" in str(data_file).lower():
                reader = TradesReader(data_file)
            elif "snapshot" in str(data_file).lower():
                reader = BookSnapshotsReader(data_file)
            elif "delta" in str(data_file).lower():
                reader = BookDeltasReader(data_file)
            else:
                # Try to infer from content
                reader = self._infer_reader(data_file)

            if reader:
                # Read in batches for memory efficiency
                batch_size = 10000
                for batch_df in reader.read(batch_size=batch_size):
                    # Convert each row to a dictionary message
                    for row in batch_df.iter_rows(named=True):
                        # Ensure event_type is set
                        if "event_type" not in row:
                            row["event_type"] = self._infer_event_type(row)

                        # Add symbol if not present
                        if "symbol" not in row and hasattr(self, "symbol"):
                            row["symbol"] = self.symbol

                        yield row

                    # Allow other coroutines to run
                    await asyncio.sleep(0)

    def _infer_reader(self, data_file: Path) -> DataIngestionBase | None:
        """Infer the appropriate reader based on file content."""
        try:
            # Read a small sample to check columns
            sample_df = pl.read_parquet(data_file, n_rows=10)
            columns = set(sample_df.columns)

            if "trade_id" in columns or (
                "price" in columns and "quantity" in columns and "side" in columns
            ):
                return TradesReader(data_file)
            if "bids" in columns and "asks" in columns:
                return BookSnapshotsReader(data_file)
            if (
                "update_id" in columns
                and "side" in columns
                and "new_quantity" in columns
            ):
                return BookDeltasReader(data_file)

        except Exception as e:
            logger.warning(f"Could not infer reader for {data_file}: {e}")

        return None

    def _infer_event_type(self, row: dict[str, Any]) -> str:
        """Infer event type from row data."""
        if "trade_id" in row:
            return EventType.TRADE.value
        if "bids" in row and "asks" in row:
            return EventType.BOOK_SNAPSHOT.value
        if "update_id" in row and "side" in row:
            return EventType.BOOK_DELTA.value
        return "UNKNOWN"


# Aliases for backward compatibility
BookDeltaV2Reader = BookDeltasReader
BookSnapshotReader = BookSnapshotsReader
