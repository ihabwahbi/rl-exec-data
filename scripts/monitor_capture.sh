#!/bin/bash
# monitor_capture.sh

while true; do
    clear
    echo "=== Capture Monitor - $(date) ==="
    
    # Check process
    if pgrep -f capture_live_data > /dev/null; then
        echo "✓ Capture process running"
        PID=$(pgrep -f capture_live_data)
        echo "  PID: $PID"
        echo "  CPU: $(ps -p $PID -o %cpu | tail -1)%"
        echo "  MEM: $(ps -p $PID -o %mem | tail -1)%"
    else
        echo "✗ Capture process NOT running!"
    fi
    
    # Check file growth
    echo -e "\nOutput files:"
    ls -lh data/golden_samples/*/*.jsonl.gz 2>/dev/null | tail -5
    
    # Check disk usage
    echo -e "\nDisk usage:"
    df -h /home/iwahbi/projects/rl-exec-data/data
    
    # Check recent logs
    echo -e "\nRecent logs:"
    tail -5 capture.log 2>/dev/null || echo "No log file found"
    
    sleep 300  # Update every 5 minutes
done