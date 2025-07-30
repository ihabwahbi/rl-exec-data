#!/bin/bash
# pre_capture_validation_macos.sh - macOS compatible version

echo "=== Pre-Capture Validation (macOS) ==="

# 1. Test WebSocket URL includes @100ms
echo -n "Testing WebSocket URL format... "
if grep -q '@depth@100ms' src/rlx_datapipe/capture/main.py; then
    echo "PASS"
else
    echo "FAIL - Missing @100ms suffix"
    exit 1
fi

# 2. Create test directory
mkdir -p /tmp/test_capture

# 3. Test 1-minute capture
echo "Running 1-minute test capture..."
poetry run python scripts/capture_live_data.py --symbol btcusdt --duration 1 --output-dir /tmp/test_capture
if [ $? -eq 0 ]; then
    echo "Capture script executed successfully"
else
    echo "FAIL - Capture script error"
    exit 1
fi

# 4. Verify output format
echo -n "Verifying output format... "
TEST_FILE=$(ls /tmp/test_capture/*.jsonl.gz 2>/dev/null | head -1)
if [ -z "$TEST_FILE" ]; then
    echo "FAIL - No output file found"
    exit 1
fi

# Check message format (using gunzip for macOS)
SAMPLE=$(gunzip -c "$TEST_FILE" | head -1)
if echo "$SAMPLE" | jq -e '.capture_ns and .stream and .data' > /dev/null; then
    echo "PASS"
else
    echo "FAIL - Invalid message format"
    exit 1
fi

# 5. Check disk space (macOS compatible)
echo -n "Checking disk space... "
AVAILABLE=$(df -h . | tail -1 | awk '{print $4}' | sed 's/Gi//')
# Convert to float for comparison
AVAILABLE_INT=$(echo "$AVAILABLE" | cut -d. -f1)
if [ "$AVAILABLE_INT" -gt 10 ]; then
    echo "PASS - ${AVAILABLE}GB available"
else
    echo "FAIL - Only ${AVAILABLE}GB available (need at least 10GB)"
    exit 1
fi

# 6. Clean up test capture
rm -rf /tmp/test_capture

echo "=== All validations passed! ==="