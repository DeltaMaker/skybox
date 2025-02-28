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
from typing import Optional, Dict, Any

class SimpleWebsocketClient:
    def __init__(self, url: str):
        """Initialize websocket client with URL."""
        self.url = url
        self.ws: Optional[websockets.WebSocketClientProtocol] = None

    async def connect(self) -> None:
        """Establish websocket connection."""
        try:
            self.ws = await websockets.connect(
                self.url,
                ping_interval=10,
                ping_timeout=30
            )
        except Exception as e:
            raise ConnectionError(f"Failed to connect to {self.url}: {str(e)}")

    async def disconnect(self) -> None:
        """Close websocket connection if it exists."""
        if self.ws:
            await self.ws.close()
            self.ws = None

    async def subscribe(self, config: Dict[str, Any]) -> None:
        """Send subscription configuration to the server."""
        if not self.ws:
            raise ConnectionError("Not connected to websocket")
        
        try:
            # Send configuration message
            await self.ws.send(json.dumps(config))
            
            # Wait for confirmation message
            response = await self.ws.recv()
            confirmation = json.loads(response)
            
            if confirmation.get('status') != 'subscribed':
                raise ConnectionError("Server did not confirm subscription")
            
        except Exception as e:
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
            raise websockets.exceptions.ConnectionClosed(
                e.code, e.reason
            ) from e
        except Exception as e:
            raise ConnectionError(f"Failed to receive message: {str(e)}")