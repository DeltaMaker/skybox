"""
SimpleWebsocketServer - Base class for WebSocket servers with broadcast capability.

This class provides the foundation for creating WebSocket servers that can:
- Accept client connections and handle subscriptions
- Broadcast data to multiple clients
- Provide server status via HTTP endpoint
- Handle client disconnections gracefully

Usage:
    Inherit from this class and implement the template methods:
    - extract_client_info(config)
    - get_broadcast_data()
    - format_client_message(message_data, client_info)
    - send_to_client(client_ws, message)

See example_server.py for implementation example.
"""

import asyncio
import json
from aiohttp import web
import logging

class SimpleWebsocketServer:
    def __init__(self, host='0.0.0.0', port=7160):
        """Initialize the WebSocket server.
        
        Args:
            host (str): Host address to bind to
            port (int): Port number to listen on
        """
        self.host = host
        self.port = port
        self.clients = {}
        self.running = False

    async def start_server(self):
        """Start the combined HTTP and WebSocket server."""
        app = web.Application()
        app.router.add_route('GET', '/websocket', self.websocket_handler)
        app.router.add_route('GET', '/status', self.http_handler)

        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, self.host, self.port)
        await site.start()

        print(f"Server started on ws://{self.host}:{self.port} (WebSocket and HTTP)")
        
        # Start the frame sending task
        asyncio.create_task(self.send_broadcast_loop())

        # Keep the server running
        while True:
            await asyncio.sleep(3600)

    async def websocket_handler(self, request):
        """Handle client subscriptions for periodic broadcast."""
        ws = web.WebSocketResponse(heartbeat=10)
        await ws.prepare(request)

        try:
            # Receive client subscription settings
            config_message = await ws.receive()

            if config_message.type == web.WSMsgType.TEXT:
                config = json.loads(config_message.data)
                client_info = self.extract_client_info(config)

                # Start processing when the first client connects
                if not self.running:
                    self.start_processing(client_info) 
                    self.running = True

                # Add client to the list with their settings
                self.clients[ws] = client_info

                # Send subscription confirmation to the client
                confirmation_message = {'status': 'subscribed', **client_info}
                await ws.send_str(json.dumps(confirmation_message))

                # Keep the connection alive and handle incoming messages
                try:
                    async for msg in ws:
                        if msg.type == web.WSMsgType.ERROR:
                            print(f'WebSocket connection closed with exception {ws.exception()}')
                            break
                        elif msg.type == web.WSMsgType.CLOSE:
                            print('WebSocket connection closed normally')
                            break
                finally:
                    if ws in self.clients:
                        del self.clients[ws]
                    if not self.clients:
                        self.stop_processing()

        except Exception as e:
            logging.error(f"Error in websocket handler: {e}")
        
        return ws

    async def send_broadcast_loop(self):
        """Template method that handles the broadcasting loop infrastructure."""
        while True:
            if self.clients:
                try:
                    message_data = await self.get_broadcast_data()
                    if message_data:
                        await self.broadcast_to_clients(message_data)
                except Exception as e:
                    logging.error(f"Error in broadcast loop: {e}")
            await asyncio.sleep(0.01)  # Small sleep to prevent busy loop

    async def broadcast_to_clients(self, message_data):
        """Handle the actual sending of data to clients."""
        clients_to_remove = []
        
        for client_ws, client_info in list(self.clients.items()):
            if not client_ws.closed:
                try:
                    formatted_message = await self.format_client_message(message_data, client_info)
                    await self.send_to_client(client_ws, formatted_message)
                except Exception as e:
                    logging.info(f"Client disconnected: {e}")
                    clients_to_remove.append(client_ws)
            else:
                clients_to_remove.append(client_ws)

        # Remove disconnected clients after iteration
        for client_ws in clients_to_remove:
            if client_ws in self.clients:
                logging.info("Removing disconnected client")
                del self.clients[client_ws]
                
                if not self.clients:
                    logging.info("No clients remaining, stopping processing")
                    self.stop_processing()

    # Template methods to be implemented by derived classes
    async def send_to_client(self, client_ws, message):
        """Template method for sending a message to a specific client."""
        raise NotImplementedError("Derived classes must implement send_to_client")

    async def get_broadcast_data(self):
        """Template method for getting the data to broadcast."""
        raise NotImplementedError("Derived classes must implement get_broadcast_data")

    async def format_client_message(self, message_data, client_info):
        """Template method for formatting message for specific client."""
        raise NotImplementedError("Derived classes must implement format_client_message")

    def extract_client_info(self, config):
        """Template method for extracting client info from subscription config."""
        raise NotImplementedError("Derived classes must implement extract_client_info")

    def start_processing(self, config):
        """Start processing with the verified configuration."""
        try:
            self.perform_initialization(config)
        except Exception as e:
            logging.error(f"Failed to start processing: {e}")
            raise

    def stop_processing(self):
        """Stop processing when no clients are connected."""
        self.running = False
        self.perform_cleanup()

    def perform_initialization(self, config):
        """Template method for initialization tasks."""
        pass

    def perform_cleanup(self):
        """Template method for cleanup tasks."""
        pass

    def status_message(self):
        """Return empty list for base class status message."""
        return []

    async def http_handler(self, request):
        """Handle HTTP requests to get the current status."""
        clients_status = self.status_message()
        return web.json_response({
            'status': 'running' if self.running else 'stopped',
            'clients': clients_status or []
        })

    def run(self):
        """Run the WebSocket server."""
        asyncio.run(self.start_server())