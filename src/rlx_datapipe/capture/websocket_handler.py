"""WebSocket connection handler with automatic reconnection."""

import asyncio
import json
import time
from collections.abc import Callable

import websockets
from loguru import logger
from websockets.exceptions import WebSocketException


class WebSocketHandler:
    """Handles WebSocket connections with automatic reconnection and message buffering."""

    def __init__(
        self,
        url: str,
        on_message: Callable[[dict, int], None],
        on_connect: Callable[[], None] | None = None,
        on_disconnect: Callable[[], None] | None = None,
        max_reconnect_attempts: int = 5,
        reconnect_delay: float = 5.0
    ):
        """Initialize WebSocket handler.
        
        Args:
            url: WebSocket URL to connect to
            on_message: Callback for handling messages (message_dict, ns_timestamp)
            on_connect: Optional callback when connected
            on_disconnect: Optional callback when disconnected
            max_reconnect_attempts: Maximum reconnection attempts
            reconnect_delay: Delay between reconnection attempts in seconds
        """
        self.url = url
        self.on_message = on_message
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self._websocket: websockets.WebSocketClientProtocol | None = None
        self._running = False
        self._reconnect_count = 0

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        try:
            self._websocket = await websockets.connect(self.url)
            self._reconnect_count = 0
            logger.info(f"Connected to WebSocket: {self.url}")

            if self.on_connect:
                self.on_connect()

        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}")
            raise

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        if self._websocket:
            await self._websocket.close()
            self._websocket = None

            if self.on_disconnect:
                self.on_disconnect()

            logger.info("Disconnected from WebSocket")

    async def _handle_message(self, message: str) -> None:
        """Process incoming WebSocket message.
        
        Args:
            message: Raw message string from WebSocket
        """
        receive_ns = time.perf_counter_ns()

        try:
            data = json.loads(message)
            # Check if on_message is async and await it
            if asyncio.iscoroutinefunction(self.on_message):
                await self.on_message(data, receive_ns)
            else:
                self.on_message(data, receive_ns)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    async def _reconnect(self) -> bool:
        """Attempt to reconnect to WebSocket.
        
        Returns:
            True if reconnection successful, False otherwise
        """
        self._reconnect_count += 1

        if self._reconnect_count > self.max_reconnect_attempts:
            logger.error("Maximum reconnection attempts reached")
            return False

        logger.info(f"Reconnection attempt {self._reconnect_count}/{self.max_reconnect_attempts}")
        await asyncio.sleep(self.reconnect_delay)

        try:
            await self.connect()
            return True
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            return False

    async def run(self) -> None:
        """Run the WebSocket handler with automatic reconnection."""
        self._running = True

        while self._running:
            try:
                if not self._websocket:
                    await self.connect()

                async for message in self._websocket:
                    await self._handle_message(message)

            except WebSocketException as e:
                logger.warning(f"WebSocket error: {e}")

                if self.on_disconnect:
                    self.on_disconnect()

                if not await self._reconnect():
                    logger.error("Failed to reconnect, stopping handler")
                    break

            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                break

        self._running = False
        await self.disconnect()

    def stop(self) -> None:
        """Stop the WebSocket handler."""
        self._running = False
        logger.info("Stopping WebSocket handler")

