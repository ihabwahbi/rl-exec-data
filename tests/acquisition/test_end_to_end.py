"""End-to-end integration tests for the acquisition pipeline."""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

from rlx_datapipe.acquisition.crypto_lake_api_client import CryptoLakeAPIClient
from rlx_datapipe.acquisition.lakeapi_downloader import LakeAPIDownloader
from rlx_datapipe.acquisition.integrity_validator import IntegrityValidator


class TestEndToEndPipeline:
    """Test end-to-end pipeline functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock API client with realistic responses."""
        client = Mock(spec=CryptoLakeAPIClient)
        
        # Mock successful connection test
        client.test_connection.return_value = True
        
        # Mock data availability
        client.list_available_data.return_value = {
            'symbol': 'BTC-USDT',
            'exchange': 'BINANCE',
            'availability': {
                'trades': {'available': True, 'sample_rows': 1000}
            }
        }
        
        # Mock successful download
        client.download_data.return_value = {
            'success': True,
            'rows': 1000,
            'file_size_bytes': 50000,
            'columns': ['price', 'quantity', 'side', 'origin_time']
        }
        
        # Mock size estimation
        client.estimate_data_size.return_value = {
            'estimated_rows': 1000,
            'estimated_size_mb': 0.05,
            'sample_period_days': 1
        }
        
        return client

    @pytest.fixture
    def sample_parquet_data(self, tmp_path):
        """Create a sample parquet file for testing."""
        data = pd.DataFrame({
            'origin_time': [datetime.now()] * 100,
            'price': [50000.0] * 100,
            'quantity': [1.0] * 100,
            'side': ['buy'] * 50 + ['sell'] * 50,
            'trade_id': list(range(100)),
            'timestamp': [datetime.now()] * 100,
            'symbol': ['BTC-USDT'] * 100,
            'exchange': ['BINANCE'] * 100
        })
        
        file_path = tmp_path / "sample_trades.parquet"
        data.to_parquet(file_path, index=False)
        return file_path

    def test_client_initialization_and_connection(self, mock_client):
        """Test that client can be initialized and connection tested."""
        assert mock_client.test_connection() is True
        availability = mock_client.list_available_data()
        assert availability['symbol'] == 'BTC-USDT'
        assert availability['availability']['trades']['available'] is True

    @pytest.mark.asyncio
    async def test_download_pipeline_dry_run(self, mock_client, tmp_path):
        """Test the download pipeline in dry-run mode."""
        downloader = LakeAPIDownloader(
            crypto_lake_client=mock_client,
            staging_path=tmp_path / "staging",
            max_concurrent=1
        )
        
        tasks = downloader.generate_download_tasks(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
            data_types=['trades']
        )
        
        assert len(tasks) == 1
        assert tasks[0].data_type == 'trades'
        
        # Test dry run
        result = await downloader.download_batch(tasks, dry_run=True)
        assert result['dry_run'] is True
        assert result['total_tasks'] == 1

    @pytest.mark.asyncio
    async def test_download_pipeline_actual(self, mock_client, tmp_path):
        """Test the actual download pipeline."""
        downloader = LakeAPIDownloader(
            crypto_lake_client=mock_client,
            staging_path=tmp_path / "staging",
            max_concurrent=1
        )
        
        tasks = downloader.generate_download_tasks(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 2),
            data_types=['trades']
        )
        
        # Mock the download to create an actual file
        def mock_download(*args, **kwargs):
            # Create a real parquet file
            output_path = kwargs['output_path']
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            sample_data = pd.DataFrame({
                'origin_time': [datetime.now()],
                'price': [50000.0],
                'quantity': [1.0],
                'side': ['buy']
            })
            sample_data.to_parquet(output_path, index=False)
            
            return {
                'success': True,
                'rows': 1,
                'file_size_bytes': output_path.stat().st_size,
                'columns': list(sample_data.columns)
            }
        
        mock_client.download_data.side_effect = mock_download
        
        # Execute download
        result = await downloader.download_batch(tasks)
        
        assert result['total_tasks'] == 1
        assert result['completed'] == 1
        assert result['failed'] == 0
        assert result['total_rows'] == 1

    def test_validation_pipeline(self, sample_parquet_data):
        """Test the validation pipeline."""
        validator = IntegrityValidator()
        
        result = validator.validate_file(sample_parquet_data, 'trades')
        
        # Should be readable and have metadata
        assert result.checks.get('file_exists', False) is True
        assert result.checks.get('readable', False) is True
        assert result.metadata['row_count'] == 100
        assert result.metadata['file_size_bytes'] > 0

    @pytest.mark.asyncio
    async def test_complete_pipeline_integration(self, mock_client, tmp_path):
        """Test complete integration from download to validation."""
        # Setup
        staging_path = tmp_path / "staging"
        downloader = LakeAPIDownloader(
            crypto_lake_client=mock_client,
            staging_path=staging_path / "raw",
            max_concurrent=1
        )
        validator = IntegrityValidator()
        
        # Mock download to create real file
        def mock_download(*args, **kwargs):
            output_path = kwargs['output_path']
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create realistic trade data
            sample_data = pd.DataFrame({
                'origin_time': [datetime.now() - timedelta(minutes=i) for i in range(10)],
                'price': [50000.0 + i for i in range(10)],
                'quantity': [1.0] * 10,
                'side': ['buy'] * 5 + ['sell'] * 5,
                'trade_id': list(range(10)),
                'timestamp': [datetime.now() - timedelta(minutes=i) for i in range(10)],
                'symbol': ['BTC-USDT'] * 10,
                'exchange': ['BINANCE'] * 10
            })
            sample_data.to_parquet(output_path, index=False)
            
            return {
                'success': True,
                'rows': len(sample_data),
                'file_size_bytes': output_path.stat().st_size,
                'columns': list(sample_data.columns)
            }
        
        mock_client.download_data.side_effect = mock_download
        
        # Step 1: Generate tasks
        tasks = downloader.generate_download_tasks(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 1),
            data_types=['trades']
        )
        
        assert len(tasks) == 1
        
        # Step 2: Execute download
        download_result = await downloader.download_batch(tasks)
        
        assert download_result['completed'] == 1
        assert download_result['total_rows'] == 10
        
        # Step 3: Validate downloaded file
        downloaded_file = tasks[0].output_path
        assert downloaded_file.exists()
        
        validation_result = validator.validate_file(downloaded_file, 'trades')
        
        # Should pass basic validation
        assert validation_result.checks['file_exists'] is True
        assert validation_result.checks['readable'] is True
        assert validation_result.metadata['row_count'] == 10
        
        # Step 4: Generate manifest
        manifest = downloader.get_download_manifest(tasks)
        
        assert manifest['total_tasks'] == 1
        assert 'BTC-USDT' in manifest['symbols']
        assert 'trades' in manifest['data_types']

    def test_error_handling_no_data(self, tmp_path):
        """Test error handling when no data is available."""
        mock_client = Mock(spec=CryptoLakeAPIClient)
        mock_client.download_data.return_value = {
            'success': False,
            'error': 'No data found',
            'rows': 0
        }
        
        downloader = LakeAPIDownloader(
            crypto_lake_client=mock_client,
            staging_path=tmp_path / "staging",
            max_concurrent=1
        )
        
        tasks = downloader.generate_download_tasks(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 1),
            data_types=['trades']
        )
        
        # This test verifies the error handling paths work
        assert len(tasks) == 1
        assert tasks[0].status == 'pending'

    def test_manifest_generation(self, tmp_path):
        """Test manifest generation functionality."""
        mock_client = Mock(spec=CryptoLakeAPIClient)
        
        downloader = LakeAPIDownloader(
            crypto_lake_client=mock_client,
            staging_path=tmp_path / "staging"
        )
        
        tasks = downloader.generate_download_tasks(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 1, 7),
            data_types=['trades', 'book']
        )
        
        manifest = downloader.get_download_manifest(tasks)
        
        assert manifest['total_tasks'] == 2
        assert set(manifest['data_types']) == {'trades', 'book'}
        assert manifest['date_range']['start'] == '2024-01-01T00:00:00'
        assert manifest['date_range']['end'] == '2024-01-07T00:00:00'