"""Data downloader using the official lakeapi package."""

import asyncio
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger
from tqdm import tqdm

from .crypto_lake_api_client import CryptoLakeAPIClient


class DownloadTask:
    """Represents a single download task for lakeapi."""

    def __init__(
        self,
        data_type: str,
        symbol: str,
        exchange: str,
        start_date: datetime,
        end_date: datetime,
        output_path: Path,
        retries: int = 0,
    ):
        self.data_type = data_type
        self.symbol = symbol
        self.exchange = exchange
        self.start_date = start_date
        self.end_date = end_date
        self.output_path = output_path
        self.retries = retries
        self.status = "pending"  # pending, downloading, completed, failed
        self.error: str | None = None
        self.start_time: float | None = None
        self.end_time: float | None = None
        self.rows_downloaded: int = 0
        self.file_size_bytes: int = 0


class LakeAPIDownloader:
    """Manages robust data downloads using the lakeapi package."""

    def __init__(
        self,
        crypto_lake_client: CryptoLakeAPIClient,
        staging_path: Path = Path("data/staging/raw"),
        max_concurrent: int = 2,  # Lower for lakeapi to avoid rate limits
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ):
        """Initialize downloader.

        Args:
            crypto_lake_client: Initialized Crypto Lake API client
            staging_path: Local path for downloaded files
            max_concurrent: Maximum concurrent downloads
            max_retries: Maximum retry attempts per task
            retry_delay: Base delay between retries (exponential backoff)
        """
        self.client = crypto_lake_client
        self.staging_path = Path(staging_path)
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Create staging directory
        self.staging_path.mkdir(parents=True, exist_ok=True)

        # Stats tracking
        self.stats = {
            "total_tasks": 0,
            "completed": 0,
            "failed": 0,
            "total_bytes": 0,
            "total_rows": 0,
            "start_time": None,
            "end_time": None,
        }

        logger.info(f"LakeAPI Downloader initialized - staging: {self.staging_path}")
        logger.info(f"Concurrency: {max_concurrent}, Max retries: {max_retries}")

    def generate_download_tasks(
        self,
        symbol: str = "BTC-USDT",
        exchange: str = "BINANCE",
        data_types: list[str] = None,
        start_date: datetime = None,
        end_date: datetime = None,
        chunk_days: int = 7,
    ) -> list[DownloadTask]:
        """Generate download tasks for date range.

        Args:
            symbol: Trading pair symbol
            exchange: Exchange name
            data_types: List of data types to download
            start_date: Start date
            end_date: End date
            chunk_days: Days per download chunk

        Returns:
            List of download tasks
        """
        if data_types is None:
            data_types = ["trades", "book", "book_delta_v2"]

        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now() - timedelta(days=1)

        tasks = []

        # Split date range into chunks
        current_date = start_date
        while current_date <= end_date:
            chunk_end = min(current_date + timedelta(days=chunk_days - 1), end_date)

            for data_type in data_types:
                # Generate output file path
                date_str = (
                    f"{current_date.strftime('%Y%m%d')}_{chunk_end.strftime('%Y%m%d')}"
                )
                filename = f"{exchange}_{symbol}_{data_type}_{date_str}.parquet"
                output_path = self.staging_path / filename

                task = DownloadTask(
                    data_type=data_type,
                    symbol=symbol,
                    exchange=exchange,
                    start_date=current_date,
                    end_date=chunk_end,
                    output_path=output_path,
                )
                tasks.append(task)

            current_date = chunk_end + timedelta(days=1)

        logger.info(f"Generated {len(tasks)} download tasks")
        logger.info(f"Date range: {start_date.date()} to {end_date.date()}")
        logger.info(f"Data types: {data_types}")

        return tasks

    async def download_task(self, task: DownloadTask) -> dict[str, Any]:
        """Download a single task.

        Args:
            task: Download task to execute

        Returns:
            Dictionary with download results
        """
        task.status = "downloading"
        task.start_time = time.time()

        try:
            logger.info(f"Downloading {task.data_type} for {task.symbol}")
            logger.info(
                f"Date range: {task.start_date.date()} to {task.end_date.date()}"
            )

            # Use the lakeapi client to download
            result = self.client.download_data(
                data_type=task.data_type,
                symbol=task.symbol,
                exchange=task.exchange,
                start_date=task.start_date,
                end_date=task.end_date,
                output_path=task.output_path,
            )

            if result["success"]:
                task.status = "completed"
                task.rows_downloaded = result["rows"]
                task.file_size_bytes = result.get("file_size_bytes", 0)

                self.stats["completed"] += 1
                self.stats["total_rows"] += task.rows_downloaded
                self.stats["total_bytes"] += task.file_size_bytes

                logger.info(
                    f"✅ Downloaded {task.rows_downloaded} rows "
                    f"({task.file_size_bytes / 1024 / 1024:.1f} MB)"
                )

            else:
                task.status = "failed"
                task.error = result.get("error", "Unknown error")
                logger.error(f"❌ Download failed: {task.error}")

            task.end_time = time.time()
            return result

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.end_time = time.time()

            logger.error(f"❌ Download task failed: {e}")
            return {"success": False, "error": str(e), "rows": 0}

    async def download_with_retry(self, task: DownloadTask) -> dict[str, Any]:
        """Download with retry logic.

        Args:
            task: Download task to execute

        Returns:
            Final download result
        """
        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                delay = self.retry_delay * (2 ** (attempt - 1))
                logger.info(
                    f"Retrying {task.data_type} download in {delay:.1f}s (attempt {attempt + 1})"
                )
                await asyncio.sleep(delay)

            result = await self.download_task(task)

            if result["success"]:
                return result

            task.retries = attempt + 1

        # All retries failed
        self.stats["failed"] += 1
        logger.error(f"❌ All retries failed for {task.data_type}")
        return result

    async def download_batch(
        self, tasks: list[DownloadTask], dry_run: bool = False
    ) -> dict[str, Any]:
        """Download a batch of tasks with concurrency control.

        Args:
            tasks: List of download tasks
            dry_run: If True, only estimate what would be downloaded

        Returns:
            Summary of download results
        """
        if dry_run:
            return await self._dry_run_batch(tasks)

        self.stats["total_tasks"] = len(tasks)
        self.stats["start_time"] = time.time()

        logger.info(f"Starting download of {len(tasks)} tasks")
        logger.info(f"Concurrency limit: {self.max_concurrent}")

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def download_with_semaphore(task):
            async with semaphore:
                return await self.download_with_retry(task)

        # Progress tracking
        with tqdm(total=len(tasks), desc="Downloading", unit="files") as pbar:

            async def download_and_update(task):
                result = await download_with_semaphore(task)
                pbar.update(1)

                # Update progress description
                completed = self.stats["completed"]
                failed = self.stats["failed"]
                pbar.set_postfix(
                    {
                        "completed": completed,
                        "failed": failed,
                        "rows": f"{self.stats['total_rows']:,}",
                    }
                )

                return result

            # Execute all downloads
            results = await asyncio.gather(
                *[download_and_update(task) for task in tasks], return_exceptions=True
            )

        self.stats["end_time"] = time.time()

        # Calculate summary
        duration = self.stats["end_time"] - self.stats["start_time"]
        avg_speed_mbps = (
            (self.stats["total_bytes"] / (1024 * 1024)) / duration
            if duration > 0
            else 0
        )

        summary = {
            "total_tasks": len(tasks),
            "completed": self.stats["completed"],
            "failed": self.stats["failed"],
            "total_rows": self.stats["total_rows"],
            "total_size_mb": self.stats["total_bytes"] / (1024 * 1024),
            "duration_seconds": duration,
            "avg_speed_mbps": avg_speed_mbps,
            "tasks": tasks,
            "results": results,
        }

        logger.info(f"Download batch completed in {duration:.1f}s")
        logger.info(
            f"Success rate: {self.stats['completed']}/{len(tasks)} "
            f"({100 * self.stats['completed'] / len(tasks):.1f}%)"
        )
        logger.info(
            f"Total data: {summary['total_size_mb']:.1f} MB "
            f"({self.stats['total_rows']:,} rows)"
        )
        logger.info(f"Average speed: {avg_speed_mbps:.1f} MB/s")

        return summary

    async def _dry_run_batch(self, tasks: list[DownloadTask]) -> dict[str, Any]:
        """Simulate download batch to estimate data size and time.

        Args:
            tasks: List of download tasks

        Returns:
            Estimated download summary
        """
        logger.info(f"DRY RUN: Estimating {len(tasks)} download tasks")

        total_estimated_rows = 0
        total_estimated_mb = 0

        # Sample a few tasks to get estimates
        sample_size = min(3, len(tasks))
        sample_tasks = tasks[:sample_size]

        for task in sample_tasks:
            try:
                estimate = self.client.estimate_data_size(
                    data_type=task.data_type,
                    symbol=task.symbol,
                    exchange=task.exchange,
                    start_date=task.start_date,
                    end_date=task.end_date,
                )

                if estimate.get("estimated_rows", 0) > 0:
                    total_estimated_rows += estimate["estimated_rows"]
                    total_estimated_mb += estimate["estimated_size_mb"]

                    logger.info(
                        f"Estimate for {task.data_type}: "
                        f"{estimate['estimated_rows']:,} rows, "
                        f"{estimate['estimated_size_mb']:.1f} MB"
                    )

            except Exception as e:
                logger.warning(f"Could not estimate {task.data_type}: {e}")

        # Scale estimates to full batch
        if sample_size > 0:
            scale_factor = len(tasks) / sample_size
            total_estimated_rows = int(total_estimated_rows * scale_factor)
            total_estimated_mb = total_estimated_mb * scale_factor

        # Estimate download time (assuming 10 MB/s average)
        estimated_duration = total_estimated_mb / 10 if total_estimated_mb > 0 else 60

        summary = {
            "dry_run": True,
            "total_tasks": len(tasks),
            "estimated_rows": total_estimated_rows,
            "estimated_size_mb": total_estimated_mb,
            "estimated_duration_minutes": estimated_duration / 60,
            "sample_tasks_checked": sample_size,
        }

        logger.info("DRY RUN ESTIMATE:")
        logger.info(f"  Tasks: {len(tasks)}")
        logger.info(
            f"  Estimated data: {total_estimated_mb:.1f} MB ({total_estimated_rows:,} rows)"
        )
        logger.info(f"  Estimated time: {estimated_duration / 60:.1f} minutes")
        logger.info(f"  Output directory: {self.staging_path}")

        return summary

    def get_download_manifest(self, tasks: list[DownloadTask]) -> dict[str, Any]:
        """Generate download manifest for tracking.

        Args:
            tasks: List of download tasks

        Returns:
            Manifest dictionary
        """
        manifest = {
            "generated_at": datetime.now().isoformat(),
            "staging_path": str(self.staging_path),
            "total_tasks": len(tasks),
            "date_range": {
                "start": min(task.start_date for task in tasks).isoformat(),
                "end": max(task.end_date for task in tasks).isoformat(),
            },
            "data_types": list(set(task.data_type for task in tasks)),
            "symbols": list(set(task.symbol for task in tasks)),
            "exchanges": list(set(task.exchange for task in tasks)),
            "tasks": [
                {
                    "data_type": task.data_type,
                    "symbol": task.symbol,
                    "exchange": task.exchange,
                    "start_date": task.start_date.isoformat(),
                    "end_date": task.end_date.isoformat(),
                    "output_path": str(task.output_path),
                    "status": task.status,
                    "retries": task.retries,
                    "error": task.error,
                    "rows_downloaded": task.rows_downloaded,
                    "file_size_bytes": task.file_size_bytes,
                }
                for task in tasks
            ],
        }

        return manifest
