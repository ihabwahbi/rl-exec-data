#!/bin/bash
# start_low_volume_capture.sh
# Start 24-hour low volume capture during Asian overnight

CAPTURE_DIR="data/golden_samples/low_volume"
LOG_FILE="$CAPTURE_DIR/capture_$(date +%Y%m%d_%H%M%S).log"

echo "=== Starting Low Volume Capture Session ==="
echo "Start time: $(date)"
echo "Output directory: $CAPTURE_DIR"
echo "Log file: $LOG_FILE"

# Create log directory
mkdir -p "$CAPTURE_DIR"

# Start capture in background with nohup
nohup .venv/bin/python scripts/capture_live_data.py \
    --symbol btcusdt \
    --duration 1440 \
    --output-dir "$CAPTURE_DIR" \
    > "$LOG_FILE" 2>&1 &

CAPTURE_PID=$!
echo "Capture process started with PID: $CAPTURE_PID"

# Save PID for monitoring
echo $CAPTURE_PID > "$CAPTURE_DIR/capture.pid"

echo ""
echo "To monitor the capture:"
echo "  - View logs: tail -f $LOG_FILE"
echo "  - Run monitor: ./scripts/monitor_capture.sh"
echo "  - Check PID: cat $CAPTURE_DIR/capture.pid"

# Show initial log output
sleep 5
echo ""
echo "Initial capture output:"
tail -20 "$LOG_FILE"