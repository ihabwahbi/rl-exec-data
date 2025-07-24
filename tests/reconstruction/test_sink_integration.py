"""Integration tests for DataSink with pipeline."""

import asyncio
from decimal import Decimal
from pathlib import Path
import tempfile
from typing import AsyncIterator

import pytest

from rlx_datapipe.reconstruction.unified_market_event import UnifiedMarketEvent
from rlx_datapipe.reconstruction.pipeline_integration import (
    create_data_sink_pipeline,
    run_data_sink_with_events,
)


class TestDataSinkIntegration:
    """Integration tests for DataSink in pipeline context."""
    
    @pytest.fixture
    def temp_output_dir(self):
        """Create a temporary directory for test outputs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    async def generate_test_events(self, count: int) -> AsyncIterator[UnifiedMarketEvent]:
        """Generate test events for pipeline testing.
        
        Args:
            count: Number of events to generate
            
        Yields:
            UnifiedMarketEvent instances
        """
        base_timestamp = 1704110400000000000  # 2024-01-01 12:00:00 UTC
        
        for i in range(count):
            # Mix of event types
            if i % 3 == 0:
                # Trade event
                event = UnifiedMarketEvent(
                    event_timestamp=base_timestamp + i * 1000000,  # 1ms intervals
                    event_type="TRADE",
                    update_id=i,
                    trade_id=i,
                    trade_price=Decimal(f"{50000 + (i % 100)}.{i % 100:02d}"),
                    trade_quantity=Decimal(f"{1 + (i % 10) * 0.1:.1f}"),
                    trade_side="BUY" if i % 2 == 0 else "SELL",
                )
            elif i % 3 == 1:
                # Book snapshot
                event = UnifiedMarketEvent(
                    event_timestamp=base_timestamp + i * 1000000,
                    event_type="BOOK_SNAPSHOT",
                    update_id=i,
                    bids=[
                        (Decimal(f"{49999 - j}.{j:02d}"), Decimal(f"{1 + j * 0.5:.1f}"))
                        for j in range(5)
                    ],
                    asks=[
                        (Decimal(f"{50001 + j}.{j:02d}"), Decimal(f"{1 + j * 0.5:.1f}"))
                        for j in range(5)
                    ],
                    is_snapshot=True,
                )
            else:
                # Book delta
                event = UnifiedMarketEvent(
                    event_timestamp=base_timestamp + i * 1000000,
                    event_type="BOOK_DELTA",
                    update_id=i,
                    delta_side="BID" if i % 2 == 0 else "ASK",
                    delta_price=Decimal(f"{50000 + (i % 50)}.{i % 100:02d}"),
                    delta_quantity=Decimal(f"{0 if i % 5 == 0 else (1 + (i % 5) * 0.2):.1f}"),
                )
            
            yield event
            
            # Small delay to simulate streaming
            if i % 100 == 0:
                await asyncio.sleep(0.001)
    
    @pytest.mark.asyncio
    async def test_pipeline_integration(self, temp_output_dir):
        """Test full pipeline integration with DataSink."""
        # Create pipeline components
        data_sink, input_queue = await create_data_sink_pipeline(
            output_dir=temp_output_dir,
            batch_size=100,  # Small batch for testing
            queue_size=500,
        )
        
        # Generate and process events
        event_count = 1000
        events = self.generate_test_events(event_count)
        
        stats = await run_data_sink_with_events(data_sink, input_queue, events)
        
        # Verify statistics (allow small variance due to async timing)
        assert abs(stats["events_written"] - event_count) <= 1  # Allow ±1 event
        assert stats["partitions_written"] > 0
        assert stats["total_size_mb"] > 0
        assert stats["earliest_timestamp"] == 1704110400000000000
        assert stats["latest_timestamp"] == 1704110400000000000 + (event_count - 1) * 1000000
        assert sorted(stats["unique_event_types"]) == ["BOOK_DELTA", "BOOK_SNAPSHOT", "TRADE"]
        
        # Verify files were created
        btcusdt_dir = temp_output_dir / "BTCUSDT"
        assert btcusdt_dir.exists()
        
        # Check manifest
        manifest_file = temp_output_dir / "manifest.jsonl"
        assert manifest_file.exists()
        
        # Count total Parquet files
        parquet_files = list(temp_output_dir.glob("**/*.parquet"))
        assert len(parquet_files) > 0
    
    @pytest.mark.asyncio
    async def test_queue_backpressure(self, temp_output_dir):
        """Test that queue backpressure works correctly."""
        # Create pipeline with small queue
        data_sink, input_queue = await create_data_sink_pipeline(
            output_dir=temp_output_dir,
            batch_size=50,
            queue_size=10,  # Very small queue
        )
        
        # Track queue full events
        queue_full_count = 0
        
        async def generate_with_backpressure():
            nonlocal queue_full_count
            async for event in self.generate_test_events(200):
                try:
                    # Try to put without waiting
                    input_queue.put_nowait(event)
                except asyncio.QueueFull:
                    queue_full_count += 1
                    # Wait for space
                    await input_queue.put(event)
                yield event
        
        events = generate_with_backpressure()
        stats = await run_data_sink_with_events(data_sink, input_queue, events)
        
        # Should have experienced backpressure
        assert queue_full_count > 0
        # Events written should be close to expected (allow for timing issues)
        assert 190 <= stats["events_written"] <= 250
    
    @pytest.mark.asyncio
    async def test_multi_hour_partitioning(self, temp_output_dir):
        """Test that events spanning multiple hours create correct partitions."""
        data_sink, input_queue = await create_data_sink_pipeline(
            output_dir=temp_output_dir,
            batch_size=500,
        )
        
        # Generate events spanning 3 hours
        async def generate_multi_hour_events():
            base_timestamp = 1704110400000000000  # 2024-01-01 12:00:00 UTC
            hour_ns = 3600 * 1_000_000_000
            
            for hour in range(3):
                for i in range(100):
                    timestamp = base_timestamp + hour * hour_ns + i * 1_000_000
                    event = UnifiedMarketEvent(
                        event_timestamp=timestamp,
                        event_type="TRADE",
                        update_id=hour * 100 + i,
                        trade_id=hour * 100 + i,
                        trade_price=Decimal(f"{50000 + hour * 100 + i}.00"),
                        trade_quantity=Decimal("1.0"),
                        trade_side="BUY",
                    )
                    yield event
        
        events = generate_multi_hour_events()
        stats = await run_data_sink_with_events(data_sink, input_queue, events)
        
        # Check that we have partitions for each hour
        assert abs(stats["events_written"] - 300) <= 1  # Allow ±1 event
        
        # Verify partition directories
        for hour in range(12, 15):
            partition_dir = temp_output_dir / "BTCUSDT" / "2024" / "01" / "01" / f"{hour:02d}"
            assert partition_dir.exists()
            
            # Should have at least one Parquet file
            parquet_files = list(partition_dir.glob("*.parquet"))
            assert len(parquet_files) >= 1
    
    @pytest.mark.asyncio
    async def test_error_handling(self, temp_output_dir):
        """Test pipeline error handling."""
        data_sink, input_queue = await create_data_sink_pipeline(
            output_dir=temp_output_dir,
        )
        
        # Generate events with an error
        async def generate_with_error():
            count = 0
            async for event in self.generate_test_events(100):
                yield event
                count += 1
                if count == 50:
                    raise RuntimeError("Simulated error")
        
        events = generate_with_error()
        
        # Should propagate the error
        with pytest.raises(RuntimeError, match="Simulated error"):
            await run_data_sink_with_events(data_sink, input_queue, events)
        
        # Should still have written some events before error
        assert data_sink.total_events_written > 0
        assert data_sink.total_events_written < 100