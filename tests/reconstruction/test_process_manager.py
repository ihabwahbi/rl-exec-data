"""Tests for the ProcessManager class."""

import multiprocessing
import time
import pytest
from unittest.mock import Mock, patch
from multiprocessing import Queue, Event

from rlx_datapipe.reconstruction.process_manager import (
    ProcessManager, WorkerState, WorkerHealth, WorkerInfo
)
from rlx_datapipe.reconstruction.config import (
    MultiSymbolConfig, SymbolConfig, ProcessManagerConfig
)


def dummy_worker(symbol: str, queue: Queue, config: SymbolConfig, shutdown_event: Event):
    """Dummy worker function for testing."""
    while not shutdown_event.is_set():
        try:
            msg = queue.get(timeout=0.1)
            if msg is None:
                break
        except:
            continue
            

class TestProcessManager:
    """Tests for ProcessManager functionality."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return MultiSymbolConfig(
            enabled=True,
            symbols=[
                SymbolConfig(name="BTC-USDT", enabled=True, queue_size=10),
                SymbolConfig(name="ETH-USDT", enabled=True, queue_size=10)
            ],
            process_manager=ProcessManagerConfig(
                health_check_interval_seconds=1,
                restart_delay_seconds=1,
                max_restart_attempts=2,
                shutdown_timeout_seconds=5
            )
        )
        
    @pytest.fixture
    def manager(self, config):
        """Create ProcessManager instance."""
        return ProcessManager(config, dummy_worker)
        
    def test_init(self, manager, config):
        """Test ProcessManager initialization."""
        assert manager.config == config
        assert manager.worker_target == dummy_worker
        assert len(manager.workers) == 0
        assert not manager.running
        
    def test_start_worker(self, manager):
        """Test starting a single worker."""
        symbol = "BTC-USDT"
        config = SymbolConfig(name=symbol, queue_size=10)
        
        manager.start_worker(symbol, config)
        
        # Check worker was created
        assert symbol in manager.workers
        worker = manager.workers[symbol]
        assert worker.symbol == symbol
        assert worker.config == config
        assert worker.queue is not None
        assert worker.health.state == WorkerState.INITIALIZING
        assert worker.health.process.is_alive()
        
        # Cleanup
        manager.stop_worker(symbol)
        
    def test_start_duplicate_worker(self, manager, caplog):
        """Test starting duplicate worker logs warning."""
        symbol = "BTC-USDT"
        config = SymbolConfig(name=symbol)
        
        manager.start_worker(symbol, config)
        manager.start_worker(symbol, config)  # Duplicate
        
        assert f"Worker for {symbol} already exists" in caplog.text
        
        # Cleanup
        manager.stop_worker(symbol)
        
    def test_stop_worker(self, manager):
        """Test stopping a worker gracefully."""
        symbol = "BTC-USDT"
        config = SymbolConfig(name=symbol)
        
        manager.start_worker(symbol, config)
        worker = manager.workers[symbol]
        
        manager.stop_worker(symbol)
        
        # Check worker stopped
        assert worker.health.state == WorkerState.STOPPED
        assert not worker.health.process.is_alive()
        
    def test_stop_nonexistent_worker(self, manager, caplog):
        """Test stopping non-existent worker logs warning."""
        manager.stop_worker("INVALID")
        assert "No worker found for INVALID" in caplog.text
        
    def test_start_all_workers(self, manager, config):
        """Test starting all configured workers."""
        manager.start_all_workers()
        
        # Check all enabled symbols have workers
        for symbol_config in config.symbols:
            if symbol_config.enabled:
                assert symbol_config.name in manager.workers
                assert manager.workers[symbol_config.name].health.process.is_alive()
                
        # Cleanup
        manager.stop_all_workers()
        
    def test_stop_all_workers(self, manager, config):
        """Test stopping all workers."""
        manager.start_all_workers()
        manager.stop_all_workers()
        
        # Check all workers stopped
        assert len(manager.workers) == 0
        
    def test_restart_worker(self, manager):
        """Test restarting a crashed worker."""
        symbol = "BTC-USDT"
        config = SymbolConfig(name=symbol)
        
        manager.start_worker(symbol, config)
        original_pid = manager.workers[symbol].process_id
        
        # Simulate crash
        manager.workers[symbol].health.state = WorkerState.CRASHED
        
        # Restart
        manager.restart_worker(symbol)
        
        # Check new process started
        assert symbol in manager.workers
        assert manager.workers[symbol].process_id != original_pid
        assert manager.workers[symbol].health.restart_count == 1
        
        # Cleanup
        manager.stop_worker(symbol)
        
    def test_restart_limit(self, manager, config):
        """Test restart limit enforcement."""
        symbol = "BTC-USDT"
        symbol_config = SymbolConfig(name=symbol)
        
        manager.start_worker(symbol, symbol_config)
        
        # Exceed restart limit
        worker = manager.workers[symbol]
        worker.health.restart_count = config.process_manager.max_restart_attempts + 1
        
        manager.restart_worker(symbol)
        
        # Check worker marked as stopped
        assert worker.health.state == WorkerState.STOPPED
        
    def test_get_worker_queue(self, manager):
        """Test getting worker queue."""
        symbol = "BTC-USDT"
        config = SymbolConfig(name=symbol)
        
        manager.start_worker(symbol, config)
        
        queue = manager.get_worker_queue(symbol)
        assert queue is not None
        assert queue == manager.workers[symbol].queue
        
        # Test non-existent worker
        assert manager.get_worker_queue("INVALID") is None
        
        # Cleanup
        manager.stop_worker(symbol)
        
    def test_get_worker_stats(self, manager):
        """Test getting worker statistics."""
        symbol = "BTC-USDT"
        config = SymbolConfig(name=symbol)
        
        manager.start_worker(symbol, config)
        
        stats = manager.get_worker_stats()
        assert symbol in stats
        assert 'state' in stats[symbol]
        assert 'messages_processed' in stats[symbol]
        assert 'process_id' in stats[symbol]
        
        # Cleanup
        manager.stop_worker(symbol)
        
    def test_add_symbol(self, manager):
        """Test dynamically adding a symbol."""
        symbol = "XRP-USDT"
        config = SymbolConfig(name=symbol)
        
        manager.add_symbol(symbol, config)
        
        assert symbol in manager.workers
        assert manager.workers[symbol].health.process.is_alive()
        
        # Cleanup
        manager.stop_worker(symbol)
        
    def test_remove_symbol(self, manager):
        """Test dynamically removing a symbol."""
        symbol = "BTC-USDT"
        config = SymbolConfig(name=symbol)
        
        manager.start_worker(symbol, config)
        manager.remove_symbol(symbol)
        
        assert symbol not in manager.workers
        
    def test_cpu_affinity(self, manager):
        """Test CPU affinity setting."""
        symbol = "BTC-USDT"
        config = SymbolConfig(name=symbol, cpu_affinity=[0, 1])
        
        with patch('os.sched_setaffinity') as mock_affinity:
            manager.start_worker(symbol, config)
            
            # Check affinity was set
            if hasattr(os, 'sched_setaffinity'):
                mock_affinity.assert_called_once()
                
        # Cleanup
        manager.stop_worker(symbol)
        
    def test_memory_limit(self, manager):
        """Test memory limit setting."""
        # This test would require running in worker process
        # Just test the wrapper function
        manager._set_memory_limit(1024)  # Should not raise
        
    def test_process_lifecycle(self, manager, config):
        """Test complete process manager lifecycle."""
        # Start
        manager.start()
        assert manager.running
        
        # Check workers started
        time.sleep(0.5)  # Give workers time to start
        for symbol_config in config.symbols:
            if symbol_config.enabled:
                assert symbol_config.name in manager.workers
                
        # Stop
        manager.stop()
        assert not manager.running
        assert len(manager.workers) == 0