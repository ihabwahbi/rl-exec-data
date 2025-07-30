"""Unit tests for OrderBookSynchronizer."""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from rlx_datapipe.capture.orderbook_sync import OrderBookSynchronizer, OrderBookSnapshot


class TestOrderBookSynchronizer:
    """Test cases for OrderBookSynchronizer."""
    
    @pytest.fixture
    def synchronizer(self):
        """Create OrderBookSynchronizer instance."""
        return OrderBookSynchronizer("BTCUSDT")
        
    def test_buffer_update(self, synchronizer):
        """Test buffering updates."""
        update1 = {"first_update_id": 100, "final_update_id": 105}
        update2 = {"first_update_id": 106, "final_update_id": 110}
        
        synchronizer.buffer_update(update1)
        synchronizer.buffer_update(update2)
        
        assert len(synchronizer._buffer) == 2
        assert synchronizer._buffer[0] == update1
        assert synchronizer._buffer[1] == update2
        
    @pytest.mark.asyncio
    async def test_fetch_snapshot_success(self, synchronizer):
        """Test successful snapshot fetch."""
        mock_response = {
            "lastUpdateId": 1000,
            "bids": [["50000.00", "0.1"], ["49999.00", "0.2"]],
            "asks": [["50001.00", "0.1"], ["50002.00", "0.2"]]
        }
        
        # Mock the entire aiohttp flow
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response)
        
        mock_get = MagicMock()
        mock_get.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get.__aexit__ = AsyncMock(return_value=None)
        
        mock_sess = MagicMock()
        mock_sess.get = MagicMock(return_value=mock_get)
        
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_sess)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session_ctx):
            
            snapshot = await synchronizer.fetch_snapshot()
            
            assert snapshot.symbol == "BTCUSDT"
            assert snapshot.last_update_id == 1000
            assert len(snapshot.bids) == 2
            assert len(snapshot.asks) == 2
            
    @pytest.mark.asyncio
    async def test_fetch_snapshot_failure(self, synchronizer):
        """Test snapshot fetch failure."""
        # Mock the entire aiohttp flow with error
        mock_resp = AsyncMock()
        mock_resp.status = 500
        
        mock_get = MagicMock()
        mock_get.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get.__aexit__ = AsyncMock(return_value=None)
        
        mock_sess = MagicMock()
        mock_sess.get = MagicMock(return_value=mock_get)
        
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_sess)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session_ctx):
            
            with pytest.raises(Exception, match="REST API error: 500"):
                await synchronizer.fetch_snapshot()
                
    def test_check_synchronization_success(self, synchronizer):
        """Test successful synchronization check."""
        # Set snapshot
        synchronizer._snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            last_update_id=1000,
            bids=[],
            asks=[]
        )
        
        # Add updates to buffer
        synchronizer.buffer_update({"first_update_id": 999, "final_update_id": 1001})
        synchronizer.buffer_update({"first_update_id": 1002, "final_update_id": 1005})
        
        # Check synchronization
        result = synchronizer._check_synchronization()
        assert result == True
        
    def test_check_synchronization_gap(self, synchronizer):
        """Test synchronization check with gap."""
        # Set snapshot
        synchronizer._snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            last_update_id=1000,
            bids=[],
            asks=[]
        )
        
        # Add update with gap
        synchronizer.buffer_update({"first_update_id": 1005, "final_update_id": 1010})
        
        # Check synchronization
        result = synchronizer._check_synchronization()
        assert result == False
        
    def test_check_synchronization_old_updates(self, synchronizer):
        """Test synchronization check discards old updates."""
        # Set snapshot
        synchronizer._snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            last_update_id=1000,
            bids=[],
            asks=[]
        )
        
        # Add old and valid updates
        synchronizer.buffer_update({"first_update_id": 990, "final_update_id": 995})
        synchronizer.buffer_update({"first_update_id": 996, "final_update_id": 999})
        synchronizer.buffer_update({"first_update_id": 1000, "final_update_id": 1005})
        
        # Check synchronization
        result = synchronizer._check_synchronization()
        
        # Should discard old updates and succeed
        assert result == True
        assert len(synchronizer._buffer) == 1
        
    def test_process_update_not_synced(self, synchronizer):
        """Test processing update when not synchronized."""
        update = {"first_update_id": 100, "final_update_id": 105}
        
        result = synchronizer.process_update(update)
        
        assert result is None
        assert len(synchronizer._buffer) == 1
        
    def test_process_update_synced(self, synchronizer):
        """Test processing update when synchronized."""
        # Set up synchronized state
        synchronizer._snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            last_update_id=1000,
            bids=[],
            asks=[]
        )
        synchronizer._is_synced = True
        
        # Process valid update
        update = {"first_update_id": 1001, "final_update_id": 1005}
        result = synchronizer.process_update(update)
        
        assert result == update
        assert synchronizer._snapshot.last_update_id == 1005
        
    def test_process_update_sequence_gap(self, synchronizer):
        """Test processing update with sequence gap."""
        # Set up synchronized state
        synchronizer._snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            last_update_id=1000,
            bids=[],
            asks=[]
        )
        synchronizer._is_synced = True
        
        # Process update with gap
        update = {"first_update_id": 1005, "final_update_id": 1010}
        
        with patch('asyncio.create_task'):
            result = synchronizer.process_update(update)
            
            assert result is None
            assert synchronizer._is_synced == False
            assert len(synchronizer._buffer) == 1
            
    def test_is_synchronized(self, synchronizer):
        """Test synchronization status check."""
        assert synchronizer.is_synchronized() == False
        
        synchronizer._is_synced = True
        assert synchronizer.is_synchronized() == True
        
    def test_get_snapshot(self, synchronizer):
        """Test getting current snapshot."""
        assert synchronizer.get_snapshot() is None
        
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            last_update_id=1000,
            bids=[],
            asks=[]
        )
        synchronizer._snapshot = snapshot
        
        assert synchronizer.get_snapshot() == snapshot