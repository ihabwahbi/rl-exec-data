"""Main entry point for multi-symbol reconstruction pipeline.

This module provides the main entry point for running the reconstruction
pipeline with support for multiple symbols in parallel processes.
"""

import argparse
import asyncio
import signal
import sys
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from .config import MultiSymbolConfig, SymbolConfig
from .data_ingestion import DataIngestion
from .process_manager import ProcessManager
from .symbol_router import SymbolRouter
from .symbol_worker import symbol_worker_entry_point


class MultiSymbolPipeline:
    """Main pipeline orchestrator for multi-symbol processing."""

    def __init__(self, config_path: Path | None = None):
        """Initialize the multi-symbol pipeline.

        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path
        self.config: MultiSymbolConfig | None = None
        self.process_manager: ProcessManager | None = None
        self.symbol_router: SymbolRouter | None = None
        self.data_ingestion: DataIngestion | None = None
        self.running = False

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def _handle_shutdown(self, signum: int, frame: Any) -> None:  # noqa: ARG002
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self.running = False

    def _load_config(self) -> MultiSymbolConfig:
        """Load configuration from file or create default."""
        if self.config_path and self.config_path.exists():
            logger.info(f"Loading configuration from {self.config_path}")
            with self.config_path.open() as f:
                config_dict = yaml.safe_load(f)
                return MultiSymbolConfig.from_dict(config_dict.get("multi_symbol", {}))
        else:
            logger.info("Using default configuration")
            # Create default config with single symbol for backward compatibility
            return MultiSymbolConfig(
                enabled=False,  # Single-symbol mode by default
                symbols=[
                    SymbolConfig(
                        name="BTCUSDT",
                        enabled=True,
                        memory_limit_mb=1024,
                        queue_size=1000
                    )
                ]
            )

    def _setup_single_symbol_mode(self, symbol: str, output_dir: Path) -> None:  # noqa: ARG002
        """Setup for single-symbol backward compatible mode.

        Args:
            symbol: Trading symbol
            output_dir: Output directory
        """
        logger.info(f"Running in single-symbol mode for {symbol}")

        # Update config for single symbol
        self.config = MultiSymbolConfig(
            enabled=False,
            symbols=[
                SymbolConfig(
                    name=symbol,
                    enabled=True,
                    memory_limit_mb=1024,
                    queue_size=1000
                )
            ]
        )

    async def run_multi_symbol(self, input_path: Path, output_dir: Path,
                              manifest_path: Path | None = None) -> None:
        """Run the pipeline in multi-symbol mode.

        Args:
            input_path: Input data path
            output_dir: Output directory
            manifest_path: Optional manifest file path
        """
        logger.info("Starting multi-symbol pipeline")

        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize process manager
        self.process_manager = ProcessManager(
            config=self.config,
            worker_target=symbol_worker_entry_point,
            output_dir=str(output_dir)
        )

        # Initialize symbol router
        self.symbol_router = SymbolRouter(
            config=self.config,
            process_manager=self.process_manager
        )

        # Start process manager and workers
        self.process_manager.start()

        # Initialize data ingestion
        self.data_ingestion = DataIngestion(
            input_path=input_path,
            manifest_path=manifest_path
        )

        # Main processing loop
        self.running = True
        messages_processed = 0

        try:
            async for message in self.data_ingestion.read_messages():
                if not self.running:
                    break

                # Route message to appropriate worker
                if self.symbol_router.route_message(message):
                    messages_processed += 1

                # Check for backpressure
                if messages_processed % 10000 == 0 and self.symbol_router.is_backpressure_detected():
                    logger.warning("Backpressure detected, slowing down")
                    await asyncio.sleep(0.1)

            logger.info(f"Processed {messages_processed} messages")

        finally:
            # Graceful shutdown
            logger.info("Shutting down multi-symbol pipeline")
            self.process_manager.stop()

    async def run_single_symbol(self, input_path: Path, output_dir: Path,
                               symbol: str, manifest_path: Path | None = None) -> None:
        """Run the pipeline in single-symbol mode for backward compatibility.

        Args:
            input_path: Input data path
            output_dir: Output directory
            symbol: Trading symbol
            manifest_path: Optional manifest file path
        """
        logger.info(f"Starting single-symbol pipeline for {symbol}")

        # For single symbol mode, run pipeline directly without multiprocessing
        # This maintains backward compatibility

        # Import existing pipeline components
        from .pipeline_integration import create_data_sink_pipeline
        from .unified_stream_enhanced import (
            EnhancedUnificationConfig,
            UnifiedEventStreamEnhanced,
        )

        # Create output directory
        symbol_output_dir = output_dir / symbol
        symbol_output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        stream_config = EnhancedUnificationConfig(
            enable_order_book=True,
            max_book_levels=20,
            checkpoint_dir=symbol_output_dir / "checkpoints",
            gc_interval=100_000,
            enable_drift_tracking=True,
        )

        event_stream = UnifiedEventStreamEnhanced(
            symbol=symbol,
            config=stream_config
        )

        # Create data sink
        data_sink, event_queue = await create_data_sink_pipeline(
            output_dir=symbol_output_dir,
            symbol=symbol,
            batch_size=5000,
            queue_size=5000,
            max_file_size_mb=400
        )

        # Start data sink
        await data_sink.start()

        # Initialize data ingestion
        self.data_ingestion = DataIngestion(
            input_path=input_path,
            manifest_path=manifest_path
        )

        # Process messages
        self.running = True
        messages_processed = 0

        try:
            async for message in self.data_ingestion.read_messages():
                if not self.running:
                    break

                # Process through event stream
                # TODO: Integrate actual message processing
                messages_processed += 1

                if messages_processed % 10000 == 0:
                    logger.info(f"Processed {messages_processed} messages")

            logger.info(f"Total processed: {messages_processed} messages")

        finally:
            # Cleanup
            await data_sink.stop()

    async def run(self, input_path: Path, output_dir: Path,
                  symbol: str | None = None,
                  manifest_path: Path | None = None) -> None:
        """Run the pipeline in appropriate mode.

        Args:
            input_path: Input data path
            output_dir: Output directory
            symbol: Trading symbol (for single-symbol mode)
            manifest_path: Optional manifest file path
        """
        # Load configuration
        self.config = self._load_config()

        # Determine mode
        if symbol or not self.config.enabled:
            # Single-symbol mode (backward compatible)
            if symbol:
                await self.run_single_symbol(input_path, output_dir, symbol, manifest_path)
            else:
                # Use first configured symbol
                first_symbol = self.config.symbols[0].name if self.config.symbols else "BTCUSDT"
                await self.run_single_symbol(input_path, output_dir, first_symbol, manifest_path)
        else:
            # Multi-symbol mode
            await self.run_multi_symbol(input_path, output_dir, manifest_path)


def main():
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Run the multi-symbol reconstruction pipeline"
    )

    parser.add_argument(
        "input_path",
        type=Path,
        help="Input data path (directory or file)"
    )

    parser.add_argument(
        "output_dir",
        type=Path,
        help="Output directory for reconstructed data"
    )

    parser.add_argument(
        "--symbol",
        type=str,
        help="Trading symbol for single-symbol mode (e.g., BTCUSDT)"
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file"
    )

    parser.add_argument(
        "--manifest",
        type=Path,
        help="Path to manifest file"
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )

    args = parser.parse_args()

    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        level=args.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )

    # Create and run pipeline
    pipeline = MultiSymbolPipeline(config_path=args.config)

    try:
        asyncio.run(
            pipeline.run(
                input_path=args.input_path,
                output_dir=args.output_dir,
                symbol=args.symbol,
                manifest_path=args.manifest
            )
        )
    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

