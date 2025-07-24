"""Tests for the SymbolRouter class."""

import pytest
from dataclasses import dataclass
from unittest.mock import Mock, MagicMock
from multiprocessing import Queue

from rlx_datapipe.reconstruction.symbol_router import (
    SymbolRouter, RoutedMessage, RoutingMetrics
)
from rlx_datapipe.reconstruction.config import (
    MultiSymbolConfig, RoutingStrategy, SymbolConfig
)


@dataclass
class MockMessage:
    """Mock message with symbol field."""
    symbol: str
    data: str


class TestSymbolRouter:
    """Tests for SymbolRouter functionality."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return MultiSymbolConfig(
            enabled=True,
            routing_strategy=RoutingStrategy.DIRECT,
            symbols=[
                SymbolConfig(name="BTC-USDT", queue_size=10),
                SymbolConfig(name="ETH-USDT", queue_size=10)
            ]
        )
        
    @pytest.fixture
    def process_manager(self):
        """Create mock process manager."""
        manager = Mock()
        
        # Mock workers
        btc_queue = MagicMock(spec=Queue)
        btc_queue.put_nowait = Mock()
        btc_queue.qsize.return_value = 5
        
        eth_queue = MagicMock(spec=Queue)
        eth_queue.put_nowait = Mock()
        eth_queue.qsize.return_value = 3
        
        manager.workers = {
            "BTC-USDT": Mock(queue=btc_queue, config=Mock(queue_size=10)),
            "ETH-USDT": Mock(queue=eth_queue, config=Mock(queue_size=10))
        }
        
        def get_queue(symbol):
            worker = manager.workers.get(symbol)
            return worker.queue if worker else None
            
        manager.get_worker_queue = get_queue
        
        return manager
        
    @pytest.fixture
    def router(self, config, process_manager):
        """Create SymbolRouter instance."""
        return SymbolRouter(config, process_manager)
        
    def test_init(self, router, config):
        """Test SymbolRouter initialization."""
        assert router.config == config
        assert router.routing_strategy == RoutingStrategy.DIRECT
        assert router.sequence_counter == 0
        assert isinstance(router.metrics, RoutingMetrics)
        
    def test_route_message_direct(self, router, process_manager):
        """Test direct routing strategy."""
        message = MockMessage(symbol="BTC-USDT", data="test")
        
        result = router.route_message(message)
        
        assert result is True
        assert router.metrics.messages_routed == 1
        assert router.metrics.messages_per_symbol["BTC-USDT"] == 1
        
        # Check message was queued
        btc_queue = process_manager.workers["BTC-USDT"].queue
        btc_queue.put_nowait.assert_called_once()
        
        # Check routed message format
        routed_msg = btc_queue.put_nowait.call_args[0][0]
        assert isinstance(routed_msg, RoutedMessage)
        assert routed_msg.symbol == "BTC-USDT"
        assert routed_msg.message == message
        assert routed_msg.sequence == 0
        
    def test_route_message_dict_format(self, router, process_manager):
        """Test routing with dict message format."""
        message = {"symbol": "ETH-USDT", "data": "test"}
        
        result = router.route_message(message)
        
        assert result is True
        eth_queue = process_manager.workers["ETH-USDT"].queue
        eth_queue.put_nowait.assert_called_once()
        
    def test_route_message_binance_format(self, router, process_manager):
        """Test routing with Binance 's' field."""
        message = Mock(s="BTC-USDT")
        
        result = router.route_message(message)
        
        assert result is True
        btc_queue = process_manager.workers["BTC-USDT"].queue
        btc_queue.put_nowait.assert_called_once()
        
    def test_route_message_missing_symbol(self, router):
        """Test routing message without symbol field."""
        message = Mock(spec=[])  # No attributes
        
        result = router.route_message(message)
        
        assert result is False
        assert router.metrics.routing_errors == 1
        
    def test_route_message_unknown_symbol(self, router):
        """Test routing to unknown symbol."""
        message = MockMessage(symbol="XRP-USDT", data="test")
        
        result = router.route_message(message)
        
        assert result is False
        assert router.metrics.messages_dropped == 1
        assert router.metrics.dropped_per_symbol["XRP-USDT"] == 1
        
    def test_route_message_queue_full(self, router, process_manager):
        """Test routing when queue is full."""
        message = MockMessage(symbol="BTC-USDT", data="test")
        
        # Simulate queue full
        btc_queue = process_manager.workers["BTC-USDT"].queue
        btc_queue.put_nowait.side_effect = Exception("Queue full")
        
        result = router.route_message(message)
        
        assert result is False
        assert router.metrics.messages_dropped == 1
        assert router.metrics.dropped_per_symbol["BTC-USDT"] == 1
        
    def test_hash_routing_strategy(self, router, process_manager):
        """Test hash-based routing strategy."""
        router.update_routing_strategy(RoutingStrategy.HASH)
        
        # Route multiple messages
        for i in range(10):
            message = {"data": f"test_{i}"}
            router.route_message(message)
            
        # Check messages were distributed
        btc_queue = process_manager.workers["BTC-USDT"].queue
        eth_queue = process_manager.workers["ETH-USDT"].queue
        
        total_calls = btc_queue.put_nowait.call_count + eth_queue.put_nowait.call_count
        assert total_calls == 10
        
    def test_round_robin_routing_strategy(self, router, process_manager):
        """Test round-robin routing strategy."""
        router.update_routing_strategy(RoutingStrategy.ROUND_ROBIN)
        
        # Route 4 messages
        for i in range(4):
            message = {"data": f"test_{i}"}
            router.route_message(message)
            
        # Check even distribution
        btc_queue = process_manager.workers["BTC-USDT"].queue
        eth_queue = process_manager.workers["ETH-USDT"].queue
        
        assert btc_queue.put_nowait.call_count == 2
        assert eth_queue.put_nowait.call_count == 2
        
    def test_route_batch(self, router):
        """Test batch routing."""
        messages = [
            MockMessage(symbol="BTC-USDT", data="1"),
            MockMessage(symbol="ETH-USDT", data="2"),
            MockMessage(symbol="XRP-USDT", data="3"),  # Unknown
        ]
        
        routed_count = router.route_batch(messages)
        
        assert routed_count == 2
        assert router.metrics.messages_routed == 2
        assert router.metrics.messages_dropped == 1
        
    def test_get_metrics(self, router):
        """Test getting routing metrics."""
        # Route some messages
        router.route_message(MockMessage(symbol="BTC-USDT", data="test"))
        router.route_message(MockMessage(symbol="XRP-USDT", data="test"))
        
        metrics = router.get_metrics()
        
        assert metrics['total_routed'] == 1
        assert metrics['total_dropped'] == 1
        assert metrics['routing_strategy'] == 'direct'
        assert 'BTC-USDT' in metrics['active_symbols']
        
    def test_get_queue_depths(self, router):
        """Test getting queue depths."""
        depths = router.get_queue_depths()
        
        assert depths['BTC-USDT'] == 5
        assert depths['ETH-USDT'] == 3
        
    def test_is_backpressure_detected(self, router, process_manager):
        """Test backpressure detection."""
        # No backpressure initially
        assert not router.is_backpressure_detected(threshold=0.8)
        
        # Simulate high queue usage
        btc_queue = process_manager.workers["BTC-USDT"].queue
        btc_queue.qsize.return_value = 9  # 90% full
        
        assert router.is_backpressure_detected(threshold=0.8)
        
    def test_clear_cache(self, router):
        """Test clearing symbol cache."""
        # Route a message to populate cache
        router.route_message(MockMessage(symbol="BTC-USDT", data="test"))
        assert len(router._symbol_cache) > 0
        
        router.clear_cache()
        assert len(router._symbol_cache) == 0