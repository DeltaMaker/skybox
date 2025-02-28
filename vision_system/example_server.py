"""
ExampleServer - Demo implementation of SimpleWebsocketServer.

This example server demonstrates how to:
- Implement all required template methods
- Send periodic messages (1 per second)
- Track client connections
- Format messages with timestamps and counters

Usage:
    python example_server.py [--host HOST] [--port PORT]

Pairs with example_client.py for testing WebSocket communication.
"""

import asyncio
import json
import time
from websocket_server.simple_server import SimpleWebsocketServer

class ExampleServer(SimpleWebsocketServer):
    def __init__(self, host='0.0.0.0', port=7160, debug=False):
        """Initialize the example server with counter for demo data."""
        super().__init__(host, port, debug)
        self.counter = 0
        self.test_data = {
            'example': 'data',
            'timestamp': 0,
            'counter': 0
        }
        self.last_broadcast = 0

    def extract_client_info(self, config):
        """Extract and log client configuration."""
        print(f"New client subscribed with config: {config}")
        return config

    async def get_broadcast_data(self):
        """Generate example data for broadcasting once per second."""
        current_time = time.time()
        if current_time - self.last_broadcast < 1.0:  # Wait for 1 second between broadcasts
            return None
            
        self.last_broadcast = current_time
        self.counter += 1
        self.test_data.update({
            'timestamp': current_time,
            'counter': self.counter
        })
        return self.test_data

    async def format_client_message(self, message_data, client_info):
        """Format message based on client configuration."""
        formatted_data = {
            'data': message_data,
            'client_config': client_info,
            'message_type': 'example'
        }
        return formatted_data

    async def send_to_client(self, client_ws, message):
        """Send formatted message to client."""
        await client_ws.send_str(json.dumps(message))

    def perform_initialization(self, config):
        """Initialize server with client config."""
        print(f"Starting example server with config: {config}")
        self.counter = 0
        self.last_broadcast = 0

    def perform_cleanup(self):
        """Cleanup when server stops."""
        print("Cleaning up example server")
        self.counter = 0
        self.last_broadcast = 0

    def status_message(self):
        """Return current server status."""
        return [{
            'config': client_info,
            'connected_since': time.time()
        } for client_info in self.clients.values()]


def main():
    """Run the example server."""
    server = ExampleServer(host='0.0.0.0', port=7160, debug=True)
    try:
        print("Starting Example Server...")
        server.run()
    except KeyboardInterrupt:
        print("\nStopping Example Server...")


if __name__ == "__main__":
    main() 