"""
Tests for delta analyzer module.
"""

import pytest
import polars as pl
from unittest.mock import Mock, patch
import time

from rlx_datapipe.analysis.delta_analyzer import (
    SequenceGapAnalyzer,
    DataQualityAnalyzer,
    MemoryProfiler,
    ThroughputAnalyzer,
    validate_book_delta_schema,
    create_sample_delta_data
)


class TestSequenceGapAnalyzer:
    """Test the SequenceGapAnalyzer class."""
    
    def test_analyze_gaps_no_gaps(self):
        """Test gap analysis with no gaps."""
        analyzer = SequenceGapAnalyzer()
        update_ids = [1, 2, 3, 4, 5]
        
        result = analyzer.analyze_gaps(update_ids)
        
        assert result["count"] == 0
        assert result["max_gap"] == 0
        assert result["mean_gap"] == 0.0
        assert result["gap_ratio_percent"] == 0.0
        assert result["gaps_by_size"] == {}
    
    def test_analyze_gaps_with_gaps(self):
        """Test gap analysis with gaps."""
        analyzer = SequenceGapAnalyzer()
        update_ids = [1, 2, 5, 6, 10]  # Gaps of 2 and 3
        
        result = analyzer.analyze_gaps(update_ids)
        
        assert result["count"] == 2
        assert result["max_gap"] == 3
        assert result["mean_gap"] == 2.5
        assert result["gap_ratio_percent"] > 0
        assert "1-10" in result["gaps_by_size"]
    
    def test_analyze_gaps_insufficient_data(self):
        """Test gap analysis with insufficient data."""
        analyzer = SequenceGapAnalyzer()
        update_ids = [1]
        
        result = analyzer.analyze_gaps(update_ids)
        
        assert result["count"] == 0
        assert result["max_gap"] == 0
        assert result["mean_gap"] == 0.0
        assert result["gap_ratio_percent"] == 0.0
    
    def test_analyze_gaps_large_gaps(self):
        """Test gap analysis with large gaps."""
        analyzer = SequenceGapAnalyzer()
        update_ids = [1, 2, 1005, 1006]  # Gap of 1002
        
        result = analyzer.analyze_gaps(update_ids)
        
        assert result["count"] == 1
        assert result["max_gap"] == 1002
        assert "1000+" in result["gaps_by_size"]
        assert result["gaps_by_size"]["1000+"] == 1


class TestDataQualityAnalyzer:
    """Test the DataQualityAnalyzer class."""
    
    def test_analyze_quality_valid_data(self):
        """Test quality analysis with valid data."""
        analyzer = DataQualityAnalyzer()
        
        df = pl.DataFrame({
            "update_id": [1, 2, 3, 4, 5],
            "price": [100.0, 101.0, 102.0, 103.0, 104.0],
            "new_quantity": [1.0, 2.0, 3.0, 4.0, 5.0]
        })
        
        result = analyzer.analyze_quality(df)
        
        assert result["valid_update_ids"] == 5
        assert result["invalid_update_ids"] == 0
        assert result["valid_prices"] == 5
        assert result["invalid_prices"] == 0
        assert result["valid_quantities"] == 5
        assert result["invalid_quantities"] == 0
    
    def test_analyze_quality_invalid_data(self):
        """Test quality analysis with invalid data."""
        analyzer = DataQualityAnalyzer()
        
        df = pl.DataFrame({
            "update_id": [1, 2, 0, -1, 5],  # Invalid: 0 and -1
            "price": [100.0, 101.0, 0.0, -1.0, 104.0],  # Invalid: 0.0 and -1.0
            "new_quantity": [1.0, 2.0, 3.0, -1.0, 5.0]  # Invalid: -1.0
        })
        
        result = analyzer.analyze_quality(df)
        
        assert result["valid_update_ids"] == 3
        assert result["invalid_update_ids"] == 2
        assert result["valid_prices"] == 3
        assert result["invalid_prices"] == 2
        assert result["valid_quantities"] == 4
        assert result["invalid_quantities"] == 1
    
    def test_analyze_quality_missing_columns(self):
        """Test quality analysis with missing columns."""
        analyzer = DataQualityAnalyzer()
        
        df = pl.DataFrame({
            "update_id": [1, 2, 3, 4, 5]
            # Missing price and new_quantity columns
        })
        
        result = analyzer.analyze_quality(df)
        
        assert result["valid_update_ids"] == 5
        assert result["invalid_update_ids"] == 0
        # Should handle missing columns gracefully
        assert result["valid_prices"] == 0
        assert result["invalid_prices"] == 5


class TestMemoryProfiler:
    """Test the MemoryProfiler class."""
    
    @patch('psutil.Process')
    def test_record_memory(self, mock_process):
        """Test memory recording."""
        # Mock memory info
        mock_process.return_value.memory_info.return_value.rss = 1024 * 1024 * 1024  # 1GB
        
        profiler = MemoryProfiler(limit_gb=24.0)
        memory_gb = profiler.record_memory()
        
        assert memory_gb == 1.0
        assert len(profiler.samples) == 1
        assert profiler.samples[0] == 1024 * 1024 * 1024
    
    @patch('psutil.Process')
    def test_get_memory_stats(self, mock_process):
        """Test memory statistics calculation."""
        # Mock memory info calls
        memory_values = [1024 * 1024 * 1024, 2 * 1024 * 1024 * 1024, 3 * 1024 * 1024 * 1024]  # 1GB, 2GB, 3GB
        mock_process.return_value.memory_info.return_value.rss = memory_values[0]
        
        profiler = MemoryProfiler(limit_gb=24.0)
        
        # Record several samples
        for i, value in enumerate(memory_values):
            mock_process.return_value.memory_info.return_value.rss = value
            profiler.record_memory()
        
        stats = profiler.get_memory_stats()
        
        assert stats["peak_gb"] == 3.0
        assert stats["min_gb"] == 1.0
        assert stats["mean_gb"] == 2.0
        assert stats["p95_gb"] > 0
    
    def test_get_memory_stats_empty(self):
        """Test memory statistics with no samples."""
        profiler = MemoryProfiler(limit_gb=24.0)
        
        stats = profiler.get_memory_stats()
        
        assert stats["peak_gb"] == 0.0
        assert stats["p95_gb"] == 0.0
        assert stats["mean_gb"] == 0.0
        assert stats["min_gb"] == 0.0


class TestThroughputAnalyzer:
    """Test the ThroughputAnalyzer class."""
    
    def test_throughput_calculation(self):
        """Test throughput calculation."""
        analyzer = ThroughputAnalyzer()
        
        analyzer.start_timing()
        time.sleep(0.1)  # Small delay
        analyzer.record_processing(1000, 1024 * 1024)  # 1000 events, 1MB
        analyzer.end_timing()
        
        stats = analyzer.get_throughput_stats()
        
        assert stats["events_per_second"] > 0
        assert stats["mb_per_second"] > 0
        assert stats["processing_time_seconds"] > 0
    
    def test_throughput_no_timing(self):
        """Test throughput calculation without timing."""
        analyzer = ThroughputAnalyzer()
        
        stats = analyzer.get_throughput_stats()
        
        assert stats["events_per_second"] == 0.0
        assert stats["mb_per_second"] == 0.0
        assert stats["processing_time_seconds"] == 0.0
    
    def test_record_processing(self):
        """Test recording processing metrics."""
        analyzer = ThroughputAnalyzer()
        
        analyzer.record_processing(100, 1024)
        analyzer.record_processing(200, 2048)
        
        assert analyzer.events_processed == 300
        assert analyzer.bytes_processed == 3072


class TestValidateBookDeltaSchema:
    """Test the validate_book_delta_schema function."""
    
    def test_valid_schema(self):
        """Test validation with valid schema."""
        df = pl.DataFrame({
            "update_id": [1, 2, 3],
            "origin_time": [1234567890000000000, 1234567891000000000, 1234567892000000000],
            "side": ["bid", "ask", "bid"],
            "price": [100.0, 101.0, 102.0],
            "new_quantity": [1.0, 2.0, 3.0]
        })
        
        is_valid, errors = validate_book_delta_schema(df)
        
        assert is_valid
        assert len(errors) == 0
    
    def test_missing_columns(self):
        """Test validation with missing columns."""
        df = pl.DataFrame({
            "update_id": [1, 2, 3],
            "origin_time": [1234567890000000000, 1234567891000000000, 1234567892000000000]
            # Missing side, price, new_quantity
        })
        
        is_valid, errors = validate_book_delta_schema(df)
        
        assert not is_valid
        assert len(errors) > 0
        assert "Missing required columns" in errors[0]
    
    def test_empty_dataframe(self):
        """Test validation with empty DataFrame."""
        df = pl.DataFrame({
            "update_id": [],
            "origin_time": [],
            "side": [],
            "price": [],
            "new_quantity": []
        })
        
        is_valid, errors = validate_book_delta_schema(df)
        
        assert not is_valid
        assert "DataFrame is empty" in errors
    
    def test_invalid_data_types(self):
        """Test validation with invalid data types."""
        df = pl.DataFrame({
            "update_id": ["1", "2", "3"],  # Should be integer
            "origin_time": ["1234567890000000000", "1234567891000000000", "1234567892000000000"],  # Should be integer
            "side": ["bid", "ask", "bid"],
            "price": [100.0, 101.0, 102.0],
            "new_quantity": [1.0, 2.0, 3.0]
        })
        
        is_valid, errors = validate_book_delta_schema(df)
        
        assert not is_valid
        assert len(errors) > 0


class TestCreateSampleDeltaData:
    """Test the create_sample_delta_data function."""
    
    def test_create_sample_data(self):
        """Test creating sample data."""
        df = create_sample_delta_data(100)
        
        assert len(df) == 100
        assert "update_id" in df.columns
        assert "origin_time" in df.columns
        assert "side" in df.columns
        assert "price" in df.columns
        assert "new_quantity" in df.columns
    
    def test_create_sample_data_with_gaps(self):
        """Test creating sample data with gaps."""
        df = create_sample_delta_data(1000)
        
        # Check that gaps were introduced
        update_ids = df["update_id"].to_list()
        
        # Should have some gaps (not perfectly consecutive)
        expected_consecutive = list(range(1, 1001))
        assert update_ids != expected_consecutive
    
    def test_schema_validation_on_sample(self):
        """Test that sample data passes schema validation."""
        df = create_sample_delta_data(50)
        
        is_valid, errors = validate_book_delta_schema(df)
        
        assert is_valid
        assert len(errors) == 0