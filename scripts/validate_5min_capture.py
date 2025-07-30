#!/usr/bin/env python3
"""Validate 5-minute captures for story 1.2.1 re-execution."""
import gzip
import json
from pathlib import Path
import sys


def validate_5min_capture(filepath: Path):
    """Validate a 5-minute capture file."""
    print(f"\n=== Validating {filepath.name} ===")
    
    stats = {
        'total_messages': 0,
        'trade_messages': 0,
        'depth_messages': 0,
        'out_of_order': 0,
        'gaps_detected': 0,
        'last_timestamp': 0,
        'first_timestamp': None
    }
    
    depth_sequences = {}
    
    with gzip.open(filepath, 'rt') as f:
        for line_num, line in enumerate(f, 1):
            try:
                msg = json.loads(line)
                stats['total_messages'] += 1
                
                # Validate structure
                assert 'capture_ns' in msg, f"Missing capture_ns at line {line_num}"
                assert 'stream' in msg, f"Missing stream at line {line_num}"
                assert 'data' in msg, f"Missing data at line {line_num}"
                
                ts = msg['capture_ns']
                if stats['first_timestamp'] is None:
                    stats['first_timestamp'] = ts
                
                # Check ordering
                if ts < stats['last_timestamp']:
                    stats['out_of_order'] += 1
                    print(f"WARNING: Out of order at line {line_num}")
                stats['last_timestamp'] = ts
                
                # Count message types
                if '@trade' in msg['stream']:
                    stats['trade_messages'] += 1
                elif '@depth' in msg['stream']:
                    stats['depth_messages'] += 1
                    
                    # Check for sequence gaps
                    if 'U' in msg['data'] and 'u' in msg['data']:
                        symbol = msg['stream'].split('@')[0]
                        first_update_id = msg['data']['U']
                        last_update_id = msg['data']['u']
                        
                        if symbol in depth_sequences:
                            expected_start = depth_sequences[symbol] + 1
                            if first_update_id != expected_start:
                                stats['gaps_detected'] += 1
                                if stats['gaps_detected'] <= 5:  # Only print first 5
                                    print(f"Gap: expected U={expected_start}, got U={first_update_id}")
                        depth_sequences[symbol] = last_update_id
                        
            except Exception as e:
                print(f"ERROR at line {line_num}: {e}")
    
    # Calculate duration
    duration_ns = stats['last_timestamp'] - stats['first_timestamp']
    duration_min = duration_ns / (1e9 * 60)
    rate = stats['total_messages'] / (duration_ns / 1e9) if duration_ns > 0 else 0
    
    # Print summary
    print(f"\nSummary:")
    print(f"  Total messages: {stats['total_messages']:,}")
    print(f"  Trade messages: {stats['trade_messages']:,}")
    print(f"  Depth messages: {stats['depth_messages']:,}")
    print(f"  Duration: {duration_min:.1f} minutes")
    print(f"  Rate: {rate:.1f} msg/sec")
    print(f"  Out of order: {stats['out_of_order']}")
    print(f"  Sequence gaps: {stats['gaps_detected']}")
    
    # Validation for 5-minute captures
    if stats['out_of_order'] > 0:
        print("❌ FAIL: Messages not in chronological order")
    elif stats['gaps_detected'] > stats['total_messages'] * 0.001:  # 0.1%
        print("❌ FAIL: Too many sequence gaps")
    elif stats['total_messages'] < 1000:  # Minimum for 5-min
        print("❌ FAIL: Too few messages")
    else:
        print("✅ PASS: Capture validated successfully")
    
    return stats


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: validate_5min_capture.py <capture_file.jsonl.gz>")
        sys.exit(1)
    
    validate_5min_capture(Path(sys.argv[1]))