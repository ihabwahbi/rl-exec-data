"""Tests for LakeAPIDownloader."""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta
from pathlib import Path

from rlx_datapipe.acquisition.lakeapi_downloader import (
    LakeAPIDownloader, 
    DownloadTask
)


class TestDownloadTask:
    """Test suite for DownloadTask."""

    def test_init(self):
        """Test DownloadTask initialization."""
        start_date = datetime.now()
        end_date = datetime.now() + timedelta(days=1)
        output_path = Path("test.parquet")
        
        task = DownloadTask(
            data_type="trades",
            symbol="BTC-USDT",
            exchange="BINANCE",
            start_date=start_date,
            end_date=end_date,
            output_path=output_path
        )
        
        assert task.data_type == "trades"
        assert task.symbol == "BTC-USDT"
        assert task.exchange == "BINANCE"
        assert task.start_date == start_date
        assert task.end_date == end_date
        assert task.output_path == output_path
        assert task.status == "pending"
        assert task.retries == 0
        assert task.error is None


class TestLakeAPIDownloader:
    """Test suite for LakeAPIDownloader."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock CryptoLakeAPIClient."""
        client = Mock()
        client.download_data.return_value = {
            'success': True,
            'rows': 1000,
            'file_size_bytes': 50000,
            'columns': ['price', 'quantity']
        }
        client.estimate_data_size.return_value = {
            'estimated_rows': 1000,
            'estimated_size_mb': 0.05,
            'sample_period_days': 1
        }
        return client

    @pytest.fixture
    def downloader(self, mock_client, tmp_path):
        """Create a test downloader instance."""
        return LakeAPIDownloader(
            crypto_lake_client=mock_client,
            staging_path=tmp_path / "staging",
            max_concurrent=1,
            max_retries=2
        )

    def test_init(self, mock_client, tmp_path):
        """Test downloader initialization."""
        staging_path = tmp_path / "staging"
        downloader = LakeAPIDownloader(
            crypto_lake_client=mock_client,
            staging_path=staging_path,
            max_concurrent=2,
            max_retries=3
        )
        
        assert downloader.client == mock_client
        assert downloader.staging_path == staging_path
        assert downloader.max_concurrent == 2
        assert downloader.max_retries == 3
        assert staging_path.exists()

    def test_generate_download_tasks_default(self, downloader):
        """Test generating download tasks with default parameters."""
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 7)
        
        tasks = downloader.generate_download_tasks(
            start_date=start_date,
            end_date=end_date,
            chunk_days=7
        )
        
        # Should generate 3 tasks (trades, book, book_delta_v2) for 1 chunk
        assert len(tasks) == 3
        
        # Check task properties
        task = tasks[0]
        assert task.symbol == "BTC-USDT"
        assert task.exchange == "BINANCE"
        assert task.start_date == start_date
        assert task.end_date == end_date

    def test_generate_download_tasks_multiple_chunks(self, downloader):
        """Test generating download tasks with multiple chunks."""
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 21)  # 21 days
        
        tasks = downloader.generate_download_tasks(
            start_date=start_date,
            end_date=end_date,
            data_types=['trades'],
            chunk_days=7
        )
        
        # Should generate 3 chunks for 21 days with 7-day chunks
        assert len(tasks) == 3
        
        # Check chunk boundaries
        assert tasks[0].start_date == datetime(2024, 1, 1)
        assert tasks[0].end_date == datetime(2024, 1, 7)
        assert tasks[1].start_date == datetime(2024, 1, 8)
        assert tasks[1].end_date == datetime(2024, 1, 14)
        assert tasks[2].start_date == datetime(2024, 1, 15)
        assert tasks[2].end_date == datetime(2024, 1, 21)

    @pytest.mark.asyncio
    async def test_download_task_success(self, downloader):
        """Test successful task download."""
        task = DownloadTask(
            data_type="trades",
            symbol="BTC-USDT", 
            exchange="BINANCE",
            start_date=datetime.now(),
            end_date=datetime.now(),
            output_path=Path("test.parquet")
        )
        
        result = await downloader.download_task(task)
        
        assert result['success'] is True
        assert task.status == "completed"
        assert task.rows_downloaded == 1000
        assert task.file_size_bytes == 50000

    @pytest.mark.asyncio
    async def test_download_task_failure(self, downloader, mock_client):
        """Test failed task download."""
        # Mock client to return failure
        mock_client.download_data.return_value = {
            'success': False,
            'error': 'Download failed',
            'rows': 0
        }
        
        task = DownloadTask(
            data_type="trades",
            symbol="BTC-USDT",
            exchange="BINANCE", 
            start_date=datetime.now(),
            end_date=datetime.now(),
            output_path=Path("test.parquet")
        )
        
        result = await downloader.download_task(task)
        
        assert result['success'] is False
        assert task.status == "failed"
        assert task.error == 'Download failed'

    @pytest.mark.asyncio
    async def test_download_task_exception(self, downloader, mock_client):
        """Test task download with exception."""
        # Mock client to raise exception
        mock_client.download_data.side_effect = Exception("Network error")
        
        task = DownloadTask(
            data_type="trades",
            symbol="BTC-USDT",
            exchange="BINANCE",
            start_date=datetime.now(),
            end_date=datetime.now(), 
            output_path=Path("test.parquet")
        )
        
        result = await downloader.download_task(task)
        
        assert result['success'] is False
        assert task.status == "failed"
        assert "Network error" in task.error

    @pytest.mark.asyncio
    async def test_download_with_retry_success_first_try(self, downloader):
        """Test retry logic with success on first try."""
        task = DownloadTask(
            data_type="trades",
            symbol="BTC-USDT",
            exchange="BINANCE",
            start_date=datetime.now(),
            end_date=datetime.now(),
            output_path=Path("test.parquet")
        )
        
        result = await downloader.download_with_retry(task)
        
        assert result['success'] is True
        assert task.retries == 0

    @pytest.mark.asyncio
    async def test_download_with_retry_success_after_retry(self, downloader, mock_client):
        """Test retry logic with success after retry."""
        # Mock first call to fail, second to succeed
        call_count = 0
        def mock_download(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {'success': False, 'error': 'Temporary failure', 'rows': 0}
            else:
                return {'success': True, 'rows': 1000, 'file_size_bytes': 50000}
        
        mock_client.download_data.side_effect = mock_download
        
        task = DownloadTask(
            data_type="trades",
            symbol="BTC-USDT",
            exchange="BINANCE",
            start_date=datetime.now(),
            end_date=datetime.now(),
            output_path=Path("test.parquet")
        )
        
        result = await downloader.download_with_retry(task)
        
        assert result['success'] is True
        assert task.retries == 1

    @pytest.mark.asyncio
    async def test_download_with_retry_all_retries_fail(self, downloader, mock_client):
        """Test retry logic when all retries fail."""
        # Mock all calls to fail
        mock_client.download_data.return_value = {
            'success': False,
            'error': 'Persistent failure',
            'rows': 0
        }
        
        task = DownloadTask(
            data_type="trades",
            symbol="BTC-USDT",
            exchange="BINANCE",
            start_date=datetime.now(),
            end_date=datetime.now(),
            output_path=Path("test.parquet")
        )
        
        result = await downloader.download_with_retry(task)
        
        assert result['success'] is False
        assert task.retries == 2  # max_retries

    @pytest.mark.asyncio
    async def test_download_batch_success(self, downloader):
        """Test successful batch download."""
        tasks = [
            DownloadTask(
                data_type="trades",
                symbol="BTC-USDT",
                exchange="BINANCE",
                start_date=datetime.now(),
                end_date=datetime.now(),
                output_path=Path("test1.parquet")
            ),
            DownloadTask(
                data_type="book",
                symbol="BTC-USDT", 
                exchange="BINANCE",
                start_date=datetime.now(),
                end_date=datetime.now(),
                output_path=Path("test2.parquet")
            )
        ]
        
        result = await downloader.download_batch(tasks)
        
        assert result['total_tasks'] == 2
        assert result['completed'] == 2
        assert result['failed'] == 0
        assert result['total_rows'] == 2000  # 1000 per task

    @pytest.mark.asyncio
    async def test_download_batch_dry_run(self, downloader):
        """Test dry run batch download."""
        tasks = [
            DownloadTask(
                data_type="trades",
                symbol="BTC-USDT",
                exchange="BINANCE",
                start_date=datetime.now(),
                end_date=datetime.now(),
                output_path=Path("test.parquet")
            )
        ]
        
        result = await downloader.download_batch(tasks, dry_run=True)
        
        assert result['dry_run'] is True
        assert result['total_tasks'] == 1
        assert 'estimated_rows' in result
        assert 'estimated_size_mb' in result

    def test_get_download_manifest(self, downloader):
        """Test download manifest generation."""
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 2)
        
        tasks = [
            DownloadTask(
                data_type="trades",
                symbol="BTC-USDT",
                exchange="BINANCE", 
                start_date=start_date,
                end_date=end_date,
                output_path=Path("test.parquet")
            )
        ]
        
        # Set some task properties to simulate completion
        tasks[0].status = "completed"
        tasks[0].rows_downloaded = 1000
        tasks[0].file_size_bytes = 50000
        
        manifest = downloader.get_download_manifest(tasks)
        
        assert 'generated_at' in manifest
        assert manifest['total_tasks'] == 1
        assert manifest['staging_path'] == str(downloader.staging_path)
        assert manifest['date_range']['start'] == start_date.isoformat()
        assert manifest['date_range']['end'] == end_date.isoformat()
        assert 'trades' in manifest['data_types']
        assert 'BTC-USDT' in manifest['symbols']
        assert 'BINANCE' in manifest['exchanges']
        assert len(manifest['tasks']) == 1
        assert manifest['tasks'][0]['rows_downloaded'] == 1000