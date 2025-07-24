"""Pipeline integration for the reconstruction components.

Connects event processing output to DataSink input.
"""

import asyncio
from pathlib import Path
from typing import Optional, AsyncIterator
import polars as pl

from loguru import logger

from rlx_datapipe.reconstruction.data_sink import DataSink, DataSinkConfig
from rlx_datapipe.reconstruction.unified_market_event import UnifiedMarketEvent


async def create_data_sink_pipeline(
    output_dir: Path,
    symbol: str = "BTCUSDT",
    batch_size: int = 5000,
    queue_size: int = 5000,
    max_file_size_mb: int = 400,
) -> tuple[DataSink, asyncio.Queue[UnifiedMarketEvent]]:
    """Create a DataSink with input queue for pipeline integration.
    
    Args:
        output_dir: Output directory for Parquet files
        symbol: Trading symbol for partitioning
        batch_size: Batch size for data sink
        queue_size: Size of input queue
        max_file_size_mb: Maximum file size in MB
        
    Returns:
        Tuple of (DataSink instance, input queue)
    """
    # Create configuration
    sink_config = DataSinkConfig(
        output_dir=output_dir,
        symbol=symbol,
        batch_size=batch_size,
        max_file_size_mb=max_file_size_mb,
        enable_compression=True,
        compression_codec="snappy",
        input_queue_size=queue_size,
    )
    
    # Create data sink
    data_sink = DataSink(sink_config)
    
    # Create input queue
    input_queue: asyncio.Queue[UnifiedMarketEvent] = asyncio.Queue(maxsize=queue_size)
    
    logger.info(f"Created DataSink pipeline with output to {output_dir}")
    
    return data_sink, input_queue


async def run_data_sink_with_events(
    data_sink: DataSink,
    input_queue: asyncio.Queue[UnifiedMarketEvent],
    events: AsyncIterator[UnifiedMarketEvent],
) -> dict:
    """Run the data sink with a stream of events.
    
    Args:
        data_sink: DataSink instance
        input_queue: Queue for events
        events: Async iterator of unified market events
        
    Returns:
        Pipeline statistics
    """
    # Start the data sink consumer
    sink_task = asyncio.create_task(data_sink.start(input_queue))
    
    try:
        # Feed events to the queue
        event_count = 0
        async for event in events:
            await input_queue.put(event)
            event_count += 1
            
            if event_count % 10000 == 0:
                logger.info(f"Processed {event_count} events")
        
        logger.info(f"All {event_count} events queued, flushing and shutting down sink...")
        
        # Flush any remaining events
        await data_sink.flush()
        
        # Small delay to ensure all writes complete
        await asyncio.sleep(0.1)
        
        # Signal completion by cancelling the sink task
        sink_task.cancel()
        
        try:
            await sink_task
        except asyncio.CancelledError:
            pass
        
        # Get final statistics
        manifest_stats = data_sink.manifest.get_manifest_stats()
        
        stats = {
            "events_written": data_sink.total_events_written,
            "partitions_written": data_sink.total_partitions_written,
            "total_size_mb": manifest_stats.get("total_size_mb", 0),
            "earliest_timestamp": manifest_stats.get("earliest_timestamp"),
            "latest_timestamp": manifest_stats.get("latest_timestamp"),
            "unique_event_types": manifest_stats.get("unique_event_types", []),
        }
        
        logger.info(f"Pipeline complete: {stats}")
        return stats
        
    except Exception as e:
        logger.error(f"Pipeline processing failed: {e}")
        sink_task.cancel()
        raise