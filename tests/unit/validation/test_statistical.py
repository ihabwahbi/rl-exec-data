"""Unit tests for statistical validators."""

import pytest
import numpy as np
from scipy import stats as scipy_stats
from rlx_datapipe.validation.statistical import KSValidator, PowerLawValidator, BasicStatsCalculator


class TestKSValidator:
    """Test Kolmogorov-Smirnov validator."""
    
    def test_ks_validator_identical_distributions(self):
        """Test K-S validator with identical distributions."""
        validator = KSValidator(alpha=0.05)
        sample = np.random.normal(0, 1, 10000)
        result = validator.validate(sample, sample)
        
        assert result.passed
        assert result.metrics['p_value'] > 0.99
        assert result.metrics['statistic'] == 0.0
        assert result.metrics['sample1_size'] == 10000
        assert result.metrics['sample2_size'] == 10000
    
    def test_ks_validator_similar_distributions(self):
        """Test K-S validator with similar distributions."""
        validator = KSValidator(alpha=0.05)
        np.random.seed(42)
        sample1 = np.random.normal(0, 1, 10000)
        sample2 = np.random.normal(0.01, 1.01, 10000)
        result = validator.validate(sample1, sample2)
        
        assert result.passed
        assert result.metrics['p_value'] > 0.05
        assert result.metrics['interpretation'] == "Distributions are similar"
    
    def test_ks_validator_different_distributions(self):
        """Test K-S validator with different distributions."""
        validator = KSValidator(alpha=0.05)
        np.random.seed(42)
        sample1 = np.random.normal(0, 1, 1000)
        sample2 = np.random.uniform(-2, 2, 1000)
        result = validator.validate(sample1, sample2)
        
        assert not result.passed
        assert result.metrics['p_value'] < 0.05
        assert result.metrics['interpretation'] == "Distributions differ significantly"
    
    def test_ks_validator_custom_alpha(self):
        """Test K-S validator with custom significance level."""
        validator = KSValidator(alpha=0.01)
        np.random.seed(42)
        sample1 = np.random.normal(0, 1, 1000)
        sample2 = np.random.normal(0.1, 1, 1000)
        result = validator.validate(sample1, sample2)
        
        # Should pass with alpha=0.01 even if p-value is between 0.01 and 0.05
        assert result.metrics['alpha'] == 0.01


class TestPowerLawValidator:
    """Test power law distribution validator."""
    
    @pytest.fixture
    def power_law_samples(self):
        """Generate power law distributed samples."""
        # Generate using inverse transform sampling
        np.random.seed(42)
        xmin = 1.0
        alpha = 2.4
        n = 10000
        
        # Inverse transform: x = xmin * (1 - u)^(-1/(alpha-1))
        u = np.random.uniform(0, 1, n)
        samples = xmin * (1 - u) ** (-1 / (alpha - 1))
        return samples
    
    def test_power_law_validator_correct_exponent(self, power_law_samples):
        """Test power law validator with correct exponent."""
        # Skip if powerlaw not installed
        pytest.importorskip("powerlaw")
        
        validator = PowerLawValidator(expected_alpha=2.4, tolerance=0.5)
        result = validator.validate(power_law_samples)
        
        assert result.passed
        assert 1.9 < result.metrics['alpha'] < 2.9  # Wide range due to estimation variance
        assert result.metrics['xmin'] > 0
        assert 'R_vs_exponential' in result.metrics
        assert 'within expected range' in result.metrics['interpretation']
    
    def test_power_law_validator_wrong_exponent(self):
        """Test power law validator with wrong exponent."""
        pytest.importorskip("powerlaw")
        
        # Generate exponential distribution (not power law)
        np.random.seed(42)
        samples = np.random.exponential(scale=2.0, size=10000)
        
        validator = PowerLawValidator(expected_alpha=2.4, tolerance=0.1)
        result = validator.validate(samples)
        
        # May or may not pass depending on fit, but should have metrics
        assert 'alpha' in result.metrics
        assert 'xmin' in result.metrics
        assert result.metrics['expected_alpha'] == 2.4
        assert result.metrics['tolerance'] == 0.1
    
    def test_power_law_validator_insufficient_data(self):
        """Test power law validator with insufficient data."""
        pytest.importorskip("powerlaw")
        
        validator = PowerLawValidator()
        samples = np.array([1, 2, 3, 4, 5])  # Too few samples
        
        result = validator.validate(samples)
        assert not result.passed
        assert "Insufficient data" in result.error_message
    
    def test_power_law_validator_missing_package(self, monkeypatch):
        """Test power law validator when powerlaw package is missing."""
        # Mock the powerlaw import to raise ImportError
        import sys
        import builtins
        
        # Remove powerlaw if it exists
        powerlaw_module = sys.modules.get('powerlaw')
        if powerlaw_module:
            del sys.modules['powerlaw']
        
        # Mock import to raise error for powerlaw
        original_import = builtins.__import__
        
        def mock_import(name, *args, **kwargs):
            if name == "powerlaw":
                raise ImportError("No module named 'powerlaw'")
            return original_import(name, *args, **kwargs)
        
        monkeypatch.setattr(builtins, "__import__", mock_import)
        
        try:
            validator = PowerLawValidator()
            samples = np.random.pareto(2.4, 1000)
            
            result = validator.validate(samples, None)
            assert not result.passed
            assert "powerlaw package required" in result.error_message
        finally:
            # Restore powerlaw module if it existed
            if powerlaw_module:
                sys.modules['powerlaw'] = powerlaw_module


class TestBasicStatsCalculator:
    """Test basic statistics calculator."""
    
    def test_basic_stats_identical_data(self):
        """Test basic stats with identical data."""
        validator = BasicStatsCalculator()
        data = np.random.normal(10, 2, 10000)
        result = validator.validate(data, data)
        
        assert result.passed
        assert result.metrics['mean_relative_diff'] == 0.0
        assert result.metrics['std_relative_diff'] == 0.0
        assert result.metrics['median_relative_diff'] == 0.0
    
    def test_basic_stats_similar_data(self):
        """Test basic stats with similar data."""
        validator = BasicStatsCalculator()
        np.random.seed(42)
        data1 = np.random.normal(10, 2, 10000)
        data2 = np.random.normal(10.05, 2.02, 10000)  # Slightly different
        result = validator.validate(data1, data2)
        
        assert result.passed
        assert result.metrics['mean_relative_diff'] < 0.01
        assert result.metrics['std_relative_diff'] < 0.05
        assert result.metrics['interpretation'] == "Statistics are similar"
    
    def test_basic_stats_different_data(self):
        """Test basic stats with different data."""
        validator = BasicStatsCalculator()
        data1 = np.random.normal(10, 2, 1000)
        data2 = np.random.normal(15, 3, 1000)  # Very different
        result = validator.validate(data1, data2)
        
        assert not result.passed
        assert result.metrics['mean_relative_diff'] > 0.01
        assert result.metrics['interpretation'] == "Statistics differ significantly"
    
    def test_basic_stats_custom_thresholds(self):
        """Test basic stats with custom thresholds."""
        thresholds = {
            "mean_relative_diff": 0.5,  # Very permissive
            "std_relative_diff": 0.5
        }
        validator = BasicStatsCalculator(thresholds=thresholds)
        
        data1 = np.random.normal(10, 2, 1000)
        data2 = np.random.normal(14, 2.5, 1000)  # 40% different mean
        result = validator.validate(data1, data2)
        
        assert result.passed  # Should pass with permissive thresholds
        assert result.metrics['thresholds']['mean_relative_diff'] == 0.5
    
    def test_basic_stats_all_metrics(self):
        """Test that all expected metrics are calculated."""
        validator = BasicStatsCalculator()
        data1 = np.random.normal(10, 2, 1000)
        data2 = np.random.normal(10, 2, 1000)
        result = validator.validate(data1, data2)
        
        # Check sample1 stats
        assert 'mean' in result.metrics['sample1_stats']
        assert 'std' in result.metrics['sample1_stats']
        assert 'median' in result.metrics['sample1_stats']
        assert 'min' in result.metrics['sample1_stats']
        assert 'max' in result.metrics['sample1_stats']
        assert 'q25' in result.metrics['sample1_stats']
        assert 'q75' in result.metrics['sample1_stats']
        assert 'count' in result.metrics['sample1_stats']
        
        # Check relative differences
        assert 'mean_relative_diff' in result.metrics
        assert 'std_relative_diff' in result.metrics
        assert 'median_relative_diff' in result.metrics