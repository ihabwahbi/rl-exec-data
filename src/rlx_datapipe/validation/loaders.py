"""Data loaders for validation framework."""

import gzip
import json
from pathlib import Path
from typing import Iterator, Optional, Callable, Dict, List, Union
import numpy as np
from loguru import logger
from tqdm import tqdm


class GoldenSampleLoader:
    """Streaming loader for golden sample JSONL files."""
    
    def __init__(self, buffer_size: int = 10000):
        """Initialize loader.
        
        Args:
            buffer_size: Number of items to buffer before yielding arrays
        """
        self.buffer_size = buffer_size
        self._total_messages = 0
        self._message_counts: Dict[str, int] = {}
    
    def load_messages(self, 
                     filepath: Path, 
                     message_filter: Optional[Callable[[dict], bool]] = None,
                     show_progress: bool = True) -> Iterator[dict]:
        """Stream messages from golden sample file.
        
        Args:
            filepath: Path to .jsonl or .jsonl.gz file
            message_filter: Optional filter function
            show_progress: Show progress bar
            
        Yields:
            Dict containing capture_ns, stream, and data
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        
        # Reset counters
        self._total_messages = 0
        self._message_counts = {}
        
        # Determine file size for progress bar
        file_size = filepath.stat().st_size if show_progress else None
        
        # Open file (handle compression)
        if filepath.suffix == '.gz':
            file_handle = gzip.open(filepath, 'rt')
        else:
            file_handle = open(filepath, 'r')
        
        try:
            with tqdm(total=file_size, unit='B', unit_scale=True, 
                     desc=f"Loading {filepath.name}",
                     disable=not show_progress) as pbar:
                for line_num, line in enumerate(file_handle, 1):
                    if show_progress:
                        pbar.update(len(line.encode('utf-8')))
                    
                    try:
                        msg = json.loads(line)
                        self._total_messages += 1
                        
                        # Track message types
                        if 'stream' in msg:
                            stream_parts = msg['stream'].split('@')
                            if len(stream_parts) > 1:
                                # Join all parts after the first @ to handle streams like depth@100ms
                                stream_type = '@'.join(stream_parts[1:])
                                self._message_counts[stream_type] = self._message_counts.get(stream_type, 0) + 1
                        
                        # Apply filter if provided
                        if message_filter is None or message_filter(msg):
                            yield msg
                            
                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON at line {line_num}: {e}")
                        continue
                        
        finally:
            file_handle.close()
        
        logger.info(f"Loaded {self._total_messages} messages from {filepath.name}")
        for msg_type, count in self._message_counts.items():
            logger.info(f"  {msg_type}: {count:,} messages")
    
    def extract_trades(self, 
                      filepath: Path, 
                      start_ns: Optional[int] = None,
                      end_ns: Optional[int] = None) -> Iterator[np.ndarray]:
        """Extract trade sizes for power law analysis.
        
        Args:
            filepath: Path to golden sample file
            start_ns: Optional start timestamp in nanoseconds
            end_ns: Optional end timestamp in nanoseconds
            
        Yields:
            Arrays of trade sizes
        """
        trade_sizes = []
        
        def trade_filter(msg):
            if '@trade' not in msg.get('stream', ''):
                return False
            if start_ns and msg.get('capture_ns', 0) < start_ns:
                return False
            if end_ns and msg.get('capture_ns', float('inf')) > end_ns:
                return False
            return True
        
        for msg in self.load_messages(filepath, message_filter=trade_filter):
            if 'data' in msg and 'q' in msg['data']:
                try:
                    quantity = float(msg['data']['q'])
                    if quantity > 0:
                        trade_sizes.append(quantity)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid trade quantity: {msg['data'].get('q')}")
                    continue
            
            # Yield periodically to avoid memory issues
            if len(trade_sizes) >= self.buffer_size:
                yield np.array(trade_sizes)
                trade_sizes = []
        
        # Yield remaining
        if trade_sizes:
            yield np.array(trade_sizes)
    
    def extract_prices(self,
                      filepath: Path,
                      message_type: str = 'trade',
                      start_ns: Optional[int] = None,
                      end_ns: Optional[int] = None) -> Iterator[np.ndarray]:
        """Extract prices from messages.
        
        Args:
            filepath: Path to golden sample file
            message_type: Type of message to extract from ('trade' or 'depth')
            start_ns: Optional start timestamp
            end_ns: Optional end timestamp
            
        Yields:
            Arrays of prices
        """
        prices = []
        
        def price_filter(msg):
            if f'@{message_type}' not in msg.get('stream', ''):
                return False
            if start_ns and msg.get('capture_ns', 0) < start_ns:
                return False
            if end_ns and msg.get('capture_ns', float('inf')) > end_ns:
                return False
            return True
        
        for msg in self.load_messages(filepath, message_filter=price_filter):
            if 'data' in msg:
                if message_type == 'trade' and 'p' in msg['data']:
                    try:
                        price = float(msg['data']['p'])
                        if price > 0:
                            prices.append(price)
                    except (ValueError, TypeError):
                        continue
                elif message_type == 'depth' and 'b' in msg['data']:
                    # Use best bid price
                    if msg['data']['b'] and len(msg['data']['b']) > 0:
                        try:
                            price = float(msg['data']['b'][0][0])
                            if price > 0:
                                prices.append(price)
                        except (ValueError, TypeError, IndexError):
                            continue
            
            if len(prices) >= self.buffer_size:
                yield np.array(prices)
                prices = []
        
        if prices:
            yield np.array(prices)
    
    def extract_orderbook_updates(self,
                                 filepath: Path,
                                 start_ns: Optional[int] = None,
                                 end_ns: Optional[int] = None) -> Iterator[Dict]:
        """Extract orderbook update messages.
        
        Args:
            filepath: Path to golden sample file
            start_ns: Optional start timestamp
            end_ns: Optional end timestamp
            
        Yields:
            Orderbook update messages
        """
        def depth_filter(msg):
            if '@depth' not in msg.get('stream', ''):
                return False
            if start_ns and msg.get('capture_ns', 0) < start_ns:
                return False
            if end_ns and msg.get('capture_ns', float('inf')) > end_ns:
                return False
            return True
        
        for msg in self.load_messages(filepath, message_filter=depth_filter):
            yield msg
    
    def get_statistics(self) -> dict:
        """Get loader statistics from last load operation."""
        return {
            "total_messages": self._total_messages,
            "message_counts": self._message_counts.copy()
        }
    
    def load_all_trades(self, filepath: Path) -> np.ndarray:
        """Load all trade sizes into a single array.
        
        Args:
            filepath: Path to golden sample file
            
        Returns:
            Array of all trade sizes
        """
        all_trades = []
        for batch in self.extract_trades(filepath):
            all_trades.extend(batch)
        return np.array(all_trades)
    
    def load_all_prices(self, filepath: Path, message_type: str = 'trade') -> np.ndarray:
        """Load all prices into a single array.
        
        Args:
            filepath: Path to golden sample file
            message_type: Type of message to extract from
            
        Returns:
            Array of all prices
        """
        all_prices = []
        for batch in self.extract_prices(filepath, message_type):
            all_prices.extend(batch)
        return np.array(all_prices)