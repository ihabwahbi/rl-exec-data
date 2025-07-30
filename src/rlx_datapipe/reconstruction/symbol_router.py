"""Symbol Router for distributing messages to worker processes.

This module implements the SymbolRouter class which handles:
- Message routing based on symbol field
- Multiple routing strategies (direct, hash, round-robin)
- Queue management and backpressure handling
- Routing metrics and monitoring
"""

import hashlib
import time
from dataclasses import dataclass
from multiprocessing import Queue
from typing import Any

from loguru import logger

from .config import MultiSymbolConfig, RoutingStrategy
from .process_manager import ProcessManager


@dataclass
class RoutedMessage:
    """Message wrapper with routing metadata."""

    symbol: str
    message: Any  # Original parsed message
    timestamp: float  # Router timestamp for monitoring
    sequence: int  # Router sequence number


@dataclass
class RoutingMetrics:
    """Metrics for routing performance."""

    messages_routed: int = 0
    messages_dropped: int = 0
    routing_errors: int = 0
    last_message_time: float = 0.0
    messages_per_symbol: dict[str, int] = None
    dropped_per_symbol: dict[str, int] = None

    def __post_init__(self):
        if self.messages_per_symbol is None:
            self.messages_per_symbol = {}
        if self.dropped_per_symbol is None:
            self.dropped_per_symbol = {}

    def increment_routed(self, symbol: str) -> None:
        """Increment routed message count."""
        self.messages_routed += 1
        self.messages_per_symbol[symbol] = self.messages_per_symbol.get(symbol, 0) + 1
        self.last_message_time = time.time()

    def increment_dropped(self, symbol: str) -> None:
        """Increment dropped message count."""
        self.messages_dropped += 1
        self.dropped_per_symbol[symbol] = self.dropped_per_symbol.get(symbol, 0) + 1


class SymbolRouter:
    """Routes messages to appropriate worker processes based on symbol."""

    def __init__(self, config: MultiSymbolConfig, process_manager: ProcessManager):
        """Initialize the symbol router.

        Args:
            config: Multi-symbol configuration
            process_manager: Process manager instance
        """
        self.config = config
        self.process_manager = process_manager
        self.routing_strategy = config.routing_strategy
        self.sequence_counter = 0
        self.round_robin_index = 0
        self.metrics = RoutingMetrics()
        self._symbol_cache: dict[str, Queue] = {}

        logger.info(
            f"Initialized SymbolRouter with strategy: {self.routing_strategy.value}"
        )

    def route_message(self, message: Any) -> bool:
        """Route a message to the appropriate worker.

        Args:
            message: Message to route (must have 'symbol' attribute)

        Returns:
            True if message was routed, False if dropped
        """
        try:
            # Extract symbol based on strategy
            symbol = self._extract_symbol(message)
            if not symbol:
                logger.warning("Message missing symbol field, dropping")
                self.metrics.routing_errors += 1
                return False

            # Get target queue
            queue = self._get_queue_for_symbol(symbol)
            if not queue:
                logger.warning(f"No worker for symbol {symbol}, dropping message")
                self.metrics.increment_dropped(symbol)
                return False

            # Create routed message
            routed_msg = RoutedMessage(
                symbol=symbol,
                message=message,
                timestamp=time.time(),
                sequence=self.sequence_counter,
            )
            self.sequence_counter += 1

            # Try to put message in queue
            try:
                queue.put_nowait(routed_msg)
                self.metrics.increment_routed(symbol)
                return True
            except Exception:  # Queue full
                logger.debug(f"Queue full for symbol {symbol}, dropping message")
                self.metrics.increment_dropped(symbol)
                return False

        except Exception as e:
            logger.error(f"Error routing message: {e}")
            self.metrics.routing_errors += 1
            return False

    def _extract_symbol(self, message: Any) -> str | None:
        """Extract symbol from message based on routing strategy.

        Args:
            message: Message to extract symbol from

        Returns:
            Symbol string or None if not found
        """
        if self.routing_strategy == RoutingStrategy.DIRECT:
            # Direct routing - use symbol field
            if hasattr(message, "symbol"):
                return message.symbol
            if isinstance(message, dict) and "symbol" in message:
                return message["symbol"]
            if hasattr(message, "s"):  # Binance uses 's' for symbol
                return message.s
            if isinstance(message, dict) and "s" in message:
                return message["s"]

        elif self.routing_strategy == RoutingStrategy.HASH:
            # Hash-based routing - hash the entire message
            symbols = list(self.process_manager.workers.keys())
            if not symbols:
                return None
            msg_hash = hashlib.md5(str(message).encode()).hexdigest()
            index = int(msg_hash, 16) % len(symbols)
            return symbols[index]

        elif self.routing_strategy == RoutingStrategy.ROUND_ROBIN:
            # Round-robin routing
            symbols = list(self.process_manager.workers.keys())
            if not symbols:
                return None
            symbol = symbols[self.round_robin_index % len(symbols)]
            self.round_robin_index += 1
            return symbol

        return None

    def _get_queue_for_symbol(self, symbol: str) -> Queue | None:
        """Get the queue for a specific symbol.

        Args:
            symbol: Symbol identifier

        Returns:
            Queue for the symbol or None if not found
        """
        # Check cache first
        if symbol in self._symbol_cache:
            return self._symbol_cache[symbol]

        # Get from process manager
        queue = self.process_manager.get_worker_queue(symbol)
        if queue:
            self._symbol_cache[symbol] = queue

        return queue

    def route_batch(self, messages: list[Any]) -> int:
        """Route a batch of messages.

        Args:
            messages: List of messages to route

        Returns:
            Number of successfully routed messages
        """
        routed_count = 0
        for message in messages:
            if self.route_message(message):
                routed_count += 1
        return routed_count

    def get_metrics(self) -> dict[str, Any]:
        """Get routing metrics.

        Returns:
            Dictionary of routing metrics
        """
        return {
            "total_routed": self.metrics.messages_routed,
            "total_dropped": self.metrics.messages_dropped,
            "routing_errors": self.metrics.routing_errors,
            "last_message_time": self.metrics.last_message_time,
            "messages_per_symbol": dict(self.metrics.messages_per_symbol),
            "dropped_per_symbol": dict(self.metrics.dropped_per_symbol),
            "routing_strategy": self.routing_strategy.value,
            "active_symbols": list(self.process_manager.workers.keys()),
        }

    def clear_cache(self) -> None:
        """Clear the symbol-to-queue cache."""
        self._symbol_cache.clear()
        logger.debug("Cleared symbol queue cache")

    def update_routing_strategy(self, strategy: RoutingStrategy) -> None:
        """Update the routing strategy.

        Args:
            strategy: New routing strategy
        """
        self.routing_strategy = strategy
        logger.info(f"Updated routing strategy to: {strategy.value}")

    def get_queue_depths(self) -> dict[str, int]:
        """Get current queue depths for all symbols.

        Returns:
            Dictionary mapping symbol to queue size
        """
        depths = {}
        for symbol, worker in self.process_manager.workers.items():
            try:
                depths[symbol] = worker.queue.qsize()
            except Exception:
                depths[symbol] = -1  # Queue size not available
        return depths

    def is_backpressure_detected(self, threshold: float = 0.8) -> bool:
        """Check if any queue is experiencing backpressure.

        Args:
            threshold: Queue fullness threshold (0.0 to 1.0)

        Returns:
            True if any queue is above threshold
        """
        for symbol, worker in self.process_manager.workers.items():
            try:
                queue_size = worker.queue.qsize()
                max_size = worker.config.queue_size
                if queue_size / max_size >= threshold:
                    logger.warning(
                        f"Backpressure detected for {symbol}: {queue_size}/{max_size}"
                    )
                    return True
            except Exception:
                pass
        return False
