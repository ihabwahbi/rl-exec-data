#!/usr/bin/env python3
"""Simple origin_time analysis for real Crypto Lake data."""

import json
from datetime import datetime
from pathlib import Path

# Try to import necessary libraries
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    print("Warning: pandas not available, will use basic analysis")

try:
    import pyarrow.parquet as pq
    HAS_PYARROW = True
except ImportError:
    HAS_PYARROW = False
    print("Warning: pyarrow not available")


def analyze_parquet_basic(file_path):
    """Basic analysis using pyarrow."""
    print(f"\nAnalyzing file: {file_path}")

    if HAS_PYARROW:
        # Read parquet file
        table = pq.read_table(file_path)
        df = table.to_pandas() if HAS_PANDAS else None

        print(f"Total rows: {table.num_rows:,}")
        print(f"Columns: {table.column_names}")

        if df is not None and "origin_time" in df.columns:
            # Analyze origin_time
            total_rows = len(df)
            null_count = df["origin_time"].isnull().sum()
            zero_count = (df["origin_time"] == 0).sum()

            null_pct = (null_count / total_rows) * 100
            zero_pct = (zero_count / total_rows) * 100
            invalid_pct = null_pct + zero_pct

            print("\nOrigin Time Analysis:")
            print(f"- Null values: {null_count:,} ({null_pct:.2f}%)")
            print(f"- Zero values: {zero_count:,} ({zero_pct:.2f}%)")
            print(f"- Total invalid: {invalid_pct:.2f}%")

            # Check sample values
            print("\nSample origin_time values:")
            sample = df["origin_time"].dropna().head(5)
            for val in sample:
                print(f"  - {val}")

            return {
                "total_rows": total_rows,
                "null_percentage": null_pct,
                "zero_percentage": zero_pct,
                "invalid_percentage": invalid_pct
            }
    else:
        print("Cannot analyze parquet file without pyarrow")
        return None


def main():
    """Main analysis function."""
    print("=" * 80)
    print("ORIGIN_TIME ANALYSIS - REAL CRYPTO LAKE DATA")
    print("=" * 80)

    # Find data files
    data_dir = Path("data/staging/raw")
    parquet_files = list(data_dir.glob("*.parquet"))

    print(f"\nFound {len(parquet_files)} parquet files in {data_dir}")

    results = []
    for file_path in parquet_files:
        result = analyze_parquet_basic(file_path)
        if result:
            result["file"] = file_path.name
            results.append(result)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    for result in results:
        print(f"\nFile: {result['file']}")
        print(f"Invalid origin_time: {result['invalid_percentage']:.2f}%")

    # Recommendation
    if results:
        avg_invalid = sum(r["invalid_percentage"] for r in results) / len(results)

        print("\n" + "=" * 80)
        print("RECOMMENDATION")
        print("=" * 80)

        if avg_invalid < 5:
            print("✅ SUCCESS: origin_time is reliable (<5% invalid)")
            print("Strategy: Use origin_time as primary chronological key")
        elif avg_invalid < 10:
            print("⚠️ WARNING: origin_time has some issues (5-10% invalid)")
            print("Strategy: Use origin_time with fallback to other fields")
        else:
            print("❌ ERROR: origin_time is unreliable (>10% invalid)")
            print("Strategy: Must use alternative chronological ordering")

    # Save results
    output_file = Path("data/analysis/origin_time_real_data_results.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w") as f:
        json.dump({
            "analysis_date": datetime.now().isoformat(),
            "data_source": "Real Crypto Lake Data (Epic 0)",
            "results": results
        }, f, indent=2)

    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
