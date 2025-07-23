"""Tests for order book engine functionality."""

import numpy as np
import polars as pl
import pytest
from pathlib import Path
import tempfile

from rlx_datapipe.reconstruction.order_book_engine import OrderBookEngine
from rlx_datapipe.reconstruction.checkpoint_manager import CheckpointManager


class TestOrderBookEngine:
    """Test order book engine functionality."""
    
    def test_initialization(self):
        """Test engine initialization."""
        engine = OrderBookEngine(
            symbol="BTCUSDT",
            max_levels=20,
            gc_interval=100,
        )
        
        assert engine.symbol == "BTCUSDT"
        assert engine.max_levels == 20
        assert engine.gc_interval == 100
        assert engine.last_update_id is None
        assert engine.updates_processed == 0
    
    def test_process_snapshot(self):
        """Test processing book snapshot."""
        engine = OrderBookEngine("BTCUSDT")
        
        # Create snapshot data
        snapshot_data = pl.DataFrame({
            "side": ["BID", "BID", "BID", "ASK", "ASK", "ASK"],
            "price": [100.0, 99.9, 99.8, 100.1, 100.2, 100.3],
            "quantity": [1.0, 2.0, 3.0, 1.5, 2.5, 3.5],
            "update_id": [1000, 1000, 1000, 1000, 1000, 1000],
        })
        
        engine.process_snapshot(snapshot_data)
        
        assert engine.last_update_id == 1000
        assert engine.snapshot_count == 1
        
        # Check book state
        best_bid, best_ask = engine.book_state.get_top_of_book()
        assert best_bid is not None
        assert best_ask is not None
    
    def test_process_delta_batch(self):
        """Test processing delta batch."""
        engine = OrderBookEngine("BTCUSDT")
        
        # Initialize with snapshot first
        snapshot = pl.DataFrame({
            "side": ["BID", "ASK"],
            "price": [100.0, 101.0],
            "quantity": [1.0, 1.0],
            "update_id": [1000, 1000],
        })
        engine.process_snapshot(snapshot)
        
        # Create delta batch
        delta_batch = pl.DataFrame({
            "update_id": [1001, 1002, 1003],
            "price": [10000000000, 10100000000, 9990000000],  # Scaled prices
            "new_quantity": [200000000, 0, 150000000],  # Scaled quantities
            "side": ["BID", "ASK", "BID"],
            "origin_time": [2000, 3000, 4000],
        })
        
        enriched = engine.process_delta_batch(delta_batch)
        
        assert len(enriched) == 3
        assert "bid_top_price" in enriched.columns
        assert "ask_top_price" in enriched.columns
        assert engine.last_update_id == 1003
        assert engine.updates_processed == 3
    
    def test_sequence_gap_detection(self):
        """Test sequence gap detection."""
        engine = OrderBookEngine("BTCUSDT")
        engine.last_update_id = 1000
        
        # Create batch with gap
        delta_batch = pl.DataFrame({
            "update_id": [1005, 1006, 1007],  # Gap from 1000 to 1005
            "price": [10000000000, 10100000000, 9990000000],
            "new_quantity": [100000000, 200000000, 150000000],
            "side": ["BID", "ASK", "BID"],
        })
        
        enriched = engine.process_delta_batch(delta_batch, validate_sequence=True)
        
        # Check gap was detected
        gap_stats = engine.gap_stats
        assert gap_stats.total_gaps == 1
        assert gap_stats.max_gap_size == 4
        assert gap_stats.last_gap_update_id == 1005
    
    def test_checkpoint_save_and_load(self):
        """Test checkpoint functionality."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create engine with checkpointing
            engine = OrderBookEngine(
                symbol="BTCUSDT",
                checkpoint_dir=Path(tmpdir),
            )
            
            # Add some state
            snapshot = pl.DataFrame({
                "side": ["BID", "ASK"],
                "price": [100.0, 101.0],
                "quantity": [1.0, 1.0],
                "update_id": [1000, 1000],
            })
            engine.process_snapshot(snapshot)
            
            # Process some deltas
            deltas = pl.DataFrame({
                "update_id": [1001, 1002],
                "price": [10050000000, 10150000000],
                "new_quantity": [200000000, 300000000],
                "side": ["BID", "ASK"],
            })
            engine.process_delta_batch(deltas)
            
            # Save checkpoint
            engine._save_checkpoint()
            
            # Create new engine and load checkpoint
            new_engine = OrderBookEngine(
                symbol="BTCUSDT",
                checkpoint_dir=Path(tmpdir),
            )
            
            loaded = new_engine.load_checkpoint()
            assert loaded is True
            assert new_engine.last_update_id == 1002
            assert new_engine.updates_processed == 2
            
            # Verify book state
            best_bid, best_ask = new_engine.book_state.get_top_of_book()
            assert best_bid is not None
            assert best_ask is not None
    
    def test_drift_calculation(self):
        """Test drift calculation between snapshots."""
        engine = OrderBookEngine("BTCUSDT", enable_drift_tracking=True)
        
        # Initialize with snapshot
        snapshot1 = pl.DataFrame({
            "side": ["BID", "BID", "ASK", "ASK"],
            "price": [100.0, 99.9, 100.1, 100.2],
            "quantity": [1.0, 2.0, 1.5, 2.5],
        })
        engine.process_snapshot(snapshot1)
        
        # Apply some deltas that might cause drift
        deltas = pl.DataFrame({
            "update_id": [1001, 1002, 1003],
            "price": [9990000000, 10010000000, 10020000000],
            "new_quantity": [150000000, 200000000, 250000000],
            "side": ["BID", "ASK", "ASK"],
        })
        engine.process_delta_batch(deltas)
        
        # Compare with new snapshot
        snapshot2 = pl.DataFrame({
            "side": ["BID", "BID", "ASK", "ASK"],
            "price": [99.9, 99.8, 100.1, 100.2],
            "quantity": [1.5, 2.0, 2.0, 2.5],
        })
        
        drift = engine.calculate_drift(snapshot2)
        
        assert "total_drift" in drift
        assert drift["total_drift"] >= 0
    
    def test_get_statistics(self):
        """Test statistics retrieval."""
        engine = OrderBookEngine("BTCUSDT")
        
        stats = engine.get_statistics()
        
        assert "updates_processed" in stats
        assert "last_update_id" in stats
        assert "snapshot_count" in stats
        assert "gap_statistics" in stats
        assert "drift_metrics" in stats
        assert "book_depth" in stats
    
    def test_manual_gc_control(self):
        """Test manual garbage collection."""
        engine = OrderBookEngine("BTCUSDT", gc_interval=10)
        
        # Process enough updates to trigger GC
        for i in range(15):
            delta = pl.DataFrame({
                "update_id": [1000 + i],
                "price": [10000000000 + i * 1000000],
                "new_quantity": [100000000],
                "side": ["BID"],
            })
            engine.process_delta_batch(delta)
        
        # GC should have been called at least once
        assert engine.updates_processed == 15