"""Integration tests for multi-symbol pipeline."""

import asyncio
import multiprocessing
import time
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import pytest
import yaml

from rlx_datapipe.reconstruction.multi_symbol_main import MultiSymbolPipeline
from rlx_datapipe.reconstruction.config import (
    MultiSymbolConfig, SymbolConfig, RoutingStrategy
)
from rlx_datapipe.reconstruction.process_manager import ProcessManager
from rlx_datapipe.reconstruction.symbol_router import SymbolRouter


class TestMultiSymbolIntegration:
    """Integration tests for the complete multi-symbol pipeline."""
    
    @pytest.fixture
    def config_file(self, tmp_path):
        """Create a test configuration file."""
        config = {
            'multi_symbol': {
                'enabled': True,
                'routing_strategy': 'direct',
                'symbols': [
                    {
                        'name': 'BTC-USDT',
                        'enabled': True,
                        'memory_limit_mb': 512,
                        'queue_size': 100
                    },
                    {
                        'name': 'ETH-USDT', 
                        'enabled': True,
                        'memory_limit_mb': 512,
                        'queue_size': 100
                    }
                ],
                'process_manager': {
                    'health_check_interval_seconds': 1,
                    'restart_delay_seconds': 1,
                    'max_restart_attempts': 2,
                    'shutdown_timeout_seconds': 5
                }
            }
        }
        
        config_path = tmp_path / "test_config.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
            
        return config_path
        
    @pytest.fixture
    def pipeline(self, config_file):
        """Create MultiSymbolPipeline instance."""
        return MultiSymbolPipeline(config_path=config_file)
        
    def test_config_loading(self, pipeline, config_file):
        """Test configuration loading from file."""
        config = pipeline._load_config()
        
        assert config.enabled is True
        assert config.routing_strategy == RoutingStrategy.DIRECT
        assert len(config.symbols) == 2
        assert config.symbols[0].name == 'BTC-USDT'
        assert config.symbols[1].name == 'ETH-USDT'
        
    def test_default_config(self):
        """Test default configuration without file."""
        pipeline = MultiSymbolPipeline()
        config = pipeline._load_config()
        
        assert config.enabled is False  # Single-symbol mode by default
        assert len(config.symbols) == 1
        assert config.symbols[0].name == 'BTCUSDT'
        
    @pytest.mark.asyncio
    async def test_single_symbol_mode(self, pipeline, tmp_path):
        """Test backward compatibility with single-symbol mode."""
        input_path = tmp_path / "input"
        input_path.mkdir()
        output_dir = tmp_path / "output"
        
        # Mock data ingestion
        with patch.object(pipeline, 'data_ingestion') as mock_ingestion:
            mock_ingestion.read_messages = AsyncMock(return_value=iter([]))
            
            # Run in single-symbol mode
            await pipeline.run(
                input_path=input_path,
                output_dir=output_dir,
                symbol='BTCUSDT'
            )
            
            # Check output directory created
            assert (output_dir / 'BTCUSDT').exists()
            
    def test_multi_symbol_components_creation(self, pipeline):
        """Test that multi-symbol components are created properly."""
        pipeline.config = pipeline._load_config()
        
        # Create components
        pm = ProcessManager(
            config=pipeline.config,
            worker_target=lambda *args: None,
            output_dir="/tmp"
        )
        
        router = SymbolRouter(
            config=pipeline.config,
            process_manager=pm
        )
        
        assert isinstance(pm, ProcessManager)
        assert isinstance(router, SymbolRouter)
        assert router.routing_strategy == RoutingStrategy.DIRECT
        
    def test_worker_spawn_count(self, pipeline):
        """Test correct number of workers are spawned."""
        pipeline.config = pipeline._load_config()
        
        pm = ProcessManager(
            config=pipeline.config,
            worker_target=lambda *args: None,
            output_dir="/tmp"
        )
        
        # Mock process creation
        with patch('multiprocessing.Process') as mock_process:
            mock_process.return_value.start = Mock()
            mock_process.return_value.pid = 12345
            mock_process.return_value.is_alive.return_value = True
            
            pm.start_all_workers()
            
            # Should create 2 processes (BTC-USDT and ETH-USDT)
            assert mock_process.call_count == 2
            
    def test_message_routing(self, pipeline):
        """Test messages are routed to correct workers."""
        pipeline.config = pipeline._load_config()
        
        # Create mock workers
        btc_queue = Mock()
        eth_queue = Mock()
        
        pm = Mock()
        pm.workers = {
            'BTC-USDT': Mock(queue=btc_queue),
            'ETH-USDT': Mock(queue=eth_queue)
        }
        pm.get_worker_queue.side_effect = lambda s: {
            'BTC-USDT': btc_queue,
            'ETH-USDT': eth_queue
        }.get(s)
        
        router = SymbolRouter(
            config=pipeline.config,
            process_manager=pm
        )
        
        # Route BTC message
        btc_msg = Mock(symbol='BTC-USDT')
        assert router.route_message(btc_msg) is True
        btc_queue.put_nowait.assert_called_once()
        
        # Route ETH message
        eth_msg = Mock(symbol='ETH-USDT')
        assert router.route_message(eth_msg) is True
        eth_queue.put_nowait.assert_called_once()
        
    def test_worker_crash_recovery(self):
        """Test worker crash detection and recovery."""
        config = MultiSymbolConfig(
            symbols=[SymbolConfig(name='BTC-USDT')],
            process_manager=Mock(
                health_check_interval_seconds=0.1,
                restart_delay_seconds=0.1,
                max_restart_attempts=2
            )
        )
        
        pm = ProcessManager(
            config=config,
            worker_target=lambda *args: None,
            output_dir="/tmp"
        )
        
        # Mock worker process
        mock_process = Mock()
        mock_process.is_alive.return_value = False  # Simulate crash
        mock_process.pid = 12345
        
        # Add worker
        pm.workers['BTC-USDT'] = Mock(
            health=Mock(
                process=mock_process,
                state=pm.workers['BTC-USDT'].health.state if 'BTC-USDT' in pm.workers else None,
                restart_count=0
            ),
            config=config.symbols[0]
        )
        
        # Test restart
        with patch.object(pm, 'start_worker') as mock_start:
            pm.restart_worker('BTC-USDT')
            mock_start.assert_called_once_with('BTC-USDT', config.symbols[0])
            
    def test_graceful_shutdown(self):
        """Test graceful shutdown of all components."""
        config = MultiSymbolConfig(
            symbols=[
                SymbolConfig(name='BTC-USDT'),
                SymbolConfig(name='ETH-USDT')
            ]
        )
        
        pm = ProcessManager(
            config=config,
            worker_target=lambda *args: None,
            output_dir="/tmp"
        )
        
        # Mock workers
        for symbol in ['BTC-USDT', 'ETH-USDT']:
            mock_process = Mock()
            mock_process.is_alive.return_value = True
            pm.workers[symbol] = Mock(
                health=Mock(process=mock_process),
                queue=Mock()
            )
            
        # Test shutdown
        pm.stop_all_workers()
        
        # All workers should be stopped
        for worker in pm.workers.values():
            worker.queue.put_nowait.assert_called_with(None)
            
    @pytest.mark.asyncio
    async def test_backpressure_handling(self, pipeline):
        """Test backpressure detection and handling."""
        pipeline.config = pipeline._load_config()
        
        # Mock components
        pm = Mock()
        router = Mock()
        router.is_backpressure_detected.return_value = True
        
        pipeline.process_manager = pm
        pipeline.symbol_router = router
        pipeline.running = True
        
        # Mock data ingestion with limited messages
        messages = [Mock(symbol='BTC-USDT') for _ in range(10001)]
        pipeline.data_ingestion = Mock()
        pipeline.data_ingestion.read_messages = AsyncMock(
            return_value=iter(messages)
        )
        
        # Track sleep calls
        sleep_called = False
        
        async def mock_sleep(duration):
            nonlocal sleep_called
            sleep_called = True
            pipeline.running = False  # Stop after first sleep
            
        with patch('asyncio.sleep', side_effect=mock_sleep):
            await pipeline.run_multi_symbol(
                input_path=Path('/tmp'),
                output_dir=Path('/tmp'),
                manifest_path=None
            )
            
        # Should detect backpressure and sleep
        assert sleep_called
        
    def test_performance_metrics_collection(self):
        """Test that performance metrics are collected."""
        config = MultiSymbolConfig(
            symbols=[SymbolConfig(name='BTC-USDT')]
        )
        
        pm = ProcessManager(
            config=config,
            worker_target=lambda *args: None,
            output_dir="/tmp"
        )
        
        router = SymbolRouter(config=config, process_manager=pm)
        
        # Route some messages
        for i in range(100):
            msg = Mock(symbol='BTC-USDT')
            router.route_message(msg)
            
        # Check metrics
        metrics = router.get_metrics()
        assert metrics['total_routed'] == 0  # No actual workers
        assert metrics['routing_strategy'] == 'direct'