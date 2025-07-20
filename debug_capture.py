#!/usr/bin/env python3
"""Debug script to test WebSocket connection."""

import asyncio
import json
import time
import websockets
from loguru import logger


async def test_websocket_connection():
    """Test basic WebSocket connection to Binance."""
    
    # Test URLs
    urls = [
        "wss://stream.binance.com:9443/ws/btcusdt@trade",  # Single stream
        "wss://stream.binance.com:9443/stream?streams=btcusdt@trade/btcusdt@depth@100ms",  # Combined
        "wss://stream.binance.com/ws/btcusdt@trade",  # Without port
    ]
    
    for url in urls:
        logger.info(f"\nTesting URL: {url}")
        try:
            async with websockets.connect(url) as websocket:
                logger.success(f"Connected to {url}")
                
                # Receive a few messages
                for i in range(5):
                    message = await websocket.recv()
                    data = json.loads(message)
                    logger.info(f"Message {i+1}: {data.get('e', data.get('stream', 'unknown'))}")
                    
                await websocket.close()
                
        except Exception as e:
            logger.error(f"Failed to connect to {url}: {e}")
    
    # Test the exact URL our capture script uses
    symbol = "btcusdt"
    capture_url = f"wss://stream.binance.com:9443/stream?streams={symbol}@trade/{symbol}@depth@100ms"
    
    logger.info(f"\nTesting capture script URL: {capture_url}")
    try:
        async with websockets.connect(capture_url) as websocket:
            logger.success("Connected successfully!")
            
            # Check message format
            for i in range(10):
                message = await websocket.recv()
                data = json.loads(message)
                logger.info(f"Stream: {data.get('stream')} - Has data: {'data' in data}")
                
                if i == 0:
                    logger.info(f"First message structure: {json.dumps(data, indent=2)}")
                    
    except Exception as e:
        logger.error(f"Connection failed: {e}")


if __name__ == "__main__":
    logger.info("Starting WebSocket connection test...")
    asyncio.run(test_websocket_connection())