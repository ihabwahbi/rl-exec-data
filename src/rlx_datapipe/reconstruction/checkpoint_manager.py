"""Checkpoint manager for order book state persistence."""

import json
import pickle
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger


class CheckpointManager:
    """Manages checkpoints for order book state recovery."""
    
    def __init__(
        self,
        checkpoint_dir: Path,
        symbol: str,
        max_checkpoints: int = 3,
        use_pickle: bool = True,
    ):
        """
        Initialize checkpoint manager.
        
        Args:
            checkpoint_dir: Directory for storing checkpoints
            symbol: Trading symbol for checkpoint naming
            max_checkpoints: Maximum number of checkpoints to keep
            use_pickle: Use pickle format (True) or JSON (False)
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.symbol = symbol
        self.max_checkpoints = max_checkpoints
        self.use_pickle = use_pickle
        
        # Create checkpoint directory if needed
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"CheckpointManager initialized for {symbol} at {checkpoint_dir}")
    
    def save_checkpoint(
        self,
        state_data: Dict[str, Any],
        update_id: int,
    ) -> Path:
        """
        Save checkpoint with atomic write pattern.
        
        Args:
            state_data: State data to checkpoint
            update_id: Current update ID for naming
            
        Returns:
            Path to saved checkpoint
        """
        if not state_data:
            raise ValueError("Cannot save empty state data")
            
        if update_id < 0:
            raise ValueError(f"Invalid update_id: {update_id}")
            
        try:
            # Generate checkpoint filename
            timestamp = int(time.time() * 1000)
            checkpoint_name = f"{self.symbol}_checkpoint_{update_id}_{timestamp}"
            
            if self.use_pickle:
                checkpoint_path = self.checkpoint_dir / f"{checkpoint_name}.pkl"
                temp_path = checkpoint_path.with_suffix(".tmp")
                
                # Write to temp file first
                with open(temp_path, "wb") as f:
                    pickle.dump(state_data, f, protocol=pickle.HIGHEST_PROTOCOL)
            else:
                checkpoint_path = self.checkpoint_dir / f"{checkpoint_name}.json"
                temp_path = checkpoint_path.with_suffix(".tmp")
                
                # Write to temp file first
                with open(temp_path, "w") as f:
                    json.dump(state_data, f, indent=2)
            
            # Atomic rename
            temp_path.rename(checkpoint_path)
            
            logger.debug(f"Saved checkpoint: {checkpoint_path}")
            
            # Clean up old checkpoints
            self._cleanup_old_checkpoints()
            
            return checkpoint_path
            
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            raise
    
    def load_latest_checkpoint(self) -> Optional[Dict[str, Any]]:
        """
        Load the most recent checkpoint.
        
        Returns:
            State data from checkpoint or None if no checkpoints
        """
        try:
            checkpoints = self._get_checkpoint_files()
            if not checkpoints:
                logger.info("No checkpoints found")
                return None
            
            # Sort by timestamp (newest first)
            checkpoints.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            
            latest = checkpoints[0]
            logger.info(f"Loading checkpoint: {latest}")
            
            if self.use_pickle:
                with open(latest, "rb") as f:
                    return pickle.load(f)
            else:
                with open(latest, "r") as f:
                    return json.load(f)
                    
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return None
    
    def load_checkpoint_by_update_id(
        self,
        target_update_id: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Load checkpoint closest to target update ID.
        
        Args:
            target_update_id: Target update ID
            
        Returns:
            State data from checkpoint or None
        """
        try:
            checkpoints = self._get_checkpoint_files()
            if not checkpoints:
                return None
            
            # Find checkpoint with closest update_id <= target
            best_checkpoint = None
            best_update_id = 0
            
            for checkpoint in checkpoints:
                # Extract update_id from filename
                parts = checkpoint.stem.split("_")
                if len(parts) >= 3:
                    update_id = int(parts[2])
                    if update_id <= target_update_id and update_id > best_update_id:
                        best_update_id = update_id
                        best_checkpoint = checkpoint
            
            if best_checkpoint:
                logger.info(f"Loading checkpoint for update_id {best_update_id}: {best_checkpoint}")
                
                if self.use_pickle:
                    with open(best_checkpoint, "rb") as f:
                        return pickle.load(f)
                else:
                    with open(best_checkpoint, "r") as f:
                        return json.load(f)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to load checkpoint by update_id: {e}")
            return None
    
    def _get_checkpoint_files(self) -> list[Path]:
        """Get all checkpoint files for this symbol."""
        pattern = f"{self.symbol}_checkpoint_*"
        
        if self.use_pickle:
            return list(self.checkpoint_dir.glob(f"{pattern}.pkl"))
        else:
            return list(self.checkpoint_dir.glob(f"{pattern}.json"))
    
    def _cleanup_old_checkpoints(self) -> None:
        """Remove old checkpoints keeping only max_checkpoints."""
        try:
            checkpoints = self._get_checkpoint_files()
            
            if len(checkpoints) <= self.max_checkpoints:
                return
            
            # Sort by modification time (oldest first)
            checkpoints.sort(key=lambda p: p.stat().st_mtime)
            
            # Remove oldest checkpoints
            to_remove = len(checkpoints) - self.max_checkpoints
            for checkpoint in checkpoints[:to_remove]:
                checkpoint.unlink()
                logger.debug(f"Removed old checkpoint: {checkpoint}")
                
        except Exception as e:
            logger.error(f"Failed to cleanup checkpoints: {e}")
    
    def clear_all_checkpoints(self) -> None:
        """Remove all checkpoints for this symbol."""
        try:
            checkpoints = self._get_checkpoint_files()
            for checkpoint in checkpoints:
                checkpoint.unlink()
            
            logger.info(f"Cleared {len(checkpoints)} checkpoints")
            
        except Exception as e:
            logger.error(f"Failed to clear checkpoints: {e}")