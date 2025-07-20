#!/bin/bash
# start_special_event_capture.sh
# Start 24-hour special event capture (e.g., options expiry)

CAPTURE_DIR="data/golden_samples/special_event"
LOG_FILE="$CAPTURE_DIR/capture_$(date +%Y%m%d_%H%M%S).log"

echo "=== Starting Special Event Capture Session ==="
echo "Start time: $(date)"
echo "Output directory: $CAPTURE_DIR"
echo "Log file: $LOG_FILE"
echo ""
echo "Event type: ${1:-'Not specified'}"
echo "Event details: ${2:-'Not specified'}"

# Create log directory
mkdir -p "$CAPTURE_DIR"

# Record event details
echo "{" > "$CAPTURE_DIR/event_info.json"
echo "  \"event_type\": \"${1:-'Not specified'}\"," >> "$CAPTURE_DIR/event_info.json"
echo "  \"event_details\": \"${2:-'Not specified'}\"," >> "$CAPTURE_DIR/event_info.json"
echo "  \"start_time\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"" >> "$CAPTURE_DIR/event_info.json"
echo "}" >> "$CAPTURE_DIR/event_info.json"

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