#!/usr/bin/env python3
"""Create metadata for high volume capture."""
from pathlib import Path
from create_capture_metadata import create_metadata

if __name__ == "__main__":
    # Create metadata for high volume capture
    high_volume_dir = Path("data/golden_samples/high_volume")
    create_metadata(
        high_volume_dir,
        "high_volume",
        "US market hours (14:30-21:00 UTC) - highest trading activity period"
    )