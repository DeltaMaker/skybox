"""
ExampleClient - Demo implementation using SimpleWebsocketClient.

This example client demonstrates how to:
- Use SimpleWebsocketClient with composition pattern
- Process and display received messages
- Handle connection lifecycle
- Implement clean shutdown

Usage:
    python example_client.py [--host HOST] [--port PORT] [--debug]

Pairs with example_server.py for testing WebSocket communication.
"""
import sys
import os
# Add the root directory of your project to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import json
import argparse
import websockets
from websocket_server.simple_client import SimpleWebsocketClient

class ExampleViewer:
    def __init__(self, debug: bool = False):
        """Initialize the example viewer."""
        self.debug = debug

    def process_message(self, message):
        """Process received message."""
        if isinstance(message, str):
            try:
                data = json.loads(message)
                print(f"Received JSON: {data}")
            except json.JSONDecodeError:
                print(f"Received text message: {message}")
        else:
            print(f"Received binary message of length: {len(message)} bytes")
        return False  # Continue running


async def run_example_client(ws_uri, debug=False):
    """Main client coroutine that connects to the websocket server and processes messages."""
    client = SimpleWebsocketClient(ws_uri)
    viewer = ExampleViewer(debug=debug)
    
    try:
        print(f"Connecting to {ws_uri}...")
        await client.connect()
        print("Connected successfully")

        # Example configuration
        config = {"test": True}

        print("Sending subscription config...")
        await client.subscribe(config)
        print("Subscription confirmed")

        # Receive messages
        print("Receiving messages (press Ctrl+C to stop)...")
        while True:
            try:
                message = await client.receive()
                if viewer.process_message(message):
                    break
            except websockets.exceptions.ConnectionClosed:
                print("\nConnection closed by server")
                break
            except Exception as e:
                print(f"\nError processing message: {e}")
                break

    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"\nConnection error: {e}")
    finally:
        print("Disconnecting...")
        await client.disconnect()
        print("Disconnected")


def main():
    """Entry point of the application."""
    parser = argparse.ArgumentParser(description="Example WebSocket Client")
    parser.add_argument("--host", type=str, default="localhost", help="Server host (default: localhost)")
    parser.add_argument("--port", type=int, default=7160, help="Server port (default: 7160)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    
    args = parser.parse_args()
    url = f"ws://{args.host}:{args.port}/websocket"

    try:
        asyncio.run(run_example_client(url, args.debug))
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"\nUnexpected error: {e}")


if __name__ == "__main__":
    main() 