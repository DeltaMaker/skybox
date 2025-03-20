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
    def __init__(self, url: str, subscription: dict, debug: bool = False):
        super().__init__(url)
        self.subscription = subscription
        self.debug = debug
        self.callback = None

    async def start(self, callback):
        """Start client with callback for updates"""
        self.callback = callback
        await self.connect()
        await self.subscribe(self.subscription)
        asyncio.create_task(self.receive_loop())

    async def receive_loop(self):
        """Continuously receive and process messages"""
        try:
            while True:
                message = await self.receive()
                if isinstance(message, str):
                    data = json.loads(message)
                    if self.callback:
                        await self.callback(data)
                await asyncio.sleep(0.1)
        except Exception as e:
            if self.debug:
                print(f"Client receive error: {e}")

class SkylightServer(SimpleWebsocketServer):
    def __init__(self, config_manager, host='0.0.0.0', debug=True):
        # Initialize server
        port = config_manager.getint('skylight', 'skylight_port', 7120)
        super().__init__(host=host, port=port, debug=debug)
        
        self.config_manager = config_manager
        self.debug = debug
        
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

    async def start_server(self):
        """Start the combined HTTP and WebSocket server."""
        # Start clients before starting server
        if self.debug:
            print("Starting client connections...")
        await self.start_clients()  # Start clients when server starts
        
        # Now start the server
        await super().start_server()

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
        return SkylightClient(
            url=self.config_manager.moonraker_uri(),
            subscription={
                "jsonrpc": "2.0",
                "method": "printer.objects.subscribe",
                "params": {
                    "objects": {
                        "print_stat": None,
                        "display_status": ["progress"],
                        "idle_timeout": ["state"],
                        "extruder": ["temperature", "target"],
                        "pause_resume": ["is_paused"]
                    }
                },
                "id": 2
            },
            debug=self.debug
        )

    def setup_skybox_client(self):
        """Setup Skybox client"""
        return SkylightClient(
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
            debug=self.debug
        )

    def perform_initialization(self, config):
        """Initialize when first client connects"""
        pass  # Client connections are now started in start_server

    async def start_clients(self):
        """Start all client connections"""
        await self.moonraker_client.start(self.handle_moonraker_update)
        # await self.skybox_client.start(self.handle_skybox_update)

    async def handle_moonraker_update(self, data):
        """Handle updates from Moonraker"""
        if 'result' in data and 'status' in data['result']:
            self.update_moonraker_state(data['result']['status'])
        elif 'params' in data and len(data['params']) > 0:
            self.update_moonraker_state(data['params'][0])

    def update_moonraker_state(self, data):
        """Update the state of the Skylight system based on Moonraker messages."""
        self.current_state["moonraker"]["temperature"] = data.get("extruder", {}).get("temperature", 25.0)
        self.current_state["moonraker"]["target"] = data.get("extruder", {}).get("target", 0.0)
        self.current_state["moonraker"]["progress"] = data.get("display_status", {}).get("progress", 0.0)
        self.current_state["moonraker"]["state"] = data.get("idle_timeout", {}).get("state", "none")
        self.current_state["moonraker"]["is_paused"] = data.get("pause_resume", {}).get("is_paused", False)

        if time.time() - self.last_update_time > self.current_state["update_interval"]:
            self.last_update_time = time.time()
            self.update_skylight_state()

    def update_skylight_state(self):
        """Determine the state of the Skylight system and update LED patterns."""
        preset_scene, percent = self.determine_mode()
        if preset_scene != self.current_state['skylight']['preset_scene']:
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
        if self.debug:
            print(f"Skybox data received: {data}")

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
        format_data = self.current_state["preset_formats"].get(name, [])
        if format_data:
            self.current_state['skylight']['preset_scene'] = name
            self.set_scene_format(format_data)

    def set_scene_format(self, formats):
        """Set the LED controller to the specified format."""
        self.current_state["scene"] = formats
        if self.debug:
            print(f"formats = {formats}")
        self.led_controller.set_data_fields(formats)

    def set_scene_values(self, values):
        """Set the LED controller to the specified values."""
        if self.debug:
            print(f"values = {values}")
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
                                if self.debug:
                                    print(f"Sending overlay to {uri}: {message_json}")
                                await websocket.send(message_json)
                                await asyncio.sleep(1.0)
                            except Exception as e:
                                if self.debug:
                                    print(f"Error sending overlay: {e}")
                                break  # Break out of the inner loop on error
                except Exception as e:
                    if self.debug:
                        print(f"Error connecting to WebSocket server at {uri}: {e}")
                    await asyncio.sleep(5.0)  # Wait before retrying
        except Exception as e:
            if self.debug:
                print(f"LED overlay task error: {e}")

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
            if self.debug:
                print(f"Cleanup error: {e}")

def main():
    # Update config path to use absolute path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_dir = os.path.join(os.path.dirname(current_dir), 'config')
    print(f"Config directory: {config_dir}")
    config_manager = ConfigManager(config_file="localhost.conf", config_dir=config_dir)
    
    # Explicitly set debug=True
    server = SkylightServer(config_manager, debug=True)
    
    try:
        server.run()
    except KeyboardInterrupt:
        print("\nShutting down server...")

if __name__ == "__main__":
    main() 