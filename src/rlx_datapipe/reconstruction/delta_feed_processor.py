"""Delta feed processor with sequence validation and gap detection."""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import polars as pl
from loguru import logger


@dataclass
class SequenceGapInfo:
    """Information about a detected sequence gap."""
    
    expected_id: int
    actual_id: int
    gap_size: int
    timestamp: float
    origin_time: Optional[int] = None
    
    def __str__(self) -> str:
        return (
            f"Gap: expected={self.expected_id}, actual={self.actual_id}, "
            f"size={self.gap_size}, time={self.timestamp}"
        )


@dataclass
class ProcessingStats:
    """Statistics for delta feed processing."""
    
    total_deltas: int = 0
    total_gaps: int = 0
    max_gap_size: int = 0
    gaps_over_threshold: int = 0
    processing_time: float = 0.0
    throughput: float = 0.0
    gap_history: List[SequenceGapInfo] = field(default_factory=list)
    
    def update_throughput(self, elapsed_time: float) -> None:
        """Update throughput calculation."""
        if elapsed_time > 0:
            self.throughput = self.total_deltas / elapsed_time


class DeltaFeedProcessor:
    """Processes delta feeds with strict sequence validation."""
    
    def __init__(
        self,
        gap_threshold: int = 1000,
        store_gap_history: bool = True,
        max_gap_history: int = 1000,
    ):
        """
        Initialize delta feed processor.
        
        Args:
            gap_threshold: Threshold for signaling recovery (default 1000)
            store_gap_history: Whether to store detailed gap history
            max_gap_history: Maximum number of gaps to store in history
        """
        self.gap_threshold = gap_threshold
        self.store_gap_history = store_gap_history
        self.max_gap_history = max_gap_history
        
        # Sequence tracking
        self.last_update_id: Optional[int] = None
        self.expected_next_id: Optional[int] = None
        
        # Statistics
        self.stats = ProcessingStats()
        
        # Gap detection
        self.gaps_by_size: Dict[int, int] = {}
        self.recovery_needed = False
        
        logger.info(
            f"DeltaFeedProcessor initialized with gap_threshold={gap_threshold}"
        )
    
    def validate_and_sort(
        self,
        delta_batch: pl.DataFrame,
        enforce_monotonic: bool = True,
    ) -> Tuple[pl.DataFrame, List[SequenceGapInfo]]:
        """
        Validate and sort delta batch by update_id.
        
        Args:
            delta_batch: DataFrame with delta updates
            enforce_monotonic: Whether to enforce strict monotonic ordering
            
        Returns:
            Tuple of (sorted DataFrame, list of detected gaps)
        """
        start_time = time.time()
        detected_gaps = []
        
        try:
            # Ensure update_id column exists
            if "update_id" not in delta_batch.columns:
                raise ValueError("Delta batch missing required 'update_id' column")
            
            # Sort by update_id
            sorted_batch = delta_batch.sort("update_id")
            
            # Get update_id array for validation
            update_ids = sorted_batch["update_id"].to_numpy()
            
            if len(update_ids) == 0:
                logger.warning("Empty delta batch received")
                return sorted_batch, detected_gaps
            
            # Validate monotonic sequence
            if enforce_monotonic:
                origin_times = sorted_batch.get_column("origin_time") if "origin_time" in sorted_batch.columns else None
                gaps_found = self._validate_sequence(
                    update_ids,
                    origin_times,
                    detected_gaps,
                )
                
                if gaps_found:
                    logger.warning(
                        f"Found {len(gaps_found)} sequence gaps in batch"
                    )
            
            # Update statistics
            self.stats.total_deltas += len(sorted_batch)
            self.stats.processing_time += time.time() - start_time
            self.stats.update_throughput(self.stats.processing_time)
            
            return sorted_batch, detected_gaps
            
        except Exception as e:
            logger.error(f"Failed to validate delta batch: {e}")
            raise
    
    def _validate_sequence(
        self,
        update_ids: np.ndarray,
        origin_times: Optional[pl.Series],
        detected_gaps: List[SequenceGapInfo],
    ) -> List[SequenceGapInfo]:
        """
        Validate sequence continuity and detect gaps.
        
        Args:
            update_ids: Array of update IDs
            origin_times: Optional series of origin times
            detected_gaps: List to append detected gaps to
            
        Returns:
            List of gaps found in this validation
        """
        gaps_in_batch = []
        
        # Check against last known update_id
        if self.last_update_id is not None:
            expected = self.last_update_id + 1
            actual = update_ids[0]
            
            if actual != expected:
                gap_size = actual - expected
                gap_info = SequenceGapInfo(
                    expected_id=expected,
                    actual_id=actual,
                    gap_size=gap_size,
                    timestamp=time.time(),
                    origin_time=origin_times[0] if origin_times is not None else None,
                )
                
                self._record_gap(gap_info)
                gaps_in_batch.append(gap_info)
                detected_gaps.append(gap_info)
        
        # Check within batch
        for i in range(1, len(update_ids)):
            expected = update_ids[i - 1] + 1
            actual = update_ids[i]
            
            if actual != expected:
                gap_size = actual - expected
                gap_info = SequenceGapInfo(
                    expected_id=expected,
                    actual_id=actual,
                    gap_size=gap_size,
                    timestamp=time.time(),
                    origin_time=origin_times[i] if origin_times is not None else None,
                )
                
                self._record_gap(gap_info)
                gaps_in_batch.append(gap_info)
                detected_gaps.append(gap_info)
        
        # Update last known update_id
        self.last_update_id = int(update_ids[-1])
        self.expected_next_id = self.last_update_id + 1
        
        return gaps_in_batch
    
    def _record_gap(self, gap_info: SequenceGapInfo) -> None:
        """Record a sequence gap in statistics."""
        # Update statistics
        self.stats.total_gaps += 1
        self.stats.max_gap_size = max(self.stats.max_gap_size, gap_info.gap_size)
        
        # Track gap size distribution
        gap_size = gap_info.gap_size
        if gap_size in self.gaps_by_size:
            self.gaps_by_size[gap_size] += 1
        else:
            self.gaps_by_size[gap_size] = 1
        
        # Check if recovery needed
        if gap_size > self.gap_threshold:
            self.stats.gaps_over_threshold += 1
            self.recovery_needed = True
            logger.error(
                f"Large gap detected: {gap_info}. Recovery signaled."
            )
        
        # Store in history if enabled
        if self.store_gap_history:
            self.stats.gap_history.append(gap_info)
            
            # Trim history if needed
            if len(self.stats.gap_history) > self.max_gap_history:
                self.stats.gap_history = self.stats.gap_history[-self.max_gap_history:]
    
    def process_batch(
        self,
        delta_batch: pl.DataFrame,
    ) -> Tuple[pl.DataFrame, bool]:
        """
        Process a batch of deltas with full validation.
        
        Args:
            delta_batch: DataFrame with delta updates
            
        Returns:
            Tuple of (processed DataFrame, recovery_needed flag)
        """
        # Reset recovery flag
        self.recovery_needed = False
        
        # Validate and sort
        sorted_batch, gaps = self.validate_and_sort(delta_batch)
        
        # Add gap detection metadata
        if gaps:
            # Mark rows that come after gaps
            gap_starts = [gap.actual_id for gap in gaps]
            is_after_gap = sorted_batch["update_id"].is_in(gap_starts)
            sorted_batch = sorted_batch.with_columns([
                is_after_gap.alias("after_gap")
            ])
        else:
            sorted_batch = sorted_batch.with_columns([
                pl.lit(False).alias("after_gap")
            ])
        
        return sorted_batch, self.recovery_needed
    
    def get_statistics(self) -> Dict:
        """Get processing statistics."""
        return {
            "total_deltas": self.stats.total_deltas,
            "total_gaps": self.stats.total_gaps,
            "max_gap_size": self.stats.max_gap_size,
            "gaps_over_threshold": self.stats.gaps_over_threshold,
            "last_update_id": self.last_update_id,
            "expected_next_id": self.expected_next_id,
            "throughput": self.stats.throughput,
            "gap_size_distribution": dict(self.gaps_by_size),
            "recovery_needed": self.recovery_needed,
        }
    
    def reset_sequence(self, new_update_id: int) -> None:
        """
        Reset sequence tracking after recovery.
        
        Args:
            new_update_id: New starting update_id
        """
        logger.info(f"Resetting sequence to update_id={new_update_id}")
        self.last_update_id = new_update_id
        self.expected_next_id = new_update_id + 1
        self.recovery_needed = False
    
    def get_gap_summary(self) -> str:
        """Get a summary of gap statistics."""
        if self.stats.total_gaps == 0:
            return "No sequence gaps detected"
        
        lines = [
            f"Total gaps: {self.stats.total_gaps}",
            f"Max gap size: {self.stats.max_gap_size}",
            f"Gaps over threshold ({self.gap_threshold}): {self.stats.gaps_over_threshold}",
            "Gap size distribution:",
        ]
        
        # Sort gap sizes for display
        for size in sorted(self.gaps_by_size.keys()):
            count = self.gaps_by_size[size]
            lines.append(f"  Size {size}: {count} occurrences")
        
        return "\n".join(lines)