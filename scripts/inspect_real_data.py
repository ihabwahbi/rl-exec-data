#!/usr/bin/env python3
"""Quick inspection of real Crypto Lake data to understand origin_time format."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import polars as pl

def inspect_data():
    """Inspect the real data file."""
    data_file = Path("data/staging/raw/BINANCE_BTC-USDT_trades_20250715_20250717.parquet")
    
    print(f"📁 Inspecting: {data_file}")
    
    # Read the file
    df = pl.read_parquet(data_file)
    
    print(f"\n📊 Data Shape: {df.shape}")
    print(f"📋 Columns: {df.columns}")
    print(f"\n🔍 Data Types:")
    for col, dtype in zip(df.columns, df.dtypes):
        print(f"  - {col}: {dtype}")
    
    print(f"\n📈 First 5 rows of origin_time:")
    if "origin_time" in df.columns:
        print(df.select("origin_time").head())
        
        # Check for nulls
        null_count = df.filter(pl.col("origin_time").is_null()).height
        print(f"\n❓ Null origin_time: {null_count}")
        
        # Get min/max
        if df.schema["origin_time"] in [pl.Int64, pl.Float64]:
            min_val = df.select(pl.col("origin_time").min()).item()
            max_val = df.select(pl.col("origin_time").max()).item()
            print(f"📅 Min origin_time: {min_val}")
            print(f"📅 Max origin_time: {max_val}")
            
            # Check if it's nanoseconds
            if min_val and min_val > 1e15:
                print("\n⏰ Appears to be nanosecond timestamps")
                # Convert sample to datetime
                sample_dt = pl.from_epoch(min_val, time_unit="ns")
                print(f"   Min as datetime: {sample_dt}")
    
    print("\n🔢 Sample of all columns (first 3 rows):")
    print(df.head(3))

if __name__ == "__main__":
    inspect_data()