"""Data staging area management for the acquisition pipeline."""

import json
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum

from loguru import logger

from .integrity_validator import ValidationResult


class FileStatus(Enum):
    """File status in staging pipeline."""
    RAW = "raw"
    VALIDATING = "validating" 
    READY = "ready"
    QUARANTINED = "quarantined"


@dataclass
class FileManifest:
    """Manifest entry for a staged file."""
    key: str  # Original S3 key
    local_path: str  # Current local path
    status: FileStatus
    size_bytes: int
    checksum: Optional[str]
    data_type: str  # trades, book, book_delta_v2
    symbol: str
    exchange: str
    date: str  # ISO date string
    created_at: datetime
    updated_at: datetime
    validation_result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class DataStagingManager:
    """Manages data lifecycle through validation stages."""
    
    def __init__(self, staging_root: Path = Path("data/staging")):
        """Initialize staging manager.
        
        Args:
            staging_root: Root directory for staging areas
        """
        self.staging_root = Path(staging_root)
        
        # Create staging directories
        self.raw_dir = self.staging_root / "raw"
        self.validating_dir = self.staging_root / "validating"
        self.ready_dir = self.staging_root / "ready"
        self.quarantine_dir = self.staging_root / "quarantine"
        
        for directory in [self.raw_dir, self.validating_dir, self.ready_dir, self.quarantine_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Manifest file
        self.manifest_file = self.staging_root / "manifest.json"
        self.manifest = self._load_manifest()
        
    def _load_manifest(self) -> Dict[str, FileManifest]:
        """Load manifest from disk."""
        if not self.manifest_file.exists():
            return {}
        
        try:
            with open(self.manifest_file, 'r') as f:
                data = json.load(f)
            
            manifest = {}
            for key, item in data.items():
                # Convert datetime strings back to datetime objects
                item['created_at'] = datetime.fromisoformat(item['created_at'])
                item['updated_at'] = datetime.fromisoformat(item['updated_at'])
                item['status'] = FileStatus(item['status'])
                manifest[key] = FileManifest(**item)
            
            return manifest
            
        except Exception as e:
            logger.error(f"Failed to load manifest: {e}")
            return {}
    
    def _save_manifest(self) -> None:
        """Save manifest to disk."""
        try:
            # Convert to serializable format
            data = {}
            for key, manifest in self.manifest.items():
                item = asdict(manifest)
                item['created_at'] = manifest.created_at.isoformat()
                item['updated_at'] = manifest.updated_at.isoformat()
                item['status'] = manifest.status.value
                data[key] = item
            
            # Atomic write
            temp_file = self.manifest_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            temp_file.rename(self.manifest_file)
            
        except Exception as e:
            logger.error(f"Failed to save manifest: {e}")
    
    def register_file(self, 
                     s3_key: str,
                     local_path: Path,
                     data_type: str,
                     symbol: str,
                     exchange: str,
                     date: str,
                     size_bytes: int,
                     checksum: Optional[str] = None) -> FileManifest:
        """Register a new file in the staging system.
        
        Args:
            s3_key: Original S3 key
            local_path: Current local path
            data_type: Type of data
            symbol: Trading symbol
            exchange: Exchange name
            date: Date string (ISO format)
            size_bytes: File size in bytes
            checksum: Optional file checksum
            
        Returns:
            FileManifest for the registered file
        """
        now = datetime.utcnow()
        
        manifest = FileManifest(
            key=s3_key,
            local_path=str(local_path),
            status=FileStatus.RAW,
            size_bytes=size_bytes,
            checksum=checksum,
            data_type=data_type,
            symbol=symbol,
            exchange=exchange,
            date=date,
            created_at=now,
            updated_at=now
        )
        
        self.manifest[s3_key] = manifest
        self._save_manifest()
        
        logger.info(f"Registered file: {s3_key} -> {local_path}")
        
        return manifest
    
    def move_to_validating(self, s3_key: str) -> bool:
        """Move file from raw to validating status.
        
        Args:
            s3_key: S3 key of file to move
            
        Returns:
            True if successful
        """
        if s3_key not in self.manifest:
            logger.error(f"File not in manifest: {s3_key}")
            return False
        
        manifest = self.manifest[s3_key]
        
        if manifest.status != FileStatus.RAW:
            logger.warning(f"File {s3_key} not in RAW status: {manifest.status}")
            return False
        
        # Move file
        old_path = Path(manifest.local_path)
        new_path = self.validating_dir / old_path.name
        
        try:
            if old_path.exists():
                shutil.move(str(old_path), str(new_path))
            
            # Update manifest
            manifest.local_path = str(new_path)
            manifest.status = FileStatus.VALIDATING
            manifest.updated_at = datetime.utcnow()
            
            self._save_manifest()
            
            logger.info(f"Moved to validating: {s3_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to move {s3_key} to validating: {e}")
            return False
    
    def move_to_ready(self, s3_key: str, validation_result: ValidationResult) -> bool:
        """Move file from validating to ready status.
        
        Args:
            s3_key: S3 key of file to move
            validation_result: Validation result
            
        Returns:
            True if successful
        """
        if s3_key not in self.manifest:
            logger.error(f"File not in manifest: {s3_key}")
            return False
        
        manifest = self.manifest[s3_key]
        
        if manifest.status != FileStatus.VALIDATING:
            logger.warning(f"File {s3_key} not in VALIDATING status: {manifest.status}")
            return False
        
        if not validation_result.passed:
            logger.error(f"Cannot move failed validation to ready: {s3_key}")
            return False
        
        # Move file
        old_path = Path(manifest.local_path)
        
        # Organize in ready directory by data type and date
        target_dir = self.ready_dir / manifest.data_type / manifest.date
        target_dir.mkdir(parents=True, exist_ok=True)
        new_path = target_dir / old_path.name
        
        try:
            if old_path.exists():
                shutil.move(str(old_path), str(new_path))
            
            # Update manifest
            manifest.local_path = str(new_path)
            manifest.status = FileStatus.READY
            manifest.updated_at = datetime.utcnow()
            manifest.validation_result = {
                'passed': validation_result.passed,
                'checks': validation_result.checks,
                'errors': validation_result.errors,
                'warnings': validation_result.warnings,
                'metadata': validation_result.metadata
            }
            
            self._save_manifest()
            
            logger.info(f"Moved to ready: {s3_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to move {s3_key} to ready: {e}")
            return False
    
    def move_to_quarantine(self, s3_key: str, validation_result: ValidationResult, error_message: str = None) -> bool:
        """Move file from validating to quarantine status.
        
        Args:
            s3_key: S3 key of file to move
            validation_result: Validation result showing failure
            error_message: Optional additional error message
            
        Returns:
            True if successful
        """
        if s3_key not in self.manifest:
            logger.error(f"File not in manifest: {s3_key}")
            return False
        
        manifest = self.manifest[s3_key]
        
        # Move file
        old_path = Path(manifest.local_path)
        
        # Organize in quarantine directory with error info
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        quarantine_name = f"{timestamp}_{old_path.name}"
        new_path = self.quarantine_dir / quarantine_name
        
        try:
            if old_path.exists():
                shutil.move(str(old_path), str(new_path))
            
            # Update manifest
            manifest.local_path = str(new_path)
            manifest.status = FileStatus.QUARANTINED
            manifest.updated_at = datetime.utcnow()
            manifest.error_message = error_message
            manifest.validation_result = {
                'passed': validation_result.passed,
                'checks': validation_result.checks,
                'errors': validation_result.errors,
                'warnings': validation_result.warnings,
                'metadata': validation_result.metadata
            }
            
            self._save_manifest()
            
            logger.warning(f"Moved to quarantine: {s3_key} - {error_message}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to move {s3_key} to quarantine: {e}")
            return False
    
    def get_files_by_status(self, status: FileStatus) -> List[FileManifest]:
        """Get all files with a specific status.
        
        Args:
            status: Status to filter by
            
        Returns:
            List of FileManifest objects
        """
        return [manifest for manifest in self.manifest.values() if manifest.status == status]
    
    def get_ready_files(self, 
                       data_type: Optional[str] = None,
                       symbol: Optional[str] = None,
                       start_date: Optional[str] = None,
                       end_date: Optional[str] = None) -> List[FileManifest]:
        """Get ready files with optional filtering.
        
        Args:
            data_type: Optional data type filter
            symbol: Optional symbol filter  
            start_date: Optional start date filter (ISO format)
            end_date: Optional end date filter (ISO format)
            
        Returns:
            List of filtered FileManifest objects
        """
        ready_files = self.get_files_by_status(FileStatus.READY)
        
        # Apply filters
        if data_type:
            ready_files = [f for f in ready_files if f.data_type == data_type]
        
        if symbol:
            ready_files = [f for f in ready_files if f.symbol == symbol]
        
        if start_date:
            ready_files = [f for f in ready_files if f.date >= start_date]
        
        if end_date:
            ready_files = [f for f in ready_files if f.date <= end_date]
        
        # Sort by date
        ready_files.sort(key=lambda f: f.date)
        
        return ready_files
    
    def get_staging_summary(self) -> Dict[str, Any]:
        """Get summary of staging area status.
        
        Returns:
            Dictionary with staging statistics
        """
        status_counts = {}
        total_size = 0
        data_type_counts = {}
        
        for manifest in self.manifest.values():
            # Count by status
            status = manifest.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
            
            # Total size
            total_size += manifest.size_bytes
            
            # Count by data type
            if manifest.status == FileStatus.READY:
                data_type = manifest.data_type
                data_type_counts[data_type] = data_type_counts.get(data_type, 0) + 1
        
        return {
            'total_files': len(self.manifest),
            'status_counts': status_counts,
            'total_size_bytes': total_size,
            'total_size_mb': total_size / (1024 * 1024),
            'ready_by_data_type': data_type_counts,
            'directories': {
                'raw': str(self.raw_dir),
                'validating': str(self.validating_dir),
                'ready': str(self.ready_dir),
                'quarantine': str(self.quarantine_dir)
            }
        }
    
    def generate_readiness_certificate(self, 
                                     symbol: str,
                                     exchange: str,
                                     start_date: str,
                                     end_date: str,
                                     required_data_types: List[str]) -> Dict[str, Any]:
        """Generate data readiness certificate.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange name
            start_date: Start date (ISO format)
            end_date: End date (ISO format)  
            required_data_types: List of required data types
            
        Returns:
            Readiness certificate dictionary
        """
        certificate = {
            'symbol': symbol,
            'exchange': exchange,
            'start_date': start_date,
            'end_date': end_date,
            'required_data_types': required_data_types,
            'generated_at': datetime.utcnow().isoformat(),
            'ready': False,
            'summary': {},
            'issues': []
        }
        
        # Check each required data type
        type_status = {}
        for data_type in required_data_types:
            ready_files = self.get_ready_files(
                data_type=data_type,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date
            )
            
            type_status[data_type] = {
                'file_count': len(ready_files),
                'total_size_mb': sum(f.size_bytes for f in ready_files) / (1024 * 1024),
                'date_range': {
                    'start': min(f.date for f in ready_files) if ready_files else None,
                    'end': max(f.date for f in ready_files) if ready_files else None
                }
            }
            
            # Check if we have sufficient data
            if not ready_files:
                certificate['issues'].append(f"No ready files found for {data_type}")
            elif type_status[data_type]['date_range']['start'] > start_date:
                certificate['issues'].append(f"{data_type}: Coverage starts late ({type_status[data_type]['date_range']['start']})")
            elif type_status[data_type]['date_range']['end'] < end_date:
                certificate['issues'].append(f"{data_type}: Coverage ends early ({type_status[data_type]['date_range']['end']})")
        
        certificate['summary'] = type_status
        certificate['ready'] = len(certificate['issues']) == 0
        
        # Save certificate
        cert_file = self.staging_root / f"readiness_certificate_{symbol}_{start_date}_{end_date}.json"
        with open(cert_file, 'w') as f:
            json.dump(certificate, f, indent=2)
        
        logger.info(f"Generated readiness certificate: {cert_file}")
        
        if certificate['ready']:
            logger.info(f"✅ Data is READY for {symbol} from {start_date} to {end_date}")
        else:
            logger.warning(f"❌ Data NOT ready for {symbol}: {len(certificate['issues'])} issues")
            for issue in certificate['issues']:
                logger.warning(f"  - {issue}")
        
        return certificate
    
    def cleanup_quarantine(self, older_than_days: int = 30) -> int:
        """Clean up old quarantined files.
        
        Args:
            older_than_days: Remove files older than this many days
            
        Returns:
            Number of files removed
        """
        removed_count = 0
        cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
        
        quarantined_files = self.get_files_by_status(FileStatus.QUARANTINED)
        
        for manifest in quarantined_files:
            if manifest.updated_at < cutoff_date:
                try:
                    # Remove file
                    file_path = Path(manifest.local_path)
                    if file_path.exists():
                        file_path.unlink()
                    
                    # Remove from manifest
                    del self.manifest[manifest.key]
                    removed_count += 1
                    
                    logger.info(f"Cleaned up quarantined file: {manifest.key}")
                    
                except Exception as e:
                    logger.error(f"Failed to cleanup {manifest.key}: {e}")
        
        if removed_count > 0:
            self._save_manifest()
            logger.info(f"Cleaned up {removed_count} quarantined files")
        
        return removed_count