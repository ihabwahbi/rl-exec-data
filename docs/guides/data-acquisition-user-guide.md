# Data Acquisition User Guide

## Overview

The data acquisition pipeline downloads and validates historical market data from Crypto Lake S3. This is **Epic 0** - the absolute blocking prerequisite for all other work.

## Prerequisites

1. **Crypto Lake Subscription**: Active subscription with S3 access
2. **AWS Credentials**: Valid access key and secret in `.env` file
3. **Python Environment**: Virtual environment with dependencies installed

## Quick Start

### 1. Verify Connection
```bash
# Test your Crypto Lake S3 access
python scripts/acquire_data.py test-connection

# If bucket name is known, specify it
python scripts/acquire_data.py --bucket cryptolake test-connection
```

### 2. Explore Available Data
```bash
# List all available data for BTC-USDT
python scripts/acquire_data.py list-inventory

# List specific data type
python scripts/acquire_data.py list-inventory --data-type trades
```

### 3. Download Sample Data
```bash
# Download one day for testing
python scripts/acquire_data.py download \
  --start-date 2024-01-01 \
  --end-date 2024-01-01 \
  --dry-run

# If dry-run looks good, remove --dry-run to download
python scripts/acquire_data.py download \
  --start-date 2024-01-01 \
  --end-date 2024-01-01
```

### 4. Validate Downloaded Data
```bash
# Validate all downloaded files
python scripts/acquire_data.py validate

# Check staging status
python scripts/acquire_data.py status
```

### 5. Generate Readiness Certificate
```bash
# Generate certificate for date range
python scripts/acquire_data.py certify \
  --start-date 2024-01-01 \
  --end-date 2024-12-31
```

## Full Production Workflow

### Phase 1: Access Verification (Week 1)
```bash
# Step 1: Test connection
python scripts/acquire_data.py test-connection

# Step 2: Explore available data
python scripts/acquire_data.py list-inventory

# Step 3: Download 1 week sample
python scripts/acquire_data.py download \
  --start-date 2024-01-01 \
  --end-date 2024-01-07 \
  --dry-run

# Step 4: Actual sample download
python scripts/acquire_data.py download \
  --start-date 2024-01-01 \
  --end-date 2024-01-07

# Step 5: Validate sample
python scripts/acquire_data.py validate
python scripts/acquire_data.py status
```

### Phase 2: Full Download (Week 2-3)
```bash
# Download 12 months of data (Q1)
python scripts/acquire_data.py download \
  --start-date 2024-01-01 \
  --end-date 2024-03-31

# Download Q2
python scripts/acquire_data.py download \
  --start-date 2024-04-01 \
  --end-date 2024-06-30

# Download Q3
python scripts/acquire_data.py download \
  --start-date 2024-07-01 \
  --end-date 2024-09-30

# Download Q4
python scripts/acquire_data.py download \
  --start-date 2024-10-01 \
  --end-date 2024-12-31

# Validate all data
python scripts/acquire_data.py validate
```

### Phase 3: Certification (Week 3)
```bash
# Generate final certificate
python scripts/acquire_data.py certify \
  --start-date 2024-01-01 \
  --end-date 2024-12-31

# Check final status
python scripts/acquire_data.py status
```

## CLI Commands Reference

### test-connection
Tests connection to Crypto Lake S3 and shows available data summary.

**Options:**
- `--bucket TEXT`: Specific bucket name (if known)
- `--verbose`: Enable detailed logging

**Example:**
```bash
python scripts/acquire_data.py test-connection
```

### list-inventory
Lists available data files in Crypto Lake S3.

**Options:**
- `--symbol TEXT`: Trading symbol (default: BTC-USDT)
- `--exchange TEXT`: Exchange name (default: binance)
- `--data-type CHOICE`: Specific data type (trades, book, book_delta_v2)

**Example:**
```bash
python scripts/acquire_data.py list-inventory --data-type trades
```

### download
Downloads historical data from Crypto Lake S3.

**Options:**
- `--symbol TEXT`: Trading symbol (default: BTC-USDT)
- `--exchange TEXT`: Exchange name (default: binance)
- `--data-types MULTIPLE`: Data types to download (default: all)
- `--start-date TEXT`: Start date (YYYY-MM-DD) **[REQUIRED]**
- `--end-date TEXT`: End date (YYYY-MM-DD) **[REQUIRED]**
- `--dry-run`: Show what would be downloaded without downloading
- `--staging-path TEXT`: Staging directory (default: data/staging)

**Example:**
```bash
python scripts/acquire_data.py download \
  --start-date 2024-01-01 \
  --end-date 2024-01-31 \
  --data-types trades \
  --data-types book
```

### validate
Validates downloaded files and moves them through the staging pipeline.

**Options:**
- `--staging-path TEXT`: Staging directory (default: data/staging)
- `--data-type TEXT`: Specific data type to validate

**Example:**
```bash
python scripts/acquire_data.py validate --data-type trades
```

### status
Shows staging area status and statistics.

**Options:**
- `--staging-path TEXT`: Staging directory (default: data/staging)

**Example:**
```bash
python scripts/acquire_data.py status
```

### certify
Generates data readiness certificate for a date range.

**Options:**
- `--symbol TEXT`: Trading symbol (default: BTC-USDT)
- `--exchange TEXT`: Exchange name (default: binance)
- `--start-date TEXT`: Start date (YYYY-MM-DD) **[REQUIRED]**
- `--end-date TEXT`: End date (YYYY-MM-DD) **[REQUIRED]**
- `--data-types MULTIPLE`: Required data types (default: all)
- `--staging-path TEXT`: Staging directory (default: data/staging)

**Example:**
```bash
python scripts/acquire_data.py certify \
  --start-date 2024-01-01 \
  --end-date 2024-12-31
```

## Directory Structure

The system creates the following directory structure:

```
data/staging/
├── raw/              # Initial downloads
├── validating/       # Files under validation
├── ready/            # Validated files organized by type/date
│   ├── trades/
│   ├── book/
│   └── book_delta_v2/
├── quarantine/       # Failed validation files
└── manifest.json     # File tracking manifest
```

## File Status Flow

Files move through the following states:

1. **RAW**: Just downloaded from S3
2. **VALIDATING**: Under validation 
3. **READY**: Passed validation, organized by type/date
4. **QUARANTINED**: Failed validation with error details

## Error Handling

### Connection Issues
- **Bucket not found**: Contact Crypto Lake support for correct bucket name
- **Access denied**: Verify subscription and permissions with Crypto Lake
- **Network errors**: Automatic retry with exponential backoff

### Download Issues
- **File not found**: Some data may not be available for all dates
- **Partial downloads**: Automatic resume from last successful chunk
- **Corruption**: Files are re-downloaded automatically

### Validation Issues
- **Schema mismatch**: Files are quarantined with detailed error logs
- **Data quality**: Issues are logged as warnings vs errors
- **Missing dates**: Reported in readiness certificate

## Troubleshooting

### "Cannot discover bucket name"
1. Contact Crypto Lake support for exact bucket name
2. Use `--bucket` option to specify bucket manually
3. Verify your subscription includes S3 access

### "Access Denied" errors
1. Check your Crypto Lake subscription status
2. Verify `.env` file has correct credentials
3. Try different AWS regions (usually us-east-1)

### Slow downloads
1. Reduce `--max-concurrent` in downloader settings
2. Check your internet connection
3. Try downloading during off-peak hours

### Validation failures
1. Check quarantine directory for error details
2. Re-download failed files
3. Adjust validation thresholds if data format changed

## Monitoring

### Progress Tracking
- Download progress shown with progress bars
- Validation results reported per file
- Overall statistics in status command

### Log Files
- All operations logged with timestamps
- Error details captured for debugging
- Progress metrics available for monitoring

### Success Metrics
- **Download Success Rate**: Should be >95%
- **Validation Pass Rate**: Should be >99% 
- **Data Completeness**: Should cover full date range
- **Speed**: Should sustain >10 MB/s download speed

## Next Steps After Completion

Once data acquisition is complete:

1. **Update Project Status**: Mark Epic 0 as complete
2. **Begin Epic 1**: Re-run Story 1.1 with real data
3. **Live Capture**: Execute Story 1.2 
4. **Technical Validation**: Complete Story 1.2.5

The readiness certificate confirms all data is available for Epic 1 work to begin.