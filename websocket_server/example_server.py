"""
Example WebSocket Server

This example demonstrates how to create a simple WebSocket server
that broadcasts random data to connected clients.
"""

import asyncio
import random
import json
from simple_server import SimpleWebsocketServer

class ExampleServer(SimpleWebsocketServer):
    def __init__(self, host='0.0.0.0', port=7170, debug=False):
        super().__init__(host, port, debug)
        self.counter = 0
    
    def extract_client_info(self, config):
        """Extract client configuration."""
        return {
            'type': config.get('type', 'default'),
            'name': config.get('name', f'client_{self.counter}'),
            'update_rate': config.get('update_rate', 1.0)
        }
        self.counter += 1
    
    async def get_broadcast_data(self):
        """Generate random data to broadcast."""
        # Simulate data generation
        await asyncio.sleep(0.5)
        self.counter += 1
        return {
            'counter': self.counter,
            'random_value': random.random(),
            'timestamp': asyncio.get_event_loop().time()
        }
    
    async def format_client_message(self, message_data, client_info):
        """Format message for specific client."""
        # You could customize the message based on client_info
        return {
            'data': message_data,
            'client_type': client_info['type']
        }
    
    async def send_to_client(self, client_ws, message):
        """Send formatted message to client."""
        if not client_ws.closed:
            await client_ws.send_str(json.dumps(message))
    
    def get_status_info(self):
        """Provide server-specific status information."""
        return {
            'server_type': 'example',
            'counter': self.counter
        }

def main():
    server = ExampleServer(debug=True)
    try:
        server.run()
    except KeyboardInterrupt:
        print("\nShutting down server...")

if __name__ == "__main__":
    main() 