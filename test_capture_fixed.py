#!/usr/bin/env python3
"""Test the fixed capture script."""

import subprocess
import time
import json
from pathlib import Path
import signal
import os

def test_capture():
    """Test capture for 1 minute."""
    
    # Create output directory
    output_dir = Path("data/test_capture")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("Starting capture test for 1 minute...")
    
    # Start capture process
    cmd = [
        ".venv/bin/python", 
        "scripts/capture_live_data.py",
        "--symbol", "btcusdt",
        "--duration", "1",  # 1 minute
        "--output-dir", str(output_dir)
    ]
    
    process = subprocess.Popen(cmd)
    
    # Wait for capture to complete
    try:
        process.wait(timeout=90)  # 1.5 minutes timeout
    except subprocess.TimeoutExpired:
        print("Process timeout, terminating...")
        process.terminate()
    
    # Check output files
    print("\nChecking output files...")
    jsonl_files = list(output_dir.glob("*.jsonl"))
    
    if not jsonl_files:
        print("ERROR: No output files found!")
        return
    
    for file in jsonl_files:
        print(f"\nFile: {file}")
        print(f"Size: {file.stat().st_size} bytes")
        
        # Count lines
        with open(file) as f:
            line_count = sum(1 for _ in f)
        print(f"Lines: {line_count}")
        
        # Show first few messages
        if line_count > 0:
            print("\nFirst 3 messages:")
            with open(file) as f:
                for i, line in enumerate(f):
                    if i >= 3:
                        break
                    msg = json.loads(line)
                    print(f"{i+1}. Stream: {msg['stream']} - capture_ns: {msg['capture_ns']}")

if __name__ == "__main__":
    test_capture()