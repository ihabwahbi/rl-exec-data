"""Unit tests for timing validators."""

import pytest
import json
import tempfile
from pathlib import Path
from rlx_datapipe.validation.validators.timing import ChronologicalOrderValidator, SequenceGapValidator


class TestChronologicalOrderValidator:
    """Test chronological order validator."""
    
    @pytest.fixture
    def ordered_file(self):
        """Create a file with chronologically ordered messages."""
        messages = [
            {"capture_ns": 1000000000, "stream": "btcusdt@trade", "data": {}},
            {"capture_ns": 1000000100, "stream": "btcusdt@trade", "data": {}},
            {"capture_ns": 1000000200, "stream": "btcusdt@trade", "data": {}},
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            for msg in messages:
                f.write(json.dumps(msg) + '\n')
            temp_path = Path(f.name)
        
        yield temp_path
        temp_path.unlink()
    
    @pytest.fixture
    def unordered_file(self):
        """Create a file with out-of-order messages."""
        messages = [
            {"capture_ns": 1000000000, "stream": "btcusdt@trade", "data": {}},
            {"capture_ns": 1000000200, "stream": "btcusdt@trade", "data": {}},
            {"capture_ns": 1000000100, "stream": "btcusdt@trade", "data": {}},  # Out of order
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            for msg in messages:
                f.write(json.dumps(msg) + '\n')
            temp_path = Path(f.name)
        
        yield temp_path
        temp_path.unlink()
    
    def test_chronological_validator_ordered(self, ordered_file):
        """Test validator with ordered messages."""
        validator = ChronologicalOrderValidator()
        result = validator.validate(ordered_file, ordered_file)
        
        assert result.passed
        assert result.metrics['file1']['out_of_order'] == 0
        assert result.metrics['file2']['out_of_order'] == 0
        assert result.metrics['both_ordered'] is True
        assert result.metrics['interpretation'] == "Both files are chronologically ordered"
    
    def test_chronological_validator_unordered(self, ordered_file, unordered_file):
        """Test validator with unordered messages."""
        validator = ChronologicalOrderValidator()
        result = validator.validate(ordered_file, unordered_file)
        
        assert not result.passed
        assert result.metrics['file1']['out_of_order'] == 0
        assert result.metrics['file2']['out_of_order'] == 1
        assert result.metrics['file2']['max_backwards_jump_ns'] == 100
        assert result.metrics['both_ordered'] is False
        assert "violations detected" in result.metrics['interpretation']
    
    def test_chronological_validator_metrics(self, ordered_file):
        """Test validator metrics."""
        validator = ChronologicalOrderValidator()
        result = validator.validate(ordered_file, ordered_file)
        
        # Check file1 metrics
        assert result.metrics['file1']['total_messages'] == 3
        assert result.metrics['file1']['out_of_order_ratio'] == 0.0
        assert result.metrics['file1']['chronologically_ordered'] is True
        
        # Check file2 metrics
        assert result.metrics['file2']['total_messages'] == 3
        assert result.metrics['file2']['out_of_order_ratio'] == 0.0
        assert result.metrics['file2']['chronologically_ordered'] is True


class TestSequenceGapValidator:
    """Test sequence gap validator."""
    
    @pytest.fixture
    def continuous_orderbook_file(self):
        """Create a file with continuous orderbook updates."""
        messages = [
            {
                "capture_ns": 1000000000,
                "stream": "btcusdt@depth@100ms",
                "data": {"U": 1000, "u": 1010}
            },
            {
                "capture_ns": 1000000100,
                "stream": "btcusdt@depth@100ms",
                "data": {"U": 1011, "u": 1020}  # Continuous from previous
            },
            {
                "capture_ns": 1000000200,
                "stream": "btcusdt@depth@100ms",
                "data": {"U": 1021, "u": 1030}  # Continuous
            },
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            for msg in messages:
                f.write(json.dumps(msg) + '\n')
            temp_path = Path(f.name)
        
        yield temp_path
        temp_path.unlink()
    
    @pytest.fixture
    def gapped_orderbook_file(self):
        """Create a file with gaps in orderbook updates."""
        messages = [
            {
                "capture_ns": 1000000000,
                "stream": "btcusdt@depth@100ms",
                "data": {"U": 1000, "u": 1010}
            },
            {
                "capture_ns": 1000000100,
                "stream": "btcusdt@depth@100ms",
                "data": {"U": 1015, "u": 1020}  # Gap: expected 1011, got 1015
            },
            {
                "capture_ns": 1000000200,
                "stream": "btcusdt@depth@100ms",
                "data": {"U": 1021, "u": 1030}  # Continuous
            },
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            for msg in messages:
                f.write(json.dumps(msg) + '\n')
            temp_path = Path(f.name)
        
        yield temp_path
        temp_path.unlink()
    
    def test_sequence_gap_validator_continuous(self, continuous_orderbook_file):
        """Test validator with continuous sequences."""
        validator = SequenceGapValidator(max_gap_ratio=0.0001)
        result = validator.validate(continuous_orderbook_file, continuous_orderbook_file)
        
        assert result.passed
        assert result.metrics['file1']['gaps_detected'] == 0
        assert result.metrics['file2']['gaps_detected'] == 0
        assert result.metrics['both_within_threshold'] is True
    
    def test_sequence_gap_validator_with_gaps(self, continuous_orderbook_file, gapped_orderbook_file):
        """Test validator with sequence gaps."""
        validator = SequenceGapValidator(max_gap_ratio=0.0001)
        result = validator.validate(continuous_orderbook_file, gapped_orderbook_file)
        
        assert not result.passed
        assert result.metrics['file1']['gaps_detected'] == 0
        assert result.metrics['file2']['gaps_detected'] == 1
        assert result.metrics['file2']['gap_ratio'] > 0
        assert result.metrics['file2']['max_gap_size'] == 4  # Gap size from 1010 to 1015
        assert "exceed threshold" in result.metrics['interpretation']
    
    def test_sequence_gap_validator_threshold(self, gapped_orderbook_file):
        """Test validator with different thresholds."""
        # Strict threshold - should fail
        validator_strict = SequenceGapValidator(max_gap_ratio=0.0001)
        result_strict = validator_strict.validate(gapped_orderbook_file, gapped_orderbook_file)
        assert not result_strict.passed
        
        # Permissive threshold - should pass
        validator_permissive = SequenceGapValidator(max_gap_ratio=0.5)
        result_permissive = validator_permissive.validate(gapped_orderbook_file, gapped_orderbook_file)
        assert result_permissive.passed
    
    def test_sequence_gap_validator_multi_symbol(self):
        """Test validator with multiple symbols."""
        messages = [
            {
                "capture_ns": 1000000000,
                "stream": "btcusdt@depth@100ms",
                "data": {"U": 1000, "u": 1010}
            },
            {
                "capture_ns": 1000000100,
                "stream": "ethusdt@depth@100ms",
                "data": {"U": 2000, "u": 2010}  # Different symbol
            },
            {
                "capture_ns": 1000000200,
                "stream": "btcusdt@depth@100ms",
                "data": {"U": 1011, "u": 1020}  # Continuous for btcusdt
            },
            {
                "capture_ns": 1000000300,
                "stream": "ethusdt@depth@100ms",
                "data": {"U": 2011, "u": 2020}  # Continuous for ethusdt
            },
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            for msg in messages:
                f.write(json.dumps(msg) + '\n')
            temp_path = Path(f.name)
        
        try:
            validator = SequenceGapValidator()
            result = validator.validate(temp_path, temp_path)
            
            assert result.passed
            assert result.metrics['file1']['symbols_tracked'] == 2
            assert result.metrics['file1']['gaps_detected'] == 0
        finally:
            temp_path.unlink()
    
    def test_sequence_gap_validator_no_orderbook_messages(self):
        """Test validator with no orderbook messages."""
        # Create a file with only trade messages
        messages = [
            {"capture_ns": 1000000000, "stream": "btcusdt@trade", "data": {"e": "trade"}},
            {"capture_ns": 1000000100, "stream": "btcusdt@trade", "data": {"e": "trade"}},
            {"capture_ns": 1000000200, "stream": "btcusdt@trade", "data": {"e": "trade"}},
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            for msg in messages:
                f.write(json.dumps(msg) + '\n')
            temp_path = Path(f.name)
        
        try:
            validator = SequenceGapValidator()
            result = validator.validate(temp_path, temp_path)
            
            assert result.passed
            assert result.metrics['file1']['total_updates'] == 0
            assert result.metrics['file1']['gaps_detected'] == 0
            assert result.metrics['file1']['gap_ratio'] == 0
        finally:
            temp_path.unlink()