import asyncio
import json
import websockets
import time
import logging
from typing import Dict, Any, Optional

class BaseWebSocketClient:
    def __init__(self, connections: Dict[str, Dict[str, Any]], debug: bool = True):
        """
        Initialize the BaseWebSocketClient with a list of connections.
        :param connections: Dictionary of connection configurations
        :param debug: Enable debug logging
        """
        self.connections = connections
        self.debug = debug
        self.current_state: Dict[str, Dict] = {}
        self.running = False
        self.tasks: Dict[str, asyncio.Task] = {}
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Initialize connection states
        for name, conn_info in self.connections.items():
            conn_info['connected'] = False
            conn_info['last_time'] = 0

    async def start(self) -> None:
        """Start the client and establish connections"""
        self.running = True
        try:
            # Get or create event loop
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

        # Start connections
        for name, conn_info in self.connections.items():
            self.tasks[name] = self.loop.create_task(
                self._connect_with_retries(
                    conn_info['uri'],
                    conn_info['root'],
                    name
                )
            )

    async def _connect_with_retries(self, uri: str, root: str, name: str) -> None:
        """Maintain persistent connection with retry logic"""
        retry_interval = 5
        while self.running:
            try:
                async with websockets.connect(uri) as websocket:
                    self.connections[name]['connected'] = True
                    if self.debug:
                        print(f"Connected to {name} at {uri}")

                    # Subscribe to the service
                    await self.subscribe(websocket, name)
                    
                    # Start monitoring tasks
                    listen_task = self.loop.create_task(
                        self.listen(websocket, root, name)
                    )
                    timeout_task = self.loop.create_task(
                        self.check_broadcast_timeout(name, root)
                    )
                    
                    # Wait for either task to complete
                    done, pending = await asyncio.wait(
                        [listen_task, timeout_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    # Cancel pending tasks
                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

            except Exception as e:
                if self.debug:
                    print(f"Connection error for {name}: {e}")
                self.connections[name]['connected'] = False
                await asyncio.sleep(retry_interval)

    async def subscribe(self, websocket, name: str) -> None:
        """Send subscription message to service"""
        subscription = self.connections[name]['subscription']
        await websocket.send(json.dumps(subscription))
        self.connections[name]['last_time'] = time.time()
        
        if self.debug:
            print(f"Subscribed to {name}")

    async def listen(self, websocket, root: str, name: str) -> None:
        """Listen for messages from the service"""
        try:
            while self.running:
                message = await websocket.recv()
                data = json.loads(message)
                
                if self.debug:
                    print(f"Received from {name}: {data}")

                self.connections[name]['last_time'] = time.time()
                await self._process_message(data, root, name)
                
        except websockets.ConnectionClosed:
            self.connections[name]['connected'] = False
            if self.debug:
                print(f"Connection to {name} closed")
            raise

    async def _process_message(self, data: Dict, root: str, name: str) -> None:
        """Process received message and update state"""
        if 'method' in data:
            if data['method'].endswith('disconnected'):
                await self.handle_disconnection(root)
            elif data['method'].endswith('update'):
                await self.update_state(data['params'][0], root)
        elif 'result' in data and 'status' in data['result']:
            await self.update_state(data['result']['status'], root)

    async def check_broadcast_timeout(self, name: str, root: str, timeout: int = 30) -> None:
        """Monitor connection for timeouts"""
        while self.running:
            await asyncio.sleep(10)
            if time.time() - self.connections[name]['last_time'] > timeout:
                if self.debug:
                    print(f"Timeout detected for {name}")
                raise TimeoutError(f"Connection to {name} timed out")

    async def stop(self) -> None:
        """Stop the client and cleanup resources"""
        self.running = False
        
        # Cancel all tasks
        for name, task in self.tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self.tasks.clear()
        
        # Reset connection states
        for conn_info in self.connections.values():
            conn_info['connected'] = False

    async def update_state(self, updated_objects: Dict, root: str) -> None:
        """Update internal state with new data"""
        if root not in self.current_state:
            self.current_state[root] = {}
        self.deep_update(self.current_state[root], updated_objects)

    def deep_update(self, source: Dict, updates: Dict) -> None:
        """Recursively update dictionary"""
        for key, value in updates.items():
            if isinstance(value, dict) and key in source and isinstance(source[key], dict):
                self.deep_update(source[key], value)
            else:
                source[key] = value

    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.stop()

    async def handle_disconnection(self, root: str):
        """Handle service disconnection"""
        if self.debug:
            print(f"Handling disconnection for {root}")
        await self.stop()
        await self.reconnect_to_service(root)

    async def reconnect_to_service(self, root):
        """
        Reconnect to a service and resubscribe to broadcasts dynamically based on the root.
        :param root: The root of the service.
        """
        if self.debug:
            print(f"Reconnecting to service for {root}...")

        # Check if the connection exists for the given root and close it if it's open
        if root in self.connections and self.connections[root]['connected']:
            # Cancel the existing task for this connection
            task = self.tasks.get(root, None)
            if task:
                task.cancel()

            self.connections[root]['connected'] = False

        # Use the URI from self.connections for this specific root
        service_uri = self.connections.get(root, {}).get("uri", None)

        if not service_uri:
            if self.debug:
                print(f"No URI found for {root}, skipping reconnection.")
            return

        # Reconnect using the connection URI and the root
        await self._connect_with_retries(service_uri, root, root)


def main():
    """Example of how to use BaseWebSocketClient to subscribe to skylight server"""
    # Define the WebSocket connections
    connections = {
        'skylight': {
            'uri': 'ws://localhost:7120/websocket',
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

    async def run_client():
        client = BaseWebSocketClient(connections, debug=True)
        await client.start()
        
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await client.stop()

    asyncio.run(run_client())

if __name__ == "__main__":
    main()