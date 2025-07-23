"""Test configuration validation."""

import pytest
from rlx_datapipe.reconstruction.config import ReplayOptimizationConfig


def test_valid_config():
    """Test that valid configuration passes validation."""
    config = ReplayOptimizationConfig()
    assert config.drift_threshold == 0.001
    assert config.max_book_levels == 20


def test_invalid_drift_threshold():
    """Test invalid drift threshold values."""
    with pytest.raises(ValueError, match="drift_threshold must be between 0 and 1"):
        ReplayOptimizationConfig(drift_threshold=0)
    
    with pytest.raises(ValueError, match="drift_threshold must be between 0 and 1"):
        ReplayOptimizationConfig(drift_threshold=1.5)


def test_invalid_book_levels():
    """Test invalid max_book_levels values."""
    with pytest.raises(ValueError, match="max_book_levels must be between 1 and 1000"):
        ReplayOptimizationConfig(max_book_levels=0)
    
    with pytest.raises(ValueError, match="max_book_levels must be between 1 and 1000"):
        ReplayOptimizationConfig(max_book_levels=1001)


def test_invalid_batch_size():
    """Test invalid micro_batch_size values."""
    with pytest.raises(ValueError, match="micro_batch_size must be positive"):
        ReplayOptimizationConfig(micro_batch_size=0)


def test_invalid_memory_limit():
    """Test invalid max_memory_mb values."""
    with pytest.raises(ValueError, match="max_memory_mb must be between 100 and 10000"):
        ReplayOptimizationConfig(max_memory_mb=50)
    
    with pytest.raises(ValueError, match="max_memory_mb must be between 100 and 10000"):
        ReplayOptimizationConfig(max_memory_mb=20000)


def test_high_throughput_config():
    """Test high throughput configuration preset."""
    config = ReplayOptimizationConfig()
    high_perf = config.get_high_throughput_config()
    
    assert high_perf.drift_threshold == 0.05
    assert high_perf.resync_on_drift is False
    assert high_perf.micro_batch_size == 10_000
    assert high_perf.skip_enrichment is True