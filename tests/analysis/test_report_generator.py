"""Tests for report generation."""

import tempfile
from pathlib import Path

import pytest
from rlx_datapipe.analysis.report_generator import OriginTimeReportGenerator


@pytest.fixture()
def sample_validation_results():
    """Create sample validation results for testing."""
    return [
        {
            "data_type": "trades",
            "total_rows": 1000,
            "valid_count": 950,
            "valid_percentage": 95.0,
            "total_invalid": 50,
            "total_invalid_percentage": 5.0,
            "validation_details": {
                "null_values": {"count": 20, "percentage": 2.0},
                "zero_values": {"count": 15, "percentage": 1.5},
                "future_dates": {"count": 10, "percentage": 1.0},
                "negative_values": {"count": 5, "percentage": 0.5},
                "invalid_format": {"count": 0, "percentage": 0.0},
            },
        },
        {
            "data_type": "book",
            "total_rows": 2000,
            "valid_count": 1900,
            "valid_percentage": 95.0,
            "total_invalid": 100,
            "total_invalid_percentage": 5.0,
            "validation_details": {
                "null_values": {"count": 40, "percentage": 2.0},
                "zero_values": {"count": 30, "percentage": 1.5},
                "future_dates": {"count": 20, "percentage": 1.0},
                "negative_values": {"count": 10, "percentage": 0.5},
                "invalid_format": {"count": 0, "percentage": 0.0},
            },
        },
    ]


@pytest.fixture()
def low_reliability_results():
    """Create validation results with low reliability."""
    return [
        {
            "data_type": "trades",
            "total_rows": 1000,
            "valid_count": 800,
            "valid_percentage": 80.0,
            "total_invalid": 200,
            "total_invalid_percentage": 20.0,
            "validation_details": {
                "null_values": {"count": 100, "percentage": 10.0},
                "zero_values": {"count": 50, "percentage": 5.0},
                "future_dates": {"count": 30, "percentage": 3.0},
                "negative_values": {"count": 20, "percentage": 2.0},
                "invalid_format": {"count": 0, "percentage": 0.0},
            },
        },
        {
            "data_type": "book",
            "total_rows": 2000,
            "valid_count": 1600,
            "valid_percentage": 80.0,
            "total_invalid": 400,
            "total_invalid_percentage": 20.0,
            "validation_details": {
                "null_values": {"count": 200, "percentage": 10.0},
                "zero_values": {"count": 100, "percentage": 5.0},
                "future_dates": {"count": 60, "percentage": 3.0},
                "negative_values": {"count": 40, "percentage": 2.0},
                "invalid_format": {"count": 0, "percentage": 0.0},
            },
        },
    ]


@pytest.fixture()
def report_generator():
    """Create report generator for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield OriginTimeReportGenerator(output_path=Path(temp_dir))


def test_report_generator_initialization():
    """Test report generator initialization."""
    with tempfile.TemporaryDirectory() as temp_dir:
        generator = OriginTimeReportGenerator(output_path=Path(temp_dir))
        assert generator.output_path == Path(temp_dir)
        assert generator.output_path.exists()


def test_generate_summary_statistics(report_generator, sample_validation_results):
    """Test summary statistics generation."""
    summary = report_generator.generate_summary_statistics(sample_validation_results)

    assert summary["total_datasets"] == 2
    assert summary["total_rows_analyzed"] == 3000
    assert summary["total_valid_rows"] == 2850
    assert summary["overall_validity_percentage"] == 95.0
    assert len(summary["datasets"]) == 2

    trades_summary = next(d for d in summary["datasets"] if d["data_type"] == "trades")
    assert trades_summary["total_rows"] == 1000
    assert trades_summary["valid_count"] == 950
    assert trades_summary["valid_percentage"] == 95.0


def test_generate_summary_statistics_empty():
    """Test summary statistics with empty results."""
    generator = OriginTimeReportGenerator()
    summary = generator.generate_summary_statistics([])
    assert summary == {}


def test_generate_chronological_recommendation_high_reliability(
    report_generator, sample_validation_results
):
    """Test recommendation generation with high reliability data."""
    recommendation = report_generator.generate_chronological_recommendation(
        sample_validation_results
    )

    assert recommendation["strategy"] == "origin_time_primary"
    assert recommendation["confidence"] == "high"
    assert recommendation["details"]["can_use_origin_time"] is True
    assert recommendation["details"]["trades_reliability"] == 95.0
    assert recommendation["details"]["book_reliability"] == 95.0


def test_generate_chronological_recommendation_low_reliability(
    report_generator, low_reliability_results
):
    """Test recommendation generation with low reliability data."""
    recommendation = report_generator.generate_chronological_recommendation(
        low_reliability_results
    )

    assert recommendation["strategy"] == "alternative_timestamp"
    assert recommendation["confidence"] == "low"
    assert recommendation["details"]["can_use_origin_time"] is False
    assert recommendation["details"]["trades_reliability"] == 80.0
    assert recommendation["details"]["book_reliability"] == 80.0


def test_generate_chronological_recommendation_mixed_reliability(report_generator):
    """Test recommendation generation with mixed reliability data."""
    mixed_results = [
        {
            "data_type": "trades",
            "total_rows": 1000,
            "valid_count": 960,
            "valid_percentage": 96.0,
            "validation_details": {},
        },
        {
            "data_type": "book",
            "total_rows": 2000,
            "valid_count": 1600,
            "valid_percentage": 80.0,
            "validation_details": {},
        },
    ]

    recommendation = report_generator.generate_chronological_recommendation(
        mixed_results
    )

    assert recommendation["strategy"] == "snapshot_anchored"
    assert recommendation["confidence"] == "medium"
    assert recommendation["details"]["can_use_origin_time"] is False


def test_generate_chronological_recommendation_empty():
    """Test recommendation generation with empty results."""
    generator = OriginTimeReportGenerator()
    recommendation = generator.generate_chronological_recommendation([])

    assert recommendation["strategy"] == "unknown"
    assert "No validation results provided" in recommendation["reason"]


def test_generate_detailed_validation_report(
    report_generator, sample_validation_results
):
    """Test detailed report generation."""
    report = report_generator.generate_detailed_validation_report(
        sample_validation_results
    )

    assert "# Origin Time Completeness Report" in report
    assert "## Summary Statistics" in report
    assert "## Dataset Details" in report
    assert "### Trades Data" in report
    assert "### Book Data" in report
    assert "## Chronological Unification Recommendation" in report
    assert "## Conclusion" in report
    assert "Total Datasets Analyzed:** 2" in report
    assert "Total Rows Analyzed:** 3,000" in report
    assert "Overall Validity:** 95.00%" in report
    assert "origin_time_primary" in report


def test_generate_detailed_validation_report_empty():
    """Test detailed report generation with empty results."""
    generator = OriginTimeReportGenerator()
    report = generator.generate_detailed_validation_report([])

    assert "# Origin Time Completeness Report" in report
    assert "No validation results provided" in report


def test_save_report(report_generator, sample_validation_results):
    """Test saving report to file."""
    report_path = report_generator.save_report(sample_validation_results)

    assert report_path.exists()
    assert report_path.name == "origin_time_completeness_report.md"

    content = report_path.read_text()
    assert "# Origin Time Completeness Report" in content
    assert "## Summary Statistics" in content


def test_save_report_custom_filename(report_generator, sample_validation_results):
    """Test saving report with custom filename."""
    custom_filename = "custom_report.md"
    report_path = report_generator.save_report(
        sample_validation_results, custom_filename
    )

    assert report_path.exists()
    assert report_path.name == custom_filename


def test_print_summary(report_generator, sample_validation_results, capsys):
    """Test printing summary to console."""
    report_generator.print_summary(sample_validation_results)

    captured = capsys.readouterr()
    assert "ORIGIN TIME COMPLETENESS ANALYSIS SUMMARY" in captured.out
    assert "Total Datasets: 2" in captured.out
    assert "Total Rows: 3,000" in captured.out
    assert "Overall Validity: 95.00%" in captured.out
    assert "TRADES DATA:" in captured.out
    assert "BOOK DATA:" in captured.out
    assert "RECOMMENDATION: origin_time_primary" in captured.out


def test_print_summary_empty(report_generator, capsys):
    """Test printing summary with empty results."""
    report_generator.print_summary([])

    captured = capsys.readouterr()
    assert "No validation results to display." in captured.out
