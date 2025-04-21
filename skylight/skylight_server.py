import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time
import asyncio
import json
import websockets
from aiohttp import web
from websocket_server.simple_server import SimpleWebsocketServer
from websocket_server.simple_client import SimpleWebsocketClient
from skylight.led_controller import LEDController
from config.config_manager import ConfigManager

class SkylightClient(SimpleWebsocketClient):
    """Client for connecting to external services (Moonraker, Skybox)"""
    def __init__(self, url: str, subscription: dict, debug: bool = False, debug_level: int = 1):
        super().__init__(url, debug=debug, debug_level=debug_level)
        self.subscription = subscription
        self.last_state = None  # Track last known state

    async def start(self, callback):
        """Start client with callback for updates"""
        self.debug_log(f"Starting SkylightClient connection to {self.url}", 3)
        self.callback = callback
        await self.connect()
        self.debug_log(f"Connected and subscribing with: {self.subscription}", 3)
        await self.subscribe(self.subscription)
        asyncio.create_task(self.receive_loop())

    async def receive_loop(self):
        """Continuously receive and process messages"""
        self.debug_log(f"Receive loop started for {self.url}", 3)
        disconnect_time = None
        
        while True:
            try:
                if not self.is_connected:
                    if disconnect_time is None:
                        disconnect_time = time.time()
                        print(f"Connection lost to {self.url} at {time.strftime('%H:%M:%S')}")
                    
                    if time.time() - disconnect_time > 30:  # Only log every 30 seconds
                        print(f"Connection has been down for {(time.time() - disconnect_time):.0f}s, attempting to reconnect...")
                    
                    await self.connect()
                    if disconnect_time is not None:
                        print(f"Reconnected to {self.url} after {(time.time() - disconnect_time):.0f}s downtime")
                        disconnect_time = None
                    await self.subscribe(self.subscription)
                
                message = await self.receive()
                if isinstance(message, str):
                    data = json.loads(message)
                    if self.callback:
                        # Track significant state changes only
                        if isinstance(data, dict):
                            if 'params' in data and isinstance(data['params'], list) and data['params']:
                                new_state = data['params'][0]
                                if self.last_state != new_state:
                                    # Only log state changes that affect printer status
                                    state_diff = {}
                                    for key in ['state', 'is_paused', 'target', 'temperature']:
                                        if key in new_state and (not self.last_state or key not in self.last_state or new_state[key] != self.last_state[key]):
                                            state_diff[key] = new_state[key]
                                    if state_diff:
                                        self.debug_log(f"State changes: {state_diff}", 2)
                                    self.last_state = new_state
                        await self.callback(data)
                await asyncio.sleep(0.1)
            except websockets.exceptions.ConnectionClosed as e:
                self.debug_log(f"WebSocket connection closed to {self.url}: code={e.code}", 2)
                await asyncio.sleep(1.0)  # Wait before retry
            except json.JSONDecodeError as e:
                self.debug_log(f"JSON decode error from {self.url}", 2)
                await asyncio.sleep(1.0)
            except Exception as e:
                self.debug_log(f"Error in receive loop for {self.url}: {type(e).__name__}: {str(e)}", 1)
                await asyncio.sleep(1.0)

class SkylightServer(SimpleWebsocketServer):
    def __init__(self, config_manager, host='0.0.0.0', debug=True, debug_level=2):
        # Initialize server
        port = config_manager.getint('skylight', 'skylight_port', 7120)
        super().__init__(host=host, port=port, debug=debug, debug_level=debug_level)
        
        self.config_manager = config_manager
        
        # Initialize LED controller
        led_count = config_manager.getint('skylight', 'led_count', 30)
        self.update_interval = config_manager.getint('skylight', 'update_interval', 2)
        self.last_update_time = 0
        self.current_state = self.initialize_current_state(led_count, self.update_interval)
        self.led_controller = LEDController(led_count)
        
        # Initialize clients
        self.moonraker_client = self.setup_moonraker_client()
        # self.skybox_client = self.setup_skybox_client()
        
        # Start with rainbow preset
        self.show_preset("rainbow")

    def initialize_current_state(self, led_count, update_interval):
        """Initialize the current state of the Skylight system."""
        return {
            "update_interval": update_interval,
            "scene": {},
            "skylight": {
                "status": "on",
                "chain_count": led_count,
                "preset_scene": "rainbow",
                "brightness": 50,
                "error": None
            },
            "moonraker": {
                "temperature": 0,
                "target": 0,
                "progress": 0,
                "state": "none",
                "is_paused": False
            },
            "preset_formats": {
                "temperature": [["fade", 0, led_count, "blue", "red", 0]],
                "progress": [["progress", 0, led_count, "green", "white", 0]],
                "paused": [["breathe", 0, led_count, "yellow", "black", 0]],
                "ready": [["blend", 0, led_count, "blue", "green", 0]],
                "idle": [["chase", 0, led_count, "white", "black", 0]],
                "rainbow": [["rainbow", 0, led_count, "white", "black", 0]],
                "data": [["output", "1001", 4, "green", "blue", 1],
                         ["breathe", "11101", 5, "blue", "green", 1],
                         ["chase", "0000", 4, "red", "black", 1]]
            }
        }

    def setup_moonraker_client(self):
        """Setup Moonraker client"""
        self.debug_log(f"Setting up Moonraker client with URI: {self.config_manager.moonraker_uri()}", 3)
        
        client = SkylightClient(
            url=self.config_manager.moonraker_uri(),
            subscription={
                "jsonrpc": "2.0",
                "method": "printer.objects.subscribe",
                "params": {
                    "objects": {
                        "print_stats": None,  # ["state"],
                        "display_status": ["progress"],
                        "idle_timeout": ["state"],
                        "extruder": ["temperature", "target"],
                        "pause_resume": ["is_paused"]
                    }
                },
                "id": 2 
            },
            debug=self.debug,
            debug_level=1  # Only show errors by default
        )
        
        # Configure subscription validation
        def moonraker_confirmation(data: dict) -> bool:
            self.debug_log(f"Checking Moonraker subscription confirmation: {data}", 3)
            if data.get('jsonrpc') == '2.0':
                if 'result' in data and isinstance(data['result'], dict) and 'status' in data['result']:
                    self.update_moonraker_state(data['result']['status'])
                    self.debug_log("Moonraker subscription confirmed", 3)
                    return True
                if 'error' in data:
                    self.debug_log(f"Subscription error: {data['error']}", 1)
            return False
        
        async def handle_notifications(msg: dict) -> None:
            # Only handle non-status-update notifications here
            # Status updates are handled by handle_moonraker_update
            if 'method' in msg:
                if msg['method'] != 'notify_status_update':
                    self.debug_log(f"Moonraker notification: {msg['method']}", 3)
                else:
                    self.debug_log("Received status update notification", 4)
        
        self.debug_log("Setting up Moonraker subscription handlers", 3)
        
        client.set_subscription_handlers(
            confirmation_predicate=moonraker_confirmation,
            notification_handler=handle_notifications
        )
        
        self.debug_log("Moonraker client setup complete", 3)
        
        return client

    def setup_skybox_client(self):
        """Setup Skybox client"""
        self.debug_log(f"Setting up Skybox client with URI: {self.config_manager.skybox_uri()}", 3)
        
        client = SkylightClient(
            url=self.config_manager.skybox_uri(),
            subscription={
                "jsonrpc": "2.0",
                "method": "subscribe",
                "params": {
                    "objects": {
                        "data_fields": None,
                        "data_values": None,
                    }
                },
                "id": 3
            },
            debug=self.debug,
            debug_level=1  # Only show errors by default
        )
        
        # Configure subscription validation
        def skybox_confirmation(response: dict) -> bool:
            if response.get('jsonrpc') == '2.0':
                if 'result' in response and response['result'].get('status') == 'ok':
                    self.debug_log("Skybox subscription confirmed", 3)
                    return True
                if 'error' in response:
                    self.debug_log(f"Subscription error: {response['error']}", 1)
            return False
        
        async def handle_notifications(msg: dict) -> None:
            if 'method' in msg and msg['method'] == 'notify_data_update':
                self.debug_log(f"Received data update during subscribe: {msg}", 4)
        
        self.debug_log("Setting up Skybox subscription handlers", 3)
        
        client.set_subscription_handlers(
            confirmation_predicate=skybox_confirmation,
            notification_handler=handle_notifications
        )
        
        self.debug_log("Skybox client setup complete", 3)
        
        return client

    def perform_initialization(self, config):
        """Initialize when first client connects"""
        pass  # Client connections are now started in start_server

    async def start_clients(self):
        """Start all client connections"""
        await self.moonraker_client.start(self.handle_moonraker_update)
        # await self.skybox_client.start(self.handle_skybox_update)

    async def handle_moonraker_update(self, data):
        """Handle updates from Moonraker"""
        try:
            if isinstance(data, dict):
                if 'result' in data and isinstance(data['result'], dict) and 'status' in data['result']:
                    self.update_moonraker_state(data['result']['status'])
                elif 'params' in data and isinstance(data['params'], list) and len(data['params']) > 0:
                    self.update_moonraker_state(data['params'][0])
                elif 'method' in data and data['method'] == 'notify_status_update':
                    if 'params' in data and isinstance(data['params'], list) and len(data['params']) > 0:
                        self.update_moonraker_state(data['params'][0])
                else:
                    self.debug_log(f"Unhandled dict message format: {data}", 4)
            else:
                self.debug_log(f"Unhandled message type: {type(data)}", 4)
            
        except Exception as e:
            self.debug_log(f"Error processing Moonraker update: {str(e)}", 1)
            self.debug_log(f"Message type: {type(data)}", 1)
            self.debug_log(f"Message content: {data}", 1)
            if isinstance(data, dict):
                self.debug_log(f"Message keys: {data.keys()}", 1)

    def update_moonraker_state(self, data):
        """Update the state of the Skylight system based on Moonraker messages."""
        try:
            if not isinstance(data, dict):
                return

            # Extract values with better error handling
            extruder_data = data.get("extruder", {})
            if not isinstance(extruder_data, dict):
                extruder_data = {}
            
            display_data = data.get("display_status", {})
            if not isinstance(display_data, dict):
                display_data = {}
            
            idle_data = data.get("idle_timeout", {})
            if not isinstance(idle_data, dict):
                idle_data = {}
            
            pause_data = data.get("pause_resume", {})
            if not isinstance(pause_data, dict):
                pause_data = {}

            # Update state with extracted values
            default_state = self.current_state["moonraker"]
            new_state = {
                "temperature": extruder_data.get("temperature", default_state["temperature"]),
                "target": extruder_data.get("target", default_state["target"]),
                "progress": display_data.get("progress", default_state["progress"]),
                "state": idle_data.get("state", default_state["state"]),
                "is_paused": pause_data.get("is_paused", default_state["is_paused"])
            }

            # Only update and log if there are meaningful changes
            changes = {}
            for key, value in new_state.items():
                if abs(value - default_state[key]) > 0.01 if isinstance(value, float) else value != default_state[key]:
                    changes[key] = value
                    self.current_state["moonraker"][key] = value

            # Update LED state if enough time has passed
            if time.time() - self.last_update_time > self.current_state["update_interval"]:
                self.last_update_time = time.time()
                self.update_skylight_state()
                if changes:
                    self.debug_log(f"Moonraker state changes: {changes}", 2)

        except Exception as e:
            self.debug_log(f"Error in update_moonraker_state: {str(e)}", 1)

    def update_skylight_state(self):
        """Determine the state of the Skylight system and update LED patterns."""
        preset_scene, percent = self.determine_mode()
        default_state = self.current_state["skylight"]
        if preset_scene != default_state['preset_scene']:
            self.debug_log(f"Changing preset scene from {default_state['preset_scene']} to {preset_scene}", 3)
            self.current_state['skylight']['preset_scene'] = preset_scene
            formats = self.current_state["preset_formats"].get(preset_scene, [])
            self.set_scene_format(formats)
        else:
            self.set_scene_values(percent)

    def determine_mode(self):
        """Determine the current mode of the Skylight system based on the Moonraker state."""
        heater_on = self.current_state["moonraker"]["target"] > 0
        warming_up = heater_on and (
                self.current_state["moonraker"]["target"] - self.current_state["moonraker"]["temperature"] > 2)
        cooling_down = self.current_state["moonraker"]["temperature"] > 50 and not heater_on
        ratio = max(0.0, min(1.0, self.current_state["moonraker"]["temperature"] / (
                self.current_state["moonraker"]["target"] or 250)))
        progress = self.current_state["moonraker"]["progress"]
        is_paused = self.current_state["moonraker"]["is_paused"]
        is_ready = self.current_state["moonraker"]["state"] == "Ready" and not heater_on and progress < 0.01
        is_idle = self.current_state["moonraker"]["state"] == "Idle"

        if is_paused:
            return "paused", 0
        if not warming_up and progress > 0:
            return "progress", progress
        if heater_on or cooling_down:
            return "temperature", ratio
        if is_ready:
            return "ready", 0
        if is_idle:
            return "idle", 0
        return "rainbow", 0

    async def handle_skybox_update(self, data):
        """Handle updates from Skybox"""
        self.debug_log(f"Skybox data received: {data}", 3)

    def extract_client_info(self, config):
        """Extract client configuration"""
        return {
            'type': config.get('type', 'web'),
            'name': config.get('name', 'unknown')
        }

    async def get_broadcast_data(self):
        """Get current state for broadcasting"""
        return {
            'timestamp': time.time(),
            'state': self.current_state
        }

    async def format_client_message(self, message_data, client_info):
        """Format message for specific client"""
        return {
            'data': message_data['state']
        }

    async def send_to_client(self, client_ws, message):
        """Send formatted message to client"""
        if not client_ws.closed:
            await client_ws.send_str(json.dumps(message))

    def show_preset(self, name):
        """Display the preset scene on the Skylight system."""
        self.debug_log(f"Showing preset: {name}", 3)
        format_data = self.current_state["preset_formats"].get(name, [])
        if format_data:
            self.current_state['skylight']['preset_scene'] = name
            self.set_scene_format(format_data)

    def set_scene_format(self, formats):
        """Set the LED controller to the specified format."""
        self.current_state["scene"] = formats
        self.debug_log(f"formats = {formats}", 4)
        self.last_values = None
        self.led_controller.set_data_fields(formats)

    def set_scene_values(self, values):
        """Set the LED controller to the specified values."""
        if self.last_values != values:
            self.debug_log(f"values = {values}", 4)
            self.last_values = values
        formats = self.current_state["scene"]
        n_values = len(formats) if formats else 1
        if not isinstance(values, list):
            values = [values] * n_values
        for i in range(n_values):
            if i < len(values):
                self.current_state["scene"][i][1] = values[i]

        self.led_controller.set_data_values(values)

    def set_brightness(self, brightness):
        """Set the brightness of the LED system."""
        self.current_state["skylight"]["brightness"] = brightness
        percent = brightness / 256 if brightness < 256 else 1.0
        self.led_controller.set_brightness(percent)

    async def send_led_overlay(self):
        """Continuously send the defined shapes (overlays) to an external WebSocket server."""
        try:
            # Get the WebSocket URI from the config manager
            uri = self.config_manager.get('skylight', 'websocket_uri', fallback='ws://localhost:7130/websocket')
            while self.running:
                try:
                    async with websockets.connect(uri) as websocket:
                        while self.running:
                            try:
                                color_strip = self.led_controller.get_overlay_shapes()
                                message_json = json.dumps({"overlay": color_strip})
                                self.debug_log(f"Sending overlay to {uri}: {message_json}", 4)
                                await websocket.send(message_json)
                                await asyncio.sleep(1.0)
                            except Exception as e:
                                self.debug_log(f"Error sending overlay: {e}", 2)
                                break  # Break out of the inner loop on error
                except Exception as e:
                    self.debug_log(f"Error connecting to WebSocket server at {uri}: {e}", 2)
                    await asyncio.sleep(5.0)  # Wait before retrying
        except Exception as e:
            self.debug_log(f"LED overlay task error: {e}", 1)

    def add_custom_routes(self, router):
        """Add custom routes for the Skylight server."""
        router.add_route('*', '/skylight/{tail:.*}', self.process_skylight_command)

    async def process_skylight_command(self, request):
        """Process Skylight control commands (e.g., brightness, actions, etc.)."""
        path = request.path
        query_params = request.query
        post_params = {}

        if request.method == 'POST':
            try:
                post_params = await request.json()
            except:
                post_params = {}

        if path == "/skylight/status" and request.method == 'GET':
            return web.json_response(self.current_state)

        if path == "/skylight/debug" and request.method in ['GET', 'POST']:
            combined_params = {**query_params, **post_params}
            if "level" in combined_params:
                new_level = int(combined_params["level"])
                self.set_debug_level(new_level)
            return web.json_response({"debug": self.debug, "level": self.debug_level})

        if path == "/skylight/control" and request.method in ['GET', 'POST']:
            combined_params = {**query_params, **post_params}

            if "brightness" in combined_params:
                self.set_brightness(int(combined_params["brightness"]))
            if "action" in combined_params:
                action = combined_params["action"]
                if action == 'on':
                    self.current_state["skylight"]["status"] = "on"
                    self.set_brightness(self.current_state["skylight"]["brightness"])
                elif action == 'off':
                    self.current_state["skylight"]["status"] = "off"
                    self.led_controller.set_brightness(0)

            return web.json_response(self.current_state["skylight"])

        if path == "/skylight/scene" and request.method in ['GET', 'POST']:
            combined_params = {**query_params, **post_params}
            if "format" in combined_params:
                format_data = json.loads(combined_params["format"])
                self.current_state['skylight']['preset_scene'] = "skybox"
                self.set_scene_format(format_data)
            if "values" in combined_params:
                values = json.loads(combined_params["values"])
                self.set_scene_values(values)
            if "preset" in combined_params:
                preset_name = combined_params["preset"]
                self.show_preset(preset_name)
            return web.json_response({"status": "success", "scene": self.current_state["scene"]})

        return web.json_response(
            {"error": "Not Found", "path": path},
            status=404
        )

    def perform_cleanup(self):
        """Cleanup when server stops"""
        asyncio.create_task(self.cleanup())

    async def cleanup(self):
        """Cleanup when server stops"""
        try:
            await self.moonraker_client.disconnect()
            # await self.skybox_client.disconnect()
            self.led_controller.cleanup()
        except Exception as e:
            self.debug_log(f"Cleanup error: {e}", 1)

    def set_debug_level(self, level):
        """Set the debug level for the server.
        
        Args:
            level: Debug level (1=errors, 2=warnings, 3=info, 4=verbose)
        """
        old_level = self.debug_level
        self.debug_level = level
        self.debug_log(f"Changed debug level from {old_level} to {level}", 1)
        
        # Update client debug levels
        if hasattr(self, 'moonraker_client'):
            self.moonraker_client.set_debug(self.debug, max(1, level - 1))  # Client gets one level less verbose
        
        return self.debug_level

def main():
    # Update config path to use absolute path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_dir = os.path.join(os.path.dirname(current_dir), 'config')
    print(f"Config directory: {config_dir}")
    config_manager = ConfigManager(config_file="localhost.conf", config_dir=config_dir)
    
    # Get debug settings from config
    debug_enabled = config_manager.getboolean('skylight', 'debug', True)
    debug_level = config_manager.getint('skylight', 'debug_level', 2)
    print(f"Debug settings: enabled={debug_enabled}, level={debug_level}")
    
    # Create server with configured debug settings
    server = SkylightServer(
        config_manager, 
        debug=debug_enabled,
        debug_level=debug_level
    )
    
    try:
        server.run()
    except KeyboardInterrupt:
        print("\nShutting down server...")

if __name__ == "__main__":
    main() 