#!/usr/bin/env python3
"""CLI interface for Crypto Lake data acquisition."""

import sys
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List

import click
from loguru import logger

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rlx_datapipe.acquisition.crypto_lake_client import CryptoLakeClient
from rlx_datapipe.acquisition.data_downloader import DataDownloader
from rlx_datapipe.acquisition.integrity_validator import IntegrityValidator
from rlx_datapipe.acquisition.staging_manager import DataStagingManager


@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--bucket', help='Specific S3 bucket name (if known)')
@click.pass_context
def cli(ctx, verbose, bucket):
    """Crypto Lake Data Acquisition CLI
    
    This tool helps acquire historical market data from Crypto Lake S3.
    
    Make sure your .env file contains:
      aws_access_key_id=your_key
      aws_secret_access_key=your_secret
    """
    # Configure logging
    log_level = "DEBUG" if verbose else "INFO"
    logger.remove()
    logger.add(
        sys.stderr, 
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        level=log_level
    )
    
    # Store context
    ctx.ensure_object(dict)
    ctx.obj['bucket'] = bucket
    ctx.obj['verbose'] = verbose


@cli.command()
@click.pass_context
def test_connection(ctx):
    """Test connection to Crypto Lake S3."""
    bucket_name = ctx.obj.get('bucket')
    
    try:
        client = CryptoLakeClient(bucket_name=bucket_name)
        click.echo(f"✅ Connected to bucket: {client.bucket_name}")
        
        if client.test_connection():
            click.echo("✅ Connection test passed")
            
            # Try to list some data
            data = client.list_available_data()
            click.echo(f"\nData inventory:")
            click.echo(f"  Trades files: {len(data['trades'])}")
            click.echo(f"  Book files: {len(data['book'])}")
            click.echo(f"  Delta files: {len(data['book_delta_v2'])}")
            
            # Show sample files
            for data_type, files in data.items():
                if files:
                    click.echo(f"\n{data_type.upper()} sample files:")
                    for file_info in files[:3]:
                        size_mb = file_info['size'] / (1024 * 1024)
                        click.echo(f"  - {file_info['key']} ({size_mb:.1f} MB)")
                    if len(files) > 3:
                        click.echo(f"  ... and {len(files) - 3} more files")
            
        else:
            click.echo("❌ Connection test failed")
            raise click.Abort()
            
    except Exception as e:
        click.echo(f"❌ Connection failed: {e}")
        if ctx.obj.get('verbose'):
            import traceback
            click.echo(traceback.format_exc())
        raise click.Abort()


@cli.command()
@click.option('--symbol', default='BTC-USDT', help='Trading symbol')
@click.option('--exchange', default='binance', help='Exchange name')
@click.option('--data-type', 
              type=click.Choice(['trades', 'book', 'book_delta_v2']),
              help='Specific data type to list')
@click.pass_context
def list_inventory(ctx, symbol, exchange, data_type):
    """List available data in Crypto Lake."""
    bucket_name = ctx.obj.get('bucket')
    
    try:
        client = CryptoLakeClient(bucket_name=bucket_name)
        data = client.list_available_data(symbol, exchange)
        
        if data_type:
            # Show specific data type
            files = data.get(data_type, [])
            click.echo(f"\n{data_type.upper()} files for {symbol} on {exchange}:")
            click.echo(f"Found {len(files)} files")
            
            total_size = sum(f['size'] for f in files)
            click.echo(f"Total size: {total_size / (1024**3):.2f} GB")
            
            if files:
                click.echo("\nSample files:")
                for file_info in files[:10]:
                    size_mb = file_info['size'] / (1024 * 1024)
                    modified = file_info['last_modified'].strftime('%Y-%m-%d')
                    click.echo(f"  - {file_info['key']} ({size_mb:.1f} MB, {modified})")
        else:
            # Show all data types
            click.echo(f"\nData inventory for {symbol} on {exchange}:")
            
            for dtype, files in data.items():
                total_size = sum(f['size'] for f in files) / (1024**3)
                click.echo(f"  {dtype}: {len(files)} files ({total_size:.2f} GB)")
        
    except Exception as e:
        click.echo(f"❌ Failed to list inventory: {e}")
        if ctx.obj.get('verbose'):
            import traceback
            click.echo(traceback.format_exc())
        raise click.Abort()


@cli.command()
@click.option('--symbol', default='BTC-USDT', help='Trading symbol')
@click.option('--exchange', default='binance', help='Exchange name')
@click.option('--data-types', multiple=True, 
              default=['trades', 'book', 'book_delta_v2'],
              help='Data types to download')
@click.option('--start-date', required=True, help='Start date (YYYY-MM-DD)')
@click.option('--end-date', required=True, help='End date (YYYY-MM-DD)')
@click.option('--dry-run', is_flag=True, help='Show what would be downloaded without downloading')
@click.option('--staging-path', default='data/staging', help='Staging directory path')
@click.pass_context
def download(ctx, symbol, exchange, data_types, start_date, end_date, dry_run, staging_path):
    """Download historical data from Crypto Lake.
    
    Example:
      acquire_data download --start-date 2024-01-01 --end-date 2024-01-02
    """
    bucket_name = ctx.obj.get('bucket')
    
    try:
        # Parse dates
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
        
        if start_dt > end_dt:
            click.echo("❌ Start date must be before end date")
            raise click.Abort()
        
        # Initialize components
        client = CryptoLakeClient(bucket_name=bucket_name)
        staging_manager = DataStagingManager(Path(staging_path))
        
        if dry_run:
            click.echo("🔍 DRY RUN - No files will be downloaded")
        
        click.echo(f"📊 Planning download for {symbol} on {exchange}")
        click.echo(f"📅 Date range: {start_date} to {end_date}")
        click.echo(f"📁 Data types: {', '.join(data_types)}")
        
        total_files = 0
        total_size = 0
        
        # Check what's available
        for data_type in data_types:
            files = client.list_files_in_date_range(
                symbol, exchange, data_type, start_dt, end_dt
            )
            
            type_size = sum(f['size'] for f in files)
            total_files += len(files)
            total_size += type_size
            
            click.echo(f"\n{data_type}:")
            click.echo(f"  Files: {len(files)}")
            click.echo(f"  Size: {type_size / (1024**2):.1f} MB")
        
        click.echo(f"\n📈 Total: {total_files} files, {total_size / (1024**3):.2f} GB")
        
        if total_files == 0:
            click.echo("❌ No files found for the specified criteria")
            return
        
        if dry_run:
            click.echo("✅ Dry run complete")
            return
        
        # Confirm download
        if not click.confirm(f"Download {total_files} files ({total_size / (1024**3):.2f} GB)?"):
            click.echo("Download cancelled")
            return
        
        # Execute download
        downloader = DataDownloader(client, Path(staging_path) / "raw")
        
        async def run_download():
            results = downloader.download_batch(
                symbol, exchange, list(data_types), start_dt, end_dt
            )
            return results
        
        click.echo("\n🚀 Starting download...")
        results = asyncio.run(run_download())
        
        # Report results
        total_downloaded = 0
        total_failed = 0
        
        for data_type, (successful, failed) in results.items():
            total_downloaded += len(successful)
            total_failed += len(failed)
            
            click.echo(f"\n{data_type}:")
            click.echo(f"  ✅ Downloaded: {len(successful)}")
            click.echo(f"  ❌ Failed: {len(failed)}")
            
            if failed and ctx.obj.get('verbose'):
                for failure in failed[:3]:
                    click.echo(f"    - {failure['key']}: {failure['error']}")
        
        # Summary
        summary = downloader.get_download_summary()
        click.echo(f"\n📊 Download Summary:")
        click.echo(f"  Success rate: {summary['success_rate']:.1%}")
        click.echo(f"  Downloaded: {summary['mb_downloaded']:.1f} MB")
        click.echo(f"  Speed: {summary['speed_mbps']:.1f} MB/s")
        click.echo(f"  Duration: {summary['duration_seconds']:.1f} seconds")
        
        if total_downloaded > 0:
            click.echo(f"\n✅ Download complete! Files are in {staging_path}/raw")
            click.echo("💡 Next step: Run 'acquire_data validate' to validate the files")
        
    except Exception as e:
        click.echo(f"❌ Download failed: {e}")
        if ctx.obj.get('verbose'):
            import traceback
            click.echo(traceback.format_exc())
        raise click.Abort()


@cli.command()
@click.option('--staging-path', default='data/staging', help='Staging directory path')
@click.option('--data-type', help='Specific data type to validate')
@click.pass_context
def validate(ctx, staging_path, data_type):
    """Validate downloaded files and move them through staging pipeline."""
    
    try:
        staging_manager = DataStagingManager(Path(staging_path))
        validator = IntegrityValidator()
        
        # Get files to validate
        raw_files = staging_manager.get_files_by_status(staging_manager.FileStatus.RAW)
        
        if data_type:
            raw_files = [f for f in raw_files if f.data_type == data_type]
        
        if not raw_files:
            click.echo("No files found to validate")
            return
        
        click.echo(f"🔍 Validating {len(raw_files)} files...")
        
        validated = 0
        moved_to_ready = 0
        quarantined = 0
        
        for manifest in raw_files:
            click.echo(f"\nValidating: {manifest.key}")
            
            # Move to validating
            if not staging_manager.move_to_validating(manifest.key):
                click.echo(f"  ❌ Failed to move to validating")
                continue
            
            # Validate
            file_path = Path(manifest.local_path)
            result = validator.validate_file(file_path, manifest.data_type)
            
            validated += 1
            
            if result.passed:
                # Move to ready
                if staging_manager.move_to_ready(manifest.key, result):
                    click.echo(f"  ✅ Moved to ready")
                    moved_to_ready += 1
                else:
                    click.echo(f"  ❌ Failed to move to ready")
            else:
                # Move to quarantine
                error_msg = "; ".join(result.errors)
                if staging_manager.move_to_quarantine(manifest.key, result, error_msg):
                    click.echo(f"  ⚠️  Quarantined: {error_msg}")
                    quarantined += 1
                else:
                    click.echo(f"  ❌ Failed to quarantine")
            
            # Show validation details if verbose
            if ctx.obj.get('verbose') and (result.warnings or result.errors):
                for warning in result.warnings:
                    click.echo(f"    ⚠️  {warning}")
                for error in result.errors:
                    click.echo(f"    ❌ {error}")
        
        # Summary
        click.echo(f"\n📊 Validation Summary:")
        click.echo(f"  Validated: {validated}")
        click.echo(f"  ✅ Ready: {moved_to_ready}")
        click.echo(f"  ⚠️  Quarantined: {quarantined}")
        
        if moved_to_ready > 0:
            click.echo(f"\n✅ Validation complete! Files are in {staging_path}/ready")
            click.echo("💡 Next step: Run 'acquire_data status' to check overall progress")
        
    except Exception as e:
        click.echo(f"❌ Validation failed: {e}")
        if ctx.obj.get('verbose'):
            import traceback
            click.echo(traceback.format_exc())
        raise click.Abort()


@cli.command()
@click.option('--staging-path', default='data/staging', help='Staging directory path')
def status(staging_path):
    """Show staging area status and statistics."""
    
    try:
        staging_manager = DataStagingManager(Path(staging_path))
        summary = staging_manager.get_staging_summary()
        
        click.echo("📊 Staging Area Status\n")
        
        # File counts by status
        click.echo("File Status:")
        for status, count in summary['status_counts'].items():
            click.echo(f"  {status}: {count}")
        
        # Size info
        click.echo(f"\nTotal Size: {summary['total_size_mb']:.1f} MB")
        
        # Ready files by data type
        if summary['ready_by_data_type']:
            click.echo(f"\nReady Files:")
            for data_type, count in summary['ready_by_data_type'].items():
                click.echo(f"  {data_type}: {count}")
        
        # Directory paths
        click.echo(f"\nDirectories:")
        for name, path in summary['directories'].items():
            click.echo(f"  {name}: {path}")
        
    except Exception as e:
        click.echo(f"❌ Failed to get status: {e}")
        raise click.Abort()


@cli.command()
@click.option('--symbol', default='BTC-USDT', help='Trading symbol')
@click.option('--exchange', default='binance', help='Exchange name')
@click.option('--start-date', required=True, help='Start date (YYYY-MM-DD)')
@click.option('--end-date', required=True, help='End date (YYYY-MM-DD)')
@click.option('--data-types', multiple=True,
              default=['trades', 'book', 'book_delta_v2'],
              help='Required data types')
@click.option('--staging-path', default='data/staging', help='Staging directory path')
def certify(symbol, exchange, start_date, end_date, data_types, staging_path):
    """Generate data readiness certificate."""
    
    try:
        staging_manager = DataStagingManager(Path(staging_path))
        
        certificate = staging_manager.generate_readiness_certificate(
            symbol, exchange, start_date, end_date, list(data_types)
        )
        
        click.echo("📋 Data Readiness Certificate\n")
        
        click.echo(f"Symbol: {certificate['symbol']}")
        click.echo(f"Exchange: {certificate['exchange']}")
        click.echo(f"Date Range: {certificate['start_date']} to {certificate['end_date']}")
        click.echo(f"Generated: {certificate['generated_at']}")
        
        if certificate['ready']:
            click.echo(f"\n✅ STATUS: READY")
        else:
            click.echo(f"\n❌ STATUS: NOT READY")
        
        # Summary by data type
        click.echo(f"\nData Summary:")
        for data_type, info in certificate['summary'].items():
            click.echo(f"  {data_type}:")
            click.echo(f"    Files: {info['file_count']}")
            click.echo(f"    Size: {info['total_size_mb']:.1f} MB")
            if info['date_range']['start']:
                click.echo(f"    Coverage: {info['date_range']['start']} to {info['date_range']['end']}")
        
        # Issues
        if certificate['issues']:
            click.echo(f"\n⚠️  Issues ({len(certificate['issues'])}):")
            for issue in certificate['issues']:
                click.echo(f"  - {issue}")
        
        if certificate['ready']:
            click.echo(f"\n🎉 Data is ready for Epic 1 validation work!")
        else:
            click.echo(f"\n💡 Fix the issues above before proceeding to Epic 1")
        
    except Exception as e:
        click.echo(f"❌ Failed to generate certificate: {e}")
        raise click.Abort()


if __name__ == '__main__':
    cli()