# Story 1.2 Fix Implementation Guide

## Overview

This guide provides specific instructions for fixing the LiveCapture implementation to meet the actual requirements. The core issue is that the current implementation transforms data when it should preserve it raw.

## Critical Issues to Fix

### 1. Output Format

**Current (WRONG)**:
```python
# In stream_parser.py
@staticmethod
def format_trade(parsed: ParsedMessage) -> dict[str, Any]:
    data = parsed.data
    return {
        "type": "trade",
        "symbol": parsed.symbol,
        "trade_id": data["t"],
        "price": data["p"],
        "quantity": data["q"],
        # ... transformed structure
    }
```

**Required (CORRECT)**:
```python
# New approach - NO transformation
async def write_message(self, msg: dict, receive_ns: int):
    """Write raw message with capture metadata."""
    output = {
        "capture_ns": receive_ns,
        "stream": msg["stream"],
        "data": msg["data"]  # Raw message preserved exactly
    }
    await self.writer.write(json.dumps(output) + "\n")
```

### 2. WebSocket URL

**Current (WRONG)**:
```python
self.ws_url = f"wss://stream.binance.com:9443/stream?streams={self.symbol}@trade/{self.symbol}@depth"
```

**Required (CORRECT)**:
```python
self.ws_url = f"wss://stream.binance.com:9443/stream?streams={self.symbol}@trade/{self.symbol}@depth@100ms"
```

The `@100ms` suffix is critical - it specifies the update frequency that matches our historical data.

### 3. File Organization

**Current (WRONG)**:
- Separate files for trades and orderbook
- Two different writers

**Required (CORRECT)**:
- Single chronological file
- One writer for all messages

### 4. CLI Location

**Current (WRONG)**:
- Main entry in `src/rlx_datapipe/capture/main.py`

**Required (CORRECT)**:
- Create `scripts/capture_live_data.py`

## Implementation Steps

### Step 1: Simplify the Parser

Replace the complex parsing logic with simple pass-through:

```python
# simplified_parser.py
class RawMessageHandler:
    """Handles raw WebSocket messages without transformation."""
    
    def __init__(self, writer: JSONLWriter):
        self.writer = writer
        self.stats = defaultdict(int)
    
    async def handle_message(self, raw_msg: str, receive_ns: int):
        """Process raw WebSocket message."""
        try:
            msg = json.loads(raw_msg)
            
            # Validate basic structure
            if "stream" not in msg or "data" not in msg:
                logger.warning("Invalid message format")
                self.stats["errors"] += 1
                return
            
            # Write raw message with metadata
            output = {
                "capture_ns": receive_ns,
                "stream": msg["stream"],
                "data": msg["data"]  # NO transformation
            }
            
            await self.writer.write_line(json.dumps(output))
            
            # Update stats
            stream_type = msg["stream"].split("@")[1]
            self.stats[stream_type] += 1
            self.stats["total"] += 1
            
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            self.stats["errors"] += 1
```

### Step 2: Fix WebSocket Connection

Update the connection handler:

```python
# websocket_handler.py
class BinanceWebSocketHandler:
    """Handles Binance WebSocket connections."""
    
    def __init__(self, symbol: str, message_handler: RawMessageHandler):
        self.symbol = symbol.lower()
        self.message_handler = message_handler
        
        # CRITICAL: Include @100ms suffix
        self.ws_url = (
            f"wss://stream.binance.com:9443/stream?"
            f"streams={self.symbol}@trade/{self.symbol}@depth@100ms"
        )
```

### Step 3: Simplify Main Capture Logic

```python
# capture_main.py
class LiveDataCapture:
    """Captures live market data from Binance."""
    
    def __init__(self, symbol: str, output_dir: Path):
        self.symbol = symbol
        self.output_dir = output_dir
        
        # Single writer for chronological order
        self.writer = JSONLWriter(
            self.output_dir / f"{symbol}_capture_{int(time.time())}.jsonl"
        )
        
        # Simple message handler
        self.message_handler = RawMessageHandler(self.writer)
        
        # WebSocket handler
        self.ws_handler = BinanceWebSocketHandler(
            symbol, 
            self.message_handler
        )
```

### Step 4: Create CLI Script

Create `scripts/capture_live_data.py`:

```python
#!/usr/bin/env python3
"""CLI script for capturing live market data."""

import asyncio
import click
from pathlib import Path
from loguru import logger

from rlx_datapipe.capture import LiveDataCapture


@click.command()
@click.option(
    "--symbol",
    default="btcusdt",
    help="Trading symbol to capture (default: btcusdt)"
)
@click.option(
    "--duration",
    default=60,
    type=int,
    help="Capture duration in minutes (default: 60)"
)
@click.option(
    "--output-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("data/golden_samples"),
    help="Output directory for captured data"
)
def capture_live_data(symbol: str, duration: int, output_dir: Path):
    """Capture raw live market data from Binance."""
    logger.info(f"Starting capture for {symbol} for {duration} minutes")
    
    # Create capture instance
    capture = LiveDataCapture(symbol, output_dir)
    
    # Run capture
    asyncio.run(capture.run(duration_minutes=duration))
    
    logger.info("Capture completed")


if __name__ == "__main__":
    capture_live_data()
```

### Step 5: Order Book Synchronization

Keep the existing synchronization logic but adapt for raw storage:

```python
class OrderBookSynchronizer:
    """Handles order book synchronization protocol."""
    
    async def initialize(self):
        """Initialize order book with REST snapshot."""
        # 1. Connect WebSocket first
        await self.ws_handler.connect()
        
        # 2. Start buffering updates
        self.buffering = True
        
        # 3. Get REST snapshot
        snapshot = await self.get_rest_snapshot()
        
        # 4. Store raw snapshot with special marker
        snapshot_msg = {
            "capture_ns": time.perf_counter_ns(),
            "stream": f"{self.symbol}@depth_snapshot",
            "data": snapshot  # Raw REST response
        }
        await self.writer.write_line(json.dumps(snapshot_msg))
        
        # 5. Apply buffered updates
        await self.apply_buffered_updates(snapshot["lastUpdateId"])
        
        # 6. Continue with live updates
        self.buffering = False
```

## Testing the Fix

### 1. Verify Output Format

```python
# Read captured file and verify format
with open(capture_file) as f:
    for line in f:
        msg = json.loads(line)
        assert "capture_ns" in msg
        assert "stream" in msg
        assert "data" in msg
        assert isinstance(msg["data"], dict)  # Raw preservation
```

### 2. Verify WebSocket URL

```python
# Check connection URL
assert "@depth@100ms" in capture.ws_handler.ws_url
```

### 3. Verify Chronological Order

```python
# Check messages are in time order
timestamps = []
with open(capture_file) as f:
    for line in f:
        msg = json.loads(line)
        timestamps.append(msg["capture_ns"])

assert timestamps == sorted(timestamps)
```

## Migration Path

1. **Keep Existing Code**: Don't delete current implementation yet
2. **Create New Module**: `rlx_datapipe.capture_v2` for fixed version
3. **Parallel Testing**: Run both versions and compare
4. **Gradual Migration**: Switch to v2 after validation
5. **Archive Old Code**: Move to archive/ after full migration

## Common Pitfalls to Avoid

1. **Don't Parse Event Types**: The whole point is raw preservation
2. **Don't Separate Streams**: Keep chronological order
3. **Don't Buffer Indefinitely**: Implement size/time limits
4. **Don't Ignore Reconnection**: Must handle gracefully
5. **Don't Transform Timestamps**: Preserve original format

## Success Criteria

The fix is successful when:
1. ✅ Output contains raw "data" field unchanged
2. ✅ WebSocket URL includes @100ms suffix
3. ✅ Single chronological output file
4. ✅ Script located in scripts/ directory
5. ✅ Order book synchronization works correctly
6. ✅ Can capture 24+ hours without data loss