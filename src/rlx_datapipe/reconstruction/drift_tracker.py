"""Drift tracking for order book reconstruction accuracy.

Monitors drift between reconstructed book state and snapshots,
calculating RMS error and triggering resynchronization when needed.
"""

from decimal import Decimal
from typing import Dict, List, Tuple, Any
import math
from loguru import logger

from .order_book_state import OrderBookState


class DriftTracker:
    """Tracks drift between reconstructed and snapshot book states.
    
    Calculates various drift metrics including RMS error and maximum
    level deviation to ensure reconstruction accuracy.
    """
    
    def __init__(self, drift_threshold: float = 0.001):
        """Initialize drift tracker.
        
        Args:
            drift_threshold: RMS error threshold for triggering resync
        """
        self.drift_threshold = drift_threshold
        self.drift_history: List[Dict[str, float]] = []
        self.total_snapshots = 0
        self.total_resyncs = 0
        
    def calculate_drift(
        self,
        reconstructed_book: OrderBookState,
        snapshot_event: Dict[str, Any]
    ) -> Dict[str, float]:
        """Calculate drift metrics between reconstructed and snapshot books.
        
        Args:
            reconstructed_book: Current reconstructed book state
            snapshot_event: Snapshot event with true book state
            
        Returns:
            Dict with drift metrics including RMS error
        """
        self.total_snapshots += 1
        
        # Extract snapshot levels
        snapshot_bids = snapshot_event.get("bids", [])
        snapshot_asks = snapshot_event.get("asks", [])
        
        # Get reconstructed levels
        recon_bids = reconstructed_book.get_bid_levels()
        recon_asks = reconstructed_book.get_ask_levels()
        
        # Calculate drift metrics
        bid_rms = self._calculate_rms_error(recon_bids, snapshot_bids)
        ask_rms = self._calculate_rms_error(recon_asks, snapshot_asks)
        
        # Combined RMS error
        combined_rms = math.sqrt((bid_rms ** 2 + ask_rms ** 2) / 2)
        
        # Maximum level deviation
        bid_max_dev = self._calculate_max_deviation(recon_bids, snapshot_bids)
        ask_max_dev = self._calculate_max_deviation(recon_asks, snapshot_asks)
        max_deviation = max(bid_max_dev, ask_max_dev)
        
        # Level count differences
        bid_count_diff = abs(len(recon_bids) - len(snapshot_bids))
        ask_count_diff = abs(len(recon_asks) - len(snapshot_asks))
        
        metrics = {
            "rms_error": combined_rms,
            "bid_rms": bid_rms,
            "ask_rms": ask_rms,
            "max_deviation": max_deviation,
            "bid_max_deviation": bid_max_dev,
            "ask_max_deviation": ask_max_dev,
            "bid_level_diff": bid_count_diff,
            "ask_level_diff": ask_count_diff,
            "snapshot_number": self.total_snapshots,
            "exceeds_threshold": combined_rms > self.drift_threshold
        }
        
        # Log if drift exceeds threshold
        if metrics["exceeds_threshold"]:
            logger.warning(
                f"Drift threshold exceeded - RMS: {combined_rms:.6f}, "
                f"Max deviation: {max_deviation:.6f}"
            )
            self.total_resyncs += 1
        
        # Store in history
        self.drift_history.append(metrics)
        
        return metrics
    
    def _calculate_rms_error(
        self,
        reconstructed: List[Tuple[Decimal, Decimal]],
        snapshot: List[List[Any]]
    ) -> float:
        """Calculate RMS error between price levels.
        
        Formula: sqrt(mean((snapshot_prices - reconstructed_prices)^2 / snapshot_prices^2))
        
        Args:
            reconstructed: Reconstructed levels as [(price, qty)]
            snapshot: Snapshot levels as [[price, qty]]
            
        Returns:
            RMS error as percentage (0.001 = 0.1%)
        """
        if not snapshot:
            return 0.0 if not reconstructed else 1.0
        
        # Convert to dicts for easier comparison
        recon_dict = {price: qty for price, qty in reconstructed}
        snap_dict = {}
        
        for level in snapshot:
            if isinstance(level, list) and len(level) >= 2:
                price = Decimal(str(level[0]))
                qty = Decimal(str(level[1]))
                snap_dict[price] = qty
        
        # Calculate squared relative errors
        squared_errors = []
        
        # Check all snapshot prices
        for price, snap_qty in snap_dict.items():
            # Convert price to match reconstructed format
            price_float = float(price)
            recon_qty = recon_dict.get(price_float, 0.0)
            
            if snap_qty != 0:
                # Relative error on quantity
                snap_qty_float = float(snap_qty)
                recon_qty_float = float(recon_qty)
                rel_error = (snap_qty_float - recon_qty_float) / snap_qty_float
                squared_errors.append(rel_error ** 2)
            elif recon_qty != 0:
                # Snapshot has 0 but reconstructed doesn't
                squared_errors.append(1.0)
        
        # Check for extra reconstructed levels
        for price, recon_qty in recon_dict.items():
            price_decimal = Decimal(str(price))
            if price_decimal not in snap_dict and recon_qty != 0:
                # Level exists in reconstructed but not snapshot
                squared_errors.append(1.0)
        
        if not squared_errors:
            return 0.0
        
        # RMS calculation
        mean_squared_error = sum(squared_errors) / len(squared_errors)
        return math.sqrt(mean_squared_error)
    
    def _calculate_max_deviation(
        self,
        reconstructed: List[Tuple[Decimal, Decimal]],
        snapshot: List[List[Any]]
    ) -> float:
        """Calculate maximum deviation between levels.
        
        Args:
            reconstructed: Reconstructed levels
            snapshot: Snapshot levels
            
        Returns:
            Maximum relative deviation
        """
        if not snapshot and not reconstructed:
            return 0.0
        
        max_deviation = 0.0
        
        # Convert snapshot to dict
        snap_dict = {}
        for level in snapshot:
            if isinstance(level, list) and len(level) >= 2:
                price = Decimal(str(level[0]))
                qty = Decimal(str(level[1]))
                snap_dict[price] = qty
        
        # Check each reconstructed level
        for price, recon_qty in reconstructed:
            price_decimal = Decimal(str(price))
            snap_qty = snap_dict.get(price_decimal, Decimal(0))
            
            if snap_qty != 0:
                snap_qty_float = float(snap_qty)
                recon_qty_float = float(recon_qty)
                deviation = abs((recon_qty_float - snap_qty_float) / snap_qty_float)
                max_deviation = max(max_deviation, deviation)
            elif recon_qty != 0:
                # No snapshot level but reconstructed has quantity
                max_deviation = max(max_deviation, 1.0)
        
        # Check snapshot levels not in reconstructed
        recon_prices = {Decimal(str(price)) for price, _ in reconstructed}
        for price, snap_qty in snap_dict.items():
            if price not in recon_prices and snap_qty != 0:
                max_deviation = max(max_deviation, 1.0)
        
        return max_deviation
    
    def get_statistics(self) -> Dict[str, float]:
        """Get drift statistics summary.
        
        Returns:
            Dict with statistical summary of drift metrics
        """
        if not self.drift_history:
            return {
                "avg_rms_error": 0.0,
                "max_rms_error": 0.0,
                "min_rms_error": 0.0,
                "total_snapshots": 0,
                "total_resyncs": 0,
                "resync_rate": 0.0
            }
        
        rms_errors = [m["rms_error"] for m in self.drift_history]
        
        return {
            "avg_rms_error": sum(rms_errors) / len(rms_errors),
            "max_rms_error": max(rms_errors),
            "min_rms_error": min(rms_errors),
            "total_snapshots": self.total_snapshots,
            "total_resyncs": self.total_resyncs,
            "resync_rate": self.total_resyncs / self.total_snapshots if self.total_snapshots > 0 else 0.0,
            "percentile_95": self._calculate_percentile(rms_errors, 0.95),
            "percentile_99": self._calculate_percentile(rms_errors, 0.99)
        }
    
    def _calculate_percentile(self, values: List[float], percentile: float) -> float:
        """Calculate percentile value.
        
        Args:
            values: List of values
            percentile: Percentile to calculate (0-1)
            
        Returns:
            Percentile value
        """
        if not values:
            return 0.0
        
        sorted_values = sorted(values)
        index = int(percentile * (len(sorted_values) - 1))
        return sorted_values[index]
    
    def export_metrics(self) -> List[Dict[str, Any]]:
        """Export drift metrics for FidelityReporter.
        
        Returns:
            List of drift metrics with metadata
        """
        return [
            {
                **metric,
                "timestamp": metric.get("timestamp", 0),
                "metric_type": "drift",
                "threshold": self.drift_threshold
            }
            for metric in self.drift_history
        ]