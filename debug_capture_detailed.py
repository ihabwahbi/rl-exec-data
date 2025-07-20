#!/usr/bin/env python3
"""Detailed debug script to trace message flow."""

import asyncio
import json
import time
from pathlib import Path
import sys
sys.path.insert(0, ".")

from loguru import logger
from src.rlx_datapipe.capture.websocket_handler import WebSocketHandler
from src.rlx_datapipe.capture.jsonl_writer import JSONLWriter

# Configure very detailed logging
logger.remove()
logger.add(sys.stderr, level="TRACE")

class DebugCapture:
    def __init__(self):
        self.symbol = "btcusdt"
        self.message_count = 0
        self.write_count = 0
        
        # Create test output directory
        self.output_dir = Path("data/debug_capture")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create writer with small buffer
        logger.info(f"Creating JSONLWriter with output_dir={self.output_dir}")
        self.writer = JSONLWriter(
            str(self.output_dir),
            f"debug_capture_{int(time.time())}",
            buffer_size=1,  # Write immediately
            compress=False  # No compression for debugging
        )
        
        # WebSocket URL
        self.ws_url = f"wss://stream.binance.com:9443/stream?streams={self.symbol}@trade/{self.symbol}@depth@100ms"
        logger.info(f"WebSocket URL: {self.ws_url}")
        
    async def on_message(self, message: dict, receive_ns: int):
        """Handle incoming message with detailed logging."""
        self.message_count += 1
        logger.trace(f"on_message called - message #{self.message_count}")
        logger.debug(f"Message stream: {message.get('stream', 'NO STREAM')}")
        
        # Check message structure
        if "stream" not in message:
            logger.error(f"Missing 'stream' in message: {message}")
            return
            
        if "data" not in message:
            logger.error(f"Missing 'data' in message: {message}")
            return
            
        # Create output record
        output = {
            "capture_ns": receive_ns,
            "stream": message["stream"],
            "data": message["data"]
        }
        
        logger.trace(f"Writing record #{self.write_count + 1}")
        
        # Write to file
        self.writer.write(output)
        self.write_count += 1
        
        # Force flush every write for debugging
        logger.trace("Forcing flush")
        self.writer.flush()
        
        # Log progress every 10 messages
        if self.message_count % 10 == 0:
            logger.info(f"Progress: {self.message_count} messages received, {self.write_count} written")
            stats = self.writer.get_stats()
            logger.info(f"Writer stats: {stats}")
            
    def on_connect(self):
        """Handle connection event."""
        logger.success("WebSocket connected!")
        
    def on_disconnect(self):
        """Handle disconnection event."""
        logger.warning("WebSocket disconnected!")
        
    async def run(self):
        """Run debug capture for 30 seconds."""
        logger.info("Starting debug capture for 30 seconds...")
        
        # Create WebSocket handler
        ws_handler = WebSocketHandler(
            url=self.ws_url,
            on_message=self.on_message,
            on_connect=self.on_connect,
            on_disconnect=self.on_disconnect
        )
        
        try:
            # Run for 30 seconds
            await asyncio.wait_for(ws_handler.run(), timeout=30)
        except asyncio.TimeoutError:
            logger.info("Timeout reached")
        finally:
            # Stop and close
            ws_handler.stop()
            self.writer.close()
            
            # Final stats
            logger.info("=== FINAL STATISTICS ===")
            logger.info(f"Messages received: {self.message_count}")
            logger.info(f"Messages written: {self.write_count}")
            logger.info(f"Writer stats: {self.writer.get_stats()}")
            
            # Check output files
            jsonl_files = list(self.output_dir.glob("*.jsonl"))
            logger.info(f"Output files: {len(jsonl_files)}")
            
            for file in jsonl_files:
                size = file.stat().st_size
                with open(file) as f:
                    lines = sum(1 for _ in f)
                logger.info(f"File: {file.name} - Size: {size} bytes - Lines: {lines}")
                
                # Show first message if any
                if lines > 0:
                    with open(file) as f:
                        first_line = f.readline()
                        logger.info(f"First message: {first_line[:100]}...")

if __name__ == "__main__":
    capture = DebugCapture()
    asyncio.run(capture.run())