"""
SimpleWebsocketClient - Base class for WebSocket clients with subscription support.

This class provides the foundation for creating WebSocket clients that can:
- Connect to a WebSocket server
- Send subscription configurations
- Receive messages (both text and binary)
- Handle connection errors and cleanup

Usage:
    Either inherit from this class or use it with composition pattern.
    See example_client.py and camera_viewer.py for usage examples.
"""

import websockets
import json
import asyncio
from typing import Optional, Dict, Any

class SimpleWebsocketClient:
    def __init__(self, url: str):
        """Initialize websocket client with URL."""
        self.url = url
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        self.subscribed = False
        self.max_retries = 5
        self.retry_delay = 1.0  # Start with 1 second delay

    async def connect(self) -> None:
        """Establish websocket connection with retries."""
        retries = 0
        while retries < self.max_retries:
            try:
                self.ws = await websockets.connect(
                    self.url,
                    ping_interval=10,
                    ping_timeout=30
                )
                self.connected = True
                print(f"Successfully connected to {self.url}")
                return
            except Exception as e:
                retries += 1
                if retries < self.max_retries:
                    print(f"Connection attempt {retries} failed: {str(e)}")
                    await asyncio.sleep(self.retry_delay * retries)  # Exponential backoff
                else:
                    raise ConnectionError(f"Failed to connect to {self.url} after {self.max_retries} attempts: {str(e)}")

    async def disconnect(self) -> None:
        """Close websocket connection if it exists."""
        if self.ws:
            await self.ws.close()
            self.ws = None
        self.connected = False
        self.subscribed = False

    async def subscribe(self, config: Dict[str, Any]) -> None:
        """Send subscription configuration to the server with retries."""
        if not self.ws:
            raise ConnectionError("Not connected to websocket")
        
        retries = 0
        while retries < self.max_retries:
            try:
                # Send configuration message
                await self.ws.send(json.dumps(config))
                
                # Wait for confirmation message with timeout
                try:
                    response = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                    confirmation = json.loads(response)
                    
                    if confirmation.get('status') == 'subscribed':
                        self.subscribed = True
                        print(f"Successfully subscribed to {self.url}")
                        return
                    else:
                        print(f"Unexpected subscription response: {confirmation}")
                except asyncio.TimeoutError:
                    print("Subscription confirmation timeout")
                
                retries += 1
                if retries < self.max_retries:
                    print(f"Subscription attempt {retries} failed, retrying...")
                    await asyncio.sleep(self.retry_delay * retries)
                else:
                    raise ConnectionError(f"Failed to subscribe after {self.max_retries} attempts")
            except Exception as e:
                retries += 1
                if retries < self.max_retries:
                    print(f"Subscription error: {str(e)}, retrying...")
                    await asyncio.sleep(self.retry_delay * retries)
                else:
                    raise ConnectionError(f"Failed to subscribe: {str(e)}")

    async def receive(self) -> str:
        """
        Receive a message from the server.
        Returns either JSON string for metadata or bytes for frame data.
        """
        if not self.ws:
            raise ConnectionError("Not connected to websocket")
        
        try:
            message = await self.ws.recv()
            return message
        except websockets.exceptions.ConnectionClosed as e:
            self.connected = False
            self.subscribed = False
            raise websockets.exceptions.ConnectionClosed(
                e.code, e.reason
            ) from e
        except Exception as e:
            self.connected = False
            self.subscribed = False
            raise ConnectionError(f"Failed to receive message: {str(e)}")

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self.connected and self.ws and not self.ws.closed

    @property
    def is_subscribed(self) -> bool:
        """Check if client is subscribed."""
        return self.subscribed and self.is_connected