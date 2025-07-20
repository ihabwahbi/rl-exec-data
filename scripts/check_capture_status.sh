#!/bin/bash
# check_capture_status.sh
# Check status of all running captures

echo "=== Capture Status Check ==="
echo "Time: $(date)"
echo ""

for regime in high_volume low_volume special_event; do
    echo "--- $regime ---"
    PID_FILE="data/golden_samples/$regime/capture.pid"
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            echo "✓ Capture running (PID: $PID)"
            
            # Show process info
            ps -p $PID -o pid,etime,pcpu,pmem,cmd | tail -1
            
            # Show latest file
            LATEST_FILE=$(ls -t data/golden_samples/$regime/*.jsonl.gz 2>/dev/null | head -1)
            if [ -n "$LATEST_FILE" ]; then
                echo "  Latest file: $(basename $LATEST_FILE)"
                echo "  File size: $(ls -lh $LATEST_FILE | awk '{print $5}')"
                
                # Count messages
                MSG_COUNT=$(zcat "$LATEST_FILE" 2>/dev/null | wc -l)
                echo "  Messages: $MSG_COUNT"
            fi
        else
            echo "✗ Capture NOT running (PID $PID not found)"
        fi
    else
        echo "- No capture started"
    fi
    echo ""
done

# Show disk usage
echo "--- Disk Usage ---"
df -h /home/iwahbi/projects/rl-exec-data/data