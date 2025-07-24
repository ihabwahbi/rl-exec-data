"""Symbol Worker Process for multi-symbol pipeline execution.

This module implements the worker process that:
- Receives messages from the symbol router
- Runs the complete pipeline for a specific symbol
- Handles proper output partitioning by symbol
- Manages graceful shutdown and error recovery
"""

import asyncio
import multiprocessing
import signal
import time
from multiprocessing import Event, Queue
from pathlib import Path
from decimal import Decimal
from typing import Any

from loguru import logger

from .config import ReplayOptimizationConfig, SymbolConfig
from .data_sink import DataSink
from .pipeline_integration import create_data_sink_pipeline
from .pipeline_state_provider import PipelineStateProvider
from .symbol_router import RoutedMessage
from .unified_market_event import UnifiedMarketEvent
from .unified_stream_enhanced import (
    EnhancedUnificationConfig,
    UnifiedEventStreamEnhanced,
)


class SymbolWorker:
    """Worker process for handling a single symbol's data pipeline."""

    def __init__(
        self,
        symbol: str,
        input_queue: Queue,
        config: SymbolConfig,
        shutdown_event: Event,
        output_dir: Path,
        replay_config: ReplayOptimizationConfig | None = None
    ):
        """Initialize the symbol worker.

        Args:
            symbol: Trading symbol to process
            input_queue: Queue for receiving messages from router
            config: Symbol-specific configuration
            shutdown_event: Event signaling shutdown
            output_dir: Base output directory
            replay_config: Replay optimization configuration
        """
        self.symbol = symbol
        self.input_queue = input_queue
        self.config = config
        self.shutdown_event = shutdown_event
        self.output_dir = output_dir
        self.replay_config = replay_config or ReplayOptimizationConfig()

        # Pipeline components
        self.event_stream: UnifiedEventStreamEnhanced | None = None
        self.data_sink: DataSink | None = None
        self.event_queue: asyncio.Queue | None = None
        
        # State provider for unified checkpointing
        self.state_provider = PipelineStateProvider(symbol)
        self.checkpoint_manager = None

        # Metrics
        self.messages_processed = 0
        self.errors_count = 0
        self.last_checkpoint_time = time.time()

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

        logger.info(f"SymbolWorker initialized for {symbol}")

    def _handle_shutdown(self, signum: int, frame: Any) -> None:  # noqa: ARG002
        """Handle shutdown signals."""
        logger.info(f"Worker {self.symbol} received signal {signum}, shutting down...")
        self.shutdown_event.set()

    async def _initialize_pipeline(self) -> None:
        """Initialize the data processing pipeline."""
        # Create symbol-specific output directory
        symbol_output_dir = self.output_dir / self.symbol.replace("-", "")
        symbol_output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize unified event stream
        stream_config = EnhancedUnificationConfig(
            enable_order_book=True,
            max_book_levels=self.replay_config.max_book_levels,
            checkpoint_dir=symbol_output_dir / "checkpoints",
            gc_interval=self.replay_config.gc_interval,
            enable_drift_tracking=self.replay_config.drift_threshold > 0,
            use_memory_mapping=True,
        )
        self.event_stream = UnifiedEventStreamEnhanced(
            symbol=self.symbol,
            config=stream_config
        )

        # Create data sink with queue
        self.data_sink, self.event_queue = await create_data_sink_pipeline(
            output_dir=symbol_output_dir,
            symbol=self.symbol,
            batch_size=5000,
            queue_size=5000,
            max_file_size_mb=400
        )

        # Start data sink
        await self.data_sink.start()
        
        # Initialize checkpoint manager with enhanced features
        from .checkpoint_manager import CheckpointManager
        self.checkpoint_manager = CheckpointManager(
            checkpoint_dir=symbol_output_dir / "checkpoints",
            symbol=self.symbol,
            enable_time_trigger=True,
            time_interval=300.0,  # 5 minutes
            event_interval=1_000_000,  # 1M events
        )
        
        # Set up state provider references
        self.state_provider.set_order_book_engine(self.event_stream.order_book_engine)
        self.state_provider.set_data_sink(self.data_sink)
        self.checkpoint_manager.set_state_provider(self.state_provider)
        
        # Start checkpoint manager
        await self.checkpoint_manager.start()

        logger.info(f"Pipeline initialized for {self.symbol} with checkpointing enabled")

    async def _process_message(self, routed_msg: RoutedMessage) -> None:
        """Process a single message through the pipeline.

        Args:
            routed_msg: Routed message from the router
        """
        try:
            # Extract the original message
            message = routed_msg.message

            # Process message based on type
            unified_events = await self._parse_and_process_message(message)

            # Queue all events for the data sink
            for event in unified_events:
                await self.event_queue.put(event)
                self.messages_processed += 1
            
            # Update state provider
            self.state_provider.increment_events_processed(len(unified_events))
            
            # Record events for checkpoint triggers
            if self.checkpoint_manager:
                await self.checkpoint_manager.record_events(len(unified_events))

        except Exception as e:
            logger.error(f"Error processing message for {self.symbol}: {e}")
            self.errors_count += 1

    async def _parse_and_process_message(self, message: Any) -> list[UnifiedMarketEvent]:
        """Parse message and process through order book if needed.
        
        Args:
            message: Raw message from data source
            
        Returns:
            List of unified market events
        """
        events = []

        # Handle different message formats
        if isinstance(message, dict):
            event_type = message.get("event_type", message.get("type", ""))

            if event_type == "TRADE" or "trade" in event_type.lower():
                events.append(self._create_trade_event(message))

            elif event_type == "BOOK_SNAPSHOT" or "snapshot" in event_type.lower():
                events.append(self._create_snapshot_event(message))
                # Update order book state
                if self.event_stream and self.event_stream.order_book_engine:
                    self.event_stream.order_book_engine.reset_from_snapshot(
                        message.get("update_id", 0),
                        message.get("bids", []),
                        message.get("asks", [])
                    )

            elif event_type == "BOOK_DELTA" or "delta" in event_type.lower():
                # Process delta through order book
                if self.event_stream and self.event_stream.order_book_engine:
                    self.event_stream.order_book_engine.apply_delta(
                        update_id=message.get("update_id", 0),
                        side=message.get("side", ""),
                        price=float(message.get("price", 0)),
                        quantity=float(message.get("new_quantity", 0))
                    )
                events.append(self._create_delta_event(message))

        elif hasattr(message, "__dict__"):
            # Handle object-based messages
            events = await self._parse_and_process_message(message.__dict__)

        return events

    def _create_trade_event(self, message: dict) -> UnifiedMarketEvent:
        """Create a trade event from message data."""
        return UnifiedMarketEvent(
            event_timestamp=int(message.get("origin_time", time.time() * 1e9)),
            event_type="TRADE",
            update_id=message.get("update_id"),
            trade_id=message.get("trade_id", message.get("id")),
            trade_price=Decimal(str(message.get("price", 0))),
            trade_quantity=Decimal(str(message.get("quantity", 0))),
            trade_side=message.get("side", "UNKNOWN")
        )

    def _create_snapshot_event(self, message: dict) -> UnifiedMarketEvent:
        """Create a book snapshot event from message data."""
        # Convert bid/ask data to required format
        bids = []
        asks = []

        if "bids" in message:
            for bid in message["bids"]:
                if isinstance(bid, (list, tuple)) and len(bid) >= 2:
                    bids.append((Decimal(str(bid[0])), Decimal(str(bid[1]))))
                elif isinstance(bid, dict):
                    bids.append((Decimal(str(bid.get("price", 0))),
                               Decimal(str(bid.get("quantity", 0)))))

        if "asks" in message:
            for ask in message["asks"]:
                if isinstance(ask, (list, tuple)) and len(ask) >= 2:
                    asks.append((Decimal(str(ask[0])), Decimal(str(ask[1]))))
                elif isinstance(ask, dict):
                    asks.append((Decimal(str(ask.get("price", 0))),
                               Decimal(str(ask.get("quantity", 0)))))

        return UnifiedMarketEvent(
            event_timestamp=int(message.get("origin_time", time.time() * 1e9)),
            event_type="BOOK_SNAPSHOT",
            update_id=message.get("update_id"),
            bids=bids,
            asks=asks,
            is_snapshot=True
        )

    def _create_delta_event(self, message: dict) -> UnifiedMarketEvent:
        """Create a book delta event from message data."""
        return UnifiedMarketEvent(
            event_timestamp=int(message.get("origin_time", time.time() * 1e9)),
            event_type="BOOK_DELTA",
            update_id=message.get("update_id"),
            delta_side=message.get("side", "UNKNOWN").upper(),
            delta_price=Decimal(str(message.get("price", 0))),
            delta_quantity=Decimal(str(message.get("new_quantity", 0)))
        )

    async def _receive_loop(self) -> None:
        """Main message receive loop."""
        logger.info(f"Starting receive loop for {self.symbol}")

        while not self.shutdown_event.is_set():
            try:
                # Get message from queue with timeout
                routed_msg = await asyncio.get_event_loop().run_in_executor(
                    None, self.input_queue.get, True, 0.1  # noqa: FBT003
                )

                if routed_msg is None:
                    # None is shutdown signal
                    logger.info(f"Received shutdown signal for {self.symbol}")
                    break

                # Process the message
                await self._process_message(routed_msg)

            except multiprocessing.queues.Empty:
                # No messages available, continue
                continue
            except Exception as e:
                logger.error(f"Error in receive loop for {self.symbol}: {e}")
                self.errors_count += 1

    async def _checkpoint(self) -> None:
        """Perform manual checkpoint operation.
        
        Note: This is now handled by the checkpoint manager automatically.
        This method is kept for manual checkpoint requests.
        """
        try:
            # Flush data sink
            if self.data_sink:
                await self.data_sink.flush()

            # Trigger manual checkpoint
            if self.checkpoint_manager:
                await self.checkpoint_manager.checkpoint_trigger.trigger_manual_checkpoint()

            logger.debug(f"Manual checkpoint triggered for {self.symbol}")

        except Exception as e:
            logger.error(f"Error during manual checkpoint for {self.symbol}: {e}")

    async def run(self) -> None:
        """Run the worker process."""
        try:
            # Initialize pipeline
            await self._initialize_pipeline()

            # Start receive loop
            await self._receive_loop()

        except Exception as e:
            logger.error(f"Fatal error in worker {self.symbol}: {e}")
            raise
        finally:
            await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up resources on shutdown."""
        logger.info(f"Cleaning up worker for {self.symbol}")

        try:
            # Stop checkpoint manager (will trigger final checkpoint)
            if self.checkpoint_manager:
                await self.checkpoint_manager.stop()

            # Stop data sink
            if self.data_sink:
                await self.data_sink.stop()

        except Exception as e:
            logger.error(f"Error during cleanup for {self.symbol}: {e}")

        logger.info(
            f"Worker {self.symbol} stopped. "
            f"Processed: {self.messages_processed}, Errors: {self.errors_count}"
        )


def symbol_worker_entry_point(
    symbol: str,
    input_queue: Queue,
    config: SymbolConfig,
    shutdown_event: Event,
    output_dir: str,
    replay_config_dict: dict | None = None
) -> None:
    """Entry point for the worker process.

    Args:
        symbol: Trading symbol to process
        input_queue: Queue for receiving messages
        config: Symbol configuration
        shutdown_event: Shutdown event
        output_dir: Output directory path
        replay_config_dict: Replay configuration as dict
    """
    # Set process name
    multiprocessing.current_process().name = f"Worker-{symbol}"

    # Configure logging for this process
    logger.remove()
    logger.add(
        f"logs/worker_{symbol}.log",
        rotation="100 MB",
        retention="7 days",
        level="INFO"
    )
    logger.add(lambda msg: print(f"[{symbol}] {msg}"), level="INFO")

    # Create replay config if provided
    replay_config = None
    if replay_config_dict:
        replay_config = ReplayOptimizationConfig(**replay_config_dict)

    # Create and run worker
    worker = SymbolWorker(
        symbol=symbol,
        input_queue=input_queue,
        config=config,
        shutdown_event=shutdown_event,
        output_dir=Path(output_dir),
        replay_config=replay_config
    )

    # Run async event loop
    asyncio.run(worker.run())


