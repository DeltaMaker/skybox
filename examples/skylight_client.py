import sys
import os
# Add the root directory of your project to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import json
import aiohttp
from websocket_server import BaseWebSocketClient
from typing import Dict, Optional

class SkylightClient(BaseWebSocketClient):
    def __init__(self, host='localhost', port=7120, debug=True):
        """Initialize the Skylight client"""
        # Configure the connection
        connections = {
            'skylight': {
                'uri': f'ws://{host}:{port}/websocket',
                'root': 'skylight',
                'subscription': {
                    "jsonrpc": "2.0",
                    "method": "subscribe",
                    "params": {
                        "objects": {
                            "skylight": None,
                            "scene": None,
                            "moonraker": None
                        }
                    },
                    "id": 1
                }
            }
        }
        # Initialize the base class
        super().__init__(connections, debug)
        self.host = host
        self.port = port

    async def set_brightness(self, brightness: int) -> Dict:
        """Set the LED brightness"""
        async with aiohttp.ClientSession() as session:
            url = f"http://{self.host}:{self.port}/skylight/control"
            params = {'brightness': brightness}
            async with session.post(url, json=params) as response:
                return await response.json()

    async def show_preset(self, preset_name: str) -> Dict:
        """Show a preset scene"""
        async with aiohttp.ClientSession() as session:
            url = f"http://{self.host}:{self.port}/skylight/scene"
            params = {'preset': preset_name}
            async with session.post(url, json=params) as response:
                return await response.json()

async def run_example():
    # Create and start client
    client = SkylightClient(debug=True)
    
    try:
        # Start the client
        await client.start()
        
        # Example interactions
        print("Setting brightness to 128...")
        await client.set_brightness(128)
        await asyncio.sleep(2)

        print("\nShowing rainbow preset...")
        await client.show_preset("rainbow")
        await asyncio.sleep(2)

        print("\nMonitoring state updates (press Ctrl+C to exit)...")
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await client.stop()

def main():
    asyncio.run(run_example())

if __name__ == "__main__":
    main()