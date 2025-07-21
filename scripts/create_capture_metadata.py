#!/usr/bin/env python3
"""Create metadata.json for a capture session."""
import json
import subprocess
import sys
from pathlib import Path


def create_metadata(capture_dir: Path, market_regime: str, event_details: str = ""):
    """Create metadata.json for the capture session."""
    print(f"Creating metadata for {capture_dir}...")

    # Run validation to get statistics
    result = subprocess.run(
        [sys.executable, "scripts/validate_capture_session.py", str(capture_dir)],
        check=False, capture_output=True,
        text=True
    )

    # Parse validation output
    lines = result.stdout.split("\n")
    stats = {}
    for line in lines:
        if "Total messages:" in line:
            stats["total_messages"] = int(line.split(":")[1].strip().replace(",", ""))
        elif "Trade messages:" in line:
            stats["trade_messages"] = int(line.split(":")[1].strip().replace(",", ""))
        elif "Depth messages:" in line:
            stats["depth_messages"] = int(line.split(":")[1].strip().replace(",", ""))
        elif "Duration:" in line and "hours" in line:
            stats["duration_hours"] = float(line.split(":")[1].strip().split()[0])
        elif "Rate:" in line and "msg/sec" in line:
            stats["messages_per_second"] = float(line.split(":")[1].strip().split()[0])
        elif "Sequence gaps:" in line and "Session Summary" in result.stdout[:result.stdout.find(line)]:
            stats["sequence_gaps"] = int(line.split(":")[1].strip())
        elif "Gap ratio:" in line:
            stats["gap_ratio_percent"] = float(line.split(":")[1].strip().rstrip("%"))

    # Get capture start and end times from filenames
    files = sorted(capture_dir.glob("*.jsonl.gz"))
    if files:
        # Extract timestamp from first file
        first_file = files[0].name
        # Format: btcusdt_capture_1753018402_20250721_003329.jsonl.gz
        timestamp_parts = first_file.split("_")[3:5]
        start_date = timestamp_parts[0]
        start_time = timestamp_parts[1].split(".")[0]
        start_datetime = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}T{start_time[:2]}:{start_time[2:4]}:{start_time[4:6]}"

        # Calculate end time based on duration
        from datetime import datetime, timedelta
        start_dt = datetime.strptime(start_datetime, "%Y-%m-%dT%H:%M:%S")
        end_dt = start_dt + timedelta(hours=stats.get("duration_hours", 0))
        end_datetime = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
    else:
        start_datetime = "unknown"
        end_datetime = "unknown"

    # Read checksums if available
    checksums = {}
    checksum_file = capture_dir / "checksums.txt"
    if checksum_file.exists():
        with open(checksum_file) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 2:
                    checksums[parts[1]] = parts[0]

    # Create metadata structure
    metadata = {
        "capture_session": {
            "market_regime": market_regime,
            "event_details": event_details,
            "capture_start": start_datetime,
            "capture_end": end_datetime,
            "duration_hours": stats.get("duration_hours", 0),
            "statistics": {
                "total_messages": stats.get("total_messages", 0),
                "trade_messages": stats.get("trade_messages", 0),
                "depth_messages": stats.get("depth_messages", 0),
                "messages_per_second": stats.get("messages_per_second", 0),
                "sequence_gaps": stats.get("sequence_gaps", 0),
                "gap_ratio_percent": stats.get("gap_ratio_percent", 0),
                "file_count": len(files),
                "total_size_mb": sum(f.stat().st_size for f in files) / (1024 * 1024)
            },
            "validation_status": "PASSED" if "ALL VALIDATION CRITERIA MET" in result.stdout else "FAILED",
            "files": []
        }
    }

    # Add file information
    for file in files:
        file_info = {
            "filename": file.name,
            "size_bytes": file.stat().st_size,
            "size_mb": file.stat().st_size / (1024 * 1024),
            "sha256": checksums.get(file.name, "not calculated")
        }
        metadata["capture_session"]["files"].append(file_info)

    # Add system information
    metadata["system_info"] = {
        "capture_script": "scripts/capture_live_data.py",
        "validation_script": "scripts/validate_capture_session.py",
        "metadata_created": datetime.now().isoformat(),
        "symbol": "BTCUSDT",
        "exchange": "Binance",
        "streams": ["btcusdt@trade", "btcusdt@depth@100ms"]
    }

    # Write metadata
    output_file = capture_dir / "metadata.json"
    with open(output_file, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"Metadata written to {output_file}")
    print(f"  Total messages: {stats.get('total_messages', 0):,}")
    print(f"  Duration: {stats.get('duration_hours', 0):.2f} hours")
    print(f"  Validation: {metadata['capture_session']['validation_status']}")

    return metadata

if __name__ == "__main__":
    # Create metadata for low volume capture
    low_volume_dir = Path("data/golden_samples/low_volume")
    create_metadata(
        low_volume_dir,
        "low_volume",
        "Asian overnight session (02:00-06:00 UTC typical low volume period)"
    )

    # Create metadata for special event capture
    special_event_dir = Path("data/golden_samples/special_event")
    create_metadata(
        special_event_dir,
        "special_event",
        "Weekend trading period - lower volume than weekday sessions"
    )
