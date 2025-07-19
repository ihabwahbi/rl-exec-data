"""Tests for IntegrityValidator with correct interface."""

import pytest
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from rlx_datapipe.acquisition.integrity_validator import IntegrityValidator


class TestIntegrityValidator:
    """Test suite for IntegrityValidator."""

    @pytest.fixture
    def validator(self):
        """Create a test validator instance."""
        return IntegrityValidator()

    @pytest.fixture
    def sample_trades_data(self):
        """Create sample trades data matching expected schema."""
        return pd.DataFrame({
            'origin_time': [
                datetime.now() - timedelta(minutes=2),
                datetime.now() - timedelta(minutes=1),
                datetime.now()
            ],
            'price': [50000.0, 50001.0, 49999.0],
            'quantity': [1.0, 2.0, 0.5],
            'side': ['buy', 'sell', 'buy'],
            'trade_id': [1, 2, 3],
            'timestamp': [
                datetime.now() - timedelta(minutes=2),
                datetime.now() - timedelta(minutes=1),
                datetime.now()
            ],
            'symbol': ['BTC-USDT', 'BTC-USDT', 'BTC-USDT'],
            'exchange': ['BINANCE', 'BINANCE', 'BINANCE']
        })

    def test_init(self, validator):
        """Test validator initialization."""
        assert validator is not None
        assert 'trades' in validator.expected_schemas
        assert 'book' in validator.expected_schemas
        assert 'book_delta_v2' in validator.expected_schemas

    def test_validate_file_not_exists(self, validator, tmp_path):
        """Test validation of non-existent file."""
        non_existent = tmp_path / "nonexistent.parquet"
        
        result = validator.validate_file(non_existent, 'trades')
        
        assert result.passed is False
        assert any("not found" in error.lower() for error in result.errors)

    def test_validate_file_trades_success(self, validator, tmp_path, sample_trades_data):
        """Test successful validation of trades file."""
        # Save sample data
        file_path = tmp_path / "trades.parquet"
        sample_trades_data.to_parquet(file_path, index=False)
        
        result = validator.validate_file(file_path, 'trades')
        
        # May have warnings but should not have critical errors
        assert len(result.errors) == 0 or result.passed is True

    def test_validate_file_empty(self, validator, tmp_path):
        """Test validation of empty file."""
        file_path = tmp_path / "empty.parquet"
        file_path.write_text("")  # Create empty file
        
        result = validator.validate_file(file_path, 'trades')
        
        assert result.passed is False
        assert any("empty" in error.lower() for error in result.errors)

    def test_validate_file_invalid_parquet(self, validator, tmp_path):
        """Test validation of invalid parquet file."""
        # Create invalid parquet file
        file_path = tmp_path / "invalid.parquet"
        file_path.write_text("not a parquet file")
        
        result = validator.validate_file(file_path, 'trades')
        
        assert result.passed is False
        assert any("parquet" in error.lower() for error in result.errors)

    def test_validate_file_unknown_data_type(self, validator, tmp_path, sample_trades_data):
        """Test validation with unknown data type."""
        file_path = tmp_path / "trades.parquet"
        sample_trades_data.to_parquet(file_path, index=False)
        
        result = validator.validate_file(file_path, 'unknown_type')
        
        # Should have warnings but file should still be readable
        assert result.checks.get('readable', False) is True
        assert any("unknown data type" in warning.lower() for warning in result.warnings)

    def test_calculate_checksum(self, validator, tmp_path):
        """Test checksum calculation."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("test content")
        
        checksum = validator._calculate_checksum(file_path)
        
        assert isinstance(checksum, str)
        assert len(checksum) == 64  # SHA256 hex length

    def test_calculate_checksum_different_algorithms(self, validator, tmp_path):
        """Test checksum with different algorithms."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("test content")
        
        sha256_sum = validator._calculate_checksum(file_path, 'sha256')
        md5_sum = validator._calculate_checksum(file_path, 'md5')
        
        assert len(sha256_sum) == 64
        assert len(md5_sum) == 32
        assert sha256_sum != md5_sum

    def test_validate_file_with_checksum_match(self, validator, tmp_path, sample_trades_data):
        """Test validation with matching checksum."""
        file_path = tmp_path / "trades.parquet"
        sample_trades_data.to_parquet(file_path, index=False)
        
        # Calculate expected checksum
        expected_checksum = validator._calculate_checksum(file_path)
        
        result = validator.validate_file(file_path, 'trades', expected_checksum)
        
        assert result.checks.get('checksum_valid', False) is True

    def test_validate_file_with_checksum_mismatch(self, validator, tmp_path, sample_trades_data):
        """Test validation with mismatched checksum."""
        file_path = tmp_path / "trades.parquet"
        sample_trades_data.to_parquet(file_path, index=False)
        
        # Use wrong checksum
        wrong_checksum = "0" * 64
        
        result = validator.validate_file(file_path, 'trades', wrong_checksum)
        
        assert result.checks.get('checksum_valid', True) is False
        assert any("checksum mismatch" in error.lower() for error in result.errors)

    def test_validation_result_metadata(self, validator, tmp_path, sample_trades_data):
        """Test that validation result includes proper metadata."""
        file_path = tmp_path / "trades.parquet"
        sample_trades_data.to_parquet(file_path, index=False)
        
        result = validator.validate_file(file_path, 'trades')
        
        assert 'file_size_bytes' in result.metadata
        assert 'file_size_mb' in result.metadata
        assert 'row_count' in result.metadata
        assert 'column_count' in result.metadata
        assert 'columns' in result.metadata
        
        assert result.metadata['row_count'] == len(sample_trades_data)
        assert result.metadata['file_size_bytes'] > 0