"""Unit tests for base validation classes."""

import pytest
import json
from pathlib import Path
import tempfile
from rlx_datapipe.validation.base import ValidationResult, ValidationReport, BaseValidator


class MockValidator(BaseValidator):
    """Mock validator for testing."""
    
    def _validate(self, data1, data2):
        return True, {"test_metric": 42}


class TestValidationResult:
    """Test ValidationResult class."""
    
    def test_validation_result_creation(self):
        """Test creating a validation result."""
        result = ValidationResult(
            validator_name="Test Validator",
            passed=True,
            metrics={"accuracy": 0.95},
            duration_seconds=1.5
        )
        
        assert result.validator_name == "Test Validator"
        assert result.passed is True
        assert result.metrics["accuracy"] == 0.95
        assert result.duration_seconds == 1.5
        assert result.error_message is None
    
    def test_validation_result_with_error(self):
        """Test validation result with error."""
        result = ValidationResult(
            validator_name="Test Validator",
            passed=False,
            metrics={},
            duration_seconds=0.1,
            error_message="Test error"
        )
        
        assert result.passed is False
        assert result.error_message == "Test error"
    
    def test_validation_result_to_dict(self):
        """Test converting result to dictionary."""
        result = ValidationResult(
            validator_name="Test Validator",
            passed=True,
            metrics={"accuracy": 0.95},
            duration_seconds=1.5
        )
        
        result_dict = result.to_dict()
        assert result_dict["validator"] == "Test Validator"
        assert result_dict["passed"] is True
        assert result_dict["metrics"]["accuracy"] == 0.95
        assert result_dict["duration"] == 1.5
        assert result_dict["error"] is None


class TestValidationReport:
    """Test ValidationReport class."""
    
    def test_validation_report_creation(self):
        """Test creating a validation report."""
        results = [
            ValidationResult("Validator 1", True, {"metric": 1}, 1.0),
            ValidationResult("Validator 2", True, {"metric": 2}, 2.0)
        ]
        
        report = ValidationReport(
            golden_sample_path="path/to/golden.jsonl",
            comparison_path="path/to/comparison.jsonl",
            results=results,
            total_duration=3.0,
            peak_memory_mb=100.0,
            overall_passed=True
        )
        
        assert report.golden_sample_path == "path/to/golden.jsonl"
        assert report.comparison_path == "path/to/comparison.jsonl"
        assert len(report.results) == 2
        assert report.total_duration == 3.0
        assert report.peak_memory_mb == 100.0
        assert report.overall_passed is True
        assert report.timestamp.endswith('Z')
    
    def test_validation_report_to_dict(self):
        """Test converting report to dictionary."""
        results = [
            ValidationResult("Validator 1", True, {"metric": 1}, 1.0)
        ]
        
        report = ValidationReport(
            golden_sample_path="golden.jsonl",
            comparison_path="comparison.jsonl",
            results=results,
            total_duration=1.0,
            peak_memory_mb=50.0,
            overall_passed=True
        )
        
        report_dict = report.to_dict()
        assert "validation_run" in report_dict
        assert report_dict["validation_run"]["golden_sample_path"] == "golden.jsonl"
        assert report_dict["validation_run"]["duration_seconds"] == 1.0
        assert report_dict["overall_passed"] is True
        assert len(report_dict["results"]) == 1
    
    def test_validation_report_to_json(self):
        """Test saving report as JSON."""
        results = [
            ValidationResult("Validator 1", True, {"metric": 1}, 1.0)
        ]
        
        report = ValidationReport(
            golden_sample_path="golden.jsonl",
            comparison_path="comparison.jsonl",
            results=results,
            total_duration=1.0,
            peak_memory_mb=50.0,
            overall_passed=True
        )
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            report.to_json(temp_path)
            
            # Load and verify
            with open(temp_path, 'r') as f:
                loaded = json.load(f)
            
            assert loaded["overall_passed"] is True
            assert loaded["validation_run"]["golden_sample_path"] == "golden.jsonl"
        finally:
            temp_path.unlink()
    
    def test_validation_report_to_markdown(self):
        """Test saving report as markdown."""
        results = [
            ValidationResult("Validator 1", True, {"accuracy": 0.95, "precision": 0.92}, 1.0),
            ValidationResult("Validator 2", False, {}, 0.5, error_message="Test error")
        ]
        
        report = ValidationReport(
            golden_sample_path="golden.jsonl",
            comparison_path="comparison.jsonl",
            results=results,
            total_duration=1.5,
            peak_memory_mb=50.0,
            overall_passed=False
        )
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            report.to_markdown(temp_path)
            
            # Load and verify
            content = temp_path.read_text()
            assert "# Validation Report" in content
            assert "❌ FAILED" in content
            assert "Validator 1" in content
            assert "✅ Pass" in content
            assert "❌ Fail" in content
            assert "Test error" in content
        finally:
            temp_path.unlink()


class TestBaseValidator:
    """Test BaseValidator class."""
    
    def test_base_validator_initialization(self):
        """Test validator initialization."""
        validator = MockValidator("Test Validator", param1="value1")
        
        assert validator.name == "Test Validator"
        assert validator.config["param1"] == "value1"
    
    def test_base_validator_validate_success(self):
        """Test successful validation."""
        validator = MockValidator("Test Validator")
        result = validator.validate("data1", "data2")
        
        assert result.validator_name == "Test Validator"
        assert result.passed is True
        assert result.metrics["test_metric"] == 42
        assert result.duration_seconds > 0
        assert result.error_message is None
    
    def test_base_validator_validate_exception(self):
        """Test validation with exception."""
        class ErrorValidator(BaseValidator):
            def _validate(self, data1, data2):
                raise ValueError("Test error")
        
        validator = ErrorValidator("Error Validator")
        result = validator.validate("data1", "data2")
        
        assert result.passed is False
        assert result.error_message == "Test error"
        assert result.duration_seconds > 0