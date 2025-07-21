"""Unit tests for data loaders."""

import pytest
import json
import gzip
import tempfile
from pathlib import Path
import numpy as np
from rlx_datapipe.validation.loaders import GoldenSampleLoader


class TestGoldenSampleLoader:
    """Test GoldenSampleLoader class."""
    
    @pytest.fixture
    def sample_messages(self):
        """Create sample messages for testing."""
        messages = [
            {
                "capture_ns": 1000000000,
                "stream": "btcusdt@trade",
                "data": {
                    "e": "trade",
                    "E": 1234567890,
                    "s": "BTCUSDT",
                    "t": 12345,
                    "p": "50000.00",
                    "q": "0.001",
                    "T": 1234567890123,
                    "m": True
                }
            },
            {
                "capture_ns": 1000000100,
                "stream": "btcusdt@depth@100ms",
                "data": {
                    "e": "depthUpdate",
                    "E": 1234567891,
                    "s": "BTCUSDT",
                    "U": 1000,
                    "u": 1010,
                    "b": [["49999.00", "0.5"], ["49998.00", "1.0"]],
                    "a": [["50001.00", "0.5"], ["50002.00", "1.0"]]
                }
            },
            {
                "capture_ns": 1000000200,
                "stream": "btcusdt@trade",
                "data": {
                    "e": "trade",
                    "E": 1234567892,
                    "s": "BTCUSDT",
                    "t": 12346,
                    "p": "50001.00",
                    "q": "0.002",
                    "T": 1234567892123,
                    "m": False
                }
            }
        ]
        return messages
    
    @pytest.fixture
    def sample_file(self, sample_messages):
        """Create a temporary sample file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            for msg in sample_messages:
                f.write(json.dumps(msg) + '\n')
            temp_path = Path(f.name)
        
        yield temp_path
        temp_path.unlink()
    
    @pytest.fixture
    def sample_gz_file(self, sample_messages):
        """Create a temporary gzipped sample file."""
        with tempfile.NamedTemporaryFile(suffix='.jsonl.gz', delete=False) as f:
            temp_path = Path(f.name)
        
        with gzip.open(temp_path, 'wt') as f:
            for msg in sample_messages:
                f.write(json.dumps(msg) + '\n')
        
        yield temp_path
        temp_path.unlink()
    
    def test_loader_initialization(self):
        """Test loader initialization."""
        loader = GoldenSampleLoader(buffer_size=5000)
        assert loader.buffer_size == 5000
        assert loader._total_messages == 0
        assert loader._message_counts == {}
    
    def test_load_messages_from_jsonl(self, sample_file):
        """Test loading messages from JSONL file."""
        loader = GoldenSampleLoader()
        messages = list(loader.load_messages(sample_file, show_progress=False))
        
        assert len(messages) == 3
        assert messages[0]['stream'] == 'btcusdt@trade'
        assert messages[1]['stream'] == 'btcusdt@depth@100ms'
        assert messages[2]['stream'] == 'btcusdt@trade'
        
        # Check statistics
        stats = loader.get_statistics()
        assert stats['total_messages'] == 3
        assert stats['message_counts']['trade'] == 2
        assert stats['message_counts']['depth@100ms'] == 1
    
    def test_load_messages_from_gzip(self, sample_gz_file):
        """Test loading messages from gzipped file."""
        loader = GoldenSampleLoader()
        messages = list(loader.load_messages(sample_gz_file, show_progress=False))
        
        assert len(messages) == 3
        assert all('capture_ns' in msg for msg in messages)
        assert all('stream' in msg for msg in messages)
        assert all('data' in msg for msg in messages)
    
    def test_load_messages_with_filter(self, sample_file):
        """Test loading messages with filter."""
        loader = GoldenSampleLoader()
        
        # Filter for trade messages only
        def trade_filter(msg):
            return '@trade' in msg['stream']
        
        messages = list(loader.load_messages(sample_file, 
                                           message_filter=trade_filter,
                                           show_progress=False))
        
        assert len(messages) == 2
        assert all('@trade' in msg['stream'] for msg in messages)
    
    def test_extract_trades(self, sample_file):
        """Test extracting trade sizes."""
        loader = GoldenSampleLoader()
        
        # Collect all trade sizes
        all_trades = []
        for batch in loader.extract_trades(sample_file):
            all_trades.extend(batch)
        
        assert len(all_trades) == 2
        assert all_trades[0] == 0.001
        assert all_trades[1] == 0.002
    
    def test_extract_trades_with_time_range(self, sample_file):
        """Test extracting trades with time range."""
        loader = GoldenSampleLoader()
        
        # Only get trades after first message
        all_trades = []
        for batch in loader.extract_trades(sample_file, start_ns=1000000150):
            all_trades.extend(batch)
        
        assert len(all_trades) == 1
        assert all_trades[0] == 0.002
    
    def test_extract_prices(self, sample_file):
        """Test extracting prices."""
        loader = GoldenSampleLoader()
        
        # Extract trade prices
        all_prices = []
        for batch in loader.extract_prices(sample_file, message_type='trade'):
            all_prices.extend(batch)
        
        assert len(all_prices) == 2
        assert all_prices[0] == 50000.00
        assert all_prices[1] == 50001.00
    
    def test_extract_orderbook_prices(self, sample_file):
        """Test extracting orderbook prices."""
        loader = GoldenSampleLoader()
        
        # Extract depth prices (best bid)
        all_prices = []
        for batch in loader.extract_prices(sample_file, message_type='depth'):
            all_prices.extend(batch)
        
        assert len(all_prices) == 1
        assert all_prices[0] == 49999.00
    
    def test_extract_orderbook_updates(self, sample_file):
        """Test extracting orderbook updates."""
        loader = GoldenSampleLoader()
        
        updates = list(loader.extract_orderbook_updates(sample_file))
        
        assert len(updates) == 1
        assert updates[0]['stream'] == 'btcusdt@depth@100ms'
        assert 'U' in updates[0]['data']
        assert 'u' in updates[0]['data']
    
    def test_load_all_trades(self, sample_file):
        """Test loading all trades at once."""
        loader = GoldenSampleLoader()
        trades = loader.load_all_trades(sample_file)
        
        assert isinstance(trades, np.ndarray)
        assert len(trades) == 2
        assert trades[0] == 0.001
        assert trades[1] == 0.002
    
    def test_load_all_prices(self, sample_file):
        """Test loading all prices at once."""
        loader = GoldenSampleLoader()
        prices = loader.load_all_prices(sample_file, message_type='trade')
        
        assert isinstance(prices, np.ndarray)
        assert len(prices) == 2
        assert prices[0] == 50000.00
        assert prices[1] == 50001.00
    
    def test_file_not_found(self):
        """Test handling of missing file."""
        loader = GoldenSampleLoader()
        
        with pytest.raises(FileNotFoundError):
            list(loader.load_messages(Path("nonexistent.jsonl")))
    
    def test_invalid_json_handling(self):
        """Test handling of invalid JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"valid": "json"}\n')
            f.write('invalid json\n')
            f.write('{"another": "valid"}\n')
            temp_path = Path(f.name)
        
        try:
            loader = GoldenSampleLoader()
            messages = list(loader.load_messages(temp_path, show_progress=False))
            
            # Should skip the invalid line
            assert len(messages) == 2
            assert messages[0]['valid'] == 'json'
            assert messages[1]['another'] == 'valid'
        finally:
            temp_path.unlink()
    
    def test_large_file_buffering(self):
        """Test buffering with large number of trades."""
        # Create file with many trades
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            for i in range(100):
                msg = {
                    "capture_ns": 1000000000 + i,
                    "stream": "btcusdt@trade",
                    "data": {"q": str(0.001 * (i + 1))}
                }
                f.write(json.dumps(msg) + '\n')
            temp_path = Path(f.name)
        
        try:
            loader = GoldenSampleLoader(buffer_size=10)
            batches = list(loader.extract_trades(temp_path))
            
            # Should have multiple batches
            assert len(batches) > 1
            assert all(len(batch) <= 10 for batch in batches[:-1])
            
            # Total should be 100
            total = sum(len(batch) for batch in batches)
            assert total == 100
        finally:
            temp_path.unlink()