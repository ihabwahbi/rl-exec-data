"""Integration tests for WebSocket data capture."""

import pytest
import asyncio
import json
import time
from unittest.mock import Mock, patch, AsyncMock
from src.rlx_datapipe.capture.websocket_handler import WebSocketHandler
from src.rlx_datapipe.capture.stream_parser import CombinedStreamParser
from src.rlx_datapipe.capture.orderbook_sync import OrderBookSynchronizer


class TestWebSocketIntegration:
    """Integration tests for WebSocket components."""
    
    @pytest.mark.asyncio
    async def test_websocket_message_flow(self):
        """Test complete message flow through WebSocket handler."""
        received_messages = []
        
        def on_message(data, ns_timestamp):
            received_messages.append((data, ns_timestamp))
            
        # Create handler
        handler = WebSocketHandler(
            url="wss://example.com/test",
            on_message=on_message
        )
        
        # Mock WebSocket connection
        mock_ws = AsyncMock()
        messages = [
            json.dumps({
                "stream": "btcusdt@trade",
                "data": {"T": 123456789}
            }),
            json.dumps({
                "stream": "btcusdt@depth", 
                "data": {"E": 987654321}
            })
        ]
        
        # Set up async iterator for messages
        async def message_generator():
            for msg in messages:
                yield msg
                
        mock_ws.__aiter__ = message_generator
        
        with patch('websockets.connect', return_value=mock_ws):
            # Run handler for a short time
            handler_task = asyncio.create_task(handler.run())
            await asyncio.sleep(0.1)
            handler.stop()
            
            try:
                await asyncio.wait_for(handler_task, timeout=1.0)
            except asyncio.TimeoutError:
                pass
                
        # Verify messages were received
        assert len(received_messages) == 2
        assert received_messages[0][0]["stream"] == "btcusdt@trade"
        assert received_messages[1][0]["stream"] == "btcusdt@depth"
        
    @pytest.mark.asyncio
    async def test_parser_integration(self):
        """Test parser integration with WebSocket handler."""
        parser = CombinedStreamParser()
        parsed_messages = []
        
        def on_message(data, ns_timestamp):
            parsed = parser.parse(data, ns_timestamp)
            if parsed:
                parsed_messages.append(parsed)
                
        handler = WebSocketHandler(
            url="wss://example.com/test",
            on_message=on_message
        )
        
        # Mock WebSocket with valid messages
        mock_ws = AsyncMock()
        messages = [
            json.dumps({
                "stream": "btcusdt@trade",
                "data": {
                    "e": "trade",
                    "E": 1234567890123,
                    "s": "BTCUSDT",
                    "t": 12345,
                    "p": "50000.00",
                    "q": "0.001",
                    "T": 1234567890123,
                    "m": True
                }
            }),
            json.dumps({
                "stream": "btcusdt@depth",
                "data": {
                    "e": "depthUpdate",
                    "E": 1234567890124,
                    "s": "BTCUSDT",
                    "U": 100,
                    "u": 105,
                    "b": [["49999.00", "1.0"]],
                    "a": [["50001.00", "1.0"]]
                }
            })
        ]
        
        async def message_generator():
            for msg in messages:
                yield msg
                
        mock_ws.__aiter__ = message_generator
        
        with patch('websockets.connect', return_value=mock_ws):
            handler_task = asyncio.create_task(handler.run())
            await asyncio.sleep(0.1)
            handler.stop()
            
            try:
                await asyncio.wait_for(handler_task, timeout=1.0)
            except asyncio.TimeoutError:
                pass
                
        # Verify parsing
        assert len(parsed_messages) == 2
        assert parsed_messages[0].data_type == "trade"
        assert parsed_messages[0].symbol == "BTCUSDT"
        assert parsed_messages[1].data_type == "orderbook_update"
        
        # Check parser stats
        stats = parser.get_stats()
        assert stats["total_messages"] == 2
        assert stats["trades"] == 1
        assert stats["orderbook_updates"] == 1
        assert stats["errors"] == 0
        
    @pytest.mark.asyncio
    async def test_orderbook_sync_integration(self):
        """Test order book synchronization with WebSocket updates."""
        synchronizer = OrderBookSynchronizer("BTCUSDT")
        
        # Mock REST snapshot response
        snapshot_response = {
            "lastUpdateId": 1000,
            "bids": [["50000.00", "1.0"]],
            "asks": [["50001.00", "1.0"]]
        }
        
        with patch('aiohttp.ClientSession') as mock_session:
            mock_get = AsyncMock()
            mock_get.__aenter__.return_value.status = 200
            mock_get.__aenter__.return_value.json = AsyncMock(return_value=snapshot_response)
            mock_session.return_value.__aenter__.return_value.get = mock_get
            
            # Buffer some updates
            synchronizer.buffer_update({
                "first_update_id": 999,
                "final_update_id": 1001,
                "U": 999,
                "u": 1001
            })
            synchronizer.buffer_update({
                "first_update_id": 1002,
                "final_update_id": 1005,
                "U": 1002,
                "u": 1005
            })
            
            # Synchronize
            result = await synchronizer.synchronize()
            assert result == True
            assert synchronizer.is_synchronized() == True
            
            # Process next update
            next_update = {
                "first_update_id": 1006,
                "final_update_id": 1010,
                "U": 1006,
                "u": 1010
            }
            processed = synchronizer.process_update(next_update)
            assert processed == next_update
            assert synchronizer.get_snapshot().last_update_id == 1010
            
    @pytest.mark.asyncio
    async def test_reconnection_behavior(self):
        """Test WebSocket reconnection behavior."""
        connection_count = 0
        
        def on_connect():
            nonlocal connection_count
            connection_count += 1
            
        handler = WebSocketHandler(
            url="wss://example.com/test",
            on_message=lambda d, t: None,
            on_connect=on_connect,
            max_reconnect_attempts=2,
            reconnect_delay=0.1
        )
        
        # Mock WebSocket that fails after first message
        mock_ws = AsyncMock()
        
        async def failing_generator():
            yield json.dumps({"test": "message"})
            raise Exception("Connection lost")
            
        mock_ws.__aiter__ = failing_generator
        
        with patch('websockets.connect', return_value=mock_ws):
            handler_task = asyncio.create_task(handler.run())
            await asyncio.sleep(0.5)
            handler.stop()
            
            try:
                await asyncio.wait_for(handler_task, timeout=1.0)
            except asyncio.TimeoutError:
                pass
                
        # Should have attempted reconnection
        assert connection_count >= 2