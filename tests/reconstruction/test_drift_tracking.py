"""Test drift tracking and metrics functionality."""

import pytest
from decimal import Decimal

from rlx_datapipe.reconstruction import DriftTracker, OrderBookState


def test_drift_tracker_initialization():
    """Test DriftTracker initialization."""
    tracker = DriftTracker(drift_threshold=0.001)
    
    assert tracker.drift_threshold == 0.001
    assert tracker.drift_history == []
    assert tracker.total_snapshots == 0
    assert tracker.total_resyncs == 0


def test_no_drift_perfect_match():
    """Test drift calculation when books match perfectly."""
    tracker = DriftTracker(drift_threshold=0.001)
    
    # Create identical book states
    book = OrderBookState(max_levels=20)
    book.initialize_from_snapshot({
        "bids": [[49999.0, 1.0], [49998.0, 2.0]],
        "asks": [[50001.0, 1.0], [50002.0, 2.0]]
    })
    
    snapshot_event = {
        "bids": [[49999.0, 1.0], [49998.0, 2.0]],
        "asks": [[50001.0, 1.0], [50002.0, 2.0]]
    }
    
    drift_metrics = tracker.calculate_drift(book, snapshot_event)
    
    assert drift_metrics["rms_error"] == 0.0
    assert drift_metrics["max_deviation"] == 0.0
    assert drift_metrics["exceeds_threshold"] is False
    assert tracker.total_snapshots == 1
    assert tracker.total_resyncs == 0


def test_drift_quantity_mismatch():
    """Test drift calculation with quantity mismatches."""
    tracker = DriftTracker(drift_threshold=0.001)
    
    # Book with different quantities
    book = OrderBookState(max_levels=20)
    book.initialize_from_snapshot({
        "bids": [[49999.0, 1.0], [49998.0, 2.0]],
        "asks": [[50001.0, 1.0], [50002.0, 2.0]]
    })
    
    # Snapshot with different quantities
    snapshot_event = {
        "bids": [[49999.0, 1.1], [49998.0, 2.0]],  # 10% difference on first bid
        "asks": [[50001.0, 1.0], [50002.0, 2.0]]
    }
    
    drift_metrics = tracker.calculate_drift(book, snapshot_event)
    
    assert drift_metrics["rms_error"] > 0.0
    assert drift_metrics["max_deviation"] > 0.0
    # 1.1 vs 1.0: (1.1 - 1.0) / 1.1 = 0.0909...
    assert abs(drift_metrics["bid_max_deviation"] - 0.0909) < 0.001
    assert drift_metrics["exceeds_threshold"] is True
    assert tracker.total_resyncs == 1


def test_drift_missing_levels():
    """Test drift calculation when levels are missing."""
    tracker = DriftTracker(drift_threshold=0.001)
    
    # Book with more levels
    book = OrderBookState(max_levels=20)
    book.initialize_from_snapshot({
        "bids": [[49999.0, 1.0], [49998.0, 2.0], [49997.0, 3.0]],
        "asks": [[50001.0, 1.0]]
    })
    
    # Snapshot with fewer levels
    snapshot_event = {
        "bids": [[49999.0, 1.0]],  # Missing two levels
        "asks": [[50001.0, 1.0]]
    }
    
    drift_metrics = tracker.calculate_drift(book, snapshot_event)
    
    assert drift_metrics["rms_error"] > 0.0
    assert drift_metrics["max_deviation"] == 1.0  # 100% for missing levels
    assert drift_metrics["bid_level_diff"] == 2


def test_drift_statistics():
    """Test drift statistics calculation."""
    tracker = DriftTracker(drift_threshold=0.001)
    
    book = OrderBookState(max_levels=20)
    book.initialize_from_snapshot({
        "bids": [[49999.0, 1.0]],
        "asks": [[50001.0, 1.0]]
    })
    
    # Process multiple snapshots with different drift levels
    snapshots = [
        # Perfect match
        {
            "bids": [[49999.0, 1.0]],
            "asks": [[50001.0, 1.0]]
        },
        # Small drift
        {
            "bids": [[49999.0, 1.001]],
            "asks": [[50001.0, 1.0]]
        },
        # Larger drift
        {
            "bids": [[49999.0, 1.1]],
            "asks": [[50001.0, 1.0]]
        }
    ]
    
    for snapshot in snapshots:
        tracker.calculate_drift(book, snapshot)
    
    stats = tracker.get_statistics()
    
    assert stats["total_snapshots"] == 3
    # Only the larger drift (0.0909) exceeds the 0.001 threshold
    assert stats["total_resyncs"] == 1
    assert stats["avg_rms_error"] > 0.0
    assert stats["max_rms_error"] > stats["min_rms_error"]
    assert stats["resync_rate"] == 1/3
    assert "percentile_95" in stats
    assert "percentile_99" in stats


def test_export_metrics():
    """Test exporting drift metrics for FidelityReporter."""
    tracker = DriftTracker(drift_threshold=0.001)
    
    book = OrderBookState(max_levels=20)
    book.initialize_from_snapshot({
        "bids": [[49999.0, 1.0]],
        "asks": [[50001.0, 1.0]]
    })
    
    # Generate some drift data
    snapshot = {
        "bids": [[49999.0, 1.1]],
        "asks": [[50001.0, 1.0]]
    }
    
    tracker.calculate_drift(book, snapshot)
    
    exported = tracker.export_metrics()
    
    assert len(exported) == 1
    assert exported[0]["metric_type"] == "drift"
    assert exported[0]["threshold"] == 0.001
    assert "rms_error" in exported[0]
    assert "max_deviation" in exported[0]


def test_rms_calculation_formula():
    """Test RMS error calculation follows the specified formula."""
    tracker = DriftTracker(drift_threshold=0.001)
    
    # Simple case for manual calculation
    book = OrderBookState(max_levels=20)
    book.initialize_from_snapshot({
        "bids": [[100.0, 10.0]],  # Single level
        "asks": [[101.0, 10.0]]
    })
    
    # Snapshot with 10% quantity difference
    snapshot_event = {
        "bids": [[100.0, 11.0]],  # 10% more
        "asks": [[101.0, 10.0]]   # Same
    }
    
    drift_metrics = tracker.calculate_drift(book, snapshot_event)
    
    # RMS for bids: sqrt((11-10)^2/11^2) = sqrt(1/121) ≈ 0.0909
    # RMS for asks: 0 (no difference)
    # Combined: sqrt((0.0909^2 + 0^2)/2) ≈ 0.0643
    
    assert abs(drift_metrics["bid_rms"] - 0.0909) < 0.001
    assert drift_metrics["ask_rms"] == 0.0
    assert abs(drift_metrics["rms_error"] - 0.0643) < 0.001


def test_drift_threshold_boundary():
    """Test behavior at drift threshold boundary."""
    tracker = DriftTracker(drift_threshold=0.05)  # 5% threshold
    
    book = OrderBookState(max_levels=20)
    book.initialize_from_snapshot({
        "bids": [[100.0, 10.0]],
        "asks": [[101.0, 10.0]]
    })
    
    # Just below threshold: (10.49 - 10.0) / 10.49 = 0.0467
    snapshot1 = {
        "bids": [[100.0, 10.49]],  # ~4.67% difference
        "asks": [[101.0, 10.0]]
    }
    
    drift1 = tracker.calculate_drift(book, snapshot1)
    assert drift1["exceeds_threshold"] is False
    assert drift1["bid_rms"] < 0.05
    
    # Above threshold: combined RMS = sqrt((bid_rms^2 + ask_rms^2) / 2)
    # Need bid_rms > 0.07 to get combined > 0.05
    snapshot2 = {
        "bids": [[100.0, 10.8]],  # ~7.4% difference
        "asks": [[101.0, 10.0]]
    }
    
    drift2 = tracker.calculate_drift(book, snapshot2)
    assert drift2["exceeds_threshold"] is True
    # Combined RMS = sqrt((0.074^2 + 0^2) / 2) ≈ 0.052