"""Tests for the SymbolWorker class."""

import asyncio
import multiprocessing
import time
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import pytest

from rlx_datapipe.reconstruction.symbol_worker import (
    SymbolWorker, symbol_worker_entry_point
)
from rlx_datapipe.reconstruction.config import SymbolConfig
from rlx_datapipe.reconstruction.symbol_router import RoutedMessage


class TestSymbolWorker:
    """Tests for SymbolWorker functionality."""
    
    @pytest.fixture
    def config(self):
        """Create test symbol configuration."""
        return SymbolConfig(
            name="BTC-USDT",
            enabled=True,
            memory_limit_mb=512,
            queue_size=100
        )
        
    @pytest.fixture
    def worker(self, config, tmp_path):
        """Create SymbolWorker instance."""
        input_queue = multiprocessing.Queue()
        shutdown_event = multiprocessing.Event()
        
        return SymbolWorker(
            symbol="BTC-USDT",
            input_queue=input_queue,
            config=config,
            shutdown_event=shutdown_event,
            output_dir=tmp_path
        )
        
    @pytest.mark.asyncio
    async def test_initialize_pipeline(self, worker):
        """Test pipeline initialization."""
        with patch('rlx_datapipe.reconstruction.symbol_worker.UnifiedEventStreamEnhanced') as mock_stream:
            with patch('rlx_datapipe.reconstruction.symbol_worker.create_data_sink_pipeline') as mock_sink:
                mock_sink.return_value = (Mock(), AsyncMock())
                
                await worker._initialize_pipeline()
                
                # Check components initialized
                assert worker.event_stream is not None
                assert worker.data_sink is not None
                assert worker.event_queue is not None
                
                # Check output directory created
                symbol_dir = worker.output_dir / "BTCUSDT"
                assert symbol_dir.exists()
                
    @pytest.mark.asyncio
    async def test_process_message(self, worker):
        """Test message processing."""
        # Initialize mocks
        worker.event_queue = AsyncMock()
        
        # Create test message
        routed_msg = RoutedMessage(
            symbol="BTC-USDT",
            message={"type": "trade", "price": 50000},
            timestamp=time.time(),
            sequence=1
        )
        
        await worker._process_message(routed_msg)
        
        # Check event queued
        worker.event_queue.put.assert_called_once()
        assert worker.messages_processed == 1
        
    @pytest.mark.asyncio
    async def test_process_message_error(self, worker):
        """Test error handling in message processing."""
        worker.event_queue = AsyncMock()
        worker.event_queue.put.side_effect = Exception("Queue error")
        
        routed_msg = RoutedMessage(
            symbol="BTC-USDT",
            message={},
            timestamp=time.time(),
            sequence=1
        )
        
        await worker._process_message(routed_msg)
        
        # Check error counted
        assert worker.errors_count == 1
        
    def test_handle_shutdown(self, worker):
        """Test shutdown signal handling."""
        worker._handle_shutdown(15, None)  # SIGTERM
        
        assert worker.shutdown_event.is_set()
        
    @pytest.mark.asyncio
    async def test_checkpoint(self, worker):
        """Test checkpoint operations."""
        # Mock components
        worker.data_sink = AsyncMock()
        worker.event_stream = Mock()
        worker.event_stream.order_book_engine = Mock()
        
        await worker._checkpoint()
        
        # Check operations performed
        worker.data_sink.flush.assert_called_once()
        worker.event_stream.order_book_engine.save_checkpoint.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_cleanup(self, worker):
        """Test cleanup operations."""
        # Mock components
        worker.data_sink = AsyncMock()
        worker.event_stream = Mock()
        worker.event_stream.order_book_engine = Mock()
        
        await worker._cleanup()
        
        # Check cleanup performed
        worker.data_sink.stop.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_receive_loop_shutdown_signal(self, worker):
        """Test receive loop with shutdown signal."""
        # Put None in queue (shutdown signal)
        worker.input_queue.put(None)
        
        # Mock pipeline initialization
        with patch.object(worker, '_process_message') as mock_process:
            await worker._receive_loop()
            
            # Should not process any messages
            mock_process.assert_not_called()
            
    @pytest.mark.asyncio
    async def test_receive_loop_processes_messages(self, worker):
        """Test receive loop processes messages."""
        # Put test messages in queue
        for i in range(3):
            msg = RoutedMessage(
                symbol="BTC-USDT",
                message={"id": i},
                timestamp=time.time(),
                sequence=i
            )
            worker.input_queue.put(msg)
            
        # Set shutdown after short delay
        async def set_shutdown():
            await asyncio.sleep(0.1)
            worker.shutdown_event.set()
            
        # Mock process message
        with patch.object(worker, '_process_message') as mock_process:
            # Run receive loop with shutdown
            await asyncio.gather(
                worker._receive_loop(),
                set_shutdown()
            )
            
            # Should process the messages
            assert mock_process.call_count >= 3
            
    def test_symbol_worker_entry_point(self, tmp_path):
        """Test worker entry point function."""
        input_queue = multiprocessing.Queue()
        shutdown_event = multiprocessing.Event()
        config = SymbolConfig(name="BTC-USDT")
        
        # Mock asyncio.run
        with patch('asyncio.run') as mock_run:
            symbol_worker_entry_point(
                symbol="BTC-USDT",
                input_queue=input_queue,
                config=config,
                shutdown_event=shutdown_event,
                output_dir=str(tmp_path)
            )
            
            # Check asyncio.run called
            mock_run.assert_called_once()
            
    @pytest.mark.asyncio
    async def test_run_complete_flow(self, worker):
        """Test complete worker run flow."""
        # Mock all components
        with patch.object(worker, '_initialize_pipeline') as mock_init:
            with patch.object(worker, '_receive_loop') as mock_loop:
                with patch.object(worker, '_cleanup') as mock_cleanup:
                    await worker.run()
                    
                    # Check all steps executed
                    mock_init.assert_called_once()
                    mock_loop.assert_called_once()
                    mock_cleanup.assert_called_once()