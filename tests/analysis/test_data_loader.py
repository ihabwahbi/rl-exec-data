"""Tests for data loading functions."""

import tempfile
from pathlib import Path

import polars as pl
import pytest
from rlx_datapipe.analysis.data_loader import (
    load_book_data,
    load_multiple_files,
    load_trades_data,
)


@pytest.fixture()
def sample_trades_data():
    """Create sample trades data for testing."""
    return pl.DataFrame(
        {
            "origin_time": [
                "2024-01-01T10:00:00",
                "2024-01-01T10:01:00",
                "2024-01-01T10:02:00",
            ],
            "trade_id": [1, 2, 3],
            "price": [45000.0, 45100.0, 45050.0],
            "quantity": [0.1, 0.2, 0.15],
            "side": ["buy", "sell", "buy"],
            "symbol": ["BTC-USDT", "BTC-USDT", "BTC-USDT"],
        }
    )


@pytest.fixture()
def sample_book_data():
    """Create sample book data for testing."""
    data = {
        "origin_time": ["2024-01-01T10:00:00", "2024-01-01T10:01:00"],
        "sequence_number": [1001, 1002],
        "symbol": ["BTC-USDT", "BTC-USDT"],
    }

    # Add bid columns (bid_0_price through bid_19_price, etc.)
    for i in range(20):
        data[f"bid_{i}_price"] = [45000.0 - i * 10, 45100.0 - i * 10]
        data[f"bid_{i}_size"] = [0.1 + i * 0.01, 0.2 + i * 0.01]
        data[f"ask_{i}_price"] = [45010.0 + i * 10, 45110.0 + i * 10]
        data[f"ask_{i}_size"] = [0.1 + i * 0.01, 0.2 + i * 0.01]

    return pl.DataFrame(data)


def test_load_trades_data_csv(sample_trades_data):
    """Test loading trades data from CSV file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "trades.csv"
        sample_trades_data.write_csv(file_path)

        df = load_trades_data(file_path)

        assert len(df) == 3
        assert "origin_time" in df.columns
        assert "trade_id" in df.columns
        assert "price" in df.columns
        assert "quantity" in df.columns
        assert "side" in df.columns


def test_load_trades_data_parquet(sample_trades_data):
    """Test loading trades data from Parquet file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "trades.parquet"
        sample_trades_data.write_parquet(file_path)

        df = load_trades_data(file_path)

        assert len(df) == 3
        assert "origin_time" in df.columns
        assert "trade_id" in df.columns


def test_load_trades_data_with_symbol_filter(sample_trades_data):
    """Test loading trades data with symbol filter."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Add some ETH-USDT data
        mixed_data = sample_trades_data.vstack(
            pl.DataFrame(
                {
                    "origin_time": ["2024-01-01T10:03:00"],
                    "trade_id": [4],
                    "price": [2500.0],
                    "quantity": [1.0],
                    "side": ["buy"],
                    "symbol": ["ETH-USDT"],
                }
            )
        )

        file_path = Path(temp_dir) / "trades.csv"
        mixed_data.write_csv(file_path)

        df = load_trades_data(file_path, symbol="BTC-USDT")

        assert len(df) == 3  # Only BTC-USDT trades
        assert all(df["symbol"] == "BTC-USDT")


def test_load_trades_data_with_date_filter(sample_trades_data):
    """Test loading trades data with date filter."""
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "trades.csv"
        sample_trades_data.write_csv(file_path)

        df = load_trades_data(
            file_path, date_filter=("2024-01-01T10:00:00", "2024-01-01T10:01:00")
        )

        assert len(df) == 2  # Only first two trades


def test_load_book_data_csv(sample_book_data):
    """Test loading book data from CSV file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "book.csv"
        sample_book_data.write_csv(file_path)

        df = load_book_data(file_path)

        assert len(df) == 2
        assert "origin_time" in df.columns
        assert "sequence_number" in df.columns
        assert "bid_0_price" in df.columns
        assert "ask_0_price" in df.columns
        assert "bid_19_price" in df.columns
        assert "ask_19_price" in df.columns


def test_load_book_data_parquet(sample_book_data):
    """Test loading book data from Parquet file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "book.parquet"
        sample_book_data.write_parquet(file_path)

        df = load_book_data(file_path)

        assert len(df) == 2
        assert "origin_time" in df.columns
        assert "sequence_number" in df.columns


def test_load_trades_data_file_not_found():
    """Test handling of missing files."""
    with pytest.raises(FileNotFoundError):
        load_trades_data("/nonexistent/file.csv")


def test_load_trades_data_unsupported_format(sample_trades_data):
    """Test handling of unsupported file formats."""
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "trades.txt"
        file_path.write_text("some text")

        with pytest.raises(ValueError, match="Unsupported file format"):
            load_trades_data(file_path)


def test_load_book_data_file_not_found():
    """Test handling of missing book files."""
    with pytest.raises(FileNotFoundError):
        load_book_data("/nonexistent/file.csv")


def test_load_multiple_files_trades(sample_trades_data):
    """Test loading multiple trades files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        file1 = Path(temp_dir) / "trades1.csv"
        file2 = Path(temp_dir) / "trades2.csv"

        # Split data into two files
        sample_trades_data[:2].write_csv(file1)
        sample_trades_data[2:].write_csv(file2)

        df = load_multiple_files([file1, file2], "trades")

        assert len(df) == 3
        assert "origin_time" in df.columns


def test_load_multiple_files_book(sample_book_data):
    """Test loading multiple book files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        file1 = Path(temp_dir) / "book1.csv"
        file2 = Path(temp_dir) / "book2.csv"

        # Split data into two files
        sample_book_data[:1].write_csv(file1)
        sample_book_data[1:].write_csv(file2)

        df = load_multiple_files([file1, file2], "book")

        assert len(df) == 2
        assert "origin_time" in df.columns
        assert "sequence_number" in df.columns


def test_load_multiple_files_invalid_type():
    """Test handling of invalid data type."""
    with pytest.raises(ValueError, match="data_type must be 'trades' or 'book'"):
        load_multiple_files([], "invalid_type")


def test_load_multiple_files_no_valid_files():
    """Test handling when no files can be loaded."""
    with pytest.raises(ValueError, match="No files were successfully loaded"):
        load_multiple_files(["/nonexistent1.csv", "/nonexistent2.csv"], "trades")
