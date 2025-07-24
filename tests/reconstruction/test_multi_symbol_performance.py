"""Performance tests for multi-symbol pipeline."""

import multiprocessing
import time
import pytest
from unittest.mock import Mock, patch

from rlx_datapipe.reconstruction.config import MultiSymbolConfig, SymbolConfig
from rlx_datapipe.reconstruction.process_manager import ProcessManager
from rlx_datapipe.reconstruction.symbol_router import SymbolRouter, RoutingStrategy


class TestMultiSymbolPerformance:
    """Performance tests to validate linear scaling and throughput."""
    
    def create_config(self, num_symbols: int) -> MultiSymbolConfig:
        """Create config with specified number of symbols."""
        symbols = []
        for i in range(num_symbols):
            symbols.append(
                SymbolConfig(
                    name=f"SYMBOL{i}",
                    enabled=True,
                    queue_size=1000
                )
            )
        
        return MultiSymbolConfig(
            enabled=True,
            routing_strategy=RoutingStrategy.DIRECT,
            symbols=symbols
        )
        
    def test_routing_throughput(self):
        """Test routing throughput for different symbol counts."""
        results = {}
        
        for num_symbols in [1, 2, 4, 8]:
            config = self.create_config(num_symbols)
            
            # Mock process manager
            pm = Mock()
            pm.workers = {}
            
            # Create mock queues
            for i in range(num_symbols):
                queue = Mock()
                queue.put_nowait = Mock()
                pm.workers[f"SYMBOL{i}"] = Mock(queue=queue)
                
            pm.get_worker_queue = lambda s: pm.workers.get(s, Mock()).queue
            
            # Create router
            router = SymbolRouter(config=config, process_manager=pm)
            
            # Measure throughput
            num_messages = 100000
            start_time = time.time()
            
            for i in range(num_messages):
                msg = Mock(symbol=f"SYMBOL{i % num_symbols}")
                router.route_message(msg)
                
            elapsed = time.time() - start_time
            throughput = num_messages / elapsed
            
            results[num_symbols] = throughput
            
        # Verify near-linear scaling
        # Throughput should not degrade significantly with more symbols
        base_throughput = results[1]
        for num_symbols, throughput in results.items():
            efficiency = throughput / base_throughput
            assert efficiency > 0.9, f"Routing efficiency degraded to {efficiency:.2f} for {num_symbols} symbols"
            
    def test_queue_distribution(self):
        """Test even distribution of messages across workers."""
        config = self.create_config(4)
        
        # Mock process manager and queues
        pm = Mock()
        queue_counts = {}
        
        for i in range(4):
            symbol = f"SYMBOL{i}"
            queue = Mock()
            call_count = 0
            
            def make_put_nowait(sym):
                def put_nowait(msg):
                    queue_counts[sym] = queue_counts.get(sym, 0) + 1
                return put_nowait
                
            queue.put_nowait = make_put_nowait(symbol)
            pm.workers[symbol] = Mock(queue=queue)
            
        pm.get_worker_queue = lambda s: pm.workers.get(s, Mock()).queue
        
        # Create router
        router = SymbolRouter(config=config, process_manager=pm)
        
        # Route messages
        num_messages = 10000
        for i in range(num_messages):
            msg = Mock(symbol=f"SYMBOL{i % 4}")
            router.route_message(msg)
            
        # Check distribution
        expected_per_symbol = num_messages / 4
        for symbol, count in queue_counts.items():
            deviation = abs(count - expected_per_symbol) / expected_per_symbol
            assert deviation < 0.01, f"Uneven distribution for {symbol}: {count} messages"
            
    def test_backpressure_impact(self):
        """Test impact of backpressure on routing performance."""
        config = self.create_config(2)
        
        # Mock process manager
        pm = Mock()
        
        # Create queues with different behaviors
        fast_queue = Mock()
        fast_queue.put_nowait = Mock()  # Always succeeds
        
        slow_queue = Mock()
        slow_queue.put_nowait = Mock(side_effect=Exception("Queue full"))  # Always fails
        
        pm.workers = {
            'SYMBOL0': Mock(queue=fast_queue),
            'SYMBOL1': Mock(queue=slow_queue)
        }
        pm.get_worker_queue = lambda s: pm.workers.get(s, Mock()).queue
        
        # Create router
        router = SymbolRouter(config=config, process_manager=pm)
        
        # Route messages
        num_messages = 1000
        start_time = time.time()
        
        for i in range(num_messages):
            msg = Mock(symbol=f"SYMBOL{i % 2}")
            router.route_message(msg)
            
        elapsed = time.time() - start_time
        
        # Check metrics
        metrics = router.get_metrics()
        assert metrics['total_routed'] == num_messages // 2  # Only fast queue succeeds
        assert metrics['total_dropped'] == num_messages // 2  # Slow queue drops all
        
        # Performance should still be good despite drops
        assert elapsed < 1.0, f"Routing took too long with backpressure: {elapsed:.2f}s"
        
    def test_memory_usage_scaling(self):
        """Test memory usage scales linearly with symbol count."""
        import psutil
        import gc
        
        process = psutil.Process()
        results = {}
        
        for num_symbols in [1, 2, 4]:
            gc.collect()
            
            # Measure baseline memory
            baseline_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            # Create components
            config = self.create_config(num_symbols)
            pm = ProcessManager(
                config=config,
                worker_target=lambda *args: None,
                output_dir="/tmp"
            )
            router = SymbolRouter(config=config, process_manager=pm)
            
            # Measure memory after creation
            gc.collect()
            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_used = current_memory - baseline_memory
            
            results[num_symbols] = memory_used
            
            # Clean up
            del pm
            del router
            
        # Verify linear scaling
        # Memory per symbol should be roughly constant
        if len(results) > 1:
            memory_per_symbol = [results[n] / n for n in results.keys()]
            max_deviation = max(memory_per_symbol) - min(memory_per_symbol)
            avg_memory = sum(memory_per_symbol) / len(memory_per_symbol)
            
            # Allow 20% deviation
            assert max_deviation / avg_memory < 0.2, "Memory usage not scaling linearly"
            
    @pytest.mark.parametrize("routing_strategy", [
        RoutingStrategy.DIRECT,
        RoutingStrategy.HASH,
        RoutingStrategy.ROUND_ROBIN
    ])
    def test_routing_strategy_performance(self, routing_strategy):
        """Test performance of different routing strategies."""
        config = self.create_config(4)
        config.routing_strategy = routing_strategy
        
        # Mock process manager
        pm = Mock()
        pm.workers = {}
        
        for i in range(4):
            queue = Mock()
            queue.put_nowait = Mock()
            pm.workers[f"SYMBOL{i}"] = Mock(queue=queue)
            
        pm.get_worker_queue = lambda s: pm.workers.get(s, Mock()).queue
        
        # Create router
        router = SymbolRouter(config=config, process_manager=pm)
        
        # Measure routing performance
        num_messages = 50000
        start_time = time.time()
        
        for i in range(num_messages):
            if routing_strategy == RoutingStrategy.DIRECT:
                msg = Mock(symbol=f"SYMBOL{i % 4}")
            else:
                msg = Mock(data=f"message_{i}")
            router.route_message(msg)
            
        elapsed = time.time() - start_time
        throughput = num_messages / elapsed
        
        # All strategies should achieve good throughput
        assert throughput > 100000, f"{routing_strategy.value} throughput too low: {throughput:.0f} msg/s"
        
    def test_concurrent_routing(self):
        """Test concurrent message routing from multiple threads."""
        import threading
        
        config = self.create_config(4)
        
        # Mock process manager
        pm = Mock()
        pm.workers = {}
        routed_counts = {}
        
        for i in range(4):
            symbol = f"SYMBOL{i}"
            queue = Mock()
            
            def make_put_nowait(sym):
                def put_nowait(msg):
                    with threading.Lock():
                        routed_counts[sym] = routed_counts.get(sym, 0) + 1
                return put_nowait
                
            queue.put_nowait = make_put_nowait(symbol)
            pm.workers[symbol] = Mock(queue=queue)
            
        pm.get_worker_queue = lambda s: pm.workers.get(s, Mock()).queue
        
        # Create router
        router = SymbolRouter(config=config, process_manager=pm)
        
        # Route messages from multiple threads
        num_threads = 4
        messages_per_thread = 10000
        threads = []
        
        def route_messages(thread_id):
            for i in range(messages_per_thread):
                msg = Mock(symbol=f"SYMBOL{(thread_id + i) % 4}")
                router.route_message(msg)
                
        start_time = time.time()
        
        for i in range(num_threads):
            thread = threading.Thread(target=route_messages, args=(i,))
            thread.start()
            threads.append(thread)
            
        for thread in threads:
            thread.join()
            
        elapsed = time.time() - start_time
        total_messages = num_threads * messages_per_thread
        throughput = total_messages / elapsed
        
        # Verify all messages routed
        total_routed = sum(routed_counts.values())
        assert total_routed == total_messages
        
        # Check performance
        assert throughput > 50000, f"Concurrent routing too slow: {throughput:.0f} msg/s"