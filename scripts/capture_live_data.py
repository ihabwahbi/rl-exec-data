#!/usr/bin/env python3
"""CLI script for capturing live market data."""

import asyncio
from pathlib import Path

import click
from loguru import logger

from rlx_datapipe.capture import DataCapture
from rlx_datapipe.capture.logging_config import configure_logging


@click.command()
@click.option(
    "--symbol",
    default="btcusdt",
    help="Trading symbol to capture (default: btcusdt)"
)
@click.option(
    "--duration",
    default=60,
    type=int,
    help="Capture duration in minutes (default: 60)"
)
@click.option(
    "--output-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("data/golden_samples"),
    help="Output directory for captured data"
)
def capture_live_data(symbol: str, duration: int, output_dir: Path):
    """Capture raw live market data from Binance."""
    # Configure logging
    configure_logging()

    logger.info(f"Starting capture for {symbol} for {duration} minutes")
    logger.info(f"Output directory: {output_dir}")

    # Create capture instance (duration in seconds)
    capture = DataCapture(symbol, str(output_dir), duration * 60)

    # Run capture
    asyncio.run(capture.run())

    logger.info("Capture completed")


if __name__ == "__main__":
    capture_live_data()

