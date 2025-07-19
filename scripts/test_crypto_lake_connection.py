#!/usr/bin/env python3
"""
Quick test script to verify Crypto Lake S3 connection using .env credentials.
This should be the first thing run to ensure data access is available.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from loguru import logger

# Configure logger
logger.remove()
logger.add(sys.stderr, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")


def test_crypto_lake_connection():
    """Test connection to Crypto Lake S3 and list available data."""
    
    # Load environment variables from .env file
    load_dotenv()
    logger.info("Loading environment variables from .env file...")
    
    # Check if credentials exist
    aws_access_key_id = os.getenv('aws_access_key_id')
    aws_secret_access_key = os.getenv('aws_secret_access_key')
    
    if not aws_access_key_id or not aws_secret_access_key:
        logger.error("AWS credentials not found in .env file!")
        logger.error("Please ensure your .env file contains:")
        logger.error("  aws_access_key_id=your_key_here")
        logger.error("  aws_secret_access_key=your_secret_here")
        return False
    
    # Set AWS credentials for boto3
    os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key_id
    os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_access_key
    logger.info("AWS credentials loaded from .env file for lakeapi.")
    
    try:
        # Create S3 client
        s3_client = boto3.client('s3', region_name='us-east-1')
        logger.info("S3 client created successfully")
        
        # List accessible buckets
        logger.info("Listing accessible S3 buckets...")
        response = s3_client.list_buckets()
        buckets = response.get('Buckets', [])
        
        if not buckets:
            logger.error("No accessible buckets found with provided credentials")
            return False
        
        logger.info(f"Found {len(buckets)} accessible bucket(s):")
        crypto_lake_bucket = None
        
        for bucket in buckets:
            bucket_name = bucket['Name']
            logger.info(f"  - {bucket_name}")
            
            # Try to identify Crypto Lake bucket
            if 'crypto' in bucket_name.lower() or 'lake' in bucket_name.lower():
                crypto_lake_bucket = bucket_name
        
        if not crypto_lake_bucket and buckets:
            # Use first bucket if no obvious match
            crypto_lake_bucket = buckets[0]['Name']
            logger.warning(f"No obvious Crypto Lake bucket found, using: {crypto_lake_bucket}")
        
        if crypto_lake_bucket:
            logger.info(f"\nTesting access to bucket: {crypto_lake_bucket}")
            
            # Try to list some objects
            try:
                # Look for BTC-USDT data
                test_prefixes = [
                    'binance/BTC-USDT/',
                    'binance/btc-usdt/',
                    'BTC-USDT/',
                    'btc-usdt/',
                    'data/binance/BTC-USDT/',
                    ''  # List root if other patterns fail
                ]
                
                found_data = False
                for prefix in test_prefixes:
                    logger.info(f"Checking prefix: {prefix or '(root)'}")
                    
                    response = s3_client.list_objects_v2(
                        Bucket=crypto_lake_bucket,
                        Prefix=prefix,
                        MaxKeys=10
                    )
                    
                    if 'Contents' in response:
                        logger.info(f"✅ Found data with prefix: {prefix or '(root)'}")
                        logger.info(f"Sample files:")
                        
                        for obj in response['Contents'][:5]:
                            size_mb = obj['Size'] / (1024 * 1024)
                            logger.info(f"  - {obj['Key']} ({size_mb:.2f} MB)")
                        
                        found_data = True
                        break
                
                if not found_data:
                    logger.warning("Could not find BTC-USDT data in common locations")
                    logger.info("You may need to explore the bucket structure manually")
                
                # Test: Can we download?
                logger.info("\nTesting download capability...")
                if found_data and response.get('Contents'):
                    test_key = response['Contents'][0]['Key']
                    test_file = '/tmp/crypto_lake_test.parquet'
                    
                    try:
                        s3_client.download_file(crypto_lake_bucket, test_key, test_file)
                        file_size = os.path.getsize(test_file) / (1024 * 1024)
                        logger.info(f"✅ Successfully downloaded test file ({file_size:.2f} MB)")
                        os.remove(test_file)
                        
                        return True
                        
                    except Exception as e:
                        logger.error(f"Download test failed: {e}")
                        return False
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == 'AccessDenied':
                    logger.error(f"Access denied to bucket: {crypto_lake_bucket}")
                else:
                    logger.error(f"Error accessing bucket: {e}")
                return False
        
    except NoCredentialsError:
        logger.error("No AWS credentials found. Check your .env file.")
        return False
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'InvalidAccessKeyId':
            logger.error("Invalid AWS Access Key ID")
        elif error_code == 'SignatureDoesNotMatch':
            logger.error("Invalid AWS Secret Access Key")
        else:
            logger.error(f"AWS Client Error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False
    
    return True


def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("Crypto Lake S3 Connection Test")
    logger.info("=" * 60)
    
    success = test_crypto_lake_connection()
    
    logger.info("=" * 60)
    if success:
        logger.info("✅ Connection test PASSED!")
        logger.info("Next steps:")
        logger.info("1. Review the bucket structure above")
        logger.info("2. Update data paths in the acquisition pipeline")
        logger.info("3. Start downloading historical data")
    else:
        logger.error("❌ Connection test FAILED!")
        logger.error("Please check:")
        logger.error("1. Your .env file has correct credentials")
        logger.error("2. Your Crypto Lake subscription is active")
        logger.error("3. You have access to the required data")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())