import asyncio
import json
import websockets
import time

class BaseWebSocketClient:
    def __init__(self, connections, subscriptions, debug=True):
        self.connections = connections
        self.subscriptions = subscriptions
        self.debug = debug
        self.current_state = {}
        self.connection_tasks = []
        self.running = False
        #self.on_state_update = None  # Callback for state updates

    async def _connect_with_retries(self, uri, root, name):
        """Attempt to connect with retries on failure."""
        retry_interval = 5
        while self.running:
            try:
                async with websockets.connect(uri) as websocket:
                    if self.debug:
                        print(f"Connected to {name}: {uri}")
                    await self.subscribe(websocket, name)
                    await self.listen(websocket, root, name)
            except (websockets.ConnectionClosedError, websockets.InvalidURI, websockets.InvalidHandshake) as e:
                if self.debug:
                    print(f"Connection to {name} failed: {e}. Retrying in {retry_interval} seconds...")
                await asyncio.sleep(retry_interval)
            except (ConnectionRefusedError, OSError) as e:
                if self.debug:
                    print(f"Connection to {name} failed: {e}. Retrying in {retry_interval} seconds...")
                await asyncio.sleep(retry_interval)
            except Exception as e:
                if self.debug:
                    print(f"Unexpected error while connecting to {name}: {e}")
                await asyncio.sleep(retry_interval)


    async def connect_with_retries(self, uri, root, name):
        """Attempt to connect with retries on failure."""
        retry_interval = 5
        max_retries = 60  # Maximum retries before considering failure (adjust as needed)
    
        retry_count = 0
        while self.running:
            try:
                async with websockets.connect(uri) as websocket:
                    if self.debug:
                        print(f"Connected to {name}: {uri}")
    
                    # Resubscribe after connecting
                    await self.subscribe(websocket, name)

                    # Start the periodic timeout checker
                    asyncio.create_task(self.check_broadcast_timeout())

                    # Start listening for messages
                    await self.listen(websocket, root, name)

                    # Reset retry count if connection was successful
                    retry_count = 0

            except (websockets.ConnectionClosedError, websockets.InvalidURI, websockets.InvalidHandshake) as e:
                if self.debug:
                    print(f"Connection to {name} failed: {e}. Retrying in {retry_interval} seconds...")

                retry_count += 1
                if retry_count >= max_retries:
                    if self.debug:
                        print(f"Max retries reached for {name}. Giving up.")
                    break  # Exit the loop if maximum retries are exceeded

                await asyncio.sleep(retry_interval)

            except (ConnectionRefusedError, OSError) as e:
                if self.debug:
                    print(f"Connection to {name} failed: {e}. Retrying in {retry_interval} seconds...")

                retry_count += 1
                if retry_count >= max_retries:
                    if self.debug:
                        print(f"Max retries reached for {name}. Giving up.")
                    break  # Exit the loop if maximum retries are exceeded

                await asyncio.sleep(retry_interval)

            except Exception as e:
                if self.debug:
                    print(f"Unexpected error while connecting to {name}: {e}")
                    import traceback
                    traceback.print_exc()  # Log detailed traceback

                await asyncio.sleep(retry_interval)


    async def subscribe(self, websocket, name):
        """Subscribe to a specific service and initialize the last_broadcast_time for that subscription."""
    
        # Ensure the dictionary to track the last broadcast time exists
        if not hasattr(self, 'last_broadcast_times'):
            self.last_broadcast_times = {}

        # Initialize the last_broadcast_time for the specific subscription (name)
        self.last_broadcast_times[name] = time.time()

        # Extract the subscription command for the specified name
        subscribe_command = self.subscriptions[name]
        await websocket.send(json.dumps(subscribe_command))

        if self.debug:
            print(f"Subscribed to {name}")


    async def listen(self, websocket, root, name):
        while self.running:
            try:
                message = await websocket.recv()
                data = json.loads(message)
                #print(f"data = {data}")
                if 'method' in data and data['method'].endswith('disconnected'):
                    if self.debug:
                        print(f"Received '{data['method']}' for {name}. Attempting to reconnect...")
                    # Stop the client and reconnect dynamically based on root
                    await self.stop()
                    # Reconnect and resubscribe dynamically
                    await self.reconnect_to_service(root)
                elif 'method' in data and data['method'].endswith('update'):
                    await self.update_state(data['params'][0], root)
                elif 'result' in data and 'status' in data['result']:
                    await self.update_state(data['result']['status'], root)
            except websockets.ConnectionClosed:
                if self.debug:
                    print(f"Connection to {name} closed")
                break
            except Exception as e:
                if self.debug:
                    print(f"Error while listening to {name}: {e}")
                break

    async def check_broadcast_timeout(self, timeout_interval=30):
        """ Periodically check if broadcasts from Moonraker are being received for each subscription. """
        while self.running:
            await asyncio.sleep(10)  # Check every 10 seconds
            print(self.last_broadcast_times)
 
            # Loop through each subscription (root) and check the last broadcast time
            for root, last_time in self.last_broadcast_times.items():
                time_since_last_broadcast = time.time() - last_time
                if time_since_last_broadcast > timeout_interval:
                    if self.debug:
                        print(f"Timeout detected for {root}: No broadcasts for {timeout_interval} seconds.")
                    # Trigger reconnection or resubscription for this root
                    await self.reconnect_to_service(root)

    async def reconnect_to_service(self, root):
        """Reconnect to a service and resubscribe to broadcasts dynamically based on the root."""
        if self.debug:
            print(f"Reconnecting to service for {root}...")

        # Check if the connection exists for the given root and close it if it's open
        if root in self.connections and self.connections[root].open:
            await self.connections[root].close()
            if self.debug:
                print(f"Closed existing WebSocket connection for {root}.")

        # Use the URI from self.connections for this specific root
        service_uri = self.connections.get(root, {}).get("uri", None)

        if not service_uri:
            if self.debug:
                print(f"No URI found for {root}, skipping reconnection.")
            return

        # Reconnect using the connection URI and the root
        await self.connect_with_retries(service_uri, root, root)

        # After reconnecting, resubscribe using the subscriptions for this root
        if root in self.subscriptions:
            subscribe_command = self.subscriptions[root]
            await self.subscribe(subscribe_command, root)

        if self.debug:
            print(f"Successfully reconnected and resubscribed to {root}.")

    async def update_state(self, updated_objects, root):
        """Update the state dictionary with the objects that have changed."""
        if root not in self.current_state:
            self.current_state[root] = {}
        if self.debug:
            print(f"updated_objects = {updated_objects}")

        self.deep_update(self.current_state[root], updated_objects)

        if self.on_state_update:
            await self.on_state_update(root, updated_objects)

    def deep_update(self, source, updates):
        """Recursively update the source dictionary with updates."""
        for key, value in updates.items():
            if isinstance(value, dict) and key in source and isinstance(source[key], dict):
                self.deep_update(source[key], value)
            else:
                source[key] = value

    def get_state(self, path, default=None):
        """Get the value from self.current_state specified by the path."""
        keys = path.split('.')
        current_dict = self.current_state
        for key in keys:
            if isinstance(current_dict, dict) and key in current_dict:
                current_dict = current_dict[key]
            else:
                return default
        if default is not None and current_dict is not None:
            if self.debug and type(default) != type(current_dict):
                print(f'get_state() type mismatch {type(default)} {type(current_dict)}')
        return current_dict if current_dict is not None else default

    async def on_state_update(self, root, updated_objects):
        """Hook method for handling state updates."""
        if self.debug:
            print(f"Updated state for {root}: {json.dumps(self.current_state[root], indent=2)}")
        pass

    async def run_connections(self):
        for connection in self.connections:
            for root, uri in connection.items():
                task = asyncio.create_task(self.connect_with_retries(uri, root, root))
                self.connection_tasks.append(task)
        await asyncio.gather(*self.connection_tasks)

    async def start(self):
        if self.debug:
            print("Starting client connections...")
        self.running = True
        await self.run_connections()

    async def stop(self):
        self.running = False
        for task in self.connection_tasks:
            task.cancel()
        await asyncio.gather(*self.connection_tasks, return_exceptions=True)
        self.connection_tasks.clear()

    def get_current_state(self):
        return self.current_state

# Example usage
def main():
    connections = [
        {"moonraker": "ws://localhost:7125/websocket"}
    ]
    subscriptions = {
        "moonraker": {
            "jsonrpc": "2.0",
            "method": "printer.objects.subscribe",
            "params": {
                "objects": {
                    "print_stat": None,
                    "display_status": None,
                    "idle_timeout": None,
                    "extruder": ['temperature', 'target', 'power']
                }
            },
            "id": 2
        }
    }
    client = BaseWebSocketClient(connections, subscriptions, debug=True)
    asyncio.run(client.start())

if __name__ == "__main__":
    main()

