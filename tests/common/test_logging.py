"""Tests for logging configuration."""

import tempfile
from pathlib import Path

from loguru import logger
from rlx_datapipe.common.logging import setup_logging


def test_setup_logging_console_only():
    """Test logging setup with console output only."""
    setup_logging(log_level="DEBUG")

    # Test that logging works
    logger.info("Test message")

    # Verify the logger is configured
    assert len(logger._core.handlers) > 0


def test_setup_logging_with_file():
    """Test logging setup with file output."""
    with tempfile.TemporaryDirectory() as temp_dir:
        log_file = Path(temp_dir) / "test.log"

        setup_logging(log_level="INFO", log_file=log_file)

        # Test that logging works
        logger.info("Test file message")

        # Verify log file was created
        assert log_file.exists()

        # Verify content was written
        content = log_file.read_text()
        assert "Test file message" in content
        assert "INFO" in content


def test_setup_logging_different_levels():
    """Test logging setup with different log levels."""
    for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        setup_logging(log_level=level)
        logger.info(f"Testing {level} level")
        assert len(logger._core.handlers) > 0
