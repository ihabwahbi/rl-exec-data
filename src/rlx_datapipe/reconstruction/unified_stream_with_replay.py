"""Unified event stream with integrated chronological replay.

This module integrates the ChronologicalEventReplay algorithm with the
existing UnifiedEventStreamEnhanced for complete event processing.
"""

from pathlib import Path
from typing import Dict, Optional
import polars as pl
from loguru import logger

from .unified_stream_enhanced import UnifiedEventStreamEnhanced, EnhancedUnificationConfig
from .event_replayer import ChronologicalEventReplay


class UnifiedEventStreamWithReplay(UnifiedEventStreamEnhanced):
    """Enhanced unified stream with chronological event replay integration."""
    
    def __init__(
        self,
        symbol: str,
        config: Optional[EnhancedUnificationConfig] = None,
        drift_threshold: float = 0.001,
        resync_on_drift: bool = True
    ):
        """Initialize unified stream with chronological replay.
        
        Args:
            symbol: Trading symbol
            config: Enhanced configuration
            drift_threshold: RMS error threshold for triggering resync
            resync_on_drift: Whether to resync on drift threshold breach
        """
        super().__init__(symbol, config)
        
        # Initialize chronological replayer
        self.chronological_replayer = ChronologicalEventReplay(
            drift_threshold=drift_threshold,
            max_levels=self.config.max_book_levels,
            resync_on_drift=resync_on_drift
        )
        
        logger.info(
            f"UnifiedEventStreamWithReplay initialized with "
            f"drift_threshold={drift_threshold}, resync_on_drift={resync_on_drift}"
        )
    
    def process_unified_stream(
        self,
        trades_path: Optional[Path] = None,
        book_snapshots_path: Optional[Path] = None,
        book_deltas_path: Optional[Path] = None,
        output_path: Optional[Path] = None,
        use_streaming: bool = True,
    ) -> Dict:
        """Process unified stream with chronological replay.
        
        Args:
            trades_path: Path to trades data
            book_snapshots_path: Path to book snapshots
            book_deltas_path: Path to book deltas
            output_path: Output directory for enriched data
            use_streaming: Use streaming mode for large datasets
            
        Returns:
            Processing statistics
        """
        logger.info("Starting unified stream processing with chronological replay")
        
        if use_streaming and self.config.use_memory_mapping:
            # Use memory-mapped streaming for large datasets
            return self._process_streaming_with_replay(
                trades_path, book_snapshots_path, book_deltas_path, output_path
            )
        else:
            # Use batch mode with full chronological replay
            return self._process_batch_with_replay(
                trades_path, book_snapshots_path, book_deltas_path, output_path
            )
    
    def _process_batch_with_replay(
        self,
        trades_path: Optional[Path],
        book_snapshots_path: Optional[Path],
        book_deltas_path: Optional[Path],
        output_path: Optional[Path],
    ) -> Dict:
        """Process data in batch mode with chronological replay.
        
        Args:
            trades_path: Path to trades data
            book_snapshots_path: Path to book snapshots
            book_deltas_path: Path to book deltas
            output_path: Output directory
            
        Returns:
            Processing statistics
        """
        # Check if any data provided
        if not any([trades_path, book_snapshots_path, book_deltas_path]):
            logger.warning("No data files provided for processing")
            return {
                "total_events": 0,
                "trades_processed": 0,
                "snapshots_processed": 0,
                "deltas_processed": 0,
                "events_with_book_state": 0,
                "drift_metrics": self.chronological_replayer.drift_tracker.get_statistics()
            }
        
        # Use parent class to merge streams
        unified_df = self.merge_streams(
            trades_path=trades_path,
            book_snapshots_path=book_snapshots_path,
            book_deltas_path=book_deltas_path,
        )
        
        logger.info(f"Unified {len(unified_df)} events for chronological replay")
        
        # Apply chronological replay with stateful processing
        replayed_df = self.chronological_replayer.execute(unified_df)
        
        # Collect statistics
        stats = {
            "total_events": len(replayed_df),
            "trades_processed": len(replayed_df.filter(pl.col("event_type") == "TRADE")),
            "snapshots_processed": len(replayed_df.filter(pl.col("event_type") == "BOOK_SNAPSHOT")),
            "deltas_processed": len(replayed_df.filter(pl.col("event_type") == "BOOK_DELTA")),
            "events_with_book_state": len(replayed_df.filter(pl.col("top_bid").is_not_null())),
        }
        
        # Get drift statistics
        drift_stats = self.chronological_replayer.drift_tracker.get_statistics()
        stats["drift_metrics"] = drift_stats
        
        # Save output if requested
        if output_path:
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Save replayed events
            replayed_df.write_parquet(
                output_path / "chronological_events_enriched.parquet"
            )
            
            # Save drift metrics separately
            drift_df = pl.DataFrame(
                self.chronological_replayer.drift_tracker.export_metrics()
            )
            if len(drift_df) > 0:
                drift_df.write_parquet(
                    output_path / "drift_metrics.parquet"
                )
            
            logger.info(f"Saved enriched events to {output_path}")
        
        return stats
    
    def _process_streaming_with_replay(
        self,
        trades_path: Optional[Path],
        book_snapshots_path: Optional[Path],
        book_deltas_path: Optional[Path],
        output_path: Optional[Path],
    ) -> Dict:
        """Process data in streaming mode with micro-batched replay.
        
        For very large datasets, processes in micro-batches while
        maintaining state across batches.
        
        Args:
            trades_path: Path to trades data
            book_snapshots_path: Path to book snapshots
            book_deltas_path: Path to book deltas
            output_path: Output directory
            
        Returns:
            Processing statistics
        """
        if not self.mmap_processor:
            raise RuntimeError("Memory-mapped processor not initialized")
        
        stats = {
            "total_events": 0,
            "trades_processed": 0,
            "snapshots_processed": 0,
            "deltas_processed": 0,
            "events_with_book_state": 0,
            "batches_processed": 0,
        }
        
        # Process in micro-batches
        batch_size = 100_000  # 100K events per batch
        
        # Collect paths to process
        data_paths = []
        if trades_path and trades_path.exists():
            data_paths.append(("TRADE", trades_path))
        if book_snapshots_path and book_snapshots_path.exists():
            data_paths.append(("BOOK_SNAPSHOT", book_snapshots_path))
        if book_deltas_path and book_deltas_path.exists():
            data_paths.append(("BOOK_DELTA", book_deltas_path))
        
        if output_path:
            output_path.mkdir(parents=True, exist_ok=True)
        
        # Process each data source
        for event_type, data_path in data_paths:
            logger.info(f"Processing {event_type} events from {data_path}")
            
            for batch_num, chunk in enumerate(
                self.mmap_processor.read_parquet_mmap(data_path, chunk_size=batch_size)
            ):
                # Add event type if not present
                if "event_type" not in chunk.columns:
                    chunk = chunk.with_columns(pl.lit(event_type).alias("event_type"))
                
                # Process batch with replay
                replayed_batch = self.chronological_replayer.execute(chunk)
                
                # Update statistics
                stats["total_events"] += len(replayed_batch)
                stats[f"{event_type.lower()}s_processed"] += len(replayed_batch)
                stats["events_with_book_state"] += len(
                    replayed_batch.filter(pl.col("top_bid").is_not_null())
                )
                stats["batches_processed"] += 1
                
                # Save batch if output requested
                if output_path:
                    batch_file = output_path / f"{event_type.lower()}_batch_{batch_num:04d}.parquet"
                    replayed_batch.write_parquet(batch_file)
                
                # Log progress
                if (batch_num + 1) % 10 == 0:
                    logger.info(
                        f"Processed {(batch_num + 1) * batch_size:,} {event_type} events"
                    )
        
        # Final drift statistics
        drift_stats = self.chronological_replayer.drift_tracker.get_statistics()
        stats["drift_metrics"] = drift_stats
        
        # Save consolidated drift metrics
        if output_path and drift_stats["total_snapshots"] > 0:
            drift_df = pl.DataFrame(
                self.chronological_replayer.drift_tracker.export_metrics()
            )
            drift_df.write_parquet(output_path / "drift_metrics.parquet")
        
        logger.info(
            f"Completed streaming replay: {stats['total_events']:,} events in "
            f"{stats['batches_processed']} batches"
        )
        
        return stats
    
    def get_drift_report(self) -> Dict:
        """Get detailed drift tracking report.
        
        Returns:
            Drift statistics and analysis
        """
        drift_stats = self.chronological_replayer.drift_tracker.get_statistics()
        
        report = {
            "summary": drift_stats,
            "thresholds": {
                "configured_threshold": self.chronological_replayer.drift_threshold,
                "resync_enabled": self.chronological_replayer.resync_on_drift,
            },
            "recommendations": []
        }
        
        # Add recommendations based on drift analysis
        if drift_stats["total_snapshots"] > 0:
            if drift_stats["resync_rate"] > 0.1:
                report["recommendations"].append(
                    "High resync rate detected. Consider adjusting drift threshold or "
                    "investigating data quality issues."
                )
            
            if drift_stats["max_rms_error"] > 0.01:
                report["recommendations"].append(
                    "Large drift detected. Verify delta feed completeness and "
                    "sequence integrity."
                )
        
        return report