"""Tests for origin_time analyzer."""

import tempfile
from pathlib import Path

import pytest
from rlx_datapipe.analysis.origin_time_analyzer import OriginTimeAnalyzer


@pytest.fixture()
def sample_trades_file():
    """Create a sample trades file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        # Write CSV header and data
        f.write("origin_time,trade_id,price,quantity,side,symbol\n")
        f.write("2024-01-01T10:00:00,1,45000.0,0.1,buy,BTC-USDT\n")
        f.write("2024-01-01T10:01:00,2,45100.0,0.2,sell,BTC-USDT\n")
        f.write("2024-01-01T10:02:00,3,45050.0,0.15,buy,BTC-USDT\n")
        f.flush()
        yield Path(f.name)

    # Clean up
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture()
def sample_book_file():
    """Create a sample book file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        # Write CSV header
        header = ["origin_time", "sequence_number", "symbol"]

        # Add bid/ask columns
        for i in range(20):
            header.extend(
                [f"bid_{i}_price", f"bid_{i}_size", f"ask_{i}_price", f"ask_{i}_size"]
            )

        f.write(",".join(header) + "\n")

        # Write sample data
        for seq in [1001, 1002]:
            row = [f"2024-01-01T10:0{seq-1000}:00", str(seq), "BTC-USDT"]

            # Add bid/ask data
            for i in range(20):
                bid_price = 45000.0 - i * 10
                bid_size = 0.1 + i * 0.01
                ask_price = 45010.0 + i * 10
                ask_size = 0.1 + i * 0.01
                row.extend(
                    [str(bid_price), str(bid_size), str(ask_price), str(ask_size)]
                )

            f.write(",".join(row) + "\n")

        f.flush()
        yield Path(f.name)

    # Clean up
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture()
def analyzer():
    """Create analyzer instance for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield OriginTimeAnalyzer(
            output_path=Path(temp_dir),
            log_level="ERROR",  # Reduce log noise during tests
        )


def test_analyzer_initialization():
    """Test analyzer initialization."""
    with tempfile.TemporaryDirectory() as temp_dir:
        analyzer = OriginTimeAnalyzer(output_path=Path(temp_dir))
        assert analyzer.validator is not None
        assert analyzer.report_generator is not None


def test_analyze_single_file_trades(analyzer, sample_trades_file):
    """Test analyzing a single trades file."""
    result = analyzer.analyze_single_file(sample_trades_file, "trades")

    assert result["data_type"] == "trades"
    assert result["total_rows"] == 3
    assert result["valid_count"] == 3
    assert result["valid_percentage"] == 100.0


def test_analyze_single_file_book(analyzer, sample_book_file):
    """Test analyzing a single book file."""
    result = analyzer.analyze_single_file(sample_book_file, "book")

    assert result["data_type"] == "book"
    assert result["total_rows"] == 2
    assert result["valid_count"] == 2
    assert result["valid_percentage"] == 100.0


def test_analyze_single_file_invalid_type(analyzer, sample_trades_file):
    """Test analyzing with invalid data type."""
    with pytest.raises(ValueError, match="Invalid data_type"):
        analyzer.analyze_single_file(sample_trades_file, "invalid")


def test_analyze_single_file_with_filters(analyzer, sample_trades_file):
    """Test analyzing with symbol and date filters."""
    result = analyzer.analyze_single_file(
        sample_trades_file,
        "trades",
        symbol="BTC-USDT",
        date_filter=("2024-01-01T10:00:00", "2024-01-01T10:01:00"),
    )

    assert result["data_type"] == "trades"
    assert result["total_rows"] == 2  # Filtered to 2 rows
    assert result["valid_count"] == 2
    assert result["valid_percentage"] == 100.0


def test_analyze_multiple_files(analyzer, sample_trades_file, sample_book_file):
    """Test analyzing multiple files."""
    results = analyzer.analyze_multiple_files(
        trades_files=[sample_trades_file], book_files=[sample_book_file]
    )

    assert len(results) == 2

    # Check trades result
    trades_result = next(r for r in results if r["data_type"] == "trades")
    assert trades_result["total_rows"] == 3
    assert trades_result["valid_percentage"] == 100.0

    # Check book result
    book_result = next(r for r in results if r["data_type"] == "book")
    assert book_result["total_rows"] == 2
    assert book_result["valid_percentage"] == 100.0


def test_analyze_multiple_files_trades_only(analyzer, sample_trades_file):
    """Test analyzing only trades files."""
    results = analyzer.analyze_multiple_files(
        trades_files=[sample_trades_file], book_files=[]
    )

    assert len(results) == 1
    assert results[0]["data_type"] == "trades"


def test_analyze_multiple_files_book_only(analyzer, sample_book_file):
    """Test analyzing only book files."""
    results = analyzer.analyze_multiple_files(
        trades_files=[], book_files=[sample_book_file]
    )

    assert len(results) == 1
    assert results[0]["data_type"] == "book"


def test_analyze_multiple_files_empty(analyzer):
    """Test analyzing with empty file lists."""
    results = analyzer.analyze_multiple_files(trades_files=[], book_files=[])

    assert len(results) == 0


def test_run_analysis_complete(analyzer, sample_trades_file, sample_book_file):
    """Test complete analysis workflow."""
    results = analyzer.run_analysis(
        trades_files=[sample_trades_file],
        book_files=[sample_book_file],
        save_report=True,
        print_summary=False,  # Avoid console output during test
    )

    assert len(results) == 2

    # Check that report was saved
    report_path = (
        analyzer.report_generator.output_path / "origin_time_completeness_report.md"
    )
    assert report_path.exists()

    # Check report content
    report_content = report_path.read_text()
    assert "# Origin Time Completeness Report" in report_content
    assert "## Summary Statistics" in report_content


def test_run_analysis_no_files(analyzer):
    """Test running analysis with no files."""
    with pytest.raises(
        ValueError, match="At least one of trades_files or book_files must be provided"
    ):
        analyzer.run_analysis()


def test_run_analysis_with_filters(analyzer, sample_trades_file):
    """Test running analysis with filters."""
    results = analyzer.run_analysis(
        trades_files=[sample_trades_file],
        symbol="BTC-USDT",
        date_filter=("2024-01-01T10:00:00", "2024-01-01T10:01:00"),
        save_report=False,
        print_summary=False,
    )

    assert len(results) == 1
    assert results[0]["total_rows"] == 2  # Filtered


def test_get_recommendation(analyzer, sample_trades_file, sample_book_file):
    """Test getting recommendation from analysis results."""
    results = analyzer.run_analysis(
        trades_files=[sample_trades_file],
        book_files=[sample_book_file],
        save_report=False,
        print_summary=False,
    )

    recommendation = analyzer.get_recommendation(results)

    assert recommendation["strategy"] == "origin_time_primary"
    assert recommendation["confidence"] == "high"
    assert recommendation["details"]["can_use_origin_time"] is True


def test_get_recommendation_empty_results(analyzer):
    """Test getting recommendation with empty results."""
    recommendation = analyzer.get_recommendation([])

    assert recommendation["strategy"] == "unknown"
    assert "No validation results provided" in recommendation["reason"]
