#!/usr/bin/env python3
"""Count total messages across all capture files in a directory."""
import gzip
import json
import sys
from pathlib import Path


def count_messages_in_directory(directory: Path):
    """Count total messages in all jsonl.gz files in a directory."""
    total_messages = 0
    total_trade = 0
    total_depth = 0
    file_count = 0

    for file in sorted(directory.glob("*.jsonl.gz")):
        file_count += 1
        print(f"Processing {file.name}...", end=" ")
        file_messages = 0

        with gzip.open(file, "rt") as f:
            for line in f:
                msg = json.loads(line)
                total_messages += 1
                file_messages += 1

                if "@trade" in msg["stream"]:
                    total_trade += 1
                elif "@depth" in msg["stream"]:
                    total_depth += 1

        print(f"{file_messages:,} messages")

    print(f"\nTotal across {file_count} files:")
    print(f"  Total messages: {total_messages:,}")
    print(f"  Trade messages: {total_trade:,}")
    print(f"  Depth messages: {total_depth:,}")
    print(f"  Average per file: {total_messages // file_count:,}")

    return total_messages

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: count_total_messages.py <directory>")
        sys.exit(1)

    directory = Path(sys.argv[1])
    if not directory.exists():
        print(f"Directory {directory} does not exist")
        sys.exit(1)

    count_messages_in_directory(directory)
