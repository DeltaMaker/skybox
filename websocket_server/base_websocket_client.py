import asyncio
import json
import websockets
import time
import logging

class BaseWebSocketClient:
    def __init__(self, connections, debug=True):
        """
        Initialize the BaseWebSocketClient with a list of connections.
        :param connections: A dictionary where the key is the service name and the value contains:
                            - 'uri': The WebSocket URI for the service.
                            - 'subscription': The JSON-RPC or subscription message.
                            - 'root': The root of the current state being subscribed to.
        :param debug: Whether to enable debug logging.
        """
        self.connections = connections
        self.debug = debug
        self.current_state = {}  # To store the current state of each service or connection
        self.running = False  # To indicate if the connection is running

        # Initialize the additional fields in the connections dictionary
        for name, conn_info in self.connections.items():
            conn_info['connected'] = False  # Initially not connected
            conn_info['task'] = None  # Will be set when the connection is established
            conn_info['last_time'] = 0  # Timestamp for the last message

    async def connect_to_services(self):
        """
        Establish WebSocket connections to all services defined in self.connections.
        """
        self.running = True  # Set running status to True
        for name, conn_info in self.connections.items():
            uri = conn_info['uri']
            # Start connection with retries
            task = asyncio.create_task(self._connect_with_retries(uri, conn_info['root'], name))
            self.connections[name]['task'] = task  # Store the task in the connections dictionary

        # Await the tasks associated with each connection
        await asyncio.gather(*[conn_info['task'] for conn_info in self.connections.values()])

    async def _connect_with_retries(self, uri, root, name):
        """
        Attempt to connect with retries on failure.
        """
        retry_interval = 5
        max_retries = 60  # Maximum retries before giving up
        retry_count = 0

        while self.running:
            try:
                async with websockets.connect(uri) as websocket:
                    self.connections[name]['connected'] = True  # Update connection status
                    if self.debug:
                        print(f"Connected to {name} at {uri}")

                    # Subscribe to the service after connecting
                    await self.subscribe(websocket, name)

                    # Start listening for messages
                    listen_task = asyncio.create_task(self.listen(websocket, root, name))
                    self.connections[name]['task'] = listen_task

                    # Start the periodic timeout checker
                    asyncio.create_task(self.check_broadcast_timeout(name, root))

                    # Reset retry count if connection was successful
                    retry_count = 0

                    # Await for the listening task to finish (i.e., connection closed)
                    await listen_task

            except (websockets.ConnectionClosedError, websockets.InvalidURI, websockets.InvalidHandshake) as e:
                if self.debug:
                    print(f"Connection to {name} failed: {e}. Retrying in {retry_interval} seconds...")

                retry_count += 1
                if retry_count >= max_retries:
                    if self.debug:
                        print(f"Max retries reached for {name}. Giving up.")
                    break  # Stop retrying if max retries are reached

                await asyncio.sleep(retry_interval)

            except (ConnectionRefusedError, OSError) as e:
                if self.debug:
                    print(f"Connection to {name} failed: {e}. Retrying in {retry_interval} seconds...")

                retry_count += 1
                if retry_count >= max_retries:
                    if self.debug:
                        print(f"Max retries reached for {name}. Giving up.")
                    break  # Stop retrying if max retries are reached

                await asyncio.sleep(retry_interval)

            except Exception as e:
                if self.debug:
                    print(f"Unexpected error while connecting to {name}: {e}")
                    import traceback
                    traceback.print_exc()  # Log the traceback for debugging
                await asyncio.sleep(retry_interval)

    async def subscribe(self, websocket, name):
        """
        Send the subscription message to the WebSocket server.
        :param websocket: The WebSocket connection.
        :param name: The name of the service.
        """
        try:
            subscription = self.connections[name]['subscription']
            await websocket.send(json.dumps(subscription))

            # Track the last broadcast time for the subscription inside the connections dictionary
            self.connections[name]['last_time'] = time.time()

            if self.debug:
                print(f"Subscribed to {name} with subscription: {subscription}")
        except Exception as e:
            logging.error(f"Error sending subscription for {name}: {e}")

    async def listen(self, websocket, root, name):
        """
        Listen for WebSocket messages and process them.
        :param websocket: The WebSocket connection.
        :param root: The root of the server's current state being subscribed to.
        :param name: The name of the service (e.g., 'moonraker', 'skybox').
        """
        try:
            while self.running:
                message = await websocket.recv()
                data = json.loads(message)
                if self.debug:
                    print(f"Received message from {name}: {data}")

                # Handle different types of messages
                if 'method' in data and data['method'].endswith('disconnected'):
                    if self.debug:
                        print(f"Received '{data['method']}' for {name}. Attempting to reconnect...")
                    # Stop the client and reconnect dynamically based on root
                    await self.stop()
                    await self.reconnect_to_service(root)

                elif 'method' in data and data['method'].endswith('update'):
                    # Update state based on the 'update' method
                    await self.update_state(data['params'][0], root)

                elif 'result' in data and 'status' in data['result']:
                    # Update state based on the 'result' key in the message
                    await self.update_state(data['result']['status'], root)

                # Update the last time a message was received
                self.connections[name]['last_time'] = time.time()

        except websockets.ConnectionClosed:
            logging.error(f"Connection to {name} closed.")
            self.connections[name]['connected'] = False  # Update connection status
        except Exception as e:
            logging.error(f"Error while listening to {name}: {e}")

    async def update_state(self, updated_objects, root):
        """
        Update the client's copy of the server's current_state for the requested objects.
        :param updated_objects: The objects that were updated.
        :param root: The root of the server's current state being updated.
        """
        if root not in self.current_state:
            self.current_state[root] = {}

        if self.debug:
            print(f"Updating state for {root}: {updated_objects}")

        # Perform a deep update on the current state for the given root
        self.deep_update(self.current_state[root], updated_objects)

    def deep_update(self, source, updates):
        """
        Recursively update the source dictionary with updates.
        :param source: The source dictionary to update.
        :param updates: The dictionary with updated values.
        """
        for key, value in updates.items():
            if isinstance(value, dict) and key in source and isinstance(source[key], dict):
                self.deep_update(source[key], value)
            else:
                source[key] = value

    async def check_broadcast_timeout(self, name, root, timeout_interval=30):
        """
        Periodically check if broadcasts from the service are being received.
        :param name: The name of the service (e.g., 'moonraker', 'skybox').
        :param root: The root of the service.
        :param timeout_interval: Timeout interval in seconds.
        """
        while self.running:
            await asyncio.sleep(10)  # Check every 10 seconds

            # Calculate the time since the last broadcast was received
            time_since_last_broadcast = time.time() - self.connections[name].get('last_time', 0)

            if time_since_last_broadcast > timeout_interval:
                if self.debug:
                    print(f"Timeout detected for {name}: No broadcasts for {timeout_interval} seconds.")

                # Reconnect to the service due to timeout
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
            task = self.connections[root].get('task', None)
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

    async def stop(self):
        """
        Stop all connections and tasks.
        """
        self.running = False  # Set running to False to stop the event loop
        for name, conn_info in self.connections.items():
            task = conn_info.get('task', None)
            if task and not task.done():
                task.cancel()  # Cancel the listening task for this connection
            conn_info['connected'] = False  # Mark the connection as disconnected

        # Await cancellation of all tasks
        await asyncio.gather(*[conn_info['task'] for conn_info in self.connections.values() if 'task' in conn_info])

        if self.debug:
            print("All WebSocket connections stopped.")


def main():
    """
    Entry point for starting the BaseWebSocketClient and subscribing to the server's current state.
    The client subscribes to specific roots in the server's current_state.
    """
    # Define the WebSocket connections with root-based subscriptions
    connections = {
        'skylight': {                       # server name
            'uri': 'ws://localhost:8080/websocket',  # WebSocket URI of the running server
            'root': 'skylight',  # Subscribe to the "skylight" root of the server's current_state
            'subscription': {
                "jsonrpc": "2.0",
                "method": "subscribe",  # Subscription method
                "params": {
                    "objects": {
                        "skylight": None,  # Subscribe to items under "skylight"
                        "scene": None  # Optionally subscribe to the "scene" root entirely
                    }
                },
                "id": 1  # Unique subscription ID
            }
        }
    }

    # Initialize the client
    client = BaseWebSocketClient(connections, debug=True)

    try:
        # Start the client connection
        asyncio.run(client.connect_to_services())
    except KeyboardInterrupt:
        # Gracefully stop the client on Ctrl+C
        asyncio.run(client.stop())

if __name__ == "__main__":
    main()