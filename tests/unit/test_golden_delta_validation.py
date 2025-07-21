"""Unit tests for golden sample delta validation script."""

import gzip
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from scripts.run_golden_delta_validation import GoldenSampleDeltaValidator


class TestGoldenSampleDeltaValidator:
    """Test golden sample delta validator."""

    @pytest.fixture
    def validator(self):
        """Create validator instance."""
        return GoldenSampleDeltaValidator()

    @pytest.fixture
    def sample_messages(self):
        """Create sample messages for testing."""
        return [
            {
                "capture_ns": 1000000000,
                "stream": "btcusdt@depth@100ms",
                "data": {
                    "e": "depthUpdate",
                    "E": 1000000,
                    "s": "BTCUSDT",
                    "U": 1000,  # First update ID
                    "u": 1009,  # Final update ID
                    "b": [["50000.00", "0.1"]],
                    "a": [["50001.00", "0.1"]]
                }
            },
            {
                "capture_ns": 1000001000,
                "stream": "btcusdt@depth@100ms",
                "data": {
                    "e": "depthUpdate",
                    "E": 1000001,
                    "s": "BTCUSDT",
                    "U": 1010,  # No gap - continues from previous
                    "u": 1019,
                    "b": [["50000.00", "0.2"]],
                    "a": [["50001.00", "0.2"]]
                }
            },
            {
                "capture_ns": 1000002000,
                "stream": "btcusdt@trade",
                "data": {
                    "e": "trade",
                    "E": 1000002,
                    "s": "BTCUSDT",
                    "p": "50000.50",
                    "q": "0.1"
                }
            }
        ]

    @pytest.fixture
    def sample_messages_with_gap(self):
        """Create sample messages with sequence gap."""
        return [
            {
                "capture_ns": 1000000000,
                "stream": "btcusdt@depth@100ms",
                "data": {
                    "e": "depthUpdate",
                    "U": 1000,
                    "u": 1009
                }
            },
            {
                "capture_ns": 1000001000,
                "stream": "btcusdt@depth@100ms",
                "data": {
                    "e": "depthUpdate",
                    "U": 1020,  # Gap of 10
                    "u": 1029
                }
            }
        ]

    def test_validate_regime_no_gaps(self, validator, sample_messages, tmp_path):
        """Test regime validation with no sequence gaps."""
        # Create test file
        test_file = tmp_path / "test.jsonl.gz"
        with gzip.open(test_file, "wt") as f:
            for msg in sample_messages:
                f.write(json.dumps(msg) + "\n")

        # Run validation
        result = validator.validate_regime("test_regime", tmp_path)

        assert result["regime"] == "test_regime"
        assert result["files_analyzed"] == 1
        assert result["total_messages"] == 3
        assert result["depth_updates"] == 2
        assert result["sequence_gaps"]["count"] == 0
        assert result["sequence_gaps"]["gap_ratio_percent"] == 0.0
        assert result["data_quality"]["valid_updates"] == 2
        assert result["data_quality"]["invalid_updates"] == 0

    def test_validate_regime_with_gaps(
        self, validator, sample_messages_with_gap, tmp_path
    ):
        """Test regime validation with sequence gaps."""
        # Create test file
        test_file = tmp_path / "test.jsonl.gz"
        with gzip.open(test_file, "wt") as f:
            for msg in sample_messages_with_gap:
                f.write(json.dumps(msg) + "\n")

        # Run validation
        result = validator.validate_regime("test_regime", tmp_path)

        assert result["sequence_gaps"]["count"] == 1
        assert result["sequence_gaps"]["max_gap"] == 10
        assert result["sequence_gaps"]["gaps_by_size"]["1-10"] == 1
        assert result["sequence_gaps"]["gap_ratio_percent"] > 0

    def test_gap_size_buckets(self, validator):
        """Test gap size bucket categorization."""
        assert validator._get_gap_size_bucket(5) == "1-10"
        assert validator._get_gap_size_bucket(50) == "11-100"
        assert validator._get_gap_size_bucket(500) == "101-1000"
        assert validator._get_gap_size_bucket(5000) == "1000+"

    def test_validate_regime_empty_directory(self, validator, tmp_path):
        """Test validation with empty directory."""
        result = validator.validate_regime("empty_regime", tmp_path)

        assert result["files_analyzed"] == 0
        assert result["total_messages"] == 0
        assert result["depth_updates"] == 0

    def test_validate_regime_invalid_json(self, validator, tmp_path):
        """Test validation with invalid JSON lines."""
        # Create test file with invalid JSON
        test_file = tmp_path / "test.jsonl.gz"
        with gzip.open(test_file, "wt") as f:
            f.write("invalid json\n")
            f.write(json.dumps({"valid": "message"}) + "\n")

        # Run validation - should handle gracefully
        result = validator.validate_regime("test_regime", tmp_path)

        assert result["files_analyzed"] == 1
        assert result["total_messages"] == 1  # Only valid message counted

    def test_validate_all_regimes(self, validator, tmp_path):
        """Test validation across all regimes."""
        # Create regime directories
        for regime in ["high_volume", "low_volume", "special_event"]:
            regime_dir = tmp_path / regime
            regime_dir.mkdir()

            # Create a sample file
            test_file = regime_dir / "test.jsonl.gz"
            with gzip.open(test_file, "wt") as f:
                f.write(json.dumps({
                    "stream": "btcusdt@depth@100ms",
                    "data": {"U": 1000, "u": 1009}
                }) + "\n")

        # Run validation
        validator.validate_all_regimes(tmp_path)

        assert len(validator.results["market_regimes"]) == 3
        assert validator.results["overall_summary"]["go_decision"] == "GO"

    def test_generate_summary_all_pass(self, validator):
        """Test summary generation when all regimes pass."""
        # Mock regime results
        validator.results["market_regimes"] = {
            "high_volume": {
                "files_analyzed": 10,
                "total_messages": 100000,
                "depth_updates": 50000,
                "sequence_gaps": {"count": 0, "max_gap": 0, "gap_ratio_percent": 0.05}
            },
            "low_volume": {
                "files_analyzed": 10,
                "total_messages": 50000,
                "depth_updates": 25000,
                "sequence_gaps": {"count": 1, "max_gap": 5, "gap_ratio_percent": 0.08}
            }
        }

        validator._generate_summary()

        assert validator.results["overall_summary"]["go_decision"] == "GO"
        expected_msg = "All market regimes show sequence gap ratios < 0.1%"
        assert expected_msg in validator.results["overall_summary"]["reasons"]

    def test_generate_summary_fail(self, validator):
        """Test summary generation when a regime fails."""
        # Mock regime results with failure
        validator.results["market_regimes"] = {
            "high_volume": {
                "files_analyzed": 10,
                "total_messages": 100000,
                "depth_updates": 50000,
                "sequence_gaps": {
                    "count": 100, "max_gap": 1000, "gap_ratio_percent": 0.5
                }
            }
        }

        validator._generate_summary()

        assert validator.results["overall_summary"]["go_decision"] == "NO-GO"
        expected_msg = "high_volume regime gap ratio 0.5000% exceeds 0.1% threshold"
        assert expected_msg in validator.results["overall_summary"]["reasons"]

    def test_out_of_order_detection(self, validator, tmp_path):
        """Test detection of out-of-order updates."""
        messages = [
            {
                "stream": "btcusdt@depth@100ms",
                "data": {"U": 1000, "u": 1009}
            },
            {
                "stream": "btcusdt@depth@100ms",
                "data": {"U": 995, "u": 999}  # Out of order
            }
        ]

        test_file = tmp_path / "test.jsonl.gz"
        with gzip.open(test_file, "wt") as f:
            for msg in messages:
                f.write(json.dumps(msg) + "\n")

        result = validator.validate_regime("test", tmp_path)

        assert result["data_quality"]["out_of_order"] == 1

    def test_save_results(self, validator, tmp_path):
        """Test saving results to JSON file."""
        validator.results = {"test": "data"}
        output_file = tmp_path / "results.json"

        validator.save_results(output_file)

        assert output_file.exists()
        with output_file.open() as f:
            loaded = json.load(f)
        assert loaded == {"test": "data"}


def test_main_function(tmp_path):
    """Test main function execution."""
    # Create test golden samples directory
    golden_dir = tmp_path / "golden_samples"
    golden_dir.mkdir()

    # Create a regime directory
    regime_dir = golden_dir / "high_volume"
    regime_dir.mkdir()

    # Create a sample file
    test_file = regime_dir / "test.jsonl.gz"
    with gzip.open(test_file, "wt") as f:
        f.write(json.dumps({
            "stream": "btcusdt@depth@100ms",
            "data": {"U": 1000, "u": 1009}
        }) + "\n")

    # Mock sys.argv
    with patch("sys.argv", ["script", "--golden-samples-dir", str(golden_dir),
                           "--output", str(tmp_path / "output.json")]):
        # Import and run main
        from scripts.run_golden_delta_validation import main

        # Run main - should complete without errors
        try:
            main()
            # Check output file was created
            assert (tmp_path / "output.json").exists()
        except SystemExit as e:
            # Should exit with 0 on success
            assert e.code == 0 or e.code is None
