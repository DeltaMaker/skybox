import asyncio
import json
import websockets
from websocket_server.base_websocket_client import BaseWebSocketClient

class WebSocketClientMixin:
    def __init__(self, connections, debug=True):
        """
        Initialize the WebSocketClientMixin with a BaseWebSocketClient.
        :param connections: A dictionary where the key is the service name and the value contains:
                            - 'uri': The WebSocket URI for the service.
                            - 'subscription': The JSON-RPC or subscription message.
                            - 'connected': The current connection status.
        :param debug: Enable or disable debug logging.
        """
        self.client = BaseWebSocketClient(connections, debug)  # Use BaseWebSocketClient to manage connections
        self.debug = debug
        self.client.on_state_update = self.handle_client_update  # Set the callback method

    async def start_client(self):
        """
        Start the WebSocket client.
        """
        if self.debug:
            print("Starting WebSocket client...")
        await self.client.start()

    async def stop_client(self):
        """
        Stop the WebSocket client.
        """
        if self.debug:
            print("Stopping WebSocket client...")
        await self.client.stop()

    async def handle_client_update(self, root, updated_objects):
        """
        Handle updates from the WebSocket client. This method should be overridden by the subclass.
        :param root: The root of the service being updated (e.g., 'moonraker', 'skybox').
        :param updated_objects: The objects that were updated.
        """
        raise NotImplementedError("Subclasses must implement this method to handle updates from WebSocket client.")