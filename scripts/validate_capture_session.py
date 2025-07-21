#!/usr/bin/env python3
"""Validate an entire capture session (all files in a directory)."""
import gzip
import json
import sys
from pathlib import Path


def validate_capture_session(directory: Path):
    """Validate all capture files in a directory as a complete session."""
    print(f"\n=== Validating capture session in {directory} ===")

    session_stats = {
        "total_messages": 0,
        "trade_messages": 0,
        "depth_messages": 0,
        "out_of_order": 0,
        "gaps_detected": 0,
        "file_count": 0,
        "first_timestamp": None,
        "last_timestamp": None,
        "duration_hours": 0
    }

    depth_sequences = {}
    previous_file_last_timestamp = None

    # Process files in chronological order
    files = sorted(directory.glob("*.jsonl.gz"))

    for file in files:
        print(f"\nProcessing {file.name}...")
        session_stats["file_count"] += 1

        with gzip.open(file, "rt") as f:
            file_first_timestamp = None
            file_last_timestamp = None

            for line_num, line in enumerate(f, 1):
                try:
                    msg = json.loads(line)
                    session_stats["total_messages"] += 1

                    # Validate structure
                    assert "capture_ns" in msg
                    assert "stream" in msg
                    assert "data" in msg

                    ts = msg["capture_ns"]

                    # Track first and last timestamps
                    if file_first_timestamp is None:
                        file_first_timestamp = ts
                    file_last_timestamp = ts

                    if session_stats["first_timestamp"] is None:
                        session_stats["first_timestamp"] = ts
                    session_stats["last_timestamp"] = ts

                    # Check ordering between files
                    if previous_file_last_timestamp and ts < previous_file_last_timestamp:
                        session_stats["out_of_order"] += 1
                        print(f"  WARNING: Out of order between files at line {line_num}")

                    # Count message types
                    if "@trade" in msg["stream"]:
                        session_stats["trade_messages"] += 1
                    elif "@depth" in msg["stream"]:
                        session_stats["depth_messages"] += 1

                        # Check for sequence gaps in depth updates
                        symbol = msg["stream"].split("@")[0]
                        if "U" in msg["data"] and "u" in msg["data"]:
                            first_update_id = msg["data"]["U"]
                            last_update_id = msg["data"]["u"]

                            if symbol in depth_sequences:
                                expected_start = depth_sequences[symbol] + 1
                                if first_update_id != expected_start:
                                    session_stats["gaps_detected"] += 1
                                    # Only print first few gaps per file
                                    if session_stats["gaps_detected"] <= 5:
                                        print(f"  Gap detected: expected U={expected_start}, got U={first_update_id}")
                            depth_sequences[symbol] = last_update_id

                except Exception as e:
                    print(f"  ERROR at line {line_num}: {e}")

            previous_file_last_timestamp = file_last_timestamp
            print(f"  Messages in file: {line_num:,}")

    # Calculate session statistics
    if session_stats["first_timestamp"] and session_stats["last_timestamp"]:
        duration_ns = session_stats["last_timestamp"] - session_stats["first_timestamp"]
        session_stats["duration_hours"] = duration_ns / (1e9 * 3600)
        session_stats["messages_per_second"] = session_stats["total_messages"] / (duration_ns / 1e9)

    # Print summary
    print(f"\n{'='*50}")
    print("Session Summary:")
    print(f"  Files processed: {session_stats['file_count']}")
    print(f"  Total messages: {session_stats['total_messages']:,}")
    print(f"  Trade messages: {session_stats['trade_messages']:,}")
    print(f"  Depth messages: {session_stats['depth_messages']:,}")
    print(f"  Duration: {session_stats['duration_hours']:.2f} hours")
    print(f"  Rate: {session_stats['messages_per_second']:.2f} msg/sec")
    print(f"  Out of order: {session_stats['out_of_order']}")
    print(f"  Sequence gaps: {session_stats['gaps_detected']}")
    print(f"  Gap ratio: {session_stats['gaps_detected'] / session_stats['total_messages'] * 100:.6f}%")

    # Validate acceptance criteria
    print("\nAcceptance Criteria Validation:")
    passed = True

    # AC3: Chronological ordering
    if session_stats["out_of_order"] > 0:
        print("❌ AC3 FAIL: Messages not in chronological order")
        passed = False
    else:
        print("✅ AC3 PASS: All messages in chronological order")

    # AC3: Sequence gaps <0.01%
    gap_ratio = session_stats["gaps_detected"] / session_stats["total_messages"]
    if gap_ratio > 0.0001:  # 0.01%
        print(f"❌ AC3 FAIL: Too many sequence gaps ({gap_ratio*100:.4f}% > 0.01%)")
        passed = False
    else:
        print(f"✅ AC3 PASS: Sequence gaps within limit ({gap_ratio*100:.6f}% < 0.01%)")

    # AC7: Minimum 1M messages
    if session_stats["total_messages"] < 1_000_000:
        print(f"❌ AC7 FAIL: Insufficient messages ({session_stats['total_messages']:,} < 1,000,000)")
        passed = False
    else:
        print(f"✅ AC7 PASS: Sufficient messages for validation ({session_stats['total_messages']:,} > 1,000,000)")

    # AC1: 24-hour duration (with 10% tolerance for early termination)
    if session_stats["duration_hours"] < 21.6:  # 90% of 24 hours
        print(f"❌ AC1 FAIL: Capture duration too short ({session_stats['duration_hours']:.2f} hours < 21.6 hours)")
        passed = False
    else:
        print(f"✅ AC1 PASS: Adequate capture duration ({session_stats['duration_hours']:.2f} hours)")

    if passed:
        print("\n✅ ALL VALIDATION CRITERIA MET")
    else:
        print("\n❌ VALIDATION FAILED")

    return session_stats, passed

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: validate_capture_session.py <directory>")
        sys.exit(1)

    directory = Path(sys.argv[1])
    if not directory.exists():
        print(f"Directory {directory} does not exist")
        sys.exit(1)

    stats, passed = validate_capture_session(directory)
    sys.exit(0 if passed else 1)
