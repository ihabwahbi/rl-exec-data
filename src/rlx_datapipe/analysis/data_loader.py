"""Data loading functions for Crypto Lake format."""

from pathlib import Path

import polars as pl
from loguru import logger


def load_trades_data(
    file_path: str | Path,
    symbol: str = "BTC-USDT",
    date_filter: tuple[str, str] | None = None,
) -> pl.DataFrame:
    """Load trades data from Crypto Lake format.

    Args:
        file_path: Path to the trades data file (CSV or Parquet)
        symbol: Trading symbol to filter for (default: BTC-USDT)
        date_filter: Optional tuple of (start_date, end_date) in YYYY-MM-DD format

    Returns:
        Polars DataFrame with trades data

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the file format is unsupported
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    logger.info(f"Loading trades data from {file_path}")

    # Determine file format and load accordingly
    if file_path.suffix.lower() == ".csv":
        df = pl.read_csv(file_path)
    elif file_path.suffix.lower() == ".parquet":
        df = pl.read_parquet(file_path)
    else:
        raise ValueError(f"Unsupported file format: {file_path.suffix}")

    logger.info(f"Loaded {len(df)} rows from {file_path}")

    # Filter by symbol if specified
    if symbol and "symbol" in df.columns:
        df = df.filter(pl.col("symbol") == symbol)
        logger.info(f"Filtered to {len(df)} rows for symbol {symbol}")

    # Apply date filter if specified
    if date_filter and "origin_time" in df.columns:
        start_date, end_date = date_filter
        df = df.filter(
            (pl.col("origin_time") >= start_date) & (pl.col("origin_time") <= end_date)
        )
        logger.info(
            f"Filtered to {len(df)} rows for date range {start_date} to {end_date}"
        )

    # Validate expected columns for trades data
    expected_columns = ["origin_time", "trade_id", "price", "quantity", "side"]
    missing_columns = [col for col in expected_columns if col not in df.columns]

    if missing_columns:
        logger.warning(f"Missing expected columns: {missing_columns}")
        logger.info(f"Available columns: {df.columns}")

    logger.info(
        f"Successfully loaded trades data with {len(df)} rows and "
        f"{len(df.columns)} columns"
    )

    return df


def load_book_data(
    file_path: str | Path,
    symbol: str = "BTC-USDT",
    date_filter: tuple[str, str] | None = None,
) -> pl.DataFrame:
    """Load L2 book snapshot data from Crypto Lake format.

    Args:
        file_path: Path to the book data file (CSV or Parquet)
        symbol: Trading symbol to filter for (default: BTC-USDT)
        date_filter: Optional tuple of (start_date, end_date) in YYYY-MM-DD format

    Returns:
        Polars DataFrame with book data

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the file format is unsupported
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    logger.info(f"Loading book data from {file_path}")

    # Determine file format and load accordingly
    if file_path.suffix.lower() == ".csv":
        df = pl.read_csv(file_path)
    elif file_path.suffix.lower() == ".parquet":
        df = pl.read_parquet(file_path)
    else:
        raise ValueError(f"Unsupported file format: {file_path.suffix}")

    logger.info(f"Loaded {len(df)} rows from {file_path}")

    # Filter by symbol if specified
    if symbol and "symbol" in df.columns:
        df = df.filter(pl.col("symbol") == symbol)
        logger.info(f"Filtered to {len(df)} rows for symbol {symbol}")

    # Apply date filter if specified
    if date_filter and "origin_time" in df.columns:
        start_date, end_date = date_filter
        df = df.filter(
            (pl.col("origin_time") >= start_date) & (pl.col("origin_time") <= end_date)
        )
        logger.info(
            f"Filtered to {len(df)} rows for date range {start_date} to {end_date}"
        )

    # Validate expected columns for book data (wide format)
    expected_base_columns = ["origin_time", "sequence_number"]

    # Check for bid/ask columns (bid_0_price through bid_19_price, etc.)
    bid_price_columns = [f"bid_{i}_price" for i in range(20)]
    bid_size_columns = [f"bid_{i}_size" for i in range(20)]
    ask_price_columns = [f"ask_{i}_price" for i in range(20)]
    ask_size_columns = [f"ask_{i}_size" for i in range(20)]

    expected_columns = (
        expected_base_columns
        + bid_price_columns
        + bid_size_columns
        + ask_price_columns
        + ask_size_columns
    )

    missing_base_columns = [
        col for col in expected_base_columns if col not in df.columns
    ]

    if missing_base_columns:
        logger.warning(f"Missing expected base columns: {missing_base_columns}")

    # Count how many bid/ask levels are present
    bid_levels = sum(1 for col in bid_price_columns if col in df.columns)
    ask_levels = sum(1 for col in ask_price_columns if col in df.columns)

    logger.info(f"Book data has {bid_levels} bid levels and {ask_levels} ask levels")
    logger.info(f"Available columns: {len(df.columns)} total")

    logger.info(
        f"Successfully loaded book data with {len(df)} rows and "
        f"{len(df.columns)} columns"
    )

    return df


def load_multiple_files(
    file_paths: list[str | Path],
    data_type: str,
    symbol: str = "BTC-USDT",
    date_filter: tuple[str, str] | None = None,
) -> pl.DataFrame:
    """Load and concatenate multiple data files.

    Args:
        file_paths: List of file paths to load
        data_type: Type of data ('trades' or 'book')
        symbol: Trading symbol to filter for (default: BTC-USDT)
        date_filter: Optional tuple of (start_date, end_date) in YYYY-MM-DD format

    Returns:
        Concatenated Polars DataFrame

    Raises:
        ValueError: If data_type is not 'trades' or 'book'
    """
    if data_type not in ["trades", "book"]:
        raise ValueError(f"data_type must be 'trades' or 'book', got: {data_type}")

    logger.info(f"Loading {len(file_paths)} {data_type} files")

    dataframes = []

    for file_path in file_paths:
        try:
            if data_type == "trades":
                df = load_trades_data(file_path, symbol, date_filter)
            else:
                df = load_book_data(file_path, symbol, date_filter)

            dataframes.append(df)

        except Exception as e:
            logger.error(f"Failed to load {file_path}: {e}")
            continue

    if not dataframes:
        raise ValueError("No files were successfully loaded")

    # Concatenate all dataframes
    combined_df = pl.concat(dataframes)

    logger.info(f"Combined {len(dataframes)} files into {len(combined_df)} total rows")

    return combined_df
