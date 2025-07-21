#!/usr/bin/env python3
"""CLI interface for Crypto Lake data acquisition using lakeapi."""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import click
from loguru import logger

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rlx_datapipe.acquisition.crypto_lake_api_client import CryptoLakeAPIClient
from rlx_datapipe.acquisition.integrity_validator import IntegrityValidator
from rlx_datapipe.acquisition.lakeapi_downloader import LakeAPIDownloader
from rlx_datapipe.acquisition.staging_manager import DataStagingManager


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx, verbose):
    """Crypto Lake Data Acquisition CLI (lakeapi version)
    
    This tool helps acquire historical market data from Crypto Lake using the official lakeapi package.
    
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
    ctx.obj["verbose"] = verbose


@cli.command()
@click.pass_context
def test_connection(ctx):
    """Test connection to Crypto Lake API."""
    logger.info("🔌 Testing Crypto Lake API connection...")

    try:
        # Initialize client
        client = CryptoLakeAPIClient()

        # Test connection
        success = client.test_connection()

        if success:
            logger.info("✅ Connection successful!")

            # Show available data sample
            logger.info("📊 Checking data availability...")
            availability = client.list_available_data()

            click.echo("\n" + "="*60)
            click.echo("📊 DATA AVAILABILITY SAMPLE")
            click.echo("="*60)
            click.echo(f"Symbol: {availability['symbol']}")
            click.echo(f"Exchange: {availability['exchange']}")
            click.echo(f"Date Range Tested: {availability['tested_date_range']['start']} to {availability['tested_date_range']['end']}")
            click.echo()

            for data_type, info in availability["availability"].items():
                status = "✅ Available" if info["available"] else "❌ Not Available"
                click.echo(f"{data_type:15} | {status}")
                if info["available"]:
                    click.echo(f"                | Sample rows: {info['sample_rows']:,}")
                    if info.get("columns"):
                        click.echo(f"                | Columns: {len(info['columns'])} ({', '.join(info['columns'][:3])}...)")
                else:
                    click.echo(f"                | Error: {info.get('error', 'Unknown')}")
                click.echo()

            return True

        logger.error("❌ Connection failed!")
        return False

    except Exception as e:
        logger.error(f"❌ Connection test failed: {e}")
        return False


@cli.command()
@click.option("--symbol", default="BTC-USDT", help="Trading symbol (default: BTC-USDT)")
@click.option("--exchange", default="BINANCE", help="Exchange name (default: BINANCE)")
@click.option("--data-type", type=click.Choice(["trades", "book", "book_delta_v2"]), help="Specific data type")
@click.pass_context
def list_inventory(ctx, symbol, exchange, data_type):
    """List available data in Crypto Lake."""
    logger.info(f"📋 Listing available data for {symbol} on {exchange}")

    try:
        client = CryptoLakeAPIClient()

        # Get data availability
        availability = client.list_available_data(symbol=symbol, exchange=exchange)

        click.echo("\n" + "="*60)
        click.echo("📋 CRYPTO LAKE DATA INVENTORY")
        click.echo("="*60)
        click.echo(f"Symbol: {availability['symbol']}")
        click.echo(f"Exchange: {availability['exchange']}")
        click.echo(f"Date Range Tested: {availability['tested_date_range']['start']} to {availability['tested_date_range']['end']}")
        click.echo()

        data_types_to_show = [data_type] if data_type else ["trades", "book", "book_delta_v2"]

        for dt in data_types_to_show:
            if dt in availability["availability"]:
                info = availability["availability"][dt]
                status = "✅ Available" if info["available"] else "❌ Not Available"

                click.echo(f"Data Type: {dt}")
                click.echo(f"Status: {status}")

                if info["available"]:
                    click.echo(f"Sample Rows: {info['sample_rows']:,}")
                    if info.get("columns"):
                        click.echo(f"Columns ({len(info['columns'])}): {', '.join(info['columns'][:5])}...")
                        if len(info["columns"]) > 5:
                            click.echo(f"  ... and {len(info['columns']) - 5} more")
                else:
                    click.echo(f"Error: {info.get('error', 'Unknown')}")

                click.echo("-" * 40)
                click.echo()

    except Exception as e:
        logger.error(f"❌ Failed to list inventory: {e}")


@cli.command()
@click.option("--symbol", default="BTC-USDT", help="Trading symbol (default: BTC-USDT)")
@click.option("--exchange", default="BINANCE", help="Exchange name (default: BINANCE)")
@click.option("--data-types", multiple=True, help="Data types to download (can specify multiple)")
@click.option("--start-date", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end-date", required=True, help="End date (YYYY-MM-DD)")
@click.option("--dry-run", is_flag=True, help="Show what would be downloaded without downloading")
@click.option("--staging-path", default="data/staging/raw", help="Staging directory")
@click.option("--chunk-days", default=7, help="Days per download chunk")
@click.pass_context
def download(ctx, symbol, exchange, data_types, start_date, end_date, dry_run, staging_path, chunk_days):
    """Download historical data from Crypto Lake."""

    # Parse dates
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as e:
        logger.error(f"❌ Invalid date format: {e}")
        return

    # Default data types
    if not data_types:
        data_types = ["trades", "book", "book_delta_v2"]

    logger.info(f"📥 {'DRY RUN: ' if dry_run else ''}Downloading {symbol} from {exchange}")
    logger.info(f"Date range: {start_date} to {end_date}")
    logger.info(f"Data types: {', '.join(data_types)}")
    logger.info(f"Staging path: {staging_path}")

    try:
        # Initialize components
        client = CryptoLakeAPIClient()
        downloader = LakeAPIDownloader(
            crypto_lake_client=client,
            staging_path=Path(staging_path),
            max_concurrent=2  # Conservative for lakeapi
        )

        # Generate download tasks
        tasks = downloader.generate_download_tasks(
            symbol=symbol,
            exchange=exchange,
            data_types=list(data_types),
            start_date=start_dt,
            end_date=end_dt,
            chunk_days=chunk_days
        )

        if not tasks:
            logger.warning("⚠️ No download tasks generated")
            return

        # Execute download
        async def run_download():
            return await downloader.download_batch(tasks, dry_run=dry_run)

        summary = asyncio.run(run_download())

        # Show results
        click.echo("\n" + "="*60)
        click.echo(f"📥 DOWNLOAD {'ESTIMATE' if dry_run else 'SUMMARY'}")
        click.echo("="*60)

        if dry_run:
            click.echo(f"Total Tasks: {summary['total_tasks']}")
            click.echo(f"Estimated Data: {summary['estimated_size_mb']:.1f} MB")
            click.echo(f"Estimated Rows: {summary['estimated_rows']:,}")
            click.echo(f"Estimated Time: {summary['estimated_duration_minutes']:.1f} minutes")
            click.echo(f"Output Directory: {staging_path}")
        else:
            click.echo(f"Total Tasks: {summary['total_tasks']}")
            click.echo(f"Completed: {summary['completed']}")
            click.echo(f"Failed: {summary['failed']}")
            click.echo(f"Success Rate: {100 * summary['completed'] / summary['total_tasks']:.1f}%")
            click.echo(f"Total Data: {summary['total_size_mb']:.1f} MB")
            click.echo(f"Total Rows: {summary['total_rows']:,}")
            click.echo(f"Duration: {summary['duration_seconds']:.1f} seconds")
            click.echo(f"Average Speed: {summary['avg_speed_mbps']:.1f} MB/s")

            # Save manifest
            manifest_path = Path(staging_path).parent / "download_manifest.json"
            manifest = downloader.get_download_manifest(tasks)
            manifest["summary"] = summary

            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)

            click.echo(f"Manifest saved: {manifest_path}")

    except Exception as e:
        logger.error(f"❌ Download failed: {e}")


@cli.command()
@click.option("--staging-path", default="data/staging", help="Staging directory")
@click.option("--data-type", help="Specific data type to validate")
@click.pass_context
def validate(ctx, staging_path, data_type):
    """Validate downloaded files and move through staging pipeline."""
    logger.info("🔍 Validating downloaded data...")

    try:
        # Initialize components
        staging_manager = DataStagingManager(staging_root=Path(staging_path))
        validator = IntegrityValidator()

        # Find files to validate
        raw_files = list((Path(staging_path) / "raw").glob("*.parquet"))

        if data_type:
            raw_files = [f for f in raw_files if data_type in f.name]

        if not raw_files:
            logger.warning("⚠️ No files found to validate")
            return

        logger.info(f"Found {len(raw_files)} files to validate")

        # Validate each file
        for file_path in raw_files:
            logger.info(f"Validating {file_path.name}...")

            # Move to validating
            validating_path = staging_manager.move_to_validating(file_path)

            # Determine data type from filename
            if "trades" in file_path.name:
                file_data_type = "trades"
            elif "book_delta" in file_path.name:
                file_data_type = "book_delta_v2"
            elif "book" in file_path.name:
                file_data_type = "book"
            else:
                logger.warning(f"⚠️ Could not determine data type for {file_path.name}")
                continue

            # Validate
            is_valid, errors = validator.validate_file(validating_path, file_data_type)

            if is_valid:
                # Move to ready
                ready_path = staging_manager.move_to_ready(validating_path, file_data_type)
                logger.info(f"✅ {file_path.name} → ready")
            else:
                # Move to quarantine
                quarantine_path = staging_manager.move_to_quarantine(validating_path, errors)
                logger.error(f"❌ {file_path.name} → quarantine: {errors}")

        # Show status
        status = staging_manager.get_status()

        click.echo("\n" + "="*60)
        click.echo("🔍 VALIDATION SUMMARY")
        click.echo("="*60)
        click.echo(f"Ready files: {status['ready_count']}")
        click.echo(f"Quarantined files: {status['quarantine_count']}")
        click.echo(f"Total validated data: {status['total_size_mb']:.1f} MB")

    except Exception as e:
        logger.error(f"❌ Validation failed: {e}")


@cli.command()
@click.option("--staging-path", default="data/staging", help="Staging directory")
@click.pass_context
def status(ctx, staging_path):
    """Show staging area status and statistics."""
    logger.info("📊 Checking staging area status...")

    try:
        staging_manager = DataStagingManager(staging_root=Path(staging_path))
        status = staging_manager.get_status()

        click.echo("\n" + "="*60)
        click.echo("📊 STAGING AREA STATUS")
        click.echo("="*60)
        click.echo(f"Staging Path: {staging_path}")
        click.echo()

        click.echo("File Counts:")
        click.echo(f"  Raw: {status['raw_count']}")
        click.echo(f"  Validating: {status['validating_count']}")
        click.echo(f"  Ready: {status['ready_count']}")
        click.echo(f"  Quarantined: {status['quarantine_count']}")
        click.echo()

        click.echo(f"Total Data Size: {status['total_size_mb']:.1f} MB")
        click.echo()

        # Show ready files by data type
        if status["ready_files"]:
            click.echo("Ready Files by Data Type:")
            by_type = {}
            for file_info in status["ready_files"]:
                data_type = file_info["data_type"]
                if data_type not in by_type:
                    by_type[data_type] = []
                by_type[data_type].append(file_info)

            for data_type, files in by_type.items():
                total_size = sum(f["size_mb"] for f in files)
                click.echo(f"  {data_type}: {len(files)} files ({total_size:.1f} MB)")

        # Show quarantine summary
        if status["quarantine_count"] > 0:
            click.echo()
            click.echo("⚠️ Quarantined Files:")
            quarantine_path = Path(staging_path) / "quarantine"
            for file_path in quarantine_path.glob("*.parquet"):
                click.echo(f"  {file_path.name}")

    except Exception as e:
        logger.error(f"❌ Status check failed: {e}")


@cli.command()
@click.option("--symbol", default="BTC-USDT", help="Trading symbol")
@click.option("--exchange", default="BINANCE", help="Exchange name")
@click.option("--start-date", required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end-date", required=True, help="End date (YYYY-MM-DD)")
@click.option("--data-types", multiple=True, help="Required data types")
@click.option("--staging-path", default="data/staging", help="Staging directory")
@click.pass_context
def certify(ctx, symbol, exchange, start_date, end_date, data_types, staging_path):
    """Generate data readiness certificate for a date range."""

    # Parse dates
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as e:
        logger.error(f"❌ Invalid date format: {e}")
        return

    # Default data types
    if not data_types:
        data_types = ["trades", "book", "book_delta_v2"]

    logger.info(f"📜 Generating readiness certificate for {symbol}")
    logger.info(f"Date range: {start_date} to {end_date}")
    logger.info(f"Required data types: {', '.join(data_types)}")

    try:
        staging_manager = DataStagingManager(staging_root=Path(staging_path))

        certificate = staging_manager.generate_readiness_certificate(
            symbol=symbol,
            exchange=exchange,
            start_date=start_dt,
            end_date=end_dt,
            required_data_types=list(data_types)
        )

        # Show certificate summary
        click.echo("\n" + "="*60)
        click.echo("📜 DATA READINESS CERTIFICATE")
        click.echo("="*60)
        click.echo(f"Symbol: {certificate['symbol']}")
        click.echo(f"Exchange: {certificate['exchange']}")
        click.echo(f"Date Range: {certificate['date_range']['start']} to {certificate['date_range']['end']}")
        click.echo(f"Generated: {certificate['generated_at']}")
        click.echo()

        click.echo("Data Type Coverage:")
        for data_type, coverage in certificate["coverage"].items():
            status = "✅ Complete" if coverage["complete"] else "❌ Incomplete"
            click.echo(f"  {data_type}: {status}")
            click.echo(f"    Available: {coverage['available_days']}/{coverage['total_days']} days")
            if coverage.get("missing_dates"):
                click.echo(f"    Missing: {', '.join(coverage['missing_dates'][:5])}...")

        click.echo()
        overall_status = "✅ READY" if certificate["overall_ready"] else "❌ NOT READY"
        click.echo(f"Overall Status: {overall_status}")

        if certificate["overall_ready"]:
            click.echo()
            click.echo("🎉 All required data is available!")
            click.echo("Epic 1 work can now begin with real data.")
        else:
            click.echo()
            click.echo("⚠️ Some data is missing or incomplete.")
            click.echo("Please download missing data before proceeding.")

        # Save certificate
        cert_path = Path(staging_path) / f"readiness_certificate_{symbol}_{start_date}_{end_date}.json"
        with open(cert_path, "w") as f:
            json.dump(certificate, f, indent=2)

        click.echo(f"\nCertificate saved: {cert_path}")

    except Exception as e:
        logger.error(f"❌ Certificate generation failed: {e}")


if __name__ == "__main__":
    cli()
