"""Parser for Binance combined WebSocket streams."""

from dataclasses import dataclass
from typing import Any

from loguru import logger


@dataclass
class ParsedMessage:
    """Parsed message with metadata."""

    stream: str
    data_type: str
    symbol: str
    data: dict[str, Any]
    exchange_timestamp: int
    receive_ns: int


class CombinedStreamParser:
    """Parser for Binance combined WebSocket stream messages."""

    def __init__(self):
        """Initialize the parser."""
        self._stats = {
            "total_messages": 0,
            "trades": 0,
            "orderbook_updates": 0,
            "errors": 0,
        }

    def parse(self, message: dict[str, Any], receive_ns: int) -> ParsedMessage | None:
        """Parse a combined stream message.

        Args:
            message: Raw message dict from WebSocket
            receive_ns: Nanosecond timestamp when message was received

        Returns:
            ParsedMessage if successful, None if parsing failed
        """
        self._stats["total_messages"] += 1

        try:
            if "stream" not in message or "data" not in message:
                logger.warning("Invalid message format: missing stream or data")
                self._stats["errors"] += 1
                return None

            stream = message["stream"]
            data = message["data"]

            # Parse stream name: symbol@streamtype
            parts = stream.split("@")
            if len(parts) != 2:
                logger.warning(f"Invalid stream format: {stream}")
                self._stats["errors"] += 1
                return None

            symbol = parts[0].upper()
            stream_type = parts[1]

            # Extract exchange timestamp based on stream type
            if stream_type == "trade":
                exchange_timestamp = data.get("T")  # Trade time
                data_type = "trade"
                self._stats["trades"] += 1
            elif stream_type == "depth":
                exchange_timestamp = data.get("E")  # Event time
                data_type = "orderbook_update"
                self._stats["orderbook_updates"] += 1
            else:
                logger.warning(f"Unknown stream type: {stream_type}")
                self._stats["errors"] += 1
                return None

            if exchange_timestamp is None:
                logger.warning(f"Missing exchange timestamp in {stream_type} message")
                self._stats["errors"] += 1
                return None

            return ParsedMessage(
                stream=stream,
                data_type=data_type,
                symbol=symbol,
                data=data,
                exchange_timestamp=exchange_timestamp,
                receive_ns=receive_ns,
            )

        except Exception as e:
            logger.error(f"Error parsing message: {e}")
            self._stats["errors"] += 1
            return None

    def get_stats(self) -> dict[str, int]:
        """Get parser statistics."""
        return self._stats.copy()

    def reset_stats(self) -> None:
        """Reset parser statistics."""
        self._stats = {
            "total_messages": 0,
            "trades": 0,
            "orderbook_updates": 0,
            "errors": 0,
        }

    @staticmethod
    def format_trade(parsed: ParsedMessage) -> dict[str, Any]:
        """Format trade data for storage.

        Args:
            parsed: Parsed trade message

        Returns:
            Formatted trade dict
        """
        data = parsed.data
        return {
            "type": "trade",
            "symbol": parsed.symbol,
            "trade_id": data["t"],
            "price": data["p"],
            "quantity": data["q"],
            "buyer_order_id": data["b"],
            "seller_order_id": data["a"],
            "trade_time": data["T"],
            "is_buyer_maker": data["m"],
            "receive_ns": parsed.receive_ns,
            "exchange_timestamp": parsed.exchange_timestamp,
        }

    @staticmethod
    def format_orderbook_update(parsed: ParsedMessage) -> dict[str, Any]:
        """Format orderbook update for storage.

        Args:
            parsed: Parsed orderbook update message

        Returns:
            Formatted orderbook update dict
        """
        data = parsed.data
        return {
            "type": "orderbook_update",
            "symbol": parsed.symbol,
            "event_time": data["E"],
            "first_update_id": data["U"],
            "final_update_id": data["u"],
            "bids": data["b"],  # List of [price, quantity]
            "asks": data["a"],  # List of [price, quantity]
            "receive_ns": parsed.receive_ns,
            "exchange_timestamp": parsed.exchange_timestamp,
        }
