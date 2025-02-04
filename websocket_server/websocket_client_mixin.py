import asyncio
from typing import Dict, Any, Optional
from .base_websocket_client import BaseWebSocketClient

class WebSocketClientMixin:
    """
    A mixin class that provides WebSocket client functionality.
    Inheriting classes must initialize debug and connections attributes.
    """
    
    def __init__(self, connections: Dict[str, Dict[str, Any]], debug: bool = True):
        """
        Initialize the WebSocket client mixin.
        
        :param connections: Dictionary of connection configurations
        :param debug: Enable debug logging
        """
        self.client: Optional[BaseWebSocketClient] = None
        self.connections = connections
        self.debug = debug
        if self.debug:
            print(f"Initializing WebSocketClientMixin with connections: {list(connections.keys())}")

    async def start_client(self) -> None:
        """Start the WebSocket client"""
        if self.debug:
            print("Starting WebSocket client...")
            
        if self.client is None:
            try:
                self.client = BaseWebSocketClient(self.connections, self.debug)
                await self.client.start()
                if self.debug:
                    print("WebSocket client started successfully")
            except Exception as e:
                if self.debug:
                    print(f"Error starting client: {e}")
                await self.stop_client()
                raise

    async def stop_client(self) -> None:
        """Stop the WebSocket client"""
        if self.client:
            if self.debug:
                print("Stopping WebSocket client...")
            await self.client.stop()
            self.client = None
            if self.debug:
                print("WebSocket client stopped")

    async def handle_client_update(self, root: str, updated_objects: Dict) -> None:
        """
        Handle updates from the WebSocket client.
        Override this method in the implementing class.
        
        :param root: The root of the update (e.g., 'moonraker', 'skybox')
        :param updated_objects: The updated data
        """
        raise NotImplementedError("Implementing classes must override handle_client_update")

    async def __aenter__(self):
        """Async context manager entry"""
        await self.start_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.stop_client()