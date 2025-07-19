"""Tests for CryptoLakeAPIClient."""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

from rlx_datapipe.acquisition.crypto_lake_api_client import CryptoLakeAPIClient


class TestCryptoLakeAPIClient:
    """Test suite for CryptoLakeAPIClient."""

    @pytest.fixture
    def mock_env_vars(self):
        """Mock environment variables."""
        with patch.dict(os.environ, {
            'aws_access_key_id': 'test_access_key',
            'aws_secret_access_key': 'test_secret_key'
        }):
            yield

    @pytest.fixture
    def mock_dotenv(self):
        """Mock dotenv loading."""
        with patch('rlx_datapipe.acquisition.crypto_lake_api_client.load_dotenv'):
            yield

    @pytest.fixture
    def client(self, mock_env_vars, mock_dotenv):
        """Create a test client instance."""
        return CryptoLakeAPIClient()

    def test_init_success(self, mock_env_vars, mock_dotenv):
        """Test successful client initialization."""
        client = CryptoLakeAPIClient()
        assert client.aws_access_key_id == 'test_access_key'
        assert client.aws_secret_access_key == 'test_secret_key'

    def test_init_missing_credentials(self, mock_dotenv):
        """Test initialization fails with missing credentials."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="AWS credentials not found"):
                CryptoLakeAPIClient()

    @patch('rlx_datapipe.acquisition.crypto_lake_api_client.lakeapi.load_data')
    def test_test_connection_success(self, mock_load_data, client):
        """Test successful connection test."""
        # Mock successful data load
        mock_df = pd.DataFrame({'test': [1, 2, 3]})
        mock_load_data.return_value = mock_df
        
        result = client.test_connection()
        
        assert result is True
        mock_load_data.assert_called_once()

    @patch('rlx_datapipe.acquisition.crypto_lake_api_client.lakeapi.load_data')
    def test_test_connection_failure(self, mock_load_data, client):
        """Test connection test failure."""
        # Mock exception
        mock_load_data.side_effect = Exception("Connection failed")
        
        result = client.test_connection()
        
        assert result is False

    @patch('rlx_datapipe.acquisition.crypto_lake_api_client.lakeapi.load_data')
    def test_list_available_data_success(self, mock_load_data, client):
        """Test successful data availability listing."""
        # Mock data for each data type
        mock_data = {
            'trades': pd.DataFrame({'price': [100, 101], 'quantity': [1, 2]}),
            'book': pd.DataFrame({'bid_0_price': [99], 'ask_0_price': [101]}),
            'book_delta_v2': pd.DataFrame({'price': [100], 'side_is_bid': [True]})
        }
        
        def mock_load_side_effect(*args, **kwargs):
            table = kwargs.get('table', args[0] if args else 'trades')
            return mock_data.get(table, pd.DataFrame())
        
        mock_load_data.side_effect = mock_load_side_effect
        
        result = client.list_available_data()
        
        assert 'symbol' in result
        assert 'exchange' in result
        assert 'availability' in result
        assert 'trades' in result['availability']
        assert result['availability']['trades']['available'] is True
        assert result['availability']['trades']['sample_rows'] == 2

    @patch('rlx_datapipe.acquisition.crypto_lake_api_client.lakeapi.load_data')
    def test_download_data_success(self, mock_load_data, client, tmp_path):
        """Test successful data download."""
        # Mock successful data load
        mock_df = pd.DataFrame({
            'price': [100.0, 101.0],
            'quantity': [1.0, 2.0],
            'side': ['buy', 'sell'],
            'origin_time': [datetime.now(), datetime.now()]
        })
        mock_load_data.return_value = mock_df
        
        output_path = tmp_path / "test_data.parquet"
        start_date = datetime.now() - timedelta(days=1)
        end_date = datetime.now()
        
        result = client.download_data(
            data_type='trades',
            symbol='BTC-USDT',
            exchange='BINANCE',
            start_date=start_date,
            end_date=end_date,
            output_path=output_path
        )
        
        assert result['success'] is True
        assert result['rows'] == 2
        assert result['file_path'] == str(output_path)
        assert output_path.exists()

    @patch('rlx_datapipe.acquisition.crypto_lake_api_client.lakeapi.load_data')
    def test_download_data_no_data(self, mock_load_data, client, tmp_path):
        """Test download with no data available."""
        # Mock empty data
        mock_load_data.return_value = pd.DataFrame()
        
        output_path = tmp_path / "test_data.parquet"
        start_date = datetime.now() - timedelta(days=1)
        end_date = datetime.now()
        
        result = client.download_data(
            data_type='trades',
            symbol='BTC-USDT',
            exchange='BINANCE',
            start_date=start_date,
            end_date=end_date,
            output_path=output_path
        )
        
        assert result['success'] is False
        assert result['error'] == 'No data found'
        assert result['rows'] == 0

    @patch('rlx_datapipe.acquisition.crypto_lake_api_client.lakeapi.load_data')
    def test_download_data_exception(self, mock_load_data, client, tmp_path):
        """Test download with exception."""
        # Mock exception
        mock_load_data.side_effect = Exception("API Error")
        
        output_path = tmp_path / "test_data.parquet"
        start_date = datetime.now() - timedelta(days=1)
        end_date = datetime.now()
        
        result = client.download_data(
            data_type='trades',
            symbol='BTC-USDT',
            exchange='BINANCE',
            start_date=start_date,
            end_date=end_date,
            output_path=output_path
        )
        
        assert result['success'] is False
        assert 'API Error' in result['error']

    def test_get_data_schema_trades(self, client):
        """Test getting schema for trades data type."""
        schema = client.get_data_schema('trades')
        
        expected_columns = [
            'side', 'quantity', 'price', 'trade_id', 
            'origin_time', 'received_time', 'exchange', 'symbol'
        ]
        
        for col in expected_columns:
            assert col in schema

    def test_get_data_schema_book(self, client):
        """Test getting schema for book data type."""
        schema = client.get_data_schema('book')
        
        # Should have bid/ask prices and sizes for 20 levels
        assert 'bid_0_price' in schema
        assert 'bid_19_price' in schema
        assert 'ask_0_size' in schema
        assert 'ask_19_size' in schema

    def test_get_data_schema_unknown(self, client):
        """Test getting schema for unknown data type."""
        schema = client.get_data_schema('unknown')
        assert schema == {}

    @patch('rlx_datapipe.acquisition.crypto_lake_api_client.lakeapi.load_data')
    def test_estimate_data_size_success(self, mock_load_data, client):
        """Test successful data size estimation."""
        # Mock sample data
        mock_df = pd.DataFrame({'price': [100] * 1000})  # 1000 rows
        mock_load_data.return_value = mock_df
        
        start_date = datetime.now() - timedelta(days=7)
        end_date = datetime.now()
        
        result = client.estimate_data_size(
            data_type='trades',
            symbol='BTC-USDT',
            exchange='BINANCE',
            start_date=start_date,
            end_date=end_date
        )
        
        assert result['estimated_rows'] > 0
        assert result['estimated_size_mb'] > 0
        assert result['sample_period_days'] >= 1  # Could be 1 or 2 depending on timing
        assert result['total_period_days'] == 8

    @patch('rlx_datapipe.acquisition.crypto_lake_api_client.lakeapi.load_data')
    def test_estimate_data_size_no_data(self, mock_load_data, client):
        """Test data size estimation with no data."""
        # Mock empty data
        mock_load_data.return_value = pd.DataFrame()
        
        start_date = datetime.now() - timedelta(days=1)
        end_date = datetime.now()
        
        result = client.estimate_data_size(
            data_type='trades',
            symbol='BTC-USDT',
            exchange='BINANCE',
            start_date=start_date,
            end_date=end_date
        )
        
        assert result['estimated_rows'] == 0
        assert result['estimated_size_mb'] == 0

    @patch('rlx_datapipe.acquisition.crypto_lake_api_client.lakeapi.load_data')
    def test_estimate_data_size_exception(self, mock_load_data, client):
        """Test data size estimation with exception."""
        # Mock exception
        mock_load_data.side_effect = Exception("Estimation failed")
        
        start_date = datetime.now() - timedelta(days=1)
        end_date = datetime.now()
        
        result = client.estimate_data_size(
            data_type='trades',
            symbol='BTC-USDT',
            exchange='BINANCE',
            start_date=start_date,
            end_date=end_date
        )
        
        assert result['estimated_rows'] == 0
        assert result['estimated_size_mb'] == 0
        assert 'error' in result