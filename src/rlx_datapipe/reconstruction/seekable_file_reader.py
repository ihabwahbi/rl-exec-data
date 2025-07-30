"""Seekable file reader for recovery support."""

import gzip
from collections.abc import Iterator
from pathlib import Path

from loguru import logger


class SeekableFileReader:
    """File reader with seek support for checkpoint recovery."""

    def __init__(self, file_path: Path):
        """Initialize seekable file reader.

        Args:
            file_path: Path to file to read
        """
        self.file_path = Path(file_path)
        self.is_gzipped = file_path.suffix == ".gz"

        self._file_handle = None
        self._current_offset = 0
        self._line_number = 0

    def open(self) -> None:
        """Open the file for reading."""
        if self._file_handle:
            self.close()

        if self.is_gzipped:
            self._file_handle = gzip.open(self.file_path, "rt", encoding="utf-8")
        else:
            self._file_handle = open(self.file_path, encoding="utf-8")

        logger.debug(f"Opened file: {self.file_path}")

    def close(self) -> None:
        """Close the file."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None

    def seek(self, offset: int) -> bool:
        """Seek to specific offset in file.

        Args:
            offset: Byte offset to seek to

        Returns:
            True if seek successful
        """
        if not self._file_handle:
            self.open()

        try:
            if self.is_gzipped:
                # For gzipped files, we need to read from start
                logger.warning("Seeking in gzipped file, reading from start")
                self.close()
                self.open()

                # Read and discard data until we reach offset
                bytes_read = 0
                while bytes_read < offset:
                    chunk_size = min(8192, offset - bytes_read)
                    data = self._file_handle.read(chunk_size)
                    if not data:
                        break
                    bytes_read += len(data.encode("utf-8"))

                self._current_offset = bytes_read

            else:
                # Direct seek for uncompressed files
                self._file_handle.seek(offset)
                self._current_offset = offset

            logger.info(f"Seeked to offset {self._current_offset} in {self.file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to seek to offset {offset}: {e}")
            return False

    def read_line(self) -> str | None:
        """Read next line from file.

        Returns:
            Line content or None if EOF
        """
        if not self._file_handle:
            self.open()

        try:
            line = self._file_handle.readline()
            if line:
                self._line_number += 1
                # Update offset (approximate for gzipped files)
                self._current_offset += len(line.encode("utf-8"))
                return line.rstrip("\n")
            return None

        except Exception as e:
            logger.error(f"Error reading line: {e}")
            return None

    def read_lines_iter(self) -> Iterator[str]:
        """Iterate over lines in file.

        Yields:
            Lines from file
        """
        while True:
            line = self.read_line()
            if line is None:
                break
            yield line

    def get_position(self) -> tuple[str, int, int]:
        """Get current position in file.

        Returns:
            Tuple of (filename, offset, line_number)
        """
        return str(self.file_path), self._current_offset, self._line_number

    def skip_lines(self, count: int) -> int:
        """Skip specified number of lines.

        Args:
            count: Number of lines to skip

        Returns:
            Number of lines actually skipped
        """
        skipped = 0
        for _ in range(count):
            line = self.read_line()
            if line is None:
                break
            skipped += 1

        return skipped

    def find_update_id(self, target_update_id: int) -> bool:
        """Seek to position after specified update_id.

        Args:
            target_update_id: Update ID to find

        Returns:
            True if found and positioned after
        """
        import json

        logger.info(f"Searching for update_id > {target_update_id}")

        found = False
        lines_checked = 0

        for line in self.read_lines_iter():
            lines_checked += 1

            try:
                # Try to parse as JSON
                data = json.loads(line)

                # Check for update_id field
                update_id = data.get("update_id")
                if update_id and update_id > target_update_id:
                    logger.info(
                        f"Found update_id {update_id} > {target_update_id} "
                        f"after checking {lines_checked} lines"
                    )

                    # Rewind one line so this event will be processed
                    # This is approximate but good enough for recovery
                    self._current_offset -= len(line.encode("utf-8"))
                    self._line_number -= 1

                    found = True
                    break

            except json.JSONDecodeError:
                # Skip non-JSON lines
                continue
            except Exception as e:
                logger.debug(f"Error parsing line for update_id: {e}")
                continue

        if not found:
            logger.warning(f"Could not find update_id > {target_update_id}")

        return found

    def __enter__(self):
        """Context manager entry."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
