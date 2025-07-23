"""Tests for delta feed processor."""

import polars as pl
import pytest

from rlx_datapipe.reconstruction.delta_feed_processor import (
    DeltaFeedProcessor,
    SequenceGapInfo,
)


class TestDeltaFeedProcessor:
    """Test delta feed processor functionality."""
    
    def test_initialization(self):
        """Test processor initialization."""
        processor = DeltaFeedProcessor(gap_threshold=500)
        
        assert processor.gap_threshold == 500
        assert processor.last_update_id is None
        assert processor.stats.total_deltas == 0
        assert processor.stats.total_gaps == 0
        assert not processor.recovery_needed
    
    def test_validate_and_sort(self):
        """Test validation and sorting of delta batch."""
        processor = DeltaFeedProcessor()
        
        # Create test data with unsorted update_ids
        data = {
            "update_id": [103, 101, 102, 105, 104],
            "price": [100, 101, 102, 105, 104],
            "new_quantity": [10, 20, 30, 50, 40],
            "side": ["BID", "BID", "ASK", "ASK", "BID"],
        }
        df = pl.DataFrame(data)
        
        sorted_df, gaps = processor.validate_and_sort(df)
        
        # Check sorting
        update_ids = sorted_df["update_id"].to_list()
        assert update_ids == [101, 102, 103, 104, 105]
        
        # No gaps in continuous sequence
        assert len(gaps) == 0
        assert processor.last_update_id == 105
    
    def test_gap_detection_initial(self):
        """Test gap detection from initial state."""
        processor = DeltaFeedProcessor()
        processor.last_update_id = 100
        
        # Create data with gap
        data = {
            "update_id": [105, 106, 107],
            "price": [105, 106, 107],
            "new_quantity": [50, 60, 70],
            "side": ["BID", "ASK", "BID"],
        }
        df = pl.DataFrame(data)
        
        sorted_df, gaps = processor.validate_and_sort(df)
        
        # Should detect gap from 100 to 105
        assert len(gaps) == 1
        assert gaps[0].expected_id == 101
        assert gaps[0].actual_id == 105
        assert gaps[0].gap_size == 4
        
        # Stats should be updated
        assert processor.stats.total_gaps == 1
        assert processor.stats.max_gap_size == 4
    
    def test_gap_detection_within_batch(self):
        """Test gap detection within a single batch."""
        processor = DeltaFeedProcessor()
        
        # Create data with gaps within batch
        data = {
            "update_id": [100, 101, 105, 106, 110],
            "price": [100, 101, 105, 106, 110],
            "new_quantity": [10, 20, 50, 60, 100],
            "side": ["BID", "BID", "ASK", "ASK", "BID"],
        }
        df = pl.DataFrame(data)
        
        sorted_df, gaps = processor.validate_and_sort(df)
        
        # Should detect 2 gaps
        assert len(gaps) == 2
        
        # First gap: 101 -> 105
        assert gaps[0].expected_id == 102
        assert gaps[0].actual_id == 105
        assert gaps[0].gap_size == 3
        
        # Second gap: 106 -> 110
        assert gaps[1].expected_id == 107
        assert gaps[1].actual_id == 110
        assert gaps[1].gap_size == 3
        
        assert processor.stats.total_gaps == 2
        assert processor.stats.max_gap_size == 3
    
    def test_large_gap_recovery_signal(self):
        """Test recovery signaling for large gaps."""
        processor = DeltaFeedProcessor(gap_threshold=1000)
        processor.last_update_id = 1000
        
        # Create data with large gap
        data = {
            "update_id": [3000, 3001, 3002],
            "price": [3000, 3001, 3002],
            "new_quantity": [30, 31, 32],
            "side": ["BID", "ASK", "BID"],
        }
        df = pl.DataFrame(data)
        
        sorted_df, recovery_needed = processor.process_batch(df)
        
        # Should signal recovery
        assert recovery_needed
        assert processor.recovery_needed
        assert processor.stats.gaps_over_threshold == 1
        
        # Check after_gap column
        assert sorted_df["after_gap"][0] == True
        assert sorted_df["after_gap"][1] == False
        assert sorted_df["after_gap"][2] == False
    
    def test_process_batch_no_gaps(self):
        """Test processing batch without gaps."""
        processor = DeltaFeedProcessor()
        processor.last_update_id = 100
        
        # Create continuous data
        data = {
            "update_id": [101, 102, 103],
            "price": [101, 102, 103],
            "new_quantity": [10, 20, 30],
            "side": ["BID", "ASK", "BID"],
            "origin_time": [1000, 2000, 3000],
        }
        df = pl.DataFrame(data)
        
        sorted_df, recovery_needed = processor.process_batch(df)
        
        assert not recovery_needed
        assert "after_gap" in sorted_df.columns
        assert sorted_df["after_gap"].sum() == 0
    
    def test_gap_size_distribution(self):
        """Test gap size distribution tracking."""
        processor = DeltaFeedProcessor()
        
        # Process multiple batches with different gap sizes
        batches = [
            pl.DataFrame({"update_id": [1, 3, 5]}),  # Gaps of size 1
            pl.DataFrame({"update_id": [10, 13]}),   # Gap of size 2
            pl.DataFrame({"update_id": [15, 17]}),   # Gap of size 1
        ]
        
        for batch in batches:
            processor.validate_and_sort(batch)
        
        stats = processor.get_statistics()
        gap_dist = stats["gap_size_distribution"]
        
        # We expect:
        # Batch 1: gaps at 1->3 (size 1), 3->5 (size 1)
        # Batch 2: gap at 5->10 (size 4), 10->13 (size 2)
        # Batch 3: gap at 13->15 (size 1), 15->17 (size 1)
        assert gap_dist[1] == 4  # Four gaps of size 1
        assert gap_dist[2] == 1  # One gap of size 2
        assert gap_dist[4] == 1  # One gap of size 4 (from 5 to 10)
    
    def test_reset_sequence(self):
        """Test sequence reset functionality."""
        processor = DeltaFeedProcessor()
        processor.last_update_id = 1000
        processor.recovery_needed = True
        
        processor.reset_sequence(5000)
        
        assert processor.last_update_id == 5000
        assert processor.expected_next_id == 5001
        assert not processor.recovery_needed
    
    def test_get_gap_summary(self):
        """Test gap summary generation."""
        processor = DeltaFeedProcessor()
        
        # No gaps initially
        summary = processor.get_gap_summary()
        assert summary == "No sequence gaps detected"
        
        # Create some gaps
        data = pl.DataFrame({
            "update_id": [1, 3, 4, 10],
        })
        processor.validate_and_sort(data)
        
        summary = processor.get_gap_summary()
        assert "Total gaps: 2" in summary
        assert "Max gap size: 5" in summary
        assert "Size 1:" in summary
        assert "Size 5:" in summary
    
    def test_missing_update_id_column(self):
        """Test error handling for missing update_id column."""
        processor = DeltaFeedProcessor()
        
        # Create data without update_id
        data = {
            "price": [100, 101],
            "quantity": [10, 20],
        }
        df = pl.DataFrame(data)
        
        with pytest.raises(ValueError, match="missing required 'update_id' column"):
            processor.validate_and_sort(df)
    
    def test_throughput_calculation(self):
        """Test throughput statistics."""
        processor = DeltaFeedProcessor()
        
        # Process multiple batches
        for i in range(3):
            data = {
                "update_id": list(range(i * 100, (i + 1) * 100)),
                "price": list(range(i * 100, (i + 1) * 100)),
            }
            df = pl.DataFrame(data)
            processor.validate_and_sort(df)
        
        stats = processor.get_statistics()
        assert stats["total_deltas"] == 300
        assert stats["throughput"] > 0  # Should have calculated throughput