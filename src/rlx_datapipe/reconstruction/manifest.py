"""Manifest tracking for written Parquet partitions.

Tracks metadata about written partitions for discovery and validation.
"""

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import os
import sys
import time

from loguru import logger


class FileLock:
    """Cross-platform file locking implementation."""
    
    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self.lock_file = None
        
    def acquire(self, timeout: float = 10.0) -> bool:
        """Acquire exclusive lock with timeout."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Try to create lock file exclusively
                self.lock_file = open(self.lock_path, 'x')
                return True
            except FileExistsError:
                # Lock is held by another process
                time.sleep(0.1)
        return False
        
    def release(self) -> None:
        """Release the lock."""
        if self.lock_file:
            self.lock_file.close()
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass  # Already released
            self.lock_file = None
            
    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(f"Could not acquire lock on {self.lock_path}")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


@dataclass
class PartitionMetadata:
    """Metadata for a single written partition file."""
    partition_path: str  # Relative path from output directory
    file_name: str
    row_count: int
    file_size_bytes: int
    timestamp_min: int  # Nanoseconds
    timestamp_max: int  # Nanoseconds
    event_types: List[str]  # Unique event types in partition
    write_timestamp: str  # ISO format timestamp when written
    checksum: Optional[str] = None  # Optional file checksum
    

class ManifestTracker:
    """Tracks written partitions with atomic manifest updates.
    
    The manifest is a newline-delimited JSON file where each line
    contains metadata about a written partition. This format allows
    for append-only updates and easy streaming reads.
    """
    
    def __init__(self, output_dir: Path):
        """Initialize manifest tracker.
        
        Args:
            output_dir: Base output directory for data sink
        """
        self.output_dir = output_dir
        self.manifest_path = output_dir / "manifest.jsonl"
        self.lock_path = output_dir / ".manifest.lock"
        
        # Create manifest file if it doesn't exist
        if not self.manifest_path.exists():
            self.manifest_path.touch()
            logger.info(f"Created new manifest at {self.manifest_path}")
        else:
            # Validate existing manifest on startup
            self._validate_manifest()
    
    def add_partition(self, metadata: PartitionMetadata) -> None:
        """Add a partition to the manifest with atomic update.
        
        Args:
            metadata: Partition metadata to record
        """
        # Serialize metadata
        entry = json.dumps(asdict(metadata), separators=(',', ':'))
        
        # Use file locking for concurrent access safety
        with FileLock(self.lock_path):
            # Append to manifest
            with open(self.manifest_path, 'a') as f:
                f.write(entry + '\n')
                f.flush()
                os.fsync(f.fileno())  # Ensure data is written to disk
                
            logger.debug(f"Added partition to manifest: {metadata.file_name}")
    
    def read_manifest(self) -> List[PartitionMetadata]:
        """Read all entries from the manifest.
        
        Returns:
            List of partition metadata entries
        """
        entries = []
        
        if not self.manifest_path.exists():
            return entries
        
        with open(self.manifest_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                    
                try:
                    data = json.loads(line)
                    entries.append(PartitionMetadata(**data))
                except (json.JSONDecodeError, TypeError) as e:
                    logger.error(f"Invalid manifest entry at line {line_num}: {e}")
                    continue
        
        return entries
    
    def get_partitions_for_time_range(
        self, 
        start_ns: int, 
        end_ns: int
    ) -> List[PartitionMetadata]:
        """Get partitions that contain data within a time range.
        
        Args:
            start_ns: Start timestamp in nanoseconds
            end_ns: End timestamp in nanoseconds
            
        Returns:
            List of partitions that overlap with the time range
        """
        all_partitions = self.read_manifest()
        
        matching = []
        for partition in all_partitions:
            # Check if partition time range overlaps with query range
            if partition.timestamp_max >= start_ns and partition.timestamp_min <= end_ns:
                matching.append(partition)
        
        return matching
    
    def get_manifest_stats(self) -> Dict[str, Any]:
        """Get summary statistics from the manifest.
        
        Returns:
            Dictionary with manifest statistics
        """
        partitions = self.read_manifest()
        
        if not partitions:
            return {
                "total_partitions": 0,
                "total_rows": 0,
                "total_size_bytes": 0,
                "earliest_timestamp": None,
                "latest_timestamp": None,
                "unique_event_types": [],
            }
        
        total_rows = sum(p.row_count for p in partitions)
        total_size = sum(p.file_size_bytes for p in partitions)
        earliest = min(p.timestamp_min for p in partitions)
        latest = max(p.timestamp_max for p in partitions)
        
        # Collect unique event types
        event_types = set()
        for p in partitions:
            event_types.update(p.event_types)
        
        return {
            "total_partitions": len(partitions),
            "total_rows": total_rows,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "earliest_timestamp": earliest,
            "latest_timestamp": latest,
            "earliest_datetime": datetime.fromtimestamp(earliest / 1e9, tz=timezone.utc).isoformat(),
            "latest_datetime": datetime.fromtimestamp(latest / 1e9, tz=timezone.utc).isoformat(),
            "unique_event_types": sorted(event_types),
        }
    
    def _validate_manifest(self) -> None:
        """Validate manifest integrity on startup.
        
        Checks for corrupted entries and logs warnings.
        """
        logger.info("Validating existing manifest...")
        
        valid_count = 0
        invalid_count = 0
        
        with open(self.manifest_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    PartitionMetadata(**data)  # Validate structure
                    valid_count += 1
                except Exception as e:
                    logger.warning(f"Invalid manifest entry at line {line_num}: {e}")
                    invalid_count += 1
        
        logger.info(f"Manifest validation complete: {valid_count} valid, {invalid_count} invalid entries")
        
        if invalid_count > 0:
            logger.warning(f"Found {invalid_count} invalid entries in manifest")
    
    def compact_manifest(self) -> None:
        """Compact the manifest by removing invalid entries.
        
        Creates a new manifest with only valid entries.
        """
        logger.info("Compacting manifest...")
        
        valid_entries = self.read_manifest()
        
        # Write to temporary file
        temp_path = self.manifest_path.with_suffix('.tmp')
        
        with open(temp_path, 'w') as f:
            for entry in valid_entries:
                line = json.dumps(asdict(entry), separators=(',', ':'))
                f.write(line + '\n')
            f.flush()
            os.fsync(f.fileno())
        
        # Atomic replace
        temp_path.rename(self.manifest_path)
        
        logger.info(f"Manifest compacted: {len(valid_entries)} entries retained")
