# Engineering Action Plan - Data Acquisition Implementation

## Immediate Technical Tasks (Day 1-2)

### 1. Create Data Acquisition Module Structure
```bash
mkdir -p src/data_acquisition/{api,download,validation,staging}
touch src/data_acquisition/__init__.py
touch src/data_acquisition/api/crypto_lake_client.py
touch src/data_acquisition/download/downloader.py
touch src/data_acquisition/validation/integrity_validator.py
touch src/data_acquisition/staging/staging_manager.py
```

### 2. Implement Crypto Lake API Client

```python
# src/data_acquisition/api/crypto_lake_client.py
import os
import aiohttp
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
import logging

class CryptoLakeAPIClient:
    """Handles all interactions with Crypto Lake API."""
    
    def __init__(self):
        self.api_key = os.environ.get('CRYPTO_LAKE_API_KEY')
        self.api_secret = os.environ.get('CRYPTO_LAKE_API_SECRET')
        self.base_url = "https://api.crypto-lake.com/v1"
        self.session: Optional[aiohttp.ClientSession] = None
        
        if not self.api_key or not self.api_secret:
            raise ValueError("Crypto Lake credentials not found in environment")
    
    async def test_connection(self) -> bool:
        """Test API connectivity and authentication."""
        try:
            async with aiohttp.ClientSession() as session:
                headers = self._get_headers()
                async with session.get(
                    f"{self.base_url}/health",
                    headers=headers
                ) as response:
                    return response.status == 200
        except Exception as e:
            logging.error(f"Connection test failed: {e}")
            return False
    
    async def get_data_inventory(self, symbol: str, exchange: str) -> Dict[str, Any]:
        """Check available data for a symbol."""
        # Implementation here
        pass
    
    def _get_headers(self) -> Dict[str, str]:
        """Generate authenticated headers."""
        # Add proper authentication headers
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
```

### 3. Implement Download Manager

```python
# src/data_acquisition/download/downloader.py
import asyncio
import aiohttp
from pathlib import Path
from typing import List, Dict, Any
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class DownloadChunk:
    symbol: str
    exchange: str
    data_type: str  # 'trades', 'book', 'book_delta_v2'
    start_date: datetime
    end_date: datetime
    file_path: Path
    status: str = 'pending'
    checksum: Optional[str] = None
    
class DataDownloader:
    """Manages resilient data downloads with chunking and retry."""
    
    def __init__(self, api_client: CryptoLakeAPIClient, 
                 staging_path: Path,
                 max_concurrent: int = 3,
                 max_retries: int = 3):
        self.api_client = api_client
        self.staging_path = staging_path
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        
    async def download_dataset(self, 
                              symbol: str,
                              exchange: str,
                              data_type: str,
                              start_date: datetime,
                              end_date: datetime) -> List[DownloadChunk]:
        """Download a full dataset with chunking."""
        
        # Create weekly chunks
        chunks = self._create_chunks(
            symbol, exchange, data_type, start_date, end_date
        )
        
        # Download with concurrency limit
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def download_with_limit(chunk):
            async with semaphore:
                return await self._download_chunk(chunk)
        
        tasks = [download_with_limit(chunk) for chunk in chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle results and failures
        successful_chunks = []
        failed_chunks = []
        
        for chunk, result in zip(chunks, results):
            if isinstance(result, Exception):
                failed_chunks.append(chunk)
                logging.error(f"Chunk download failed: {chunk}, Error: {result}")
            else:
                successful_chunks.append(chunk)
                
        return successful_chunks, failed_chunks
```

### 4. Implement Integrity Validator

```python
# src/data_acquisition/validation/integrity_validator.py
import polars as pl
from pathlib import Path
from typing import Dict, List, Any
from dataclasses import dataclass
import hashlib

@dataclass
class ValidationResult:
    file_path: Path
    passed: bool
    checks: Dict[str, bool]
    errors: List[str]
    warnings: List[str]

class IntegrityValidator:
    """Validates downloaded data files for completeness and quality."""
    
    def __init__(self):
        self.required_columns = {
            'trades': ['origin_time', 'price', 'quantity', 'side'],
            'book': ['origin_time', 'bids', 'asks'],
            'book_delta_v2': ['origin_time', 'update_id', 'bids', 'asks']
        }
    
    async def validate_file(self, file_path: Path, 
                           data_type: str,
                           expected_checksum: str = None) -> ValidationResult:
        """Run comprehensive validation on a data file."""
        
        errors = []
        warnings = []
        checks = {}
        
        # Level 1: File integrity
        checks['file_exists'] = file_path.exists()
        if not checks['file_exists']:
            errors.append(f"File not found: {file_path}")
            return ValidationResult(file_path, False, checks, errors, warnings)
        
        # Checksum validation
        if expected_checksum:
            actual_checksum = self._calculate_checksum(file_path)
            checks['checksum_valid'] = actual_checksum == expected_checksum
            if not checks['checksum_valid']:
                errors.append(f"Checksum mismatch: expected {expected_checksum}, got {actual_checksum}")
        
        # Level 2: Schema validation
        try:
            df = pl.read_parquet(file_path)
            
            # Check required columns
            missing_cols = set(self.required_columns[data_type]) - set(df.columns)
            checks['schema_valid'] = len(missing_cols) == 0
            if missing_cols:
                errors.append(f"Missing required columns: {missing_cols}")
            
            # Level 3: Data quality
            if 'origin_time' in df.columns:
                # Check temporal ordering
                is_sorted = df['origin_time'].is_sorted()
                checks['temporal_order'] = is_sorted
                if not is_sorted:
                    warnings.append("Data not sorted by origin_time")
                
                # Check for gaps
                if len(df) > 1:
                    time_diffs = df['origin_time'].diff().drop_nulls()
                    max_gap = time_diffs.max()
                    checks['no_large_gaps'] = max_gap < pd.Timedelta(minutes=5)
                    if max_gap >= pd.Timedelta(minutes=5):
                        warnings.append(f"Large time gap detected: {max_gap}")
            
            # Level 4: Statistical sanity checks
            if 'price' in df.columns:
                checks['positive_prices'] = (df['price'] > 0).all()
                if not checks['positive_prices']:
                    errors.append("Negative or zero prices found")
                    
            if 'quantity' in df.columns:
                checks['positive_quantities'] = (df['quantity'] > 0).all()
                if not checks['positive_quantities']:
                    errors.append("Negative or zero quantities found")
                    
        except Exception as e:
            errors.append(f"Failed to read file: {str(e)}")
            checks['readable'] = False
        
        passed = len(errors) == 0
        return ValidationResult(file_path, passed, checks, errors, warnings)
```

### 5. Create CLI Entry Point

```python
# src/data_acquisition/cli.py
import click
import asyncio
from datetime import datetime
from pathlib import Path
from .acquisition_manager import DataAcquisitionManager

@click.group()
def cli():
    """RLX Data Pipeline - Data Acquisition Tools"""
    pass

@cli.command()
@click.option('--test-only', is_flag=True, help='Only test connection')
def verify_access(test_only):
    """Verify Crypto Lake API access."""
    async def run():
        manager = DataAcquisitionManager()
        if await manager.verify_access():
            click.echo("✅ Crypto Lake access verified!")
            if not test_only:
                inventory = await manager.check_inventory('BTC-USDT', 'binance')
                click.echo(f"Available data: {inventory}")
        else:
            click.echo("❌ Crypto Lake access failed!")
            raise click.Abort()
    
    asyncio.run(run())

@cli.command()
@click.option('--symbol', default='BTC-USDT', help='Trading symbol')
@click.option('--exchange', default='binance', help='Exchange name')
@click.option('--start-date', required=True, help='Start date (YYYY-MM-DD)')
@click.option('--end-date', required=True, help='End date (YYYY-MM-DD)')
@click.option('--data-types', multiple=True, 
              default=['trades', 'book', 'book_delta_v2'],
              help='Data types to download')
def download(symbol, exchange, start_date, end_date, data_types):
    """Download historical data from Crypto Lake."""
    async def run():
        manager = DataAcquisitionManager()
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        
        result = await manager.acquire_data(
            symbol=symbol,
            exchange=exchange,
            start_date=start,
            end_date=end,
            data_types=list(data_types)
        )
        
        if result.success:
            click.echo(f"✅ Data acquisition complete!")
            click.echo(f"Files downloaded: {result.file_count}")
            click.echo(f"Total size: {result.total_size_gb:.2f} GB")
        else:
            click.echo(f"❌ Data acquisition failed!")
            for error in result.errors:
                click.echo(f"  - {error}")
    
    asyncio.run(run())

if __name__ == '__main__':
    cli()
```

### 6. Create Integration Tests

```python
# tests/test_data_acquisition.py
import pytest
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from src.data_acquisition import DataAcquisitionManager

@pytest.mark.asyncio
async def test_crypto_lake_connection():
    """Test that we can connect to Crypto Lake API."""
    manager = DataAcquisitionManager()
    assert await manager.verify_access()

@pytest.mark.asyncio
async def test_download_one_day():
    """Test downloading one day of data."""
    manager = DataAcquisitionManager()
    
    # Use a recent date to ensure data availability
    end_date = datetime.now() - timedelta(days=7)
    start_date = end_date - timedelta(days=1)
    
    result = await manager.acquire_data(
        symbol='BTC-USDT',
        exchange='binance',
        start_date=start_date,
        end_date=end_date,
        data_types=['trades']
    )
    
    assert result.success
    assert result.file_count > 0
    assert all(Path(f).exists() for f in result.files)

@pytest.mark.asyncio
async def test_data_validation():
    """Test that downloaded data passes validation."""
    # Download small sample
    # Validate it
    # Assert validation passes
    pass
```

## Environment Setup

### 1. Create .env.template
```bash
# Crypto Lake API Credentials
CRYPTO_LAKE_API_KEY=your_api_key_here
CRYPTO_LAKE_API_SECRET=your_api_secret_here

# Data Paths
DATA_STAGING_PATH=/path/to/data/staging
DATA_READY_PATH=/path/to/data/ready

# Download Settings
MAX_CONCURRENT_DOWNLOADS=3
DOWNLOAD_CHUNK_DAYS=7
```

### 2. Update requirements.txt
```
aiohttp>=3.9.0
asyncio
polars>=0.20.0
pyarrow>=14.0.0
click>=8.1.0
python-dotenv>=1.0.0
pytest>=7.4.0
pytest-asyncio>=0.21.0
```

## Execution Plan

### Day 1: Foundation
1. Set up project structure
2. Implement API client with connection test
3. Get credentials and verify access
4. If no access: STOP and escalate

### Day 2-3: Core Implementation  
1. Implement download manager
2. Implement integrity validator
3. Create CLI interface
4. Test with 1-day sample

### Day 4-5: Production Download
1. Start downloading Q1 2024
2. Monitor progress continuously
3. Validate each completed chunk
4. Handle any failures immediately

### Week 2: Complete Download
1. Continue downloading remaining quarters
2. Run comprehensive validation
3. Generate data manifest
4. Issue readiness certificate

## Monitoring During Download

```python
# Simple progress monitor
import time
from datetime import datetime

class DownloadMonitor:
    def __init__(self, total_chunks):
        self.total_chunks = total_chunks
        self.completed_chunks = 0
        self.failed_chunks = 0
        self.start_time = time.time()
        
    def update(self, success=True):
        if success:
            self.completed_chunks += 1
        else:
            self.failed_chunks += 1
            
        # Calculate metrics
        elapsed = time.time() - self.start_time
        rate = self.completed_chunks / elapsed if elapsed > 0 else 0
        eta = (self.total_chunks - self.completed_chunks) / rate if rate > 0 else 0
        
        # Print status
        print(f"\rProgress: {self.completed_chunks}/{self.total_chunks} "
              f"({self.completed_chunks/self.total_chunks*100:.1f}%) "
              f"Failed: {self.failed_chunks} "
              f"Rate: {rate:.2f} chunks/sec "
              f"ETA: {eta/3600:.1f} hours", end='')
```

## Success Criteria

The implementation is complete when:
1. ✅ All code modules are implemented and tested
2. ✅ Connection to Crypto Lake is verified
3. ✅ 1-day sample successfully downloaded and validated
4. ✅ Full download process is running
5. ✅ Monitoring shows steady progress
6. ✅ No critical errors in logs

---

**Remember**: This is the foundation of the entire project. Take time to get it right. Test thoroughly. Monitor continuously. Escalate blockers immediately.