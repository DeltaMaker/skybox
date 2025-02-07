import asyncio
import json
import numpy as np
from aiohttp import web
import logging


class SimpleWebsocketServer:
    def __init__(self, host='0.0.0.0', port=7160):
        self.host = host
        self.port = port
        self.clients = {}
        self.running = False
     

    async def start_server(self):
        """Start the combined HTTP and WebSocket server."""
        app = web.Application()

        # Add routes for WebSocket and HTTP requests
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

                # Extract config dict from client subscription
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

    def start_processing(self, config : dict):
        """Start processing with the verified configuration."""
        try:
            self.perform_initialization(config)

        except Exception as e:
            logging.error(f"Failed to start processing: {e}")
            raise

    async def send_broadcast_loop(self):
        """Continuous loop to send periodic broadcasts to all connected clients."""
        while True:
            if self.clients:
                await self.send_broadcast_function()
            await asyncio.sleep(0.01)  # Small delay to prevent CPU overload

    async def send_broadcast(self):
        """Send periodic broadcast to all connected clients."""
        try:
            while self.clients:
                self.send_broadcast_data()
                await asyncio.sleep(0.01)
        except Exception as e:
            logging.error(f"Error sending broadcast data: {e}")


    def send_broadcast_data(self):
        # implemented in derived classes
        pass

    def stop_processing(self):
        """Stop processing when no clients are connected."""
        self.running = False
        self.perform_cleanup()

    def perform_initialization(self, config : dict):
        # implemented in derived classes
        pass

    def perform_cleanup(self):
        # implemented in derived classes
        pass

    def status_message(self):
        # implemented in derived classes
        pass    


    async def http_handler(self, request):
        """Handle HTTP requests to get the current status of connected clients."""

        clients_status = self.status_message()
        return web.json_response({
            'status': 'running' if self.running else 'stopped', **clients_status
        })

    def run(self):
        """Run the WebSocket server."""
        asyncio.run(self.start_server())


def convert_numpy_types(obj):
    if isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj

