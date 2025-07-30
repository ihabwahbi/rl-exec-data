"""Main capture script for live data collection from Binance."""

import asyncio
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any

import click
from loguru import logger

from .jsonl_writer import JSONLWriter
from .logging_config import configure_logging
from .websocket_handler import WebSocketHandler


class DataCapture:
    """Main data capture coordinator."""

    def __init__(self, symbol: str, output_dir: str, duration: int | None = None):
        """Initialize data capture.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            output_dir: Directory for output files
            duration: Capture duration in seconds (None for continuous)
        """
        self.symbol = symbol.lower()
        self.output_dir = output_dir
        self.duration = duration

        # Initialize components
        # Single writer for chronological order with small buffer for immediate writes
        self.writer = JSONLWriter(
            output_dir,
            f"{symbol}_capture_{int(time.time())}",
            buffer_size=10,  # Small buffer for quicker writes
        )

        # WebSocket URL for combined streams
        self.ws_url = f"wss://stream.binance.com:9443/stream?streams={self.symbol}@trade/{self.symbol}@depth@100ms"

        # Control flags
        self._running = False
        self._start_time = None

    async def _on_message(self, message: dict[str, Any], receive_ns: int) -> None:
        """Handle incoming WebSocket message.

        Args:
            message: Raw message from WebSocket
            receive_ns: Nanosecond timestamp when received
        """
        # Validate basic structure
        if "stream" not in message or "data" not in message:
            logger.warning("Invalid message format: missing stream or data")
            return

        # Write raw message with capture metadata - NO TRANSFORMATION
        output = {
            "capture_ns": receive_ns,
            "stream": message["stream"],
            "data": message["data"],  # This is the RAW message, untouched!
        }

        # Write to single chronological file
        self.writer.write(output)

    def _on_connect(self) -> None:
        """Handle WebSocket connection established."""
        logger.info("WebSocket connected")
        # Note: Order book synchronization is handled separately
        # We capture raw data as-is without modification

    def _print_stats(self) -> None:
        """Print capture statistics."""
        if self._start_time:
            elapsed = (datetime.now(timezone.utc) - self._start_time).total_seconds()
        else:
            elapsed = 0

        writer_stats = self.writer.get_stats()

        logger.info(f"=== Capture Statistics (elapsed: {elapsed:.1f}s) ===")
        logger.info(f"Total records: {writer_stats['total_records']}")
        logger.info(f"Buffered records: {writer_stats.get('buffer_size', 0)}")
        logger.info(f"Current file: {writer_stats.get('current_file', 'N/A')}")

        # Force flush to ensure data is written
        self.writer.flush()

    async def run(self) -> None:
        """Run the data capture."""
        self._running = True
        self._start_time = datetime.now(timezone.utc)

        # Create WebSocket handler
        ws_handler = WebSocketHandler(
            url=self.ws_url, on_message=self._on_message, on_connect=self._on_connect
        )

        # Start periodic stats printing
        async def print_stats_loop():
            while self._running:
                await asyncio.sleep(30)  # Print stats every 30 seconds
                self._print_stats()

        stats_task = asyncio.create_task(print_stats_loop())

        try:
            if self.duration:
                logger.info(f"Starting capture for {self.duration} seconds")
                # Run with timeout
                await asyncio.wait_for(ws_handler.run(), timeout=self.duration)
            else:
                logger.info("Starting continuous capture (press Ctrl+C to stop)")
                # Run continuously
                await ws_handler.run()

        except asyncio.TimeoutError:
            logger.info("Capture duration reached")
        except KeyboardInterrupt:
            logger.info("Capture interrupted by user")
        finally:
            self._running = False
            ws_handler.stop()
            stats_task.cancel()

            # Final stats and cleanup
            self._print_stats()
            self.writer.close()

            logger.info("Data capture completed")


@click.command()
@click.option("--symbol", "-s", default="BTCUSDT", help="Trading symbol")
@click.option("--output-dir", "-o", default="data/capture", help="Output directory")
@click.option("--duration", "-d", type=int, help="Capture duration in seconds")
def main(symbol: str, output_dir: str, duration: int | None):
    """Live data capture from Binance WebSocket streams."""
    # Configure logging
    configure_logging()

    logger.info(f"Starting data capture for {symbol}")
    logger.info(f"Output directory: {output_dir}")

    # Create and run capture
    capture = DataCapture(symbol, output_dir, duration)

    # Handle signals
    def signal_handler(sig, frame):
        logger.info("Received signal, stopping capture")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run async capture
    asyncio.run(capture.run())


if __name__ == "__main__":
    main()
