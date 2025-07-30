"""Data downloader for Crypto Lake S3 files."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from tqdm import tqdm

from .crypto_lake_client import CryptoLakeClient


class DownloadChunk:
    """Represents a single download task."""

    def __init__(self, key: str, local_path: Path, size: int, retries: int = 0):
        self.key = key
        self.local_path = local_path
        self.size = size
        self.retries = retries
        self.status = "pending"  # pending, downloading, completed, failed
        self.error: str | None = None
        self.start_time: float | None = None
        self.end_time: float | None = None


class DataDownloader:
    """Manages robust data downloads with chunking, retry, and progress tracking."""

    def __init__(
        self,
        crypto_lake_client: CryptoLakeClient,
        staging_path: Path = Path("data/staging/raw"),
        max_concurrent: int = 3,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """Initialize downloader.

        Args:
            crypto_lake_client: Initialized Crypto Lake S3 client
            staging_path: Local path for downloaded files
            max_concurrent: Maximum concurrent downloads
            max_retries: Maximum retry attempts per file
            retry_delay: Base delay between retries (exponential backoff)
        """
        self.client = crypto_lake_client
        self.staging_path = Path(staging_path)
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Create staging directory
        self.staging_path.mkdir(parents=True, exist_ok=True)

        # Statistics
        self.stats = {
            "total_files": 0,
            "downloaded": 0,
            "failed": 0,
            "bytes_downloaded": 0,
            "start_time": None,
            "end_time": None,
        }

    def download_file(self, s3_key: str, local_path: Path | None = None) -> Path:
        """Download a single file from S3.

        Args:
            s3_key: S3 object key
            local_path: Optional local path (defaults to staging_path + s3_key)

        Returns:
            Path to downloaded file

        Raises:
            ClientError: If download fails after retries
        """
        if local_path is None:
            # Preserve S3 directory structure locally
            local_path = self.staging_path / s3_key

        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # Get file info
        file_info = self.client.get_file_info(s3_key)
        file_size = file_info["size"]

        # Download with progress bar and retry logic
        for attempt in range(self.max_retries + 1):
            try:
                logger.info(
                    f"Downloading {s3_key} (attempt {attempt + 1}/{self.max_retries + 1})"
                )

                # Download with progress bar
                with tqdm(
                    total=file_size,
                    unit="B",
                    unit_scale=True,
                    desc=s3_key.split("/")[-1],
                ) as pbar:

                    def callback(bytes_transferred):
                        pbar.update(bytes_transferred)

                    self.client.s3_client.download_file(
                        self.client.bucket_name,
                        s3_key,
                        str(local_path),
                        Callback=callback,
                    )

                # Verify download
                if local_path.exists() and local_path.stat().st_size == file_size:
                    logger.info(f"✅ Downloaded: {s3_key} -> {local_path}")
                    self.stats["downloaded"] += 1
                    self.stats["bytes_downloaded"] += file_size
                    return local_path
                else:
                    raise RuntimeError(f"Downloaded file size mismatch for {s3_key}")

            except Exception as e:
                logger.warning(
                    f"Download attempt {attempt + 1} failed for {s3_key}: {e}"
                )

                # Remove partial file
                if local_path.exists():
                    local_path.unlink()

                # Wait before retry (exponential backoff)
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2**attempt)
                    logger.info(f"Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                else:
                    # Final failure
                    self.stats["failed"] += 1
                    logger.error(
                        f"❌ Failed to download {s3_key} after {self.max_retries + 1} attempts"
                    )
                    raise

    async def download_date_range(
        self,
        symbol: str,
        exchange: str,
        data_type: str,
        start_date: datetime,
        end_date: datetime,
    ) -> tuple[list[Path], list[dict[str, Any]]]:
        """Download data for a date range with concurrent processing.

        Args:
            symbol: Trading pair symbol (e.g., 'BTC-USDT')
            exchange: Exchange name (e.g., 'binance')
            data_type: Data type ('trades', 'book', 'book_delta_v2')
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            Tuple of (successful_downloads, failed_downloads)
        """
        # Get list of files to download
        logger.info(
            f"Finding files for {symbol} {data_type} from {start_date.date()} to {end_date.date()}"
        )

        files = self.client.list_files_in_date_range(
            symbol, exchange, data_type, start_date, end_date
        )

        if not files:
            logger.warning(f"No files found for {symbol} {data_type} in date range")
            return [], []

        logger.info(f"Found {len(files)} files to download")

        # Create download chunks
        chunks = []
        for file_info in files:
            key = file_info["key"]
            local_path = self.staging_path / key
            size = file_info["size"]
            chunks.append(DownloadChunk(key, local_path, size))

        # Update stats
        self.stats["total_files"] = len(chunks)
        self.stats["start_time"] = time.time()

        # Download with concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def download_chunk(chunk: DownloadChunk) -> Path | None:
            async with semaphore:
                return await self._download_chunk_async(chunk)

        # Execute downloads
        logger.info(f"Starting concurrent downloads (max {self.max_concurrent})")
        tasks = [download_chunk(chunk) for chunk in chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        successful = []
        failed = []

        for chunk, result in zip(chunks, results, strict=False):
            if isinstance(result, Exception):
                failed.append(
                    {"key": chunk.key, "error": str(result), "retries": chunk.retries}
                )
            elif result is not None:
                successful.append(result)

        # Update final stats
        self.stats["end_time"] = time.time()

        # Log summary
        duration = self.stats["end_time"] - self.stats["start_time"]
        mb_downloaded = self.stats["bytes_downloaded"] / (1024 * 1024)
        speed_mbps = mb_downloaded / duration if duration > 0 else 0

        logger.info(
            f"Download complete: {len(successful)} successful, {len(failed)} failed"
        )
        logger.info(
            f"Downloaded {mb_downloaded:.1f} MB in {duration:.1f}s ({speed_mbps:.1f} MB/s)"
        )

        return successful, failed

    async def _download_chunk_async(self, chunk: DownloadChunk) -> Path | None:
        """Download a single chunk asynchronously.

        Args:
            chunk: Download chunk to process

        Returns:
            Path to downloaded file or None if failed
        """
        chunk.status = "downloading"
        chunk.start_time = time.time()

        try:
            # Run synchronous download in thread pool
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                result = await loop.run_in_executor(
                    executor, self.download_file, chunk.key, chunk.local_path
                )

            chunk.status = "completed"
            chunk.end_time = time.time()
            return result

        except Exception as e:
            chunk.status = "failed"
            chunk.error = str(e)
            chunk.end_time = time.time()
            logger.error(f"Chunk download failed: {chunk.key} - {e}")
            return None

    def download_batch(
        self,
        symbol: str,
        exchange: str,
        data_types: list[str],
        start_date: datetime,
        end_date: datetime,
    ) -> dict[str, tuple[list[Path], list[dict[str, Any]]]]:
        """Download multiple data types for a date range.

        Args:
            symbol: Trading pair symbol
            exchange: Exchange name
            data_types: List of data types to download
            start_date: Start date
            end_date: End date

        Returns:
            Dictionary mapping data type to (successful, failed) downloads
        """
        results = {}

        for data_type in data_types:
            logger.info(f"\n=== Downloading {data_type} data ===")

            try:
                successful, failed = asyncio.run(
                    self.download_date_range(
                        symbol, exchange, data_type, start_date, end_date
                    )
                )
                results[data_type] = (successful, failed)

            except Exception as e:
                logger.error(f"Failed to download {data_type}: {e}")
                results[data_type] = (
                    [],
                    [{"key": "all", "error": str(e), "retries": 0}],
                )

        return results

    def get_download_summary(self) -> dict[str, Any]:
        """Get download statistics summary.

        Returns:
            Dictionary with download statistics
        """
        duration = 0
        if self.stats["start_time"] and self.stats["end_time"]:
            duration = self.stats["end_time"] - self.stats["start_time"]

        mb_downloaded = self.stats["bytes_downloaded"] / (1024 * 1024)
        speed_mbps = mb_downloaded / duration if duration > 0 else 0

        return {
            "total_files": self.stats["total_files"],
            "downloaded": self.stats["downloaded"],
            "failed": self.stats["failed"],
            "success_rate": (
                self.stats["downloaded"] / self.stats["total_files"]
                if self.stats["total_files"] > 0
                else 0
            ),
            "bytes_downloaded": self.stats["bytes_downloaded"],
            "mb_downloaded": mb_downloaded,
            "duration_seconds": duration,
            "speed_mbps": speed_mbps,
        }
