"""Unit tests for the DataSink module."""

import asyncio
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import tempfile
from typing import Dict, Any, List
import json

import pytest
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from rlx_datapipe.reconstruction.data_sink import DataSink, DataSinkConfig
from rlx_datapipe.reconstruction.unified_market_event import UnifiedMarketEvent


class TestDataSink:
    """Test suite for DataSink functionality."""
    
    @pytest.fixture
    def temp_output_dir(self):
        """Create a temporary directory for test outputs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def data_sink_config(self, temp_output_dir):
        """Create a test configuration."""
        return DataSinkConfig(
            output_dir=temp_output_dir,
            batch_size=3,  # Small batch for testing
            max_file_size_mb=1,
            enable_compression=True,
            compression_codec="snappy",
            input_queue_size=10
        )
    
    @pytest.fixture
    def data_sink(self, data_sink_config):
        """Create a DataSink instance."""
        return DataSink(data_sink_config)
    
    def test_initialization(self, data_sink, temp_output_dir):
        """Test DataSink initialization."""
        assert data_sink.output_dir == temp_output_dir
        assert data_sink.batch_size == 3
        assert data_sink.max_file_size_bytes == 1 * 1024 * 1024
        assert data_sink.current_batch == []
        assert data_sink.total_events_written == 0
        assert temp_output_dir.exists()
    
    def test_parquet_schema_creation(self, data_sink):
        """Test that the Parquet schema is created correctly with decimal128 types."""
        schema = data_sink._schema
        
        # Check core fields
        assert schema.field("event_timestamp").type == pa.int64()
        assert not schema.field("event_timestamp").nullable
        assert schema.field("event_type").type == pa.string()
        assert schema.field("update_id").type == pa.int64()
        assert schema.field("update_id").nullable
        
        # Check decimal fields
        decimal_type = pa.decimal128(38, 18)
        assert schema.field("trade_price").type == decimal_type
        assert schema.field("trade_quantity").type == decimal_type
        assert schema.field("delta_price").type == decimal_type
        assert schema.field("delta_quantity").type == decimal_type
        
        # Check nullable fields
        assert schema.field("trade_id").nullable
        assert schema.field("trade_side").nullable
        assert schema.field("bids").nullable
        assert schema.field("asks").nullable
    
    def test_event_to_dict_trade(self, data_sink):
        """Test conversion of trade event to dictionary."""
        event = UnifiedMarketEvent(
            event_timestamp=1234567890123456789,
            event_type="TRADE",
            update_id=100,
            trade_id=1001,
            trade_price=Decimal("50000.123456789012345678"),
            trade_quantity=Decimal("0.123456789012345678"),
            trade_side="BUY"
        )
        
        result = data_sink._event_to_dict(event)
        
        assert result["event_timestamp"] == 1234567890123456789
        assert result["event_type"] == "TRADE"
        assert result["update_id"] == 100
        assert result["trade_id"] == 1001
        assert result["trade_price"] == Decimal("50000.123456789012345678")
        assert result["trade_quantity"] == Decimal("0.123456789012345678")
        assert result["trade_side"] == "BUY"
        
        # Non-trade fields should be None
        assert result["bids"] is None
        assert result["asks"] is None
        assert result["is_snapshot"] is None
        assert result["delta_side"] is None
        assert result["delta_price"] is None
        assert result["delta_quantity"] is None
    
    def test_event_to_dict_book_snapshot(self, data_sink):
        """Test conversion of book snapshot event to dictionary."""
        bids = [[Decimal("49999.5"), Decimal("1.5")], [Decimal("49999.0"), Decimal("2.0")]]
        asks = [[Decimal("50000.5"), Decimal("1.0")], [Decimal("50001.0"), Decimal("2.5")]]
        
        event = UnifiedMarketEvent(
            event_timestamp=1234567890123456789,
            event_type="BOOK_SNAPSHOT",
            update_id=200,
            bids=bids,
            asks=asks,
            is_snapshot=True
        )
        
        result = data_sink._event_to_dict(event)
        
        assert result["event_type"] == "BOOK_SNAPSHOT"
        # Verify JSON serialization converts Decimals to strings
        assert result["bids"] == json.dumps([["49999.5", "1.5"], ["49999.0", "2.0"]])
        assert result["asks"] == json.dumps([["50000.5", "1.0"], ["50001.0", "2.5"]])
        assert result["is_snapshot"] is True
        
        # Non-book fields should be None
        assert result["trade_id"] is None
        assert result["trade_price"] is None
        assert result["delta_side"] is None
    
    def test_event_to_dict_book_delta(self, data_sink):
        """Test conversion of book delta event to dictionary."""
        event = UnifiedMarketEvent(
            event_timestamp=1234567890123456789,
            event_type="BOOK_DELTA",
            update_id=300,
            delta_side="BID",
            delta_price=Decimal("49998.5"),
            delta_quantity=Decimal("0.5")
        )
        
        result = data_sink._event_to_dict(event)
        
        assert result["event_type"] == "BOOK_DELTA"
        assert result["delta_side"] == "BID"
        assert result["delta_price"] == Decimal("49998.5")
        assert result["delta_quantity"] == Decimal("0.5")
        
        # Non-delta fields should be None
        assert result["trade_id"] is None
        assert result["bids"] is None
        assert result["is_snapshot"] is None
    
    def test_partition_by_hour(self, data_sink):
        """Test hourly partitioning of events."""
        events = [
            # Same hour
            {"event_timestamp": 1704110400000000000},  # 2024-01-01 12:00:00
            {"event_timestamp": 1704110700000000000},  # 2024-01-01 12:05:00
            {"event_timestamp": 1704113999000000000},  # 2024-01-01 12:59:59
            # Next hour
            {"event_timestamp": 1704114000000000000},  # 2024-01-01 13:00:00
            {"event_timestamp": 1704114300000000000},  # 2024-01-01 13:05:00
            # Different day
            {"event_timestamp": 1704196800000000000},  # 2024-01-02 12:00:00
        ]
        
        partitions = data_sink._partition_by_hour(events)
        
        assert len(partitions) == 3
        assert "2024/01/01/12" in partitions
        assert "2024/01/01/13" in partitions
        assert "2024/01/02/12" in partitions
        
        assert len(partitions["2024/01/01/12"]) == 3
        assert len(partitions["2024/01/01/13"]) == 2
        assert len(partitions["2024/01/02/12"]) == 1
    
    @pytest.mark.asyncio
    async def test_queue_based_input(self, data_sink):
        """Test queue-based input with backpressure."""
        input_queue = asyncio.Queue(maxsize=5)
        
        # Create test events
        events = [
            UnifiedMarketEvent(
                event_timestamp=1704110400000000000 + i * 1000000000,
                event_type="TRADE",
                update_id=i,
                trade_id=i,
                trade_price=Decimal(f"{50000 + i}.0"),
                trade_quantity=Decimal("1.0"),
                trade_side="BUY"
            )
            for i in range(5)
        ]
        
        # Put events in queue
        for event in events:
            await input_queue.put(event)
        
        # Start data sink task
        task = asyncio.create_task(data_sink.start(input_queue))
        
        # Wait a bit for processing
        await asyncio.sleep(0.1)
        
        # Check that events were accumulated in batch
        assert len(data_sink.current_batch) == 2  # 5 events with batch_size=3
        
        # Cancel the task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    
    def test_data_sink_config_defaults(self):
        """Test DataSinkConfig default values."""
        config = DataSinkConfig(output_dir=Path("/tmp/test"))
        
        assert config.batch_size == 5000
        assert config.max_file_size_mb == 400
        assert config.enable_compression is True
        assert config.compression_codec == "snappy"
        assert config.input_queue_size == 5000
    
    def test_create_arrow_table(self, data_sink):
        """Test creation of PyArrow table with decimal128 types."""
        events = [
            {
                "event_timestamp": 1234567890123456789,
                "event_type": "TRADE",
                "update_id": 100,
                "trade_id": 1001,
                "trade_price": Decimal("50000.123456789012345678"),
                "trade_quantity": Decimal("0.123456789012345678"),
                "trade_side": "BUY",
                "bids": None,
                "asks": None,
                "is_snapshot": None,
                "delta_side": None,
                "delta_price": None,
                "delta_quantity": None,
            },
            {
                "event_timestamp": 1234567890223456789,
                "event_type": "BOOK_DELTA",
                "update_id": 101,
                "trade_id": None,
                "trade_price": None,
                "trade_quantity": None,
                "trade_side": None,
                "bids": None,
                "asks": None,
                "is_snapshot": None,
                "delta_side": "BID",
                "delta_price": Decimal("49999.5"),
                "delta_quantity": Decimal("1.5"),
            }
        ]
        
        table = data_sink._create_arrow_table(events)
        
        # Verify schema
        assert table.schema == data_sink._schema
        
        # Verify data
        assert table.num_rows == 2
        assert table.column("event_timestamp").to_pylist() == [1234567890123456789, 1234567890223456789]
        assert table.column("event_type").to_pylist() == ["TRADE", "BOOK_DELTA"]
        
        # Check decimal fields maintain precision
        trade_prices = table.column("trade_price").to_pylist()
        assert trade_prices[0] == Decimal("50000.123456789012345678")
        assert trade_prices[1] is None
        
        delta_prices = table.column("delta_price").to_pylist()
        assert delta_prices[0] is None
        assert delta_prices[1] == Decimal("49999.5")
    
    @pytest.mark.asyncio
    async def test_write_partition(self, data_sink, temp_output_dir):
        """Test writing events to Parquet partition."""
        events = [
            {
                "event_timestamp": 1704110400000000000,  # 2024-01-01 12:00:00 UTC
                "event_type": "TRADE",
                "update_id": 100,
                "trade_id": 1001,
                "trade_price": Decimal("50000.0"),
                "trade_quantity": Decimal("1.0"),
                "trade_side": "BUY",
                "bids": None,
                "asks": None,
                "is_snapshot": None,
                "delta_side": None,
                "delta_price": None,
                "delta_quantity": None,
            }
        ]
        
        partition_key = "2024/01/01/12"
        await data_sink._write_partition(partition_key, events)
        
        # Verify file was created
        expected_path = temp_output_dir / "BTCUSDT" / partition_key / "events_1704110400000000000.parquet"
        assert expected_path.exists()
        
        # Verify statistics updated
        assert data_sink.total_events_written == 1
        assert data_sink.total_partitions_written == 1
        
        # Read back and verify content
        table = pq.read_table(expected_path)
        assert table.num_rows == 1
        assert table.column("event_type").to_pylist() == ["TRADE"]
        assert table.column("trade_price").to_pylist() == [Decimal("50000.0")]
    
    @pytest.mark.asyncio
    async def test_file_size_splitting(self, temp_output_dir):
        """Test that large partitions are split into multiple files."""
        # Create data sink with small max file size
        config = DataSinkConfig(
            output_dir=temp_output_dir,
            batch_size=100,
            max_file_size_mb=1,  # 1MB limit to trigger splitting
            enable_compression=False  # Disable compression for predictable sizes
        )
        data_sink = DataSink(config)
        
        # Create many events for same partition
        base_timestamp = 1704110400000000000  # 2024-01-01 12:00:00 UTC
        partition_key = "2024/01/01/12"
        
        # Write first batch
        events_batch1 = [
            {
                "event_timestamp": base_timestamp + i,
                "event_type": "TRADE",
                "update_id": i,
                "trade_id": i,
                "trade_price": Decimal(f"{50000 + i}.0"),
                "trade_quantity": Decimal("1.0"),
                "trade_side": "BUY",
                "bids": None,
                "asks": None,
                "is_snapshot": None,
                "delta_side": None,
                "delta_price": None,
                "delta_quantity": None,
            }
            for i in range(5000)  # Large batch to ensure file size
        ]
        
        await data_sink._write_partition(partition_key, events_batch1)
        
        # Write second batch - should create new file
        events_batch2 = [
            {
                "event_timestamp": base_timestamp + 10000 + i,
                "event_type": "TRADE",
                "update_id": 10000 + i,
                "trade_id": 10000 + i,
                "trade_price": Decimal(f"{60000 + i}.0"),
                "trade_quantity": Decimal("2.0"),
                "trade_side": "SELL",
                "bids": None,
                "asks": None,
                "is_snapshot": None,
                "delta_side": None,
                "delta_price": None,
                "delta_quantity": None,
            }
            for i in range(5000)
        ]
        
        await data_sink._write_partition(partition_key, events_batch2)
        
        # Check that multiple files were created
        partition_dir = temp_output_dir / "BTCUSDT" / partition_key
        parquet_files = list(partition_dir.glob("*.parquet"))
        
        assert len(parquet_files) >= 2, "Should have created multiple files due to size limit"
        
        # Verify filenames
        filenames = sorted([f.name for f in parquet_files])
        assert filenames[0] == f"events_{base_timestamp}.parquet"
        assert "_001.parquet" in filenames[1] or "_002.parquet" in filenames[1]
        
        # Verify total events written
        assert data_sink.total_events_written == 10000
    
    def test_estimate_table_size(self, data_sink):
        """Test table size estimation."""
        # Create a small table
        events = [{
            "event_timestamp": 1234567890123456789,
            "event_type": "TRADE",
            "update_id": 100,
            "trade_id": 1001,
            "trade_price": Decimal("50000.0"),
            "trade_quantity": Decimal("1.0"),
            "trade_side": "BUY",
            "bids": None,
            "asks": None,
            "is_snapshot": None,
            "delta_side": None,
            "delta_price": None,
            "delta_quantity": None,
        }]
        
        table = data_sink._create_arrow_table(events)
        estimated_size = data_sink._estimate_table_size(table)
        
        # Should apply compression ratio (0.4 for compressed)
        assert estimated_size < table.nbytes  # Compressed size < uncompressed
        assert estimated_size == int(table.nbytes * 0.4)  # Default compression ratio
        
        # Test uncompressed estimation
        data_sink.config.enable_compression = False
        estimated_uncompressed = data_sink._estimate_table_size(table)
        assert estimated_uncompressed > table.nbytes  # Parquet overhead
        assert estimated_uncompressed == int(table.nbytes * 1.2)
    
    @pytest.mark.asyncio
    async def test_atomic_write_success(self, data_sink, temp_output_dir):
        """Test atomic write operation completes successfully."""
        events = [{
            "event_timestamp": 1704110400000000000,
            "event_type": "TRADE",
            "update_id": 100,
            "trade_id": 1001,
            "trade_price": Decimal("50000.0"),
            "trade_quantity": Decimal("1.0"),
            "trade_side": "BUY",
            "bids": None,
            "asks": None,
            "is_snapshot": None,
            "delta_side": None,
            "delta_price": None,
            "delta_quantity": None,
        }]
        
        partition_key = "2024/01/01/12"
        await data_sink._write_partition(partition_key, events)
        
        # Verify final file exists
        expected_path = temp_output_dir / "BTCUSDT" / partition_key / "events_1704110400000000000.parquet"
        assert expected_path.exists()
        
        # Verify no temp files remain
        temp_files = list(temp_output_dir.glob("**/*.tmp"))
        assert len(temp_files) == 0
    
    def test_cleanup_temp_files(self, temp_output_dir):
        """Test cleanup of orphaned temp files."""
        # Create some fake temp files
        partition_dir = temp_output_dir / "BTCUSDT" / "2024" / "01" / "01" / "12"
        partition_dir.mkdir(parents=True)
        
        temp_file1 = partition_dir / "events_123.tmp"
        temp_file2 = partition_dir / "events_456.tmp"
        temp_file1.write_text("orphaned data")
        temp_file2.write_text("orphaned data")
        
        # Create data sink (should clean up temp files on init)
        config = DataSinkConfig(output_dir=temp_output_dir)
        data_sink = DataSink(config)
        
        # Verify temp files were cleaned up
        assert not temp_file1.exists()
        assert not temp_file2.exists()
    
    @pytest.mark.asyncio
    async def test_atomic_write_failure_cleanup(self, temp_output_dir, monkeypatch):
        """Test that temp files are cleaned up on write failure."""
        config = DataSinkConfig(output_dir=temp_output_dir)
        data_sink = DataSink(config)
        
        events = [{
            "event_timestamp": 1704110400000000000,
            "event_type": "TRADE",
            "update_id": 100,
            "trade_id": 1001,
            "trade_price": Decimal("50000.0"),
            "trade_quantity": Decimal("1.0"),
            "trade_side": "BUY",
            "bids": None,
            "asks": None,
            "is_snapshot": None,
            "delta_side": None,
            "delta_price": None,
            "delta_quantity": None,
        }]
        
        # Mock write_table to fail
        def mock_write_table(*args, **kwargs):
            # Create the temp file to simulate partial write
            temp_path = args[1]
            temp_path.write_text("partial data")
            raise IOError("Simulated write failure")
        
        monkeypatch.setattr(pq, "write_table", mock_write_table)
        
        partition_key = "2024/01/01/12"
        
        # Should raise the error
        with pytest.raises(IOError, match="Simulated write failure"):
            await data_sink._write_partition(partition_key, events)
        
        # Verify no temp files remain
        temp_files = list(temp_output_dir.glob("**/*.tmp"))
        assert len(temp_files) == 0
        
        # Verify final file doesn't exist
        expected_path = temp_output_dir / "BTCUSDT" / partition_key / "events_1704110400000000000.parquet"
        assert not expected_path.exists()
    
    @pytest.mark.asyncio
    async def test_manifest_integration(self, data_sink, temp_output_dir):
        """Test that manifest tracking works with data sink."""
        events = [
            {
                "event_timestamp": 1704110400000000000 + i,
                "event_type": "TRADE" if i % 2 == 0 else "BOOK_DELTA",
                "update_id": i,
                "trade_id": i if i % 2 == 0 else None,
                "trade_price": Decimal(f"{50000 + i}.0") if i % 2 == 0 else None,
                "trade_quantity": Decimal("1.0") if i % 2 == 0 else None,
                "trade_side": "BUY" if i % 2 == 0 else None,
                "bids": None,
                "asks": None,
                "is_snapshot": None,
                "delta_side": "BID" if i % 2 == 1 else None,
                "delta_price": Decimal(f"{49999 + i}.0") if i % 2 == 1 else None,
                "delta_quantity": Decimal("0.5") if i % 2 == 1 else None,
            }
            for i in range(100)
        ]
        
        partition_key = "2024/01/01/12"
        await data_sink._write_partition(partition_key, events)
        
        # Check manifest was updated
        entries = data_sink.manifest.read_manifest()
        assert len(entries) == 1
        
        entry = entries[0]
        assert entry.partition_path == "BTCUSDT/2024/01/01/12"
        assert entry.row_count == 100
        assert entry.timestamp_min == 1704110400000000000
        assert entry.timestamp_max == 1704110400000000099
        assert sorted(entry.event_types) == ["BOOK_DELTA", "TRADE"]
        assert entry.file_size_bytes > 0
        
        # Check manifest stats
        stats = data_sink.manifest.get_manifest_stats()
        assert stats["total_partitions"] == 1
        assert stats["total_rows"] == 100
        assert stats["total_size_bytes"] == entry.file_size_bytes
    
    @pytest.mark.asyncio
    async def test_batch_sorting(self, data_sink, temp_output_dir):
        """Test that events are sorted by timestamp before writing."""
        # Create events with deliberately unsorted timestamps
        unsorted_timestamps = [
            1704110400000000005,
            1704110400000000002,
            1704110400000000008,
            1704110400000000001,
            1704110400000000006,
        ]
        
        events = [
            {
                "event_timestamp": ts,
                "event_type": "TRADE",
                "update_id": i,
                "trade_id": i,
                "trade_price": Decimal("50000.0"),
                "trade_quantity": Decimal("1.0"),
                "trade_side": "BUY",
                "bids": None,
                "asks": None,
                "is_snapshot": None,
                "delta_side": None,
                "delta_price": None,
                "delta_quantity": None,
            }
            for i, ts in enumerate(unsorted_timestamps)
        ]
        
        # Add to batch
        data_sink.current_batch = events.copy()
        
        # Write batch
        await data_sink._write_batch()
        
        # Read back the written file
        partition_dir = temp_output_dir / "BTCUSDT" / "2024/01/01/12"
        parquet_files = list(partition_dir.glob("*.parquet"))
        assert len(parquet_files) == 1
        
        table = pq.read_table(parquet_files[0])
        timestamps = table.column("event_timestamp").to_pylist()
        
        # Verify events are sorted
        assert timestamps == sorted(unsorted_timestamps)
    
    def test_memory_estimation(self, data_sink):
        """Test memory estimation for events."""
        event_dict = {
            "event_timestamp": 1704110400000000000,
            "event_type": "TRADE",
            "update_id": 100,
            "trade_id": 1001,
            "trade_price": Decimal("50000.123456789012345678"),
            "trade_quantity": Decimal("0.123456789012345678"),
            "trade_side": "BUY",
            "bids": None,
            "asks": None,
            "is_snapshot": None,
            "delta_side": None,
            "delta_price": None,
            "delta_quantity": None,
        }
        
        memory = data_sink._estimate_event_memory(event_dict)
        
        # Should be reasonable size (few KB per event)
        assert 500 < memory < 2000
        
        # Test with book snapshot (larger due to bid/ask lists)
        book_event = {
            "event_timestamp": 1704110400000000000,
            "event_type": "BOOK_SNAPSHOT",
            "update_id": 200,
            "trade_id": None,
            "trade_price": None,
            "trade_quantity": None,
            "trade_side": None,
            "bids": "[[\"49999.5\", \"1.5\"], [\"49999.0\", \"2.0\"]]",
            "asks": "[[\"50000.5\", \"1.0\"], [\"50001.0\", \"2.5\"]]",
            "is_snapshot": True,
            "delta_side": None,
            "delta_price": None,
            "delta_quantity": None,
        }
        
        book_memory = data_sink._estimate_event_memory(book_event)
        assert book_memory > memory  # Book events use more memory
    
    @pytest.mark.asyncio
    async def test_concurrent_partition_writes(self, temp_output_dir):
        """Test that multiple partitions are written concurrently."""
        config = DataSinkConfig(
            output_dir=temp_output_dir,
            batch_size=1000,
        )
        data_sink = DataSink(config)
        
        # Create events spanning multiple hours
        events = []
        for hour in range(3):  # 3 different hours
            base_ts = 1704110400000000000 + hour * 3600 * 1_000_000_000
            for i in range(100):
                events.append({
                    "event_timestamp": base_ts + i,
                    "event_type": "TRADE",
                    "update_id": hour * 100 + i,
                    "trade_id": hour * 100 + i,
                    "trade_price": Decimal(f"{50000 + hour * 100 + i}.0"),
                    "trade_quantity": Decimal("1.0"),
                    "trade_side": "BUY",
                    "bids": None,
                    "asks": None,
                    "is_snapshot": None,
                    "delta_side": None,
                    "delta_price": None,
                    "delta_quantity": None,
                })
        
        # Set batch and write
        data_sink.current_batch = events
        
        # Time the write operation
        import time
        start_time = time.time()
        await data_sink._write_batch()
        elapsed = time.time() - start_time
        
        # Verify all partitions were written
        for hour in range(12, 15):
            partition_dir = temp_output_dir / "BTCUSDT" / "2024" / "01" / "01" / f"{hour:02d}"
            assert partition_dir.exists()
            parquet_files = list(partition_dir.glob("*.parquet"))
            assert len(parquet_files) == 1
        
        # Should be reasonably fast due to concurrent writes
        assert elapsed < 2.0  # Should complete in under 2 seconds
        
        # Verify total events written
        assert data_sink.total_events_written == 300
        assert data_sink.total_partitions_written == 3