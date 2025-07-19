"""Crypto Lake S3 client for data access."""

import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv
from loguru import logger


class CryptoLakeClient:
    """Handles all interactions with Crypto Lake S3 buckets."""
    
    def __init__(self, region_name: str = "us-east-1", bucket_name: Optional[str] = None):
        """Initialize Crypto Lake S3 client.
        
        Args:
            region_name: AWS region for S3 client
            bucket_name: Specific bucket name to use (if known)
            
        Raises:
            ValueError: If AWS credentials not found in environment
            ClientError: If S3 client creation fails
        """
        self.region_name = region_name
        self._load_credentials()
        self.s3_client = self._create_s3_client()
        
        if bucket_name:
            self.bucket_name = bucket_name
            logger.info(f"Using manually specified bucket: {bucket_name}")
        else:
            self.bucket_name = self._discover_bucket_name()
        
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
        
        # Set AWS credentials for boto3
        os.environ['AWS_ACCESS_KEY_ID'] = self.aws_access_key_id
        os.environ['AWS_SECRET_ACCESS_KEY'] = self.aws_secret_access_key
        
        logger.info("AWS credentials loaded from .env file for lakeapi")
        
    def _create_s3_client(self):
        """Create S3 client with loaded credentials.
        
        Returns:
            boto3.client: Configured S3 client
            
        Raises:
            ClientError: If S3 client creation fails
        """
        try:
            return boto3.client(
                's3',
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                region_name=self.region_name
            )
        except Exception as e:
            logger.error(f"Failed to create S3 client: {e}")
            raise
            
    def _discover_bucket_name(self) -> str:
        """Discover Crypto Lake bucket name from accessible buckets.
        
        Returns:
            str: Bucket name to use for data access
            
        Raises:
            ClientError: If bucket listing fails
            ValueError: If no accessible buckets found
        """
        # Try common Crypto Lake bucket names first
        common_bucket_names = [
            'crypto-lake',
            'cryptolake',
            'crypto-lake-data',
            'cryptolake-data',
            'datalake-crypto',
            'lake-crypto',
            'crypto-lake-prod',
            'crypto-lake-s3',
            'binance-crypto-lake',
            'market-data-lake'
        ]
        
        # Test each common bucket name
        for bucket_name in common_bucket_names:
            try:
                # Try to list objects in the bucket (requires less permissions than ListBuckets)
                self.s3_client.list_objects_v2(
                    Bucket=bucket_name,
                    MaxKeys=1
                )
                logger.info(f"Found accessible Crypto Lake bucket: {bucket_name}")
                return bucket_name
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == 'NoSuchBucket':
                    continue  # Try next bucket name
                elif error_code == 'AccessDenied':
                    logger.warning(f"Access denied to bucket {bucket_name}")
                    continue
                else:
                    logger.debug(f"Error accessing bucket {bucket_name}: {e}")
                    continue
        
        # If common names don't work, try to list all buckets
        try:
            response = self.s3_client.list_buckets()
            buckets = [b['Name'] for b in response['Buckets']]
            
            if not buckets:
                raise ValueError("No accessible buckets found with provided credentials")
            
            # Look for crypto-lake related bucket
            for bucket in buckets:
                if 'crypto' in bucket.lower() or 'lake' in bucket.lower():
                    logger.info(f"Found Crypto Lake bucket: {bucket}")
                    return bucket
            
            # If no obvious match, use first bucket and warn
            bucket_name = buckets[0]
            logger.warning(f"No obvious Crypto Lake bucket found, using: {bucket_name}")
            logger.info(f"Available buckets: {buckets}")
            return bucket_name
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                # Can't list buckets, but we already tried common names
                raise ValueError(
                    "Cannot discover bucket name. User lacks ListBuckets permission "
                    "and common bucket names are not accessible. "
                    "Please provide bucket name manually or contact Crypto Lake support."
                )
            else:
                logger.error(f"Error listing buckets: {e}")
                raise
            
    def test_connection(self) -> bool:
        """Test connection to Crypto Lake S3.
        
        Returns:
            bool: True if connection successful
        """
        try:
            # Try to list objects in bucket
            self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                MaxKeys=1
            )
            logger.info("S3 connection test successful")
            return True
        except Exception as e:
            logger.error(f"S3 connection test failed: {e}")
            return False
            
    def list_available_data(self, symbol: str = 'BTC-USDT', exchange: str = 'binance') -> Dict[str, List[Dict[str, Any]]]:
        """List available data files for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC-USDT')
            exchange: Exchange name (e.g., 'binance')
            
        Returns:
            Dict containing lists of available files by data type
            
        Raises:
            ClientError: If S3 listing fails
        """
        # Try multiple possible prefix patterns
        prefix_patterns = [
            f"{exchange}/{symbol}/",
            f"{exchange}/{symbol.lower()}/",
            f"{symbol}/",
            f"{symbol.lower()}/",
            f"data/{exchange}/{symbol}/",
            f"data/{exchange}/{symbol.lower()}/"
        ]
        
        all_files = []
        
        for prefix in prefix_patterns:
            try:
                logger.debug(f"Checking prefix: {prefix}")
                paginator = self.s3_client.get_paginator('list_objects_v2')
                pages = paginator.paginate(
                    Bucket=self.bucket_name,
                    Prefix=prefix
                )
                
                for page in pages:
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            all_files.append({
                                'key': obj['Key'],
                                'size': obj['Size'],
                                'last_modified': obj['LastModified'],
                                'prefix_used': prefix
                            })
                
                # If we found files with this prefix, use it
                if all_files:
                    logger.info(f"Found data with prefix: {prefix}")
                    break
                    
            except ClientError as e:
                logger.warning(f"Error checking prefix {prefix}: {e}")
                continue
        
        if not all_files:
            logger.warning(f"No data found for {symbol} on {exchange}")
            return {'trades': [], 'book': [], 'book_delta_v2': []}
        
        # Organize by data type
        trades_files = [f for f in all_files if 'trades' in f['key'].lower()]
        book_files = [f for f in all_files if 'book' in f['key'].lower() and 'delta' not in f['key'].lower()]
        delta_files = [f for f in all_files if 'book_delta' in f['key'].lower() or 'delta' in f['key'].lower()]
        
        logger.info(f"Found {len(trades_files)} trades files, {len(book_files)} book files, {len(delta_files)} delta files")
        
        return {
            'trades': trades_files,
            'book': book_files,
            'book_delta_v2': delta_files
        }
        
    def list_files_in_date_range(self, symbol: str, exchange: str, data_type: str, 
                                start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """List files for a specific data type within a date range.
        
        Args:
            symbol: Trading pair symbol
            exchange: Exchange name  
            data_type: Type of data ('trades', 'book', 'book_delta_v2')
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            
        Returns:
            List of file metadata dictionaries
        """
        all_data = self.list_available_data(symbol, exchange)
        files = all_data.get(data_type, [])
        
        # Filter by date range (basic implementation - may need refinement based on actual S3 structure)
        filtered_files = []
        for file_info in files:
            key = file_info['key']
            file_date = self._extract_date_from_key(key)
            
            if file_date and start_date <= file_date <= end_date:
                filtered_files.append(file_info)
        
        # Sort by date
        filtered_files.sort(key=lambda x: self._extract_date_from_key(x['key']) or datetime.min)
        
        return filtered_files
        
    def _extract_date_from_key(self, key: str) -> Optional[datetime]:
        """Extract date from S3 key path.
        
        Args:
            key: S3 object key
            
        Returns:
            datetime object if date found, None otherwise
        """
        # Try to find date patterns in the key
        import re
        
        # Look for YYYY-MM-DD pattern
        date_pattern = r'(\d{4})-(\d{2})-(\d{2})'
        match = re.search(date_pattern, key)
        if match:
            year, month, day = match.groups()
            try:
                return datetime(int(year), int(month), int(day))
            except ValueError:
                pass
        
        # Look for YYYY/MM/DD pattern
        date_pattern = r'(\d{4})/(\d{2})/(\d{2})'
        match = re.search(date_pattern, key)
        if match:
            year, month, day = match.groups()
            try:
                return datetime(int(year), int(month), int(day))
            except ValueError:
                pass
                
        return None
        
    def get_file_info(self, key: str) -> Dict[str, Any]:
        """Get metadata for a specific S3 object.
        
        Args:
            key: S3 object key
            
        Returns:
            Dictionary with file metadata
            
        Raises:
            ClientError: If object doesn't exist or access denied
        """
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=key
            )
            
            return {
                'key': key,
                'size': response['ContentLength'],
                'last_modified': response['LastModified'],
                'content_type': response.get('ContentType'),
                'etag': response.get('ETag')
            }
            
        except ClientError as e:
            logger.error(f"Error getting file info for {key}: {e}")
            raise