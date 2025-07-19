# Crypto Lake S3 Integration Guide

## Overview
This guide provides specific implementation details for integrating with Crypto Lake's S3-based data storage using the AWS credentials from the `.env` file.

## Environment Setup

### 1. `.env` File Structure
```bash
# Crypto Lake AWS Credentials
aws_access_key_id=your_access_key_here
aws_secret_access_key=your_secret_key_here

# Optional: AWS Region (if specified by Crypto Lake)
aws_region=us-east-1
```

### 2. Loading Credentials
```python
from dotenv import load_dotenv
import os
import boto3
from loguru import logger

# Load environment variables from .env file
load_dotenv()

# Set AWS credentials for lakeapi if they exist in the .env file
if os.getenv('aws_access_key_id') and os.getenv('aws_secret_access_key'):
    os.environ['AWS_ACCESS_KEY_ID'] = os.getenv('aws_access_key_id')
    os.environ['AWS_SECRET_ACCESS_KEY'] = os.getenv('aws_secret_access_key')
    logger.info("AWS credentials loaded from .env file for lakeapi.")
```

## Implementation Components

### 1. S3 Client Initialization
```python
import boto3
from botocore.exceptions import ClientError

class CryptoLakeS3Client:
    def __init__(self):
        self.load_credentials()
        self.s3_client = self._create_s3_client()
        self.bucket_name = self._discover_bucket_name()
    
    def _create_s3_client(self):
        """Create S3 client with loaded credentials."""
        try:
            return boto3.client(
                's3',
                aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
                aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
                region_name=os.getenv('aws_region', 'us-east-1')
            )
        except Exception as e:
            logger.error(f"Failed to create S3 client: {e}")
            raise
    
    def _discover_bucket_name(self):
        """Discover Crypto Lake bucket name."""
        try:
            # List all accessible buckets
            response = self.s3_client.list_buckets()
            buckets = [b['Name'] for b in response['Buckets']]
            
            # Look for crypto-lake related bucket
            for bucket in buckets:
                if 'crypto' in bucket.lower() or 'lake' in bucket.lower():
                    logger.info(f"Found Crypto Lake bucket: {bucket}")
                    return bucket
            
            # If no obvious match, use first bucket
            if buckets:
                logger.warning(f"No obvious Crypto Lake bucket found, using: {buckets[0]}")
                return buckets[0]
            
            raise ValueError("No accessible buckets found")
            
        except ClientError as e:
            logger.error(f"Error listing buckets: {e}")
            raise
```

### 2. Data Discovery
```python
def list_available_data(self, symbol='BTC-USDT', exchange='binance'):
    """List available data files for a symbol."""
    prefix = f"{exchange}/{symbol}/"
    
    try:
        paginator = self.s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(
            Bucket=self.bucket_name,
            Prefix=prefix
        )
        
        files = []
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    files.append({
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'last_modified': obj['LastModified']
                    })
        
        # Organize by data type
        trades_files = [f for f in files if 'trades' in f['key']]
        book_files = [f for f in files if 'book' in f['key'] and 'delta' not in f['key']]
        delta_files = [f for f in files if 'book_delta' in f['key']]
        
        return {
            'trades': trades_files,
            'book': book_files,
            'book_delta_v2': delta_files
        }
        
    except ClientError as e:
        logger.error(f"Error listing objects: {e}")
        raise
```

### 3. Download Implementation
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tqdm import tqdm

class DataDownloader:
    def __init__(self, s3_client, staging_path='data/staging/raw'):
        self.s3_client = s3_client
        self.staging_path = Path(staging_path)
        self.staging_path.mkdir(parents=True, exist_ok=True)
        
    async def download_file(self, s3_key, local_path=None):
        """Download a single file from S3."""
        if local_path is None:
            # Preserve S3 directory structure locally
            local_path = self.staging_path / s3_key
        
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Get file size for progress bar
            response = self.s3_client.s3_client.head_object(
                Bucket=self.s3_client.bucket_name,
                Key=s3_key
            )
            file_size = response['ContentLength']
            
            # Download with progress bar
            with tqdm(total=file_size, unit='B', unit_scale=True, desc=s3_key.split('/')[-1]) as pbar:
                def callback(bytes_transferred):
                    pbar.update(bytes_transferred)
                
                self.s3_client.s3_client.download_file(
                    self.s3_client.bucket_name,
                    s3_key,
                    str(local_path),
                    Callback=callback
                )
            
            logger.info(f"Downloaded: {s3_key} -> {local_path}")
            return local_path
            
        except ClientError as e:
            logger.error(f"Download failed for {s3_key}: {e}")
            raise
    
    async def download_date_range(self, symbol, exchange, data_type, start_date, end_date):
        """Download data for a date range."""
        # List all files in range
        files = await self.list_files_in_range(symbol, exchange, data_type, start_date, end_date)
        
        # Download concurrently with limit
        semaphore = asyncio.Semaphore(3)  # Max 3 concurrent downloads
        
        async def download_with_limit(file_info):
            async with semaphore:
                return await self.download_file(file_info['key'])
        
        tasks = [download_with_limit(f) for f in files]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Separate successes and failures
        downloaded = []
        failed = []
        
        for file_info, result in zip(files, results):
            if isinstance(result, Exception):
                failed.append((file_info, result))
            else:
                downloaded.append(result)
        
        return downloaded, failed
```

### 4. Data Validation
```python
import polars as pl
import hashlib

class DataValidator:
    def __init__(self):
        self.expected_schemas = {
            'trades': ['origin_time', 'price', 'quantity', 'side'],
            'book': ['origin_time', 'bids', 'asks'],
            'book_delta_v2': ['origin_time', 'update_id', 'bids', 'asks']
        }
    
    def validate_file(self, file_path, data_type):
        """Validate a downloaded file."""
        try:
            # Read file
            df = pl.read_parquet(file_path)
            
            # Check schema
            missing_cols = set(self.expected_schemas.get(data_type, [])) - set(df.columns)
            if missing_cols:
                raise ValueError(f"Missing columns: {missing_cols}")
            
            # Check data quality
            if 'origin_time' in df.columns:
                if df['origin_time'].null_count() > 0:
                    raise ValueError("Null values in origin_time")
                
                if not df['origin_time'].is_sorted():
                    logger.warning(f"Data not sorted by origin_time in {file_path}")
            
            if 'price' in df.columns:
                if (df['price'] <= 0).any():
                    raise ValueError("Non-positive prices found")
            
            logger.info(f"Validation passed for {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Validation failed for {file_path}: {e}")
            return False
```

### 5. CLI Implementation
```python
import click
from datetime import datetime
import asyncio

@click.group()
def cli():
    """Crypto Lake Data Acquisition CLI"""
    pass

@cli.command()
def test_connection():
    """Test connection to Crypto Lake S3."""
    try:
        client = CryptoLakeS3Client()
        click.echo(f"✅ Connected to bucket: {client.bucket_name}")
        
        # Try to list some files
        files = client.list_available_data()
        click.echo(f"Found {len(files['trades'])} trades files")
        click.echo(f"Found {len(files['book'])} book snapshot files")
        click.echo(f"Found {len(files['book_delta_v2'])} delta files")
        
    except Exception as e:
        click.echo(f"❌ Connection failed: {e}")
        raise click.Abort()

@cli.command()
@click.option('--symbol', default='BTC-USDT', help='Trading symbol')
@click.option('--exchange', default='binance', help='Exchange')
@click.option('--data-type', type=click.Choice(['trades', 'book', 'book_delta_v2', 'all']), default='all')
@click.option('--start-date', required=True, help='Start date (YYYY-MM-DD)')
@click.option('--end-date', required=True, help='End date (YYYY-MM-DD)')
def download(symbol, exchange, data_type, start_date, end_date):
    """Download data from Crypto Lake."""
    async def run():
        client = CryptoLakeS3Client()
        downloader = DataDownloader(client)
        
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        
        if data_type == 'all':
            data_types = ['trades', 'book', 'book_delta_v2']
        else:
            data_types = [data_type]
        
        for dt in data_types:
            click.echo(f"\nDownloading {dt} data...")
            downloaded, failed = await downloader.download_date_range(
                symbol, exchange, dt, start, end
            )
            
            click.echo(f"✅ Downloaded {len(downloaded)} files")
            if failed:
                click.echo(f"❌ Failed {len(failed)} files")
    
    asyncio.run(run())

if __name__ == '__main__':
    cli()
```

## Usage Examples

### 1. Test Connection
```bash
python scripts/acquire_data.py test-connection
```

### 2. Download One Day Sample
```bash
python scripts/acquire_data.py download \
    --symbol BTC-USDT \
    --exchange binance \
    --data-type trades \
    --start-date 2024-01-01 \
    --end-date 2024-01-01
```

### 3. Download Full Year
```bash
python scripts/acquire_data.py download \
    --symbol BTC-USDT \
    --exchange binance \
    --data-type all \
    --start-date 2024-01-01 \
    --end-date 2024-12-31
```

## Expected S3 Path Patterns

Based on common Crypto Lake structures:
```
s3://crypto-lake-bucket/
├── binance/
│   ├── BTC-USDT/
│   │   ├── trades/
│   │   │   ├── 2024/
│   │   │   │   ├── 01/
│   │   │   │   │   ├── 2024-01-01.parquet
│   │   │   │   │   ├── 2024-01-02.parquet
│   │   │   │   │   └── ...
│   │   ├── book/
│   │   │   └── [similar structure]
│   │   └── book_delta_v2/
│   │       └── [similar structure]
```

## Error Handling

1. **Authentication Errors**: Check `.env` file has correct credentials
2. **Access Denied**: Verify your access includes the required data
3. **File Not Found**: Some data types might not be available for all dates
4. **Network Issues**: Implement retry with exponential backoff

## Next Steps

1. Run `test-connection` to verify access
2. Download 1-day sample to understand data structure
3. Validate data schema matches expectations
4. Plan full download schedule based on available bandwidth