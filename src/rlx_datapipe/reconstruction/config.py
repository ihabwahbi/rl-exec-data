"""Configuration for event replay optimizations and multi-symbol processing."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum


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


class RoutingStrategy(Enum):
    """Message routing strategies for multi-symbol processing."""
    DIRECT = "direct"  # Route based on message symbol field
    HASH = "hash"  # Hash-based distribution
    ROUND_ROBIN = "round_robin"  # Round-robin distribution


@dataclass
class SymbolConfig:
    """Configuration for a single symbol."""
    name: str
    enabled: bool = True
    memory_limit_mb: Optional[int] = 1024
    cpu_affinity: Optional[List[int]] = None
    queue_size: int = 1000


@dataclass
class ProcessManagerConfig:
    """Configuration for the process manager."""
    health_check_interval_seconds: int = 5
    restart_delay_seconds: int = 2
    max_restart_attempts: int = 3
    shutdown_timeout_seconds: int = 30


@dataclass
class MonitoringConfig:
    """Configuration for monitoring and metrics."""
    enable_metrics: bool = True
    metrics_interval_seconds: int = 10
    metrics_export_port: Optional[int] = None


@dataclass
class MultiSymbolConfig:
    """Configuration for multi-symbol processing."""
    enabled: bool = True
    routing_strategy: RoutingStrategy = RoutingStrategy.DIRECT
    symbols: List[SymbolConfig] = field(default_factory=list)
    process_manager: ProcessManagerConfig = field(default_factory=ProcessManagerConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "MultiSymbolConfig":
        """Create configuration from dictionary.
        
        Args:
            config_dict: Configuration dictionary
            
        Returns:
            MultiSymbolConfig instance
        """
        # Parse routing strategy
        routing_strategy = RoutingStrategy(config_dict.get('routing_strategy', 'direct'))
        
        # Parse symbols
        symbols = []
        for symbol_dict in config_dict.get('symbols', []):
            symbols.append(SymbolConfig(**symbol_dict))
            
        # Parse process manager config
        pm_dict = config_dict.get('process_manager', {})
        process_manager = ProcessManagerConfig(**pm_dict)
        
        # Parse monitoring config
        mon_dict = config_dict.get('monitoring', {})
        monitoring = MonitoringConfig(**mon_dict)
        
        return cls(
            enabled=config_dict.get('enabled', True),
            routing_strategy=routing_strategy,
            symbols=symbols,
            process_manager=process_manager,
            monitoring=monitoring
        )
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary.
        
        Returns:
            Configuration as dictionary
        """
        return {
            'enabled': self.enabled,
            'routing_strategy': self.routing_strategy.value,
            'symbols': [
                {
                    'name': s.name,
                    'enabled': s.enabled,
                    'memory_limit_mb': s.memory_limit_mb,
                    'cpu_affinity': s.cpu_affinity,
                    'queue_size': s.queue_size
                }
                for s in self.symbols
            ],
            'process_manager': {
                'health_check_interval_seconds': self.process_manager.health_check_interval_seconds,
                'restart_delay_seconds': self.process_manager.restart_delay_seconds,
                'max_restart_attempts': self.process_manager.max_restart_attempts,
                'shutdown_timeout_seconds': self.process_manager.shutdown_timeout_seconds
            },
            'monitoring': {
                'enable_metrics': self.monitoring.enable_metrics,
                'metrics_interval_seconds': self.monitoring.metrics_interval_seconds,
                'metrics_export_port': self.monitoring.metrics_export_port
            }
        }
