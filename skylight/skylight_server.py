#
##### SKYLIGHT SERVER #####
#

import sys
import os
# Add the root directory of your project to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import time
import asyncio
from aiohttp import web
from websocket_server.base_websocket_server import BaseWebSocketServer
from websocket_server.websocket_client_mixin import WebSocketClientMixin
from skylight.led_controller import LEDController
from config.config_manager import ConfigManager
import json

class SkylightServer(BaseWebSocketServer, WebSocketClientMixin):
    def __init__(self, config_manager, host='0.0.0.0'):
        # Initialize server part
        skylight_port = config_manager.getint('skylight', 'skylight_port', 7120)
        debug = config_manager.getboolean('skylight', 'debug', True)
        BaseWebSocketServer.__init__(self, host, skylight_port, debug)

        # Initialize client part
        connections = [{'moonraker': config_manager.moonraker_uri()},
                       {'skybox': config_manager.skybox_uri()}]
        subscriptions = {
            'moonraker': {
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
            "skybox": {
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
        WebSocketClientMixin.__init__(self, connections, subscriptions, debug)

        # Other initializations
        self.config_manager = config_manager
        led_count = config_manager.getint('skylight', 'led_count', 30)
        update_interval = config_manager.getint('skylight', 'update_interval', 2)
        self.last_update_time = 0
        self.current_state = self.initialize_current_state(led_count, update_interval)
        self.led_controller = LEDController(led_count)
        self.show_preset("rainbow")

    def initialize_current_state(self, led_count, update_interval):
        return {
            "update_interval": update_interval,
            "scene": {},
            "skylight": {
                "status": "on",
                "chain_count": led_count,
                "display_mode": "rainbow",
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
        """Override the handle_client_update to call handle_moonraker_update."""
        self.handle_moonraker_update(root, updated_objects)

    def handle_moonraker_update(self, root, updated_objects):
        if root == "moonraker":
            self.current_state["moonraker"]["temperature"] = self.client.get_state("moonraker.extruder.temperature", 25.0)
            self.current_state["moonraker"]["target"] = self.client.get_state("moonraker.extruder.target", 0.0)
            self.current_state["moonraker"]["progress"] = self.client.get_state("moonraker.display_status.progress", 0.0)
            self.current_state["moonraker"]["state"] = self.client.get_state("moonraker.idle_timeout.state")
            self.current_state["moonraker"]["is_paused"] = self.client.get_state("moonraker.pause_resume.is_paused")
            if time.time() - self.last_update_time > self.current_state["update_interval"]:
                self.last_update_time = time.time()
                self.update_skylight("moonraker")
        if root == "skybox":
            print(root, updated_objects)


    def determine_mode(self):
        heater_on = self.get_state("moonraker.target") > 0
        warming_up = self.get_state("moonraker.target") - self.get_state("moonraker.temperature") > 2 and heater_on
        cooling_down = self.get_state("moonraker.temperature") > 50 and not heater_on
        ratio = (self.current_state["moonraker"]["temperature"] /
                 (self.current_state["moonraker"]["target"] if heater_on else 250))
        progress = self.current_state["moonraker"]["progress"]
        is_paused = self.current_state["moonraker"]["is_paused"]
        is_ready = (self.current_state["moonraker"]["state"] == "Ready" and not heater_on and progress < 0.01)
        is_idle = (self.current_state["moonraker"]["state"] == "Idle")

        if is_paused:
            return "paused", 0
        if not warming_up and progress > 0:
            return "progress", progress
        if heater_on or cooling_down:
            ratio = max(0.0, min(1.0, ratio))
            return "temperature", ratio
        if is_ready:
            return "ready", 0
        if is_idle:
            return "idle", 0
        return "rainbow", 0

    def update_skylight(self, root):
        if self.current_state['skylight']['display_mode'] == "skybox":
            return

        try:
            display_mode, percent = self.determine_mode()
            if display_mode != self.current_state['skylight']['display_mode']:
                self.current_state['skylight']['display_mode'] = display_mode

                formats = self.current_state["preset_formats"].get(display_mode, [])
                self.set_scene_format(formats)
            else:
                self.set_scene_values(percent)
        except Exception as e:
            print(f'Exception in handle_moonraker_update(): {e}')

    def show_preset(self, name):
        format_data = self.current_state["preset_formats"].get(name, [])
        if format_data:
            self.set_scene_format(format_data)

    def set_scene_format(self, formats):
        self.current_state["scene"] = formats
        if self.debug:
            print(f'formats = {formats}')
        self.led_controller.set_data_fields(formats)

    def set_scene_values(self, values):
        if self.debug:
            print(f'values = {values}')
        formats = self.current_state["scene"]
        n_values = len(formats) if formats else 1
        if not isinstance(values, list):
            values = [values] * n_values
        for i in range(n_values):
            self.current_state["scene"][i][1] = values[i]

        self.led_controller.set_data_values(values)

    def add_custom_routes(self, router):
        router.add_route('*', '/skylight/{tail:.*}', self.process_skylight_command)
        #router.add_route('*', '/skylight/status', self.process_skylight_command)

    async def process_skylight_command(self, request):
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
                self.set_scene_format(format_data)
            if "values" in combined_params:
                values = json.loads(combined_params["values"])
                self.set_scene_values(values)
            if "preset" in combined_params:
                preset_name = combined_params["preset"]
                print(f'preset = {preset_name}')
                self.show_preset(preset_name)

            return web.json_response({"status": "success", "scene": self.current_state["scene"]})

        return web.Response(status=404, text=f"{path} Not Found")

    def set_brightness(self, brightness):
        self.current_state["skylight"]["brightness"] = brightness
        percent = brightness / 256 if brightness < 256 else 1.0
        self.led_controller.set_brightness(percent)

    async def start_background_tasks(self, app):
        if self.debug:
            print("Starting background tasks...")
        self.running = True
        asyncio.create_task(self.start_client())  # Non-blocking task creation

    async def cleanup_background_tasks(self, app):
        if self.debug:
            print("Cleaning up background tasks...")
        self.running = False
        await self.stop_client()


def main():
    config_manager = ConfigManager(config_file='test.conf')
    server = SkylightServer(config_manager)
    server.start()


if __name__ == "__main__":
    main()

