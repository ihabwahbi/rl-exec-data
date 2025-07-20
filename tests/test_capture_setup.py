"""Tests for capture setup and validation."""
import subprocess
import json
import gzip
from pathlib import Path
import pytest


def test_websocket_url_includes_100ms():
    """Verify WebSocket URL includes @depth@100ms suffix."""
    with open("src/rlx_datapipe/capture/main.py", "r") as f:
        content = f.read()
        assert "@depth@100ms" in content, "WebSocket URL missing @100ms suffix"


def test_output_directories_exist():
    """Verify golden sample directories are created."""
    dirs = [
        "data/golden_samples/high_volume",
        "data/golden_samples/low_volume", 
        "data/golden_samples/special_event"
    ]
    for dir_path in dirs:
        assert Path(dir_path).exists(), f"Directory {dir_path} not created"


def test_scripts_are_executable():
    """Verify all scripts have executable permissions."""
    scripts = [
        "scripts/pre_capture_validation.sh",
        "scripts/monitor_capture.sh",
        "scripts/validate_capture.py"
    ]
    for script in scripts:
        path = Path(script)
        assert path.exists(), f"Script {script} not found"
        assert path.stat().st_mode & 0o111, f"Script {script} not executable"


def test_capture_output_format():
    """Verify captured data has correct format."""
    # Check test capture file from validation
    test_files = list(Path("/tmp/test_capture").glob("*.jsonl.gz"))
    if test_files:
        with gzip.open(test_files[0], 'rt') as f:
            line = f.readline()
            msg = json.loads(line)
            
            # Verify message structure
            assert 'capture_ns' in msg, "Missing capture_ns field"
            assert 'stream' in msg, "Missing stream field"
            assert 'data' in msg, "Missing data field"
            assert isinstance(msg['capture_ns'], int), "capture_ns should be integer"
            assert isinstance(msg['data'], dict), "data should be dict"


def test_disk_space_available():
    """Verify sufficient disk space for captures."""
    result = subprocess.run(
        ["df", "-BG", "/home/iwahbi/projects/rl-exec-data/data"],
        capture_output=True,
        text=True
    )
    lines = result.stdout.strip().split('\n')
    if len(lines) >= 2:
        available = int(lines[1].split()[3].rstrip('G'))
        assert available > 50, f"Insufficient disk space: {available}GB (need >50GB)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])