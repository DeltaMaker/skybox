import sys
import os
# Add the root directory of your project to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import time
import asyncio
from aiohttp import web
import websockets
from websocket_server.base_websocket_server import BaseWebSocketServer
from websocket_server.websocket_client_mixin import WebSocketClientMixin
from skylight.led_controller import LEDController
from config.config_manager import ConfigManager
import json

class SkylightServer(BaseWebSocketServer, WebSocketClientMixin):
    def __init__(self, config_manager, host='0.0.0.0'):
        """
        Initialize the SkylightServer.
        :param config_manager: Configuration manager to retrieve settings.
        :param host: The host address for the WebSocket server.
        """
        # Initialize the server part (WebSocket and HTTP server)
        skylight_port = config_manager.getint('skylight', 'skylight_port', 7120)
        debug = config_manager.getboolean('skylight', 'debug', True)
        BaseWebSocketServer.__init__(self, host, skylight_port, debug)

        # Unified connections and subscriptions for WebSocket clients
        connections = {
            'moonraker': {
                'uri': config_manager.moonraker_uri(),
                'root': 'moonraker',
                'connected': False,
                'subscription': {
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
                }
            },
            'skybox': {
                'uri': config_manager.skybox_uri(),
                'root': 'skybox',
                'connected': False,
                'subscription': {
                    "jsonrpc": "2.0",
                    "method": "subscribe",
                    "params": {
                        "objects": {
                            "data_fields": None,
                            "data_values": None,
                        }
                    },
                    "id": 3
                }
            }
        }

        # Initialize the WebSocket client mixin with connections
        WebSocketClientMixin.__init__(self, connections, debug)

        # Other Skylight-specific initializations
        self.config_manager = config_manager
        led_count = config_manager.getint('skylight', 'led_count', 30)
        update_interval = config_manager.getint('skylight', 'update_interval', 2)
        self.last_update_time = 0
        self.current_state = self.initialize_current_state(led_count, update_interval)
        self.led_controller = LEDController(led_count)
        self.show_preset("rainbow")

    def initialize_current_state(self, led_count, update_interval):
        """
        Initialize the current state of the Skylight system.
        :param led_count: Number of LEDs in the Skylight.
        :param update_interval: Interval for updates.
        :return: Initial state dictionary.
        """
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

    async def handle_client_update(self, root, updated_objects):
        """
        Override this method to handle updates from WebSocket services (e.g., Moonraker, Skybox).
        :param root: The root of the service being updated.
        :param updated_objects: The objects that were updated.
        """
        if root == 'moonraker':
            self.update_moonraker_state(updated_objects)
        elif root == 'skybox':
            print(f"Skybox data received: {updated_objects}")
        else:
            print(f"Unhandled message from {root}: {updated_objects}")

    def update_moonraker_state(self, data):
        """
        Update the state of the Skylight system based on Moonraker messages.
        :param data: Data received from Moonraker WebSocket.
        """
        self.current_state["moonraker"]["temperature"] = data.get("extruder", {}).get("temperature", 25.0)
        self.current_state["moonraker"]["target"] = data.get("extruder", {}).get("target", 0.0)
        self.current_state["moonraker"]["progress"] = data.get("display_status", {}).get("progress", 0.0)
        self.current_state["moonraker"]["state"] = data.get("idle_timeout", {}).get("state", "none")
        self.current_state["moonraker"]["is_paused"] = data.get("pause_resume", {}).get("is_paused", False)

        if time.time() - self.last_update_time > self.current_state["update_interval"]:
            self.last_update_time = time.time()
            self.update_skylight_state()

    def update_skylight_state(self):
        """
        Determine the state of the Skylight system and update LED patterns.
        """
        preset_scene, percent = self.determine_mode()
        if preset_scene != self.current_state['skylight']['preset_scene']:
            self.current_state['skylight']['preset_scene'] = preset_scene
            formats = self.current_state["preset_formats"].get(preset_scene, [])
            self.set_scene_format(formats)
        else:
            self.set_scene_values(percent)

    def determine_mode(self):
        """
        Determine the current mode of the Skylight system based on the Moonraker state.
        :return: A tuple containing the scene name and the percent value.
        """
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

    def show_preset(self, name):
        """
        Display the preset scene on the Skylight system.
        :param name: The name of the preset scene.
        """
        format_data = self.current_state["preset_formats"].get(name, [])
        if format_data:
            self.current_state['skylight']['preset_scene'] = name
            self.set_scene_format(format_data)

    def set_scene_format(self, formats):
        """
        Set the LED controller to the specified format.
        :param formats: The scene format for the LED controller.
        """
        self.current_state["scene"] = formats
        if self.debug:
            print(f"formats = {formats}")
        self.led_controller.set_data_fields(formats)

    def set_scene_values(self, values):
        """
        Set the LED controller to the specified values.
        :param values: The values for the LED controller.
        """
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

        def add_custom_routes(self, router):
            """
            Add custom routes for the Skylight server.
            :param router: The aiohttp router object.
            """
            router.add_route('*', '/skylight/{tail:.*}', self.process_skylight_command)

        async def process_skylight_command(self, request):
            """
            Process Skylight control commands (e.g., brightness, actions, etc.).
            :param request: The aiohttp web request.
            """
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

            return web.Response(status=404, text=f"{path} Not Found")

        def set_brightness(self, brightness):
            """
            Set the brightness of the LED system.
            :param brightness: The brightness value to set.
            """
            self.current_state["skylight"]["brightness"] = brightness
            percent = brightness / 256 if brightness < 256 else 1.0
            self.led_controller.set_brightness(percent)

        async def send_led_overlay(self):
            """
            Continuously send the defined shapes (overlays) to an external WebSocket server.
            """
            # Get the WebSocket URI from the config manager
            uri = self.config_manager.get('skylight', 'websocket_uri', fallback='ws://localhost:7130/websocket')

            async with websockets.connect(uri) as websocket:
                while True:
                    color_strip = self.led_controller.get_overlay_shapes()
                    message_json = json.dumps({"overlay": color_strip})
                    await websocket.send(message_json)
                    await asyncio.sleep(1.0)

        async def start_background_tasks(self, app):
            """
            Start background tasks such as WebSocket connections.
            :param app: The aiohttp web app.
            """
            if self.debug:
                print("Starting background tasks...")
            self.running = True
            asyncio.create_task(self.start_client())  # Non-blocking task creation
            asyncio.create_task(self.send_led_overlay())

        async def cleanup_background_tasks(self, app):
            """
            Clean up background tasks when shutting down.
            :param app: The aiohttp web app.
            """
            if self.debug:
                print("Cleaning up background tasks...")
            self.running = False
            await self.stop_client()

        def start(self):
            """
            Start the Skylight server with the aiohttp event loop.
            """
            if self.debug:
                print("Starting Skylight server...")

            # Create aiohttp app and configure routes
            app = web.Application()
            self.add_custom_routes(app.router)

            app.on_startup.append(self.start_background_tasks)
            app.on_cleanup.append(self.cleanup_background_tasks)

            # Start the server
            web.run_app(app, host='0.0.0.0', port=self.port)

def main():
    config_manager = ConfigManager(config_file="localhost.conf", config_dir="../config")

    skylight_server = SkylightServer(config_manager)
    skylight_server.start()

if __name__ == "__main__":
    main()
