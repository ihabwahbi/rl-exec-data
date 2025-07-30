"""Logging configuration with nanosecond timestamp precision."""

import time

from loguru import logger


def configure_logging():
    """Configure loguru with nanosecond timestamp precision."""

    def nanosecond_formatter(record):
        """Add nanosecond timestamp to log records."""
        record["extra"]["ns_timestamp"] = time.perf_counter_ns()
        return "{time:YYYY-MM-DD HH:mm:ss.SSS} | {extra[ns_timestamp]} | {level} | {message}\n"

    logger.remove()
    logger.add(
        "logs/capture_{time:YYYY-MM-DD}.log",
        format=nanosecond_formatter,
        rotation="1 day",
        retention="7 days",
        level="INFO",
    )
    logger.add(
        lambda msg: print(msg, end=""), format=nanosecond_formatter, level="INFO"
    )

    return logger
