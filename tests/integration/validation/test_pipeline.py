"""Integration tests for validation pipeline."""

import pytest
import json
import gzip
import tempfile
from pathlib import Path
import numpy as np
from rlx_datapipe.validation import (
    ValidationPipeline, 
    KSValidator,
    PowerLawValidator,
    BasicStatsCalculator,
    ChronologicalOrderValidator,
    SequenceGapValidator
)
from rlx_datapipe.validation.base import BaseValidator


class TestValidationPipeline:
    """Test validation pipeline integration."""
    
    @pytest.fixture
    def sample_golden_file(self):
        """Create a sample golden file with realistic data."""
        np.random.seed(42)
        messages = []
        
        # Generate trade messages
        for i in range(1000):
            messages.append({
                "capture_ns": 1000000000 + i * 1000,
                "stream": "btcusdt@trade",
                "data": {
                    "e": "trade",
                    "p": str(50000 + np.random.normal(0, 10)),
                    "q": str(np.random.pareto(2.4) * 0.01),  # Power law distributed
                    "T": 1234567890000 + i
                }
            })
        
        # Generate depth messages
        for i in range(500):
            messages.append({
                "capture_ns": 1000000500 + i * 2000,
                "stream": "btcusdt@depth@100ms",
                "data": {
                    "e": "depthUpdate",
                    "U": 1000 + i * 10,
                    "u": 1000 + i * 10 + 9,
                    "b": [["49999.00", "0.5"]],
                    "a": [["50001.00", "0.5"]]
                }
            })
        
        # Sort by timestamp to ensure chronological order
        messages.sort(key=lambda x: x['capture_ns'])
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl.gz', delete=False) as f:
            temp_path = Path(f.name)
        
        with gzip.open(temp_path, 'wt') as f:
            for msg in messages:
                f.write(json.dumps(msg) + '\n')
        
        yield temp_path
        temp_path.unlink()
    
    @pytest.fixture
    def sample_comparison_file(self):
        """Create a comparison file similar to golden but slightly different."""
        np.random.seed(43)  # Different seed for variation
        messages = []
        
        # Generate trade messages
        for i in range(1000):
            messages.append({
                "capture_ns": 1000000000 + i * 1000,
                "stream": "btcusdt@trade",
                "data": {
                    "e": "trade",
                    "p": str(50000 + np.random.normal(0.05, 10.1)),  # Very slightly different
                    "q": str(np.random.pareto(2.42) * 0.01),  # Very slightly different exponent
                    "T": 1234567890000 + i
                }
            })
        
        # Generate depth messages with one gap
        for i in range(500):
            if i == 250:
                # Introduce a sequence gap
                u_val = 1000 + i * 10 + 15  # Gap of 6
            else:
                u_val = 1000 + i * 10
            
            messages.append({
                "capture_ns": 1000000500 + i * 2000,
                "stream": "btcusdt@depth@100ms",
                "data": {
                    "e": "depthUpdate",
                    "U": u_val,
                    "u": u_val + 9,
                    "b": [["49999.00", "0.5"]],
                    "a": [["50001.00", "0.5"]]
                }
            })
        
        messages.sort(key=lambda x: x['capture_ns'])
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl.gz', delete=False) as f:
            temp_path = Path(f.name)
        
        with gzip.open(temp_path, 'wt') as f:
            for msg in messages:
                f.write(json.dumps(msg) + '\n')
        
        yield temp_path
        temp_path.unlink()
    
    def test_pipeline_basic_run(self, sample_golden_file, sample_comparison_file):
        """Test basic pipeline execution."""
        pipeline = ValidationPipeline()
        
        # Add validators
        pipeline.add_validator(ChronologicalOrderValidator())
        pipeline.add_validator(SequenceGapValidator())
        
        # Run pipeline
        report = pipeline.run(sample_golden_file, sample_comparison_file)
        
        assert report.golden_sample_path == str(sample_golden_file)
        assert report.comparison_path == str(sample_comparison_file)
        assert len(report.results) == 2
        assert report.total_duration > 0
        assert report.peak_memory_mb > 0
    
    def test_pipeline_statistical_validators(self, sample_golden_file, sample_comparison_file):
        """Test pipeline with statistical validators."""
        pipeline = ValidationPipeline()
        
        # Add statistical validators
        pipeline.add_validator(KSValidator(alpha=0.05))
        # Use slightly more lenient thresholds for test data with random variations
        pipeline.add_validator(BasicStatsCalculator(thresholds={
            "mean_relative_diff": 0.01,
            "std_relative_diff": 0.06,  # Allow 6% difference in std
            "median_relative_diff": 0.01
        }))
        
        # Run pipeline
        report = pipeline.run(sample_golden_file, sample_comparison_file)
        
        # K-S test should pass (similar distributions)
        ks_result = next(r for r in report.results if r.validator_name == "Kolmogorov-Smirnov Test")
        assert ks_result.passed
        assert ks_result.metrics['p_value'] > 0.05
        
        # Basic stats should also pass
        stats_result = next(r for r in report.results if r.validator_name == "Basic Statistics Comparison")
        assert stats_result.passed
    
    @pytest.mark.skipif(True, reason="Skip power law test - requires powerlaw package")
    def test_pipeline_power_law_validator(self, sample_golden_file, sample_comparison_file):
        """Test pipeline with power law validator."""
        pipeline = ValidationPipeline()
        pipeline.add_validator(PowerLawValidator(expected_alpha=2.4, tolerance=0.5))
        
        report = pipeline.run(sample_golden_file, sample_comparison_file)
        
        power_law_result = report.results[0]
        assert 'alpha' in power_law_result.metrics
        # Result depends on data and powerlaw fitting
    
    def test_pipeline_checkpoint_resume(self, sample_golden_file, sample_comparison_file):
        """Test pipeline checkpoint and resume functionality."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            checkpoint_path = Path(f.name)
        
        try:
            # First run with one validator
            pipeline1 = ValidationPipeline()
            pipeline1.add_validator(ChronologicalOrderValidator())
            report1 = pipeline1.run(sample_golden_file, sample_comparison_file, checkpoint_path)
            
            assert len(report1.results) == 1
            assert checkpoint_path.exists()
            
            # Second run with additional validator using checkpoint
            pipeline2 = ValidationPipeline()
            pipeline2.add_validator(ChronologicalOrderValidator())  # Should skip
            pipeline2.add_validator(SequenceGapValidator())  # Should run
            report2 = pipeline2.run(sample_golden_file, sample_comparison_file, checkpoint_path)
            
            assert len(report2.results) == 2
            # First validator should have been skipped (loaded from checkpoint)
            assert report2.results[0].duration_seconds == report1.results[0].duration_seconds
        finally:
            checkpoint_path.unlink(missing_ok=True)
    
    def test_pipeline_file_not_found(self):
        """Test pipeline with missing files."""
        pipeline = ValidationPipeline()
        pipeline.add_validator(ChronologicalOrderValidator())
        
        with pytest.raises(FileNotFoundError):
            pipeline.run(Path("nonexistent.jsonl"), Path("also_nonexistent.jsonl"))
    
    def test_pipeline_validator_error_handling(self, sample_golden_file):
        """Test pipeline handles validator errors gracefully."""
        class ErrorValidator(BaseValidator):
            def _validate(self, data1, data2):
                raise ValueError("Test error")
        
        pipeline = ValidationPipeline()
        pipeline.add_validator(ErrorValidator("Error Test"))
        pipeline.add_validator(ChronologicalOrderValidator())
        
        report = pipeline.run(sample_golden_file, sample_golden_file)
        
        # Should have results for both validators
        assert len(report.results) == 2
        
        # First should have failed with error
        assert not report.results[0].passed
        assert report.results[0].error_message == "Test error"
        
        # Second should have succeeded
        assert report.results[1].passed
        
        # Overall should fail
        assert not report.overall_passed
    
    def test_pipeline_clear_validators(self):
        """Test clearing validators from pipeline."""
        pipeline = ValidationPipeline()
        pipeline.add_validator(ChronologicalOrderValidator())
        pipeline.add_validator(SequenceGapValidator())
        
        assert len(pipeline.get_validator_names()) == 2
        
        pipeline.clear_validators()
        assert len(pipeline.get_validator_names()) == 0
    
    def test_pipeline_report_generation(self, sample_golden_file, sample_comparison_file):
        """Test report generation in different formats."""
        pipeline = ValidationPipeline()
        pipeline.add_validator(ChronologicalOrderValidator())
        pipeline.add_validator(SequenceGapValidator())
        
        report = pipeline.run(sample_golden_file, sample_comparison_file)
        
        # Test JSON generation
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json_path = Path(f.name)
        
        try:
            report.to_json(json_path)
            assert json_path.exists()
            
            # Load and verify
            with open(json_path, 'r') as f:
                data = json.load(f)
            assert 'validation_run' in data
            assert 'results' in data
            assert len(data['results']) == 2
        finally:
            json_path.unlink()
        
        # Test Markdown generation
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            md_path = Path(f.name)
        
        try:
            report.to_markdown(md_path)
            assert md_path.exists()
            
            content = md_path.read_text()
            assert "# Validation Report" in content
            assert "Chronological Order Check" in content
            assert "Sequence Gap Detection" in content
        finally:
            md_path.unlink()
    
    @pytest.mark.asyncio
    async def test_pipeline_async_run(self, sample_golden_file, sample_comparison_file):
        """Test async pipeline execution."""
        pipeline = ValidationPipeline()
        pipeline.add_validator(ChronologicalOrderValidator())
        
        report = await pipeline.run_async(sample_golden_file, sample_comparison_file)
        
        assert len(report.results) == 1
        assert report.overall_passed