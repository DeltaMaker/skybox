import asyncio
import json
import websockets
from websocket_server.base_websocket_client import BaseWebSocketClient

class WebSocketClientMixin:
    def __init__(self, connections, subscriptions, debug=True):
        self.client = BaseWebSocketClient(connections, subscriptions, debug)
        self.debug = debug
        self.client.on_state_update = self.handle_client_update  # Set the callback method

    async def start_client(self):
        if self.debug:
            print("Starting WebSocket client...")
        await self.client.start()

    async def stop_client(self):
        if self.debug:
            print("Stopping WebSocket client...")
        await self.client.stop()

    async def handle_client_update(self, root, updated_objects):
        """This method should be overridden in the subclass to handle updates from the client."""
        pass

