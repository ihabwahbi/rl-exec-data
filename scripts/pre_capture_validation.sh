#!/bin/bash
# pre_capture_validation.sh

echo "=== Pre-Capture Validation ==="

# 1. Test WebSocket URL includes @100ms
echo -n "Testing WebSocket URL format... "
if grep -q '@depth@100ms' src/rlx_datapipe/capture/main.py; then
    echo "PASS"
else
    echo "FAIL - Missing @100ms suffix"
    exit 1
fi

# 2. Test 1-minute capture
echo "Running 1-minute test capture..."
.venv/bin/python scripts/capture_live_data.py --symbol btcusdt --duration 1 --output-dir /tmp/test_capture
if [ $? -eq 0 ]; then
    echo "Capture script executed successfully"
else
    echo "FAIL - Capture script error"
    exit 1
fi

# 3. Verify output format
echo -n "Verifying output format... "
TEST_FILE=$(ls /tmp/test_capture/*.jsonl.gz 2>/dev/null | head -1)
if [ -z "$TEST_FILE" ]; then
    echo "FAIL - No output file found"
    exit 1
fi

# Check message format
SAMPLE=$(zcat "$TEST_FILE" | head -1)
if echo "$SAMPLE" | jq -e '.capture_ns and .stream and .data' > /dev/null; then
    echo "PASS"
else
    echo "FAIL - Invalid message format"
    exit 1
fi

# 4. Check disk space
echo -n "Checking disk space... "
AVAILABLE=$(df -BG /home/iwahbi/projects/rl-exec-data/data | tail -1 | awk '{print $4}' | sed 's/G//')
if [ "$AVAILABLE" -gt 50 ]; then
    echo "PASS - ${AVAILABLE}GB available"
else
    echo "FAIL - Only ${AVAILABLE}GB available (need 50GB)"
    exit 1
fi

echo "=== All validations passed! ==="