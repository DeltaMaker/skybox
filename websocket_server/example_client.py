"""
Example WebSocket Client

This example demonstrates how to create a simple WebSocket client
that connects to the example server and processes messages.
"""

import asyncio
import json
from simple_client import SimpleWebsocketClient

class ExampleClient:
    def __init__(self, uri="ws://localhost:7170/websocket", debug=False):
        self.client = SimpleWebsocketClient(uri)
        self.debug = debug
        self.running = False
    
    async def connect(self):
        """Connect to the WebSocket server."""
        await self.client.connect()
        
        # Configure subscription
        config = {
            "type": "example",
            "name": "example_client",
            "update_rate": 1.0
        }
        await self.client.subscribe(config)
        
        self.running = True
    
    async def run(self):
        """Process messages from the server."""
        try:
            while self.running:
                message = await self.client.receive()
                if isinstance(message, str):
                    data = json.loads(message)
                    if self.debug:
                        print(f"Received: {data}")
                    
                    # Process the data here
                    if 'data' in data:
                        counter = data['data'].get('counter', 0)
                        random_value = data['data'].get('random_value', 0)
                        print(f"Counter: {counter}, Random: {random_value:.4f}")
        except Exception as e:
            if self.debug:
                print(f"Error: {e}")
            self.running = False
    
    async def disconnect(self):
        """Disconnect from the server."""
        self.running = False
        await self.client.disconnect()

async def main():
    client = ExampleClient(debug=True)
    try:
        await client.connect()
        await client.run()
    except KeyboardInterrupt:
        print("\nDisconnecting...")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main()) 