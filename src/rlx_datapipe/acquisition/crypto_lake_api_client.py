"""Crypto Lake API client using the official lakeapi package."""

import os
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

import lakeapi
from dotenv import load_dotenv
from loguru import logger


class CryptoLakeAPIClient:
    """Handles data access using the official Crypto Lake API."""
    
    def __init__(self):
        """Initialize Crypto Lake API client.
        
        Raises:
            ValueError: If AWS credentials not found in environment
        """
        self._load_credentials()
        self._setup_api()
        
    def _load_credentials(self) -> None:
        """Load AWS credentials from .env file."""
        # Load environment variables from .env file
        load_dotenv()
        
        # Get credentials
        self.aws_access_key_id = os.getenv('aws_access_key_id')
        self.aws_secret_access_key = os.getenv('aws_secret_access_key')
        
        if not self.aws_access_key_id or not self.aws_secret_access_key:
            raise ValueError("AWS credentials not found in .env file. "
                           "Please ensure aws_access_key_id and aws_secret_access_key are set.")
        
        # Set AWS credentials for lakeapi
        os.environ['AWS_ACCESS_KEY_ID'] = self.aws_access_key_id
        os.environ['AWS_SECRET_ACCESS_KEY'] = self.aws_secret_access_key
        
        logger.info("AWS credentials loaded from .env file for lakeapi")
        
    def _setup_api(self) -> None:
        """Setup the lakeapi client."""
        try:
            # Test basic API access
            # Note: lakeapi handles authentication automatically using AWS credentials
            logger.info("Crypto Lake API client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Crypto Lake API: {e}")
            raise
            
    def test_connection(self) -> bool:
        """Test connection to Crypto Lake API.
        
        Returns:
            bool: True if connection successful
        """
        try:
            # Try a simple query to test access
            test_data = lakeapi.load_data(
                table='trades',
                start=datetime.now() - timedelta(days=2),
                end=datetime.now() - timedelta(days=1),
                symbols=['BTC-USDT'],
                exchanges=['BINANCE']
            )
            
            logger.info(f"✅ Connection test successful - found {len(test_data)} rows")
            return True
            
        except Exception as e:
            logger.error(f"❌ Connection test failed: {e}")
            return False
            
    def list_available_data(self, symbol: str = 'BTC-USDT', exchange: str = 'BINANCE') -> Dict[str, Any]:
        """Get information about available data for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC-USDT')
            exchange: Exchange name (e.g., 'BINANCE')
            
        Returns:
            Dictionary with data availability information
        """
        try:
            # Test each data type for the last few days to see what's available
            data_types = ['trades', 'book', 'book_delta_v2']
            end_date = datetime.now() - timedelta(days=1)  # Data available until yesterday
            start_date = end_date - timedelta(days=3)  # Check last 3 days
            
            availability = {}
            
            for data_type in data_types:
                try:
                    logger.info(f"Checking {data_type} availability for {symbol} on {exchange}")
                    
                    # Try to load a small sample
                    sample_data = lakeapi.load_data(
                        table=data_type,
                        start=start_date,
                        end=end_date,
                        symbols=[symbol],
                        exchanges=[exchange]
                    )
                    
                    availability[data_type] = {
                        'available': True,
                        'sample_rows': len(sample_data),
                        'columns': list(sample_data.columns) if len(sample_data) > 0 else [],
                        'date_range_tested': {
                            'start': start_date.isoformat(),
                            'end': end_date.isoformat()
                        }
                    }
                    
                    logger.info(f"✅ {data_type}: {len(sample_data)} rows available")
                    
                except Exception as e:
                    logger.warning(f"❌ {data_type}: Not available - {e}")
                    availability[data_type] = {
                        'available': False,
                        'error': str(e),
                        'date_range_tested': {
                            'start': start_date.isoformat(),
                            'end': end_date.isoformat()
                        }
                    }
            
            return {
                'symbol': symbol,
                'exchange': exchange,
                'availability': availability,
                'tested_date_range': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to check data availability: {e}")
            return {
                'symbol': symbol,
                'exchange': exchange,
                'error': str(e),
                'availability': {}
            }
            
    def download_data(self, 
                     data_type: str,
                     symbol: str,
                     exchange: str,
                     start_date: datetime,
                     end_date: datetime,
                     output_path: Path) -> Dict[str, Any]:
        """Download data for a specific period.
        
        Args:
            data_type: Type of data ('trades', 'book', 'book_delta_v2')
            symbol: Trading pair symbol
            exchange: Exchange name
            start_date: Start date
            end_date: End date
            output_path: Path to save the data
            
        Returns:
            Dictionary with download results
        """
        try:
            logger.info(f"Downloading {data_type} for {symbol} on {exchange}")
            logger.info(f"Date range: {start_date.date()} to {end_date.date()}")
            logger.info(f"Output: {output_path}")
            
            # Download data using lakeapi
            data = lakeapi.load_data(
                table=data_type,
                start=start_date,
                end=end_date,
                symbols=[symbol],
                exchanges=[exchange]
            )
            
            if len(data) == 0:
                logger.warning(f"No data found for {data_type} in specified date range")
                return {
                    'success': False,
                    'error': 'No data found',
                    'rows': 0,
                    'file_path': None
                }
            
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save as Parquet file
            data.to_parquet(output_path, index=False)
            
            file_size = output_path.stat().st_size
            
            logger.info(f"✅ Downloaded {len(data)} rows ({file_size / 1024 / 1024:.1f} MB)")
            
            return {
                'success': True,
                'rows': len(data),
                'columns': list(data.columns),
                'file_path': str(output_path),
                'file_size_bytes': file_size,
                'date_range': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Download failed for {data_type}: {e}")
            return {
                'success': False,
                'error': str(e),
                'rows': 0,
                'file_path': None
            }
            
    def get_data_schema(self, data_type: str) -> Dict[str, str]:
        """Get the schema for a data type.
        
        Args:
            data_type: Type of data
            
        Returns:
            Dictionary mapping column names to types
        """
        # Return the expected schema based on Crypto Lake documentation
        schemas = {
            'trades': {
                'side': 'category',
                'quantity': 'float64',
                'price': 'float64',
                'trade_id': 'Int64',
                'origin_time': 'datetime64[ns]',
                'received_time': 'datetime64[ns]',
                'exchange': 'category',
                'symbol': 'category'
            },
            'book': {
                'origin_time': 'datetime64[ns]',
                'received_time': 'datetime64[ns]',
                'sequence_number': 'Int64',
                'exchange': 'category',
                'symbol': 'category',
                # bid_0_price through bid_19_price, bid_0_size through bid_19_size
                # ask_0_price through ask_19_price, ask_0_size through ask_19_size
                **{f'bid_{i}_price': 'float64' for i in range(20)},
                **{f'bid_{i}_size': 'float64' for i in range(20)},
                **{f'ask_{i}_price': 'float64' for i in range(20)},
                **{f'ask_{i}_size': 'float64' for i in range(20)}
            },
            'book_delta_v2': {
                'origin_time': 'datetime64[ns]',
                'received_time': 'datetime64[ns]',
                'sequence_number': 'Int64',
                'side_is_bid': 'bool',
                'price': 'float64',
                'size': 'float64',
                'exchange': 'category',
                'symbol': 'category'
            }
        }
        
        return schemas.get(data_type, {})
        
    def estimate_data_size(self, 
                          data_type: str,
                          symbol: str,
                          exchange: str,
                          start_date: datetime,
                          end_date: datetime) -> Dict[str, Any]:
        """Estimate data size for a date range.
        
        Args:
            data_type: Type of data
            symbol: Trading pair symbol
            exchange: Exchange name
            start_date: Start date
            end_date: End date
            
        Returns:
            Dictionary with size estimates
        """
        try:
            # Sample one day to estimate
            sample_end = min(start_date + timedelta(days=1), end_date)
            
            sample_data = lakeapi.load_data(
                table=data_type,
                start=start_date,
                end=sample_end,
                symbols=[symbol],
                exchanges=[exchange]
            )
            
            if len(sample_data) == 0:
                return {
                    'estimated_rows': 0,
                    'estimated_size_mb': 0,
                    'sample_period_days': 0
                }
            
            # Calculate rates
            sample_days = (sample_end - start_date).days + 1
            total_days = (end_date - start_date).days + 1
            
            rows_per_day = len(sample_data) / sample_days
            estimated_total_rows = int(rows_per_day * total_days)
            
            # Estimate size (rough approximation)
            bytes_per_row = 100  # Rough estimate
            if data_type == 'book':
                bytes_per_row = 800  # Much larger due to 40 price/size columns
            elif data_type == 'book_delta_v2':
                bytes_per_row = 80
                
            estimated_size_bytes = estimated_total_rows * bytes_per_row
            
            return {
                'estimated_rows': estimated_total_rows,
                'estimated_size_mb': estimated_size_bytes / (1024 * 1024),
                'sample_period_days': sample_days,
                'total_period_days': total_days,
                'sample_rows': len(sample_data)
            }
            
        except Exception as e:
            logger.error(f"Failed to estimate data size: {e}")
            return {
                'estimated_rows': 0,
                'estimated_size_mb': 0,
                'error': str(e)
            }