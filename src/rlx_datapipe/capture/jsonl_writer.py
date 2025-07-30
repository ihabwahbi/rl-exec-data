"""JSONL file writer with compression support."""

import gzip
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class JSONLWriter:
    """Writes data to JSONL files with optional compression."""

    def __init__(
        self,
        output_dir: str,
        file_prefix: str,
        compress: bool = True,
        buffer_size: int = 1000,
        rotation_interval: int = 3600,  # seconds
    ):
        """Initialize JSONL writer.

        Args:
            output_dir: Directory to write files to
            file_prefix: Prefix for output files
            compress: Whether to compress files with gzip
            buffer_size: Number of records to buffer before writing
            rotation_interval: Time interval for file rotation in seconds
        """
        self.output_dir = Path(output_dir)
        self.file_prefix = file_prefix
        self.compress = compress
        self.buffer_size = buffer_size
        self.rotation_interval = rotation_interval

        self._buffer = []
        self._current_file = None
        self._file_handle = None
        self._file_start_time = None
        self._record_count = 0
        self._total_records = 0

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_filename(self) -> Path:
        """Generate filename with timestamp."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.file_prefix}_{timestamp}.jsonl"

        if self.compress:
            filename += ".gz"

        return self.output_dir / filename

    def _open_file(self) -> None:
        """Open a new file for writing."""
        self._close_file()

        self._current_file = self._get_filename()
        self._file_start_time = datetime.now()
        self._record_count = 0

        if self.compress:
            self._file_handle = gzip.open(self._current_file, "wt", encoding="utf-8")
        else:
            self._file_handle = open(self._current_file, "w", encoding="utf-8")

        logger.info(f"Opened new file: {self._current_file}")

    def _close_file(self) -> None:
        """Close current file if open."""
        if self._file_handle:
            # Flush any remaining buffer
            self._flush_buffer()

            self._file_handle.close()
            self._file_handle = None

            if self._current_file:
                logger.info(
                    f"Closed file: {self._current_file} ({self._record_count} records)"
                )

    def _should_rotate(self) -> bool:
        """Check if file should be rotated."""
        if not self._file_start_time:
            return True

        elapsed = (datetime.now() - self._file_start_time).total_seconds()
        return elapsed >= self.rotation_interval

    def _flush_buffer(self) -> None:
        """Write buffer contents to file."""
        if not self._buffer or not self._file_handle:
            return

        for record in self._buffer:
            json_line = json.dumps(record, separators=(",", ":"))
            self._file_handle.write(json_line + "\n")

        self._record_count += len(self._buffer)
        self._total_records += len(self._buffer)
        self._buffer.clear()

    def write(self, record: dict[str, Any]) -> None:
        """Write a record to JSONL file.

        Args:
            record: Dictionary to write as JSON line
        """
        # Check if we need to open a new file
        if not self._file_handle or self._should_rotate():
            self._open_file()

        # Add to buffer
        self._buffer.append(record)

        # Flush if buffer is full
        if len(self._buffer) >= self.buffer_size:
            self._flush_buffer()

    def flush(self) -> None:
        """Force flush buffer to disk."""
        self._flush_buffer()

        if self._file_handle:
            self._file_handle.flush()

    def close(self) -> None:
        """Close writer and flush remaining data."""
        self._close_file()
        logger.info(
            f"JSONL writer closed. Total records written: {self._total_records}"
        )

    def get_stats(self) -> dict[str, Any]:
        """Get writer statistics."""
        return {
            "current_file": str(self._current_file) if self._current_file else None,
            "current_file_records": self._record_count,
            "total_records": self._total_records,
            "buffer_size": len(self._buffer),
        }
