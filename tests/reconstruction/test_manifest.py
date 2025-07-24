"""Unit tests for the ManifestTracker module."""

import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile

import pytest

from rlx_datapipe.reconstruction.manifest import ManifestTracker, PartitionMetadata


class TestManifestTracker:
    """Test suite for ManifestTracker functionality."""
    
    @pytest.fixture
    def temp_output_dir(self):
        """Create a temporary directory for test outputs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def manifest_tracker(self, temp_output_dir):
        """Create a ManifestTracker instance."""
        return ManifestTracker(temp_output_dir)
    
    def test_initialization(self, manifest_tracker, temp_output_dir):
        """Test ManifestTracker initialization."""
        assert manifest_tracker.output_dir == temp_output_dir
        assert manifest_tracker.manifest_path == temp_output_dir / "manifest.jsonl"
        assert manifest_tracker.lock_path == temp_output_dir / ".manifest.lock"
        assert manifest_tracker.manifest_path.exists()
    
    def test_add_partition(self, manifest_tracker):
        """Test adding a partition to the manifest."""
        metadata = PartitionMetadata(
            partition_path="BTCUSDT/2024/01/01/12",
            file_name="events_1704110400000000000.parquet",
            row_count=5000,
            file_size_bytes=363293,
            timestamp_min=1704110400000000000,
            timestamp_max=1704113999999999999,
            event_types=["TRADE", "BOOK_DELTA"],
            write_timestamp=datetime.now(timezone.utc).isoformat(),
        )
        
        manifest_tracker.add_partition(metadata)
        
        # Verify entry was written
        with open(manifest_tracker.manifest_path, 'r') as f:
            line = f.readline().strip()
            data = json.loads(line)
            
        assert data["partition_path"] == "BTCUSDT/2024/01/01/12"
        assert data["file_name"] == "events_1704110400000000000.parquet"
        assert data["row_count"] == 5000
        assert data["event_types"] == ["TRADE", "BOOK_DELTA"]
    
    def test_read_manifest(self, manifest_tracker):
        """Test reading entries from the manifest."""
        # Add multiple entries
        metadata1 = PartitionMetadata(
            partition_path="BTCUSDT/2024/01/01/12",
            file_name="events_1704110400000000000.parquet",
            row_count=5000,
            file_size_bytes=363293,
            timestamp_min=1704110400000000000,
            timestamp_max=1704113999999999999,
            event_types=["TRADE"],
            write_timestamp=datetime.now(timezone.utc).isoformat(),
        )
        
        metadata2 = PartitionMetadata(
            partition_path="BTCUSDT/2024/01/01/13",
            file_name="events_1704114000000000000.parquet",
            row_count=4500,
            file_size_bytes=340000,
            timestamp_min=1704114000000000000,
            timestamp_max=1704117599999999999,
            event_types=["BOOK_SNAPSHOT", "BOOK_DELTA"],
            write_timestamp=datetime.now(timezone.utc).isoformat(),
        )
        
        manifest_tracker.add_partition(metadata1)
        manifest_tracker.add_partition(metadata2)
        
        # Read back
        entries = manifest_tracker.read_manifest()
        
        assert len(entries) == 2
        assert entries[0].file_name == "events_1704110400000000000.parquet"
        assert entries[1].file_name == "events_1704114000000000000.parquet"
        assert entries[0].row_count == 5000
        assert entries[1].row_count == 4500
    
    def test_get_partitions_for_time_range(self, manifest_tracker):
        """Test querying partitions by time range."""
        # Base timestamp: 2024-01-01 00:00:00 UTC
        base_ts = 1704067200
        
        # Add partitions for different hours
        for hour in range(12, 16):
            hour_start = base_ts + hour * 3600
            hour_end = base_ts + (hour + 1) * 3600 - 1
            
            metadata = PartitionMetadata(
                partition_path=f"BTCUSDT/2024/01/01/{hour:02d}",
                file_name=f"events_{hour_start}000000000.parquet",
                row_count=1000,
                file_size_bytes=100000,
                timestamp_min=hour_start * 1_000_000_000,
                timestamp_max=hour_end * 1_000_000_000,
                event_types=["TRADE"],
                write_timestamp=datetime.now(timezone.utc).isoformat(),
            )
            manifest_tracker.add_partition(metadata)
        
        # Query for hours 13-14  
        start_ns = (base_ts + 13 * 3600) * 1_000_000_000  # 13:00
        end_ns = (base_ts + 15 * 3600 - 1) * 1_000_000_000  # 14:59:59
        
        matching = manifest_tracker.get_partitions_for_time_range(start_ns, end_ns)
        
        assert len(matching) == 2
        assert "13" in matching[0].partition_path
        assert "14" in matching[1].partition_path
    
    def test_get_manifest_stats(self, manifest_tracker):
        """Test getting manifest statistics."""
        # Add some partitions
        metadata1 = PartitionMetadata(
            partition_path="BTCUSDT/2024/01/01/12",
            file_name="events_1704110400000000000.parquet",
            row_count=5000,
            file_size_bytes=1_000_000,
            timestamp_min=1704110400000000000,
            timestamp_max=1704113999999999999,
            event_types=["TRADE", "BOOK_DELTA"],
            write_timestamp=datetime.now(timezone.utc).isoformat(),
        )
        
        metadata2 = PartitionMetadata(
            partition_path="BTCUSDT/2024/01/01/13",
            file_name="events_1704114000000000000.parquet",
            row_count=4500,
            file_size_bytes=900_000,
            timestamp_min=1704114000000000000,
            timestamp_max=1704117599999999999,
            event_types=["BOOK_SNAPSHOT", "BOOK_DELTA"],
            write_timestamp=datetime.now(timezone.utc).isoformat(),
        )
        
        manifest_tracker.add_partition(metadata1)
        manifest_tracker.add_partition(metadata2)
        
        stats = manifest_tracker.get_manifest_stats()
        
        assert stats["total_partitions"] == 2
        assert stats["total_rows"] == 9500
        assert stats["total_size_bytes"] == 1_900_000
        assert stats["total_size_mb"] == 1.81
        assert stats["earliest_timestamp"] == 1704110400000000000
        assert stats["latest_timestamp"] == 1704117599999999999
        assert sorted(stats["unique_event_types"]) == ["BOOK_DELTA", "BOOK_SNAPSHOT", "TRADE"]
    
    def test_validate_manifest_with_corrupt_entry(self, manifest_tracker):
        """Test manifest validation with corrupt entries."""
        # Write some valid and invalid entries
        with open(manifest_tracker.manifest_path, 'w') as f:
            # Valid entry
            valid = json.dumps({
                "partition_path": "BTCUSDT/2024/01/01/12",
                "file_name": "events_1704110400000000000.parquet",
                "row_count": 5000,
                "file_size_bytes": 363293,
                "timestamp_min": 1704110400000000000,
                "timestamp_max": 1704113999999999999,
                "event_types": ["TRADE"],
                "write_timestamp": datetime.now(timezone.utc).isoformat(),
            })
            f.write(valid + '\n')
            
            # Invalid JSON
            f.write('{"invalid json\n')
            
            # Missing required field
            f.write('{"partition_path": "test"}\n')
        
        # Re-initialize to trigger validation
        new_tracker = ManifestTracker(manifest_tracker.output_dir)
        
        # Should still be able to read valid entries
        entries = new_tracker.read_manifest()
        assert len(entries) == 1
        assert entries[0].file_name == "events_1704110400000000000.parquet"
    
    def test_compact_manifest(self, manifest_tracker):
        """Test manifest compaction."""
        # Write mixed valid and invalid entries
        with open(manifest_tracker.manifest_path, 'w') as f:
            # Valid entry
            valid1 = json.dumps({
                "partition_path": "BTCUSDT/2024/01/01/12",
                "file_name": "events_1.parquet",
                "row_count": 1000,
                "file_size_bytes": 100000,
                "timestamp_min": 1000000000,
                "timestamp_max": 2000000000,
                "event_types": ["TRADE"],
                "write_timestamp": datetime.now(timezone.utc).isoformat(),
            })
            f.write(valid1 + '\n')
            
            # Invalid entry
            f.write('corrupt data\n')
            
            # Another valid entry
            valid2 = json.dumps({
                "partition_path": "BTCUSDT/2024/01/01/13",
                "file_name": "events_2.parquet",
                "row_count": 2000,
                "file_size_bytes": 200000,
                "timestamp_min": 3000000000,
                "timestamp_max": 4000000000,
                "event_types": ["BOOK_DELTA"],
                "write_timestamp": datetime.now(timezone.utc).isoformat(),
            })
            f.write(valid2 + '\n')
        
        # Compact the manifest
        manifest_tracker.compact_manifest()
        
        # Read back - should only have valid entries
        entries = manifest_tracker.read_manifest()
        assert len(entries) == 2
        assert entries[0].file_name == "events_1.parquet"
        assert entries[1].file_name == "events_2.parquet"
        
        # Verify file only has valid entries
        with open(manifest_tracker.manifest_path, 'r') as f:
            lines = f.readlines()
        assert len(lines) == 2
    
    def test_empty_manifest_stats(self, manifest_tracker):
        """Test getting stats from empty manifest."""
        stats = manifest_tracker.get_manifest_stats()
        
        assert stats["total_partitions"] == 0
        assert stats["total_rows"] == 0
        assert stats["total_size_bytes"] == 0
        assert stats["earliest_timestamp"] is None
        assert stats["latest_timestamp"] is None
        assert stats["unique_event_types"] == []