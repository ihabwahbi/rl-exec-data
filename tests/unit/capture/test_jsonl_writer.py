"""Unit tests for JSONLWriter."""

import json
import gzip
from pathlib import Path
import tempfile
import shutil
import pytest
from src.rlx_datapipe.capture.jsonl_writer import JSONLWriter


class TestJSONLWriter:
    """Test cases for JSONLWriter."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
        
    def test_write_uncompressed(self, temp_dir):
        """Test writing uncompressed JSONL."""
        writer = JSONLWriter(
            output_dir=temp_dir,
            file_prefix="test",
            compress=False,
            buffer_size=2
        )
        
        # Write records
        records = [
            {"id": 1, "data": "test1"},
            {"id": 2, "data": "test2"},
            {"id": 3, "data": "test3"}
        ]
        
        for record in records:
            writer.write(record)
            
        writer.close()
        
        # Check file was created
        files = list(Path(temp_dir).glob("test_*.jsonl"))
        assert len(files) == 1
        
        # Read and verify content
        with open(files[0], "r") as f:
            lines = f.readlines()
            
        assert len(lines) == 3
        for i, line in enumerate(lines):
            data = json.loads(line.strip())
            assert data == records[i]
            
    def test_write_compressed(self, temp_dir):
        """Test writing compressed JSONL."""
        writer = JSONLWriter(
            output_dir=temp_dir,
            file_prefix="test",
            compress=True,
            buffer_size=2
        )
        
        # Write records
        records = [
            {"id": 1, "data": "test1"},
            {"id": 2, "data": "test2"}
        ]
        
        for record in records:
            writer.write(record)
            
        writer.close()
        
        # Check file was created
        files = list(Path(temp_dir).glob("test_*.jsonl.gz"))
        assert len(files) == 1
        
        # Read and verify compressed content
        with gzip.open(files[0], "rt") as f:
            lines = f.readlines()
            
        assert len(lines) == 2
        for i, line in enumerate(lines):
            data = json.loads(line.strip())
            assert data == records[i]
            
    def test_buffer_behavior(self, temp_dir):
        """Test buffer flushing behavior."""
        writer = JSONLWriter(
            output_dir=temp_dir,
            file_prefix="test",
            compress=False,
            buffer_size=3
        )
        
        # Write 2 records (less than buffer size)
        writer.write({"id": 1})
        writer.write({"id": 2})
        
        # Check stats - should be buffered
        stats = writer.get_stats()
        assert stats["buffer_size"] == 2
        assert stats["current_file_records"] == 0
        
        # Write one more to trigger flush
        writer.write({"id": 3})
        
        stats = writer.get_stats()
        assert stats["buffer_size"] == 0
        assert stats["current_file_records"] == 3
        
        writer.close()
        
    def test_manual_flush(self, temp_dir):
        """Test manual flush."""
        writer = JSONLWriter(
            output_dir=temp_dir,
            file_prefix="test",
            compress=False,
            buffer_size=10
        )
        
        # Write and manually flush
        writer.write({"id": 1})
        writer.flush()
        
        stats = writer.get_stats()
        assert stats["buffer_size"] == 0
        assert stats["current_file_records"] == 1
        
        writer.close()
        
    def test_file_rotation(self, temp_dir):
        """Test file rotation."""
        import time
        writer = JSONLWriter(
            output_dir=temp_dir,
            file_prefix="test",
            compress=False,
            buffer_size=1,
            rotation_interval=0  # Force immediate rotation
        )
        
        # Write to first file
        writer.write({"id": 1})
        
        # Wait a bit more to ensure different timestamp
        time.sleep(1.1)
        
        # Force rotation by manipulating file start time
        writer._file_start_time = None
        
        # Write to second file
        writer.write({"id": 2})
        
        writer.close()
        
        # Check two files were created
        files = list(Path(temp_dir).glob("test_*.jsonl"))
        assert len(files) == 2
        
    def test_stats(self, temp_dir):
        """Test statistics tracking."""
        writer = JSONLWriter(
            output_dir=temp_dir,
            file_prefix="test",
            compress=False,
            buffer_size=2
        )
        
        # Write records
        for i in range(5):
            writer.write({"id": i})
            
        writer.flush()  # Flush to get accurate stats
        stats = writer.get_stats()
        assert stats["total_records"] == 5
        assert stats["current_file_records"] == 5  # All flushed
        assert stats["buffer_size"] == 0
        
        writer.close()