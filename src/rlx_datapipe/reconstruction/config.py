"""Configuration for event replay optimizations."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ReplayOptimizationConfig:
    """Configuration for performance optimizations in event replay.
    
    These settings allow tuning the trade-off between accuracy,
    memory usage, and processing speed.
    """
    
    # Drift tracking
    drift_threshold: float = 0.001
    resync_on_drift: bool = True
    drift_check_interval: int = 1000  # Check drift every N snapshots
    
    # Order book settings
    max_book_levels: int = 20
    use_hybrid_structure: bool = True  # Arrays for top levels, hash for deep
    
    # Batching
    micro_batch_size: int = 1000  # Events per batch
    enable_micro_batching: bool = True
    
    # Memory optimization
    gc_interval: int = 100_000  # Force GC every N events
    enable_gc: bool = True
    max_memory_mb: int = 500
    
    # Processing optimization
    enable_zero_copy: bool = True
    parallel_normalization: bool = False  # Future: parallel processing
    skip_enrichment: bool = False  # Skip book state enrichment for speed
    
    # Profiling
    enable_profiling: bool = False
    profile_interval: int = 10_000
    
    def __post_init__(self):
        """Validate configuration parameters."""
        if self.drift_threshold <= 0 or self.drift_threshold > 1:
            raise ValueError(f"drift_threshold must be between 0 and 1, got {self.drift_threshold}")
        
        if self.drift_check_interval < 1:
            raise ValueError(f"drift_check_interval must be positive, got {self.drift_check_interval}")
        
        if self.max_book_levels < 1 or self.max_book_levels > 1000:
            raise ValueError(f"max_book_levels must be between 1 and 1000, got {self.max_book_levels}")
        
        if self.micro_batch_size < 1:
            raise ValueError(f"micro_batch_size must be positive, got {self.micro_batch_size}")
        
        if self.gc_interval < 1000:
            raise ValueError(f"gc_interval must be at least 1000, got {self.gc_interval}")
        
        if self.max_memory_mb < 100 or self.max_memory_mb > 10000:
            raise ValueError(f"max_memory_mb must be between 100 and 10000, got {self.max_memory_mb}")
        
        if self.profile_interval < 100:
            raise ValueError(f"profile_interval must be at least 100, got {self.profile_interval}")
    
    def get_high_throughput_config(self) -> "ReplayOptimizationConfig":
        """Get configuration optimized for high throughput.
        
        Trades accuracy for speed.
        """
        return ReplayOptimizationConfig(
            drift_threshold=0.05,  # Higher threshold
            resync_on_drift=False,  # Don't resync
            drift_check_interval=10_000,  # Check less often
            max_book_levels=10,  # Fewer levels
            micro_batch_size=10_000,  # Larger batches
            skip_enrichment=True,  # Skip book state
            enable_gc=False  # Let Python handle GC
        )
    
    def get_high_accuracy_config(self) -> "ReplayOptimizationConfig":
        """Get configuration optimized for accuracy.
        
        Trades speed for accuracy.
        """
        return ReplayOptimizationConfig(
            drift_threshold=0.0001,  # Very low threshold
            resync_on_drift=True,
            drift_check_interval=100,  # Check often
            max_book_levels=50,  # More levels
            micro_batch_size=100,  # Smaller batches
            skip_enrichment=False,
            enable_gc=True
        )
    
    def get_balanced_config(self) -> "ReplayOptimizationConfig":
        """Get balanced configuration.
        
        Default settings that balance speed and accuracy.
        """
        return ReplayOptimizationConfig()  # Use defaults