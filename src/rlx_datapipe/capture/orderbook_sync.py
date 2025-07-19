"""Order book synchronization with REST snapshot and WebSocket updates."""

import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Any

import aiohttp
from loguru import logger


@dataclass
class OrderBookSnapshot:
    """Order book snapshot from REST API."""
    symbol: str
    last_update_id: int
    bids: list[list[str]]  # [[price, quantity], ...]
    asks: list[list[str]]  # [[price, quantity], ...]


class OrderBookSynchronizer:
    """Synchronizes order book using REST snapshot and WebSocket updates."""

    def __init__(self, symbol: str, rest_url: str = "https://api.binance.com/api/v3/depth"):
        """Initialize order book synchronizer.
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            rest_url: Binance REST API URL for depth endpoint
        """
        self.symbol = symbol
        self.rest_url = rest_url
        self._buffer: deque = deque(maxlen=1000)
        self._snapshot: OrderBookSnapshot | None = None
        self._is_synced = False
        self._sync_attempts = 0
        self._max_sync_attempts = 5

    def buffer_update(self, update: dict[str, Any]) -> None:
        """Buffer order book update from WebSocket.
        
        Args:
            update: Order book update from WebSocket
        """
        self._buffer.append(update)

    async def fetch_snapshot(self, limit: int = 5000) -> OrderBookSnapshot:
        """Fetch order book snapshot from REST API.
        
        Args:
            limit: Number of order book levels to fetch (max 5000)
            
        Returns:
            OrderBookSnapshot
            
        Raises:
            Exception: If failed to fetch snapshot
        """
        params = {
            "symbol": self.symbol,
            "limit": limit
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.rest_url, params=params) as response:
                    if response.status != 200:
                        raise Exception(f"REST API error: {response.status}")

                    data = await response.json()

                    snapshot = OrderBookSnapshot(
                        symbol=self.symbol,
                        last_update_id=data["lastUpdateId"],
                        bids=data["bids"],
                        asks=data["asks"]
                    )

                    logger.info(f"Fetched snapshot for {self.symbol}, lastUpdateId: {snapshot.last_update_id}")
                    return snapshot

        except Exception as e:
            logger.error(f"Failed to fetch snapshot: {e}")
            raise

    def _check_synchronization(self) -> bool:
        """Check if buffered updates can be synchronized with snapshot.
        
        Returns:
            True if synchronization successful, False otherwise
        """
        if not self._snapshot:
            return False

        # Find the first update that can be applied
        while self._buffer:
            update = self._buffer[0]

            # Check synchronization condition:
            # First buffered update must have U <= lastUpdateId+1 AND u >= lastUpdateId+1
            first_update_id = update["first_update_id"]
            final_update_id = update["final_update_id"]

            if first_update_id <= self._snapshot.last_update_id + 1 <= final_update_id:
                logger.info(f"Synchronized at update_id {self._snapshot.last_update_id}")
                return True

            # If update is too old (final_update_id < lastUpdateId), discard it
            if final_update_id < self._snapshot.last_update_id:
                self._buffer.popleft()
                continue

            # If update is too new (first_update_id > lastUpdateId+1), we have a gap
            if first_update_id > self._snapshot.last_update_id + 1:
                logger.warning(f"Gap detected: snapshot lastUpdateId={self._snapshot.last_update_id}, "
                             f"update firstUpdateId={first_update_id}")
                return False

        # No updates in buffer
        return False

    async def synchronize(self) -> bool:
        """Synchronize order book with REST snapshot and WebSocket updates.
        
        Returns:
            True if synchronization successful, False if failed after max attempts
        """
        self._sync_attempts = 0

        while self._sync_attempts < self._max_sync_attempts:
            self._sync_attempts += 1
            logger.info(f"Synchronization attempt {self._sync_attempts}/{self._max_sync_attempts}")

            try:
                # Fetch REST snapshot
                self._snapshot = await self.fetch_snapshot()

                # Check if we can synchronize with buffered updates
                if self._check_synchronization():
                    self._is_synced = True
                    logger.info("Order book synchronized successfully")
                    return True

                # Clear buffer and wait before retrying
                logger.warning("Failed to synchronize, clearing buffer and retrying")
                self._buffer.clear()
                await asyncio.sleep(1.0)

            except Exception as e:
                logger.error(f"Synchronization error: {e}")
                await asyncio.sleep(2.0)

        logger.error("Failed to synchronize after maximum attempts")
        return False

    def process_update(self, update: dict[str, Any]) -> dict[str, Any] | None:
        """Process order book update if synchronized.
        
        Args:
            update: Order book update from parser
            
        Returns:
            Update dict if synchronized and no gap, None otherwise
        """
        if not self._is_synced:
            # Buffer update while not synchronized
            self.buffer_update(update)
            return None

        # Check for sequence gap
        expected_id = self._snapshot.last_update_id + 1

        if update["first_update_id"] != expected_id:
            logger.error(f"Sequence gap detected: expected {expected_id}, "
                        f"got {update['first_update_id']}")
            self._is_synced = False
            self._buffer.clear()
            self.buffer_update(update)

            # Trigger resynchronization
            asyncio.create_task(self.synchronize())
            return None

        # Update is in sequence
        self._snapshot.last_update_id = update["final_update_id"]
        return update

    def is_synchronized(self) -> bool:
        """Check if order book is synchronized."""
        return self._is_synced

    def get_snapshot(self) -> OrderBookSnapshot | None:
        """Get current order book snapshot."""
        return self._snapshot
