"""Unit tests for CombinedStreamParser."""

import pytest
from src.rlx_datapipe.capture.stream_parser import CombinedStreamParser, ParsedMessage


class TestCombinedStreamParser:
    """Test cases for CombinedStreamParser."""
    
    def test_parse_trade_message(self):
        """Test parsing of trade message."""
        parser = CombinedStreamParser()
        
        message = {
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
                "m": True,
                "M": True
            }
        }
        
        receive_ns = 1234567890123456789
        parsed = parser.parse(message, receive_ns)
        
        assert parsed is not None
        assert parsed.stream == "btcusdt@trade"
        assert parsed.data_type == "trade"
        assert parsed.symbol == "BTCUSDT"
        assert parsed.exchange_timestamp == 1234567890123
        assert parsed.receive_ns == receive_ns
        assert parsed.data == message["data"]
        
        # Check stats
        stats = parser.get_stats()
        assert stats["total_messages"] == 1
        assert stats["trades"] == 1
        assert stats["orderbook_updates"] == 0
        assert stats["errors"] == 0
        
    def test_parse_orderbook_message(self):
        """Test parsing of orderbook update message."""
        parser = CombinedStreamParser()
        
        message = {
            "stream": "btcusdt@depth",
            "data": {
                "e": "depthUpdate",
                "E": 1234567890123,
                "s": "BTCUSDT",
                "U": 157,
                "u": 160,
                "b": [["50000.00", "0.05"], ["49999.00", "0.10"]],
                "a": [["50001.00", "0.05"], ["50002.00", "0.10"]]
            }
        }
        
        receive_ns = 1234567890123456789
        parsed = parser.parse(message, receive_ns)
        
        assert parsed is not None
        assert parsed.stream == "btcusdt@depth"
        assert parsed.data_type == "orderbook_update"
        assert parsed.symbol == "BTCUSDT"
        assert parsed.exchange_timestamp == 1234567890123
        assert parsed.receive_ns == receive_ns
        
        # Check stats
        stats = parser.get_stats()
        assert stats["total_messages"] == 1
        assert stats["trades"] == 0
        assert stats["orderbook_updates"] == 1
        assert stats["errors"] == 0
        
    def test_parse_invalid_message(self):
        """Test parsing of invalid message."""
        parser = CombinedStreamParser()
        
        # Missing stream
        message1 = {"data": {"E": 123}}
        parsed1 = parser.parse(message1, 123456789)
        assert parsed1 is None
        
        # Missing data
        message2 = {"stream": "btcusdt@trade"}
        parsed2 = parser.parse(message2, 123456789)
        assert parsed2 is None
        
        # Invalid stream format
        message3 = {"stream": "invalid_format", "data": {}}
        parsed3 = parser.parse(message3, 123456789)
        assert parsed3 is None
        
        # Check error count
        stats = parser.get_stats()
        assert stats["errors"] == 3
        
    def test_format_trade(self):
        """Test trade formatting."""
        parser = CombinedStreamParser()
        
        parsed = ParsedMessage(
            stream="btcusdt@trade",
            data_type="trade",
            symbol="BTCUSDT",
            data={
                "t": 12345,
                "p": "50000.00",
                "q": "0.001",
                "b": 88888,
                "a": 99999,
                "T": 1234567890123,
                "m": True
            },
            exchange_timestamp=1234567890123,
            receive_ns=1234567890123456789
        )
        
        formatted = parser.format_trade(parsed)
        
        assert formatted["type"] == "trade"
        assert formatted["symbol"] == "BTCUSDT"
        assert formatted["trade_id"] == 12345
        assert formatted["price"] == "50000.00"
        assert formatted["quantity"] == "0.001"
        assert formatted["buyer_order_id"] == 88888
        assert formatted["seller_order_id"] == 99999
        assert formatted["trade_time"] == 1234567890123
        assert formatted["is_buyer_maker"] == True
        assert formatted["receive_ns"] == 1234567890123456789
        
    def test_format_orderbook_update(self):
        """Test orderbook update formatting."""
        parser = CombinedStreamParser()
        
        parsed = ParsedMessage(
            stream="btcusdt@depth",
            data_type="orderbook_update",
            symbol="BTCUSDT",
            data={
                "E": 1234567890123,
                "U": 157,
                "u": 160,
                "b": [["50000.00", "0.05"]],
                "a": [["50001.00", "0.05"]]
            },
            exchange_timestamp=1234567890123,
            receive_ns=1234567890123456789
        )
        
        formatted = parser.format_orderbook_update(parsed)
        
        assert formatted["type"] == "orderbook_update"
        assert formatted["symbol"] == "BTCUSDT"
        assert formatted["event_time"] == 1234567890123
        assert formatted["first_update_id"] == 157
        assert formatted["final_update_id"] == 160
        assert formatted["bids"] == [["50000.00", "0.05"]]
        assert formatted["asks"] == [["50001.00", "0.05"]]
        assert formatted["receive_ns"] == 1234567890123456789
        
    def test_reset_stats(self):
        """Test stats reset."""
        parser = CombinedStreamParser()
        
        # Generate some stats
        message = {
            "stream": "btcusdt@trade",
            "data": {"T": 123}
        }
        parser.parse(message, 123)
        
        # Reset
        parser.reset_stats()
        stats = parser.get_stats()
        
        assert stats["total_messages"] == 0
        assert stats["trades"] == 0
        assert stats["orderbook_updates"] == 0
        assert stats["errors"] == 0