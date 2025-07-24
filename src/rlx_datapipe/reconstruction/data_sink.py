"""Data sink module for writing processed market events to partitioned Parquet files.

This module handles the final stage of the reconstruction pipeline, writing
UnifiedMarketEvent objects to hourly-partitioned Parquet files with decimal128
precision for all price and quantity fields.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Dict, Any
import json
from dataclasses import dataclass, field

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger

from rlx_datapipe.reconstruction.unified_market_event import UnifiedMarketEvent
from rlx_datapipe.reconstruction.config import ReplayOptimizationConfig
from rlx_datapipe.reconstruction.manifest import ManifestTracker, PartitionMetadata


# Constants
NANOSECONDS_PER_SECOND = 1_000_000_000
BYTES_PER_MB = 1024 * 1024
DEFAULT_BATCH_SIZE = 5000
DEFAULT_MAX_FILE_SIZE_MB = 400
DEFAULT_QUEUE_SIZE = 5000


@dataclass
class DataSinkConfig:
    """Configuration for the DataSink component."""
    output_dir: Path
    symbol: str = "BTCUSDT"  # Trading symbol for partitioning
    batch_size: int = DEFAULT_BATCH_SIZE
    max_file_size_mb: int = DEFAULT_MAX_FILE_SIZE_MB  # Target file size between 100-500MB
    enable_compression: bool = True
    compression_codec: str = "snappy"
    input_queue_size: int = DEFAULT_QUEUE_SIZE
    

class DataSink:
    """Writes unified market events to partitioned Parquet files.
    
    This class handles:
    - Queue-based input with backpressure control
    - Decimal128(38,18) precision for price/quantity fields
    - Hourly partitioning with atomic writes
    - Manifest tracking for written partitions
    - Memory-bounded batch accumulation
    """
    
    def __init__(self, config: DataSinkConfig):
        """Initialize the DataSink with configuration.
        
        Args:
            config: DataSink configuration including output directory and batch settings
        """
        self.config = config
        self.output_dir = config.output_dir
        self.batch_size = config.batch_size
        self.max_file_size_bytes = config.max_file_size_mb * BYTES_PER_MB
        
        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Clean up any orphaned temp files from previous runs
        self._cleanup_temp_files()
        
        # Current batch accumulator
        self.current_batch: List[Dict[str, Any]] = []
        
        # Partition tracking  
        self.current_partition: Optional[str] = None
        self.partition_row_count: Dict[str, int] = {}
        self.partition_size_bytes: Dict[str, int] = {}
        self.partition_file_count: Dict[str, int] = {}
        
        # Define the Parquet schema with decimal128 precision
        self._schema = self._create_parquet_schema()
        
        # Initialize manifest tracker
        self.manifest = ManifestTracker(self.output_dir)
        
        # Statistics
        self.total_events_written = 0
        self.total_partitions_written = 0
        
        # Memory monitoring
        self.estimated_batch_memory = 0
        self.max_memory_bytes = 500 * 1024 * 1024  # 500MB max memory for batches
        
        logger.info(f"DataSink initialized with output directory: {self.output_dir}")
    
    def _create_parquet_schema(self) -> pa.Schema:
        """Create PyArrow schema for UnifiedMarketEvent with decimal128 types.
        
        Returns:
            PyArrow schema with proper decimal128(38,18) fields
        """
        # Define decimal type for prices and quantities
        decimal_type = pa.decimal128(38, 18)
        
        schema = pa.schema([
            # Core identifiers
            pa.field("event_timestamp", pa.int64(), nullable=False),
            pa.field("event_type", pa.string(), nullable=False),
            pa.field("update_id", pa.int64(), nullable=True),
            
            # Trade-specific fields
            pa.field("trade_id", pa.int64(), nullable=True),
            pa.field("trade_price", decimal_type, nullable=True),
            pa.field("trade_quantity", decimal_type, nullable=True),
            pa.field("trade_side", pa.string(), nullable=True),
            
            # Book snapshot fields (stored as JSON for nested lists)
            pa.field("bids", pa.string(), nullable=True),  # JSON serialized
            pa.field("asks", pa.string(), nullable=True),  # JSON serialized
            pa.field("is_snapshot", pa.bool_(), nullable=True),
            
            # Book delta fields
            pa.field("delta_side", pa.string(), nullable=True),
            pa.field("delta_price", decimal_type, nullable=True),
            pa.field("delta_quantity", decimal_type, nullable=True),
        ])
        
        return schema
    
    async def start(self, input_queue: asyncio.Queue[UnifiedMarketEvent]) -> None:
        """Start processing events from the input queue.
        
        This method runs continuously, pulling events from the queue and writing
        them to Parquet files in batches.
        
        Args:
            input_queue: Async queue providing UnifiedMarketEvent objects
        """
        logger.info("DataSink started, waiting for events...")
        
        try:
            while True:
                # Get event from queue (blocks if empty, providing backpressure)
                event = await input_queue.get()
                
                # Validate event structure
                try:
                    self._validate_event(event)
                except ValueError as e:
                    logger.error(f"Invalid event skipped: {e}")
                    continue
                
                # Convert event to dict format for accumulation
                event_dict = self._event_to_dict(event)
                self.current_batch.append(event_dict)
                
                # Estimate memory usage (rough approximation)
                self.estimated_batch_memory += self._estimate_event_memory(event_dict)
                
                # Check if we should write the batch (size or memory limit)
                if (len(self.current_batch) >= self.batch_size or 
                    self.estimated_batch_memory >= self.max_memory_bytes):
                    
                    if self.estimated_batch_memory >= self.max_memory_bytes:
                        logger.warning(f"Writing batch due to memory limit: {self.estimated_batch_memory / 1024 / 1024:.1f}MB")
                    
                    await self._write_batch()
                    self.estimated_batch_memory = 0
                    
        except asyncio.CancelledError:
            # Write any remaining events before shutting down
            if self.current_batch:
                await self._write_batch()
            logger.info("DataSink shutdown complete")
            raise
    
    async def flush(self) -> None:
        """Flush any pending events in the batch.
        
        This method ensures all accumulated events are written to disk.
        """
        if self.current_batch:
            await self._write_batch()
            self.estimated_batch_memory = 0
    
    async def _write_batch(self) -> None:
        """Write the current batch to Parquet file(s).
        
        This method handles partitioning by hour and ensures atomic writes.
        """
        if not self.current_batch:
            return
            
        # Pre-sort events by timestamp for better compression
        self.current_batch.sort(key=lambda x: x["event_timestamp"])
        
        # Group events by hour partition
        partitioned_events = self._partition_by_hour(self.current_batch)
        
        # Write each partition concurrently using asyncio
        write_tasks = []
        for partition_key, events in partitioned_events.items():
            # Create task for async write
            task = asyncio.create_task(self._write_partition(partition_key, events))
            write_tasks.append(task)
        
        # Wait for all writes to complete
        await asyncio.gather(*write_tasks)
        
        # Clear the batch
        self.current_batch.clear()
    
    def _validate_event(self, event: UnifiedMarketEvent) -> None:
        """Validate event has required fields and correct structure.
        
        Args:
            event: UnifiedMarketEvent to validate
            
        Raises:
            ValueError: If event is invalid
        """
        # Check required core fields
        if not hasattr(event, 'event_timestamp') or event.event_timestamp is None:
            raise ValueError("Event missing required field: event_timestamp")
        if not hasattr(event, 'event_type') or event.event_type is None:
            raise ValueError("Event missing required field: event_type")
        if event.event_type not in ["TRADE", "BOOK_SNAPSHOT", "BOOK_DELTA"]:
            raise ValueError(f"Invalid event_type: {event.event_type}")
            
        # Validate type-specific fields
        if event.event_type == "TRADE":
            if event.trade_id is None or event.trade_price is None or event.trade_quantity is None:
                raise ValueError("TRADE event missing required fields")
            if event.trade_side not in ["BUY", "SELL"]:
                raise ValueError(f"Invalid trade_side: {event.trade_side}")
                
        elif event.event_type == "BOOK_SNAPSHOT":
            if event.bids is None and event.asks is None:
                raise ValueError("BOOK_SNAPSHOT event must have bids or asks")
                
        elif event.event_type == "BOOK_DELTA":
            if event.delta_side not in ["BID", "ASK"]:
                raise ValueError(f"Invalid delta_side: {event.delta_side}")
            if event.delta_price is None or event.delta_quantity is None:
                raise ValueError("BOOK_DELTA event missing required fields")
    
    def _event_to_dict(self, event: UnifiedMarketEvent) -> Dict[str, Any]:
        """Convert UnifiedMarketEvent to dictionary for Parquet writing.
        
        Args:
            event: UnifiedMarketEvent object
            
        Returns:
            Dictionary with properly formatted values
        """
        # Start with core fields
        result = {
            "event_timestamp": event.event_timestamp,
            "event_type": event.event_type,
            "update_id": event.update_id,
        }
        
        # Add trade fields if present
        if event.event_type == "TRADE":
            result.update({
                "trade_id": event.trade_id,
                "trade_price": event.trade_price,
                "trade_quantity": event.trade_quantity,
                "trade_side": event.trade_side,
            })
        else:
            result.update({
                "trade_id": None,
                "trade_price": None,
                "trade_quantity": None,
                "trade_side": None,
            })
        
        # Add book snapshot fields if present
        if event.event_type == "BOOK_SNAPSHOT":
            # Serialize bid/ask lists as JSON for storage, converting Decimals to strings
            result.update({
                "bids": json.dumps([[str(price), str(qty)] for price, qty in event.bids]) if event.bids else None,
                "asks": json.dumps([[str(price), str(qty)] for price, qty in event.asks]) if event.asks else None,
                "is_snapshot": event.is_snapshot,
            })
        else:
            result.update({
                "bids": None,
                "asks": None,
                "is_snapshot": None,
            })
        
        # Add book delta fields if present
        if event.event_type == "BOOK_DELTA":
            result.update({
                "delta_side": event.delta_side,
                "delta_price": event.delta_price,
                "delta_quantity": event.delta_quantity,
            })
        else:
            result.update({
                "delta_side": None,
                "delta_price": None,
                "delta_quantity": None,
            })
        
        return result
    
    def _partition_by_hour(self, events: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group events by hour partition.
        
        Args:
            events: List of event dictionaries
            
        Returns:
            Dictionary mapping partition keys to event lists
        """
        partitions: Dict[str, List[Dict[str, Any]]] = {}
        
        for event in events:
            # Convert nanosecond timestamp to datetime (UTC)
            timestamp_ns = event["event_timestamp"]
            timestamp_s = timestamp_ns // NANOSECONDS_PER_SECOND
            dt = datetime.fromtimestamp(timestamp_s, tz=timezone.utc)
            
            # Create partition key: YYYY/MM/DD/HH
            partition_key = f"{dt.year:04d}/{dt.month:02d}/{dt.day:02d}/{dt.hour:02d}"
            
            if partition_key not in partitions:
                partitions[partition_key] = []
            partitions[partition_key].append(event)
        
        return partitions
    
    async def _write_partition(self, partition_key: str, events: List[Dict[str, Any]]) -> None:
        """Write events to a specific partition with atomic operation.
        
        Args:
            partition_key: Partition path (YYYY/MM/DD/HH)
            events: List of events for this partition
        """
        # Convert events to PyArrow table
        table = self._create_arrow_table(events)
        
        # Create partition directory
        partition_dir = self.output_dir / self.config.symbol / partition_key
        partition_dir.mkdir(parents=True, exist_ok=True)
        
        # Check current partition size
        partition_path_str = str(partition_dir)
        current_size = self.partition_size_bytes.get(partition_path_str, 0)
        
        # Estimate size of new data
        estimated_new_size = self._estimate_table_size(table)
        
        # If partition already has files and would exceed max size, use incremented filename
        if current_size > 0 and current_size + estimated_new_size > self.max_file_size_bytes:
            # Start new file in same partition
            file_count = self.partition_file_count.get(partition_path_str, 0) + 1
            self.partition_file_count[partition_path_str] = file_count
            # Reset size tracking for new file sequence
            self.partition_size_bytes[partition_path_str] = 0
            logger.info(f"Partition {partition_key} would exceed size limit ({current_size:,} + {estimated_new_size:,} > {self.max_file_size_bytes:,}), creating file #{file_count}")
        else:
            file_count = self.partition_file_count.get(partition_path_str, 0)
        
        # Generate filename with nanosecond timestamp and optional file count
        first_timestamp = events[0]["event_timestamp"]
        if file_count > 0:
            filename = f"events_{first_timestamp}_{file_count:03d}.parquet"
        else:
            filename = f"events_{first_timestamp}.parquet"
        file_path = partition_dir / filename
        
        # Write to temporary file first for atomic operation
        temp_path = file_path.with_suffix('.tmp')
        
        try:
            pq.write_table(
                table, 
                temp_path,
                compression=self.config.compression_codec if self.config.enable_compression else None,
                use_dictionary=False,  # Disable dictionary encoding for numeric precision
                use_deprecated_int96_timestamps=False,
                coerce_timestamps=None,  # Preserve exact timestamps
            )
            
            # Atomic rename (cross-platform compatible)
            temp_path.replace(file_path)
            
        except Exception as e:
            # Clean up temp file on failure
            if temp_path.exists():
                temp_path.unlink()
            logger.error(f"Failed to write partition {file_path}: {e}")
            raise
        
        # Update statistics
        self.total_events_written += len(events)
        self.total_partitions_written += 1
        
        # Track partition size
        file_size = file_path.stat().st_size
        self.partition_size_bytes[partition_path_str] = self.partition_size_bytes.get(partition_path_str, 0) + file_size
        
        # Extract metadata for manifest
        timestamp_min = min(e["event_timestamp"] for e in events)
        timestamp_max = max(e["event_timestamp"] for e in events)
        event_types = list(set(e["event_type"] for e in events))
        
        # Create metadata entry
        metadata = PartitionMetadata(
            partition_path=f"BTCUSDT/{partition_key}",
            file_name=filename,
            row_count=len(events),
            file_size_bytes=file_size,
            timestamp_min=timestamp_min,
            timestamp_max=timestamp_max,
            event_types=sorted(event_types),
            write_timestamp=datetime.now(timezone.utc).isoformat(),
        )
        
        # Add to manifest
        self.manifest.add_partition(metadata)
        
        logger.debug(f"Wrote {len(events)} events to {file_path} (size: {file_size:,} bytes)")
    
    
    def _create_arrow_table(self, events: List[Dict[str, Any]]) -> pa.Table:
        """Convert list of event dictionaries to PyArrow table.
        
        Args:
            events: List of event dictionaries
            
        Returns:
            PyArrow table with proper schema and decimal128 types
        """
        # Prepare arrays for each column
        arrays = []
        
        # Core fields (always present)
        arrays.append(pa.array([e["event_timestamp"] for e in events], type=pa.int64()))
        arrays.append(pa.array([e["event_type"] for e in events], type=pa.string()))
        arrays.append(pa.array([e["update_id"] for e in events], type=pa.int64()))
        
        # Trade fields
        arrays.append(pa.array([e["trade_id"] for e in events], type=pa.int64()))
        arrays.append(pa.array(
            [e["trade_price"] for e in events], 
            type=pa.decimal128(38, 18)
        ))
        arrays.append(pa.array(
            [e["trade_quantity"] for e in events], 
            type=pa.decimal128(38, 18)
        ))
        arrays.append(pa.array([e["trade_side"] for e in events], type=pa.string()))
        
        # Book snapshot fields (stored as JSON strings)
        arrays.append(pa.array([e["bids"] for e in events], type=pa.string()))
        arrays.append(pa.array([e["asks"] for e in events], type=pa.string()))
        arrays.append(pa.array([e["is_snapshot"] for e in events], type=pa.bool_()))
        
        # Book delta fields
        arrays.append(pa.array([e["delta_side"] for e in events], type=pa.string()))
        arrays.append(pa.array(
            [e["delta_price"] for e in events], 
            type=pa.decimal128(38, 18)
        ))
        arrays.append(pa.array(
            [e["delta_quantity"] for e in events], 
            type=pa.decimal128(38, 18)
        ))
        
        # Create table with schema
        table = pa.Table.from_arrays(arrays, schema=self._schema)
        
        return table
    
    def _estimate_table_size(self, table: pa.Table) -> int:
        """Estimate the size of a PyArrow table when written to Parquet.
        
        Args:
            table: PyArrow table
            
        Returns:
            Estimated size in bytes
        """
        # Simple estimation: use uncompressed size and apply compression ratio
        # Typical Snappy compression ratio for financial data is ~0.3-0.5
        # For uncompressed, Parquet still has some overhead
        uncompressed_size = table.nbytes
        if self.config.enable_compression:
            compression_ratio = 0.4
        else:
            # Uncompressed Parquet has metadata overhead
            compression_ratio = 1.2
        
        return int(uncompressed_size * compression_ratio)
    
    def _cleanup_temp_files(self) -> None:
        """Clean up any orphaned .tmp files from previous runs.
        
        This ensures we don't have partial files from crashed processes.
        """
        temp_files = list(self.output_dir.glob("**/*.tmp"))
        
        if temp_files:
            logger.warning(f"Found {len(temp_files)} orphaned temp files, cleaning up...")
            for temp_file in temp_files:
                try:
                    temp_file.unlink()
                    logger.debug(f"Removed orphaned temp file: {temp_file}")
                except Exception as e:
                    logger.error(f"Failed to remove temp file {temp_file}: {e}")
    
    def _estimate_event_memory(self, event_dict: Dict[str, Any]) -> int:
        """Estimate memory usage of a single event dictionary.
        
        Args:
            event_dict: Event dictionary
            
        Returns:
            Estimated memory in bytes
        """
        # Base overhead per dict
        memory = 240  # Dict overhead
        
        # Add memory for each field
        for key, value in event_dict.items():
            memory += 50  # Key string overhead
            
            if value is None:
                memory += 16
            elif isinstance(value, (int, float)):
                memory += 28
            elif isinstance(value, Decimal):
                memory += 80  # Decimal objects are larger
            elif isinstance(value, str):
                memory += 50 + len(value) * 2  # Unicode strings use ~2 bytes per char
            elif isinstance(value, list):
                memory += 64 + len(value) * 100  # Rough estimate for bid/ask lists
        
        return memory