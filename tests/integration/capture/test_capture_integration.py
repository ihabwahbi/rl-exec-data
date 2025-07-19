"""Integration tests for complete capture workflow."""

import pytest
import asyncio
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from src.rlx_datapipe.capture.main import DataCapture
from src.rlx_datapipe.capture.logging_config import configure_logging


class TestCaptureIntegration:
    """Integration tests for complete data capture."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
        
    @pytest.fixture
    def mock_websocket_messages(self):
        """Create mock WebSocket messages."""
        return [
            # Trade messages
            json.dumps({
                "stream": "btcusdt@trade",
                "data": {
                    "e": "trade",
                    "E": 1234567890123,
                    "s": "BTCUSDT",
                    "t": 12345,
                    "p": "50000.00",
                    "q": "0.001",
                    "b": 88888,
                    "a": 99999,
                    "T": 1234567890123,
                    "m": True
                }
            }),
            # Orderbook messages
            json.dumps({
                "stream": "btcusdt@depth",
                "data": {
                    "e": "depthUpdate",
                    "E": 1234567890124,
                    "s": "BTCUSDT",
                    "U": 1001,
                    "u": 1005,
                    "b": [["49999.00", "1.0"], ["49998.00", "2.0"]],
                    "a": [["50001.00", "1.0"], ["50002.00", "2.0"]]
                }
            }),
            # Another trade
            json.dumps({
                "stream": "btcusdt@trade",
                "data": {
                    "e": "trade",
                    "E": 1234567890125,
                    "s": "BTCUSDT",
                    "t": 12346,
                    "p": "50001.00",
                    "q": "0.002",
                    "b": 88889,
                    "a": 99998,
                    "T": 1234567890125,
                    "m": False
                }
            })
        ]
        
    @pytest.mark.asyncio
    async def test_capture_workflow(self, temp_dir, mock_websocket_messages):
        """Test complete capture workflow."""
        configure_logging()
        
        # Create capture instance
        capture = DataCapture(
            symbol="BTCUSDT",
            output_dir=temp_dir,
            duration=2  # 2 second capture
        )
        
        # Mock REST snapshot
        snapshot_response = {
            "lastUpdateId": 1000,
            "bids": [["50000.00", "10.0"], ["49999.00", "20.0"]],
            "asks": [["50001.00", "10.0"], ["50002.00", "20.0"]]
        }
        
        # Mock WebSocket connection
        async def message_generator():
            for msg in mock_websocket_messages:
                yield msg
                await asyncio.sleep(0.1)
                
        mock_ws = AsyncMock()
        mock_ws.__aiter__ = message_generator
        
        with patch('aiohttp.ClientSession') as mock_session, \
             patch('websockets.connect', return_value=mock_ws):
            
            # Set up REST mock
            mock_get = AsyncMock()
            mock_get.__aenter__.return_value.status = 200
            mock_get.__aenter__.return_value.json = AsyncMock(return_value=snapshot_response)
            mock_session.return_value.__aenter__.return_value.get = mock_get
            
            # Run capture
            await capture.run()
            
        # Verify files were created
        trade_files = list(Path(temp_dir).glob("*_trades_*.jsonl.gz"))
        orderbook_files = list(Path(temp_dir).glob("*_orderbook_*.jsonl.gz"))
        
        assert len(trade_files) >= 1
        assert len(orderbook_files) >= 1
        
        # Verify statistics
        assert capture.parser.get_stats()["trades"] == 2
        assert capture.parser.get_stats()["orderbook_updates"] == 1
        
    @pytest.mark.asyncio
    async def test_capture_error_handling(self, temp_dir):
        """Test capture error handling."""
        capture = DataCapture(
            symbol="BTCUSDT",
            output_dir=temp_dir,
            duration=1
        )
        
        # Mock WebSocket that sends invalid messages
        async def error_generator():
            yield "invalid json"
            yield json.dumps({"invalid": "format"})
            
        mock_ws = AsyncMock()
        mock_ws.__aiter__ = error_generator
        
        with patch('websockets.connect', return_value=mock_ws):
            # Should handle errors gracefully
            await capture.run()
            
        # Check error stats
        assert capture.parser.get_stats()["errors"] > 0
        
    @pytest.mark.asyncio 
    async def test_capture_synchronization_failure(self, temp_dir):
        """Test handling of order book synchronization failure."""
        capture = DataCapture(
            symbol="BTCUSDT",
            output_dir=temp_dir,
            duration=1
        )
        
        # Mock REST API failure
        with patch('aiohttp.ClientSession') as mock_session:
            mock_get = AsyncMock()
            mock_get.__aenter__.return_value.status = 500
            mock_session.return_value.__aenter__.return_value.get = mock_get
            
            # Mock WebSocket messages
            async def message_generator():
                yield json.dumps({
                    "stream": "btcusdt@depth",
                    "data": {
                        "e": "depthUpdate",
                        "E": 123,
                        "U": 100,
                        "u": 105,
                        "b": [],
                        "a": []
                    }
                })
                
            mock_ws = AsyncMock()
            mock_ws.__aiter__ = message_generator
            
            with patch('websockets.connect', return_value=mock_ws):
                await capture.run()
                
        # Should not be synchronized
        assert not capture.orderbook_sync.is_synchronized()
        
    def test_capture_cli_invocation(self, temp_dir):
        """Test capture CLI invocation."""
        from click.testing import CliRunner
        from src.rlx_datapipe.capture.main import main
        
        runner = CliRunner()
        
        # Test help
        result = runner.invoke(main, ['--help'])
        assert result.exit_code == 0
        assert 'Trading symbol' in result.output
        
        # Test with parameters (won't actually connect)
        with patch('asyncio.run'):
            result = runner.invoke(main, [
                '--symbol', 'ETHUSDT',
                '--output-dir', temp_dir,
                '--duration', '10'
            ])
            assert result.exit_code == 0