#!/usr/bin/env python3
# validate_capture.py
import gzip
import hashlib
import json
from pathlib import Path


def validate_golden_sample(filepath: Path):
    """Comprehensive validation of captured data."""
    print(f"\n=== Validating {filepath.name} ===")

    stats = {
        "total_messages": 0,
        "trade_messages": 0,
        "depth_messages": 0,
        "out_of_order": 0,
        "gaps_detected": 0,
        "last_timestamp": 0,
        "duration_hours": 0
    }

    timestamps = []
    depth_sequences = {}

    # Open gzipped file
    with gzip.open(filepath, "rt") as f:
        for line_num, line in enumerate(f, 1):
            try:
                msg = json.loads(line)
                stats["total_messages"] += 1

                # Validate structure
                assert "capture_ns" in msg, f"Missing capture_ns at line {line_num}"
                assert "stream" in msg, f"Missing stream at line {line_num}"
                assert "data" in msg, f"Missing data at line {line_num}"

                ts = msg["capture_ns"]
                timestamps.append(ts)

                # Check ordering
                if ts < stats["last_timestamp"]:
                    stats["out_of_order"] += 1
                    print(f"WARNING: Out of order at line {line_num}")
                stats["last_timestamp"] = ts

                # Count message types
                if "@trade" in msg["stream"]:
                    stats["trade_messages"] += 1
                elif "@depth" in msg["stream"]:
                    stats["depth_messages"] += 1

                    # Check for sequence gaps in depth updates
                    symbol = msg["stream"].split("@")[0]
                    if "U" in msg["data"] and "u" in msg["data"]:  # Update ID range
                        first_update_id = msg["data"]["U"]
                        last_update_id = msg["data"]["u"]

                        if symbol in depth_sequences:
                            expected_start = depth_sequences[symbol] + 1
                            if first_update_id != expected_start:
                                stats["gaps_detected"] += 1
                                if stats["gaps_detected"] <= 10:  # Only print first 10 gaps
                                    print(f"Gap detected: expected U={expected_start}, got U={first_update_id}")
                        depth_sequences[symbol] = last_update_id

            except Exception as e:
                print(f"ERROR at line {line_num}: {e}")

    # Calculate statistics
    if timestamps:
        duration_ns = timestamps[-1] - timestamps[0]
        stats["duration_hours"] = duration_ns / (1e9 * 3600)
        stats["messages_per_second"] = stats["total_messages"] / (duration_ns / 1e9)

    # Print summary
    print("\nSummary:")
    print(f"  Total messages: {stats['total_messages']:,}")
    print(f"  Trade messages: {stats['trade_messages']:,}")
    print(f"  Depth messages: {stats['depth_messages']:,}")
    print(f"  Duration: {stats['duration_hours']:.2f} hours")
    print(f"  Rate: {stats['messages_per_second']:.2f} msg/sec")
    print(f"  Out of order: {stats['out_of_order']}")
    print(f"  Sequence gaps: {stats['gaps_detected']}")
    print(f"  Gap ratio: {stats['gaps_detected'] / stats['total_messages'] * 100:.4f}%")

    # Validate acceptance criteria
    passed = True
    if stats["out_of_order"] > 0:
        print("❌ FAIL: Messages not in chronological order")
        passed = False
    if stats["gaps_detected"] / stats["total_messages"] > 0.0001:  # 0.01%
        print("❌ FAIL: Too many sequence gaps")
        passed = False
    if stats["total_messages"] < 1_000_000:
        print("❌ FAIL: Insufficient messages for statistical validation")
        passed = False

    if passed:
        print("✅ PASS: All validation criteria met")

    return stats

# Generate metadata file
def create_metadata(capture_dir: Path, market_regime: str, event_details: str = ""):
    """Create metadata.json for the capture session."""
    files = list(capture_dir.glob("*.jsonl.gz"))

    metadata = {
        "capture_session": {
            "market_regime": market_regime,
            "event_details": event_details,
            "files": []
        }
    }

    for file in files:
        # Calculate checksum
        sha256_hash = hashlib.sha256()
        with open(file, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        # Get file stats
        stats = validate_golden_sample(file)

        metadata["capture_session"]["files"].append({
            "filename": file.name,
            "size_bytes": file.stat().st_size,
            "sha256": sha256_hash.hexdigest(),
            "statistics": stats
        })

    # Write metadata
    with open(capture_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nMetadata written to {capture_dir / 'metadata.json'}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: validate_capture.py <capture_file.jsonl.gz>")
        sys.exit(1)

    validate_golden_sample(Path(sys.argv[1]))
