"""
Author: Bob Houston
Date: 2024-9-21
Version: 0.2
"""

import time
import asyncio
import json
import cv2
import logging
import numpy as np
from threading import Thread
import base64
import sys
import os
from aiohttp import web
import aiohttp
import aiohttp.web
import socket

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from video_streamer.streaming_module import StreamingOutput, StreamingHandler, StreamingServer
from config.config_manager import ConfigManager
from video_streamer.overlay_manager import OverlayManager


class WebSocketFrameReceiver:
    def __init__(self, port, filepath):
        self.port = port
        self.output = None
        self.connected = False
        self.default_frame = self.initialize_default_frame(filepath)
        self.overlay_manager = OverlayManager()
        self.current_frame = None
        self.current_overlay = None

    def initialize_default_frame(self, filepath):
        frame = cv2.imread(filepath, cv2.IMREAD_COLOR)
        if frame is None:
            frame = np.zeros((360, 640, 3), dtype=np.uint8)
        _, buffer = cv2.imencode('.jpg', frame)
        return buffer

    async def websocket_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.connected = True
        async for message in ws:
            try:
                # Process WebSocket message
                if message.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(message.data)
                    if 'frame' in data:
                        frame_data = base64.b64decode(data['frame'])
                        self.current_frame = cv2.imdecode(np.frombuffer(frame_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if 'overlay' in data:
                        self.current_overlay = data['overlay']
                elif message.type == aiohttp.WSMsgType.BINARY:
                    frame_data = np.frombuffer(message.data, dtype=np.uint8)
                    self.current_frame = cv2.imdecode(frame_data, cv2.IMREAD_COLOR)

                frame = self.current_frame
                if self.current_overlay:
                    frame = self.overlay_manager.draw_overlay_shapes(self.current_frame.copy(), self.current_overlay)

            except Exception as e:
                logging.error(f"Error processing message: {e}")
                continue

            if self.output:
                _, jpeg = cv2.imencode('.jpg', frame)
                self.output.update_frame(jpeg)
                self.default_frame = jpeg

        self.connected = False
        return ws

    async def http_handler(self, request):
        """Handle HTTP requests to get the current status."""
        peername = request.transport.get_extra_info('sockname')
        server_ip = peername[0] if peername else 'Unknown IP'

        response_data = {'status': {
            'connected': self.connected, 'host': self.get_server_ip(),
            'current_overlay': self.current_overlay}
        }
        return web.json_response(response_data)

    def get_server_ip(self):
        """Get the local IP address of the server."""
        try:
            # Use a dummy socket connection to find the local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Doesn't matter if there's no internet connection; the IP address used for this is sufficient
            s.connect(("8.8.8.8", 80))
            ip_address = s.getsockname()[0]
            s.close()
        except Exception as e:
            logging.error(f"Failed to get server IP: {e}")
            ip_address = "127.0.0.1"  # Fallback to localhost
        return ip_address

    async def start(self):
        """Start the combined HTTP and WebSocket server."""
        app = web.Application()

        # WebSocket route for real-time communication
        app.router.add_route('GET', '/websocket', self.websocket_handler)

        # HTTP route to query the current overlay
        app.router.add_route('GET', '/status', self.http_handler)

        runner = web.AppRunner(app)
        await runner.setup()

        # Start the server on the specified port (for both HTTP and WS)
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()

        logging.info(f"Server started on port {self.port} (HTTP & WebSocket)")

        # Run forever
        while True:
            await asyncio.sleep(3600)  # Keep the server running


class WebSocketStreamer:
    def __init__(self, config_manager):
        stream_port = config_manager.getint('video_streamer', 'stream_port', fallback=8085)
        ws_port = config_manager.getint('video_streamer', 'ws_port', fallback=7130)
        filepath = config_manager.get('video_streamer', 'default_frame_filepath')

        self.output = StreamingOutput()
        StreamingHandler.output = self.output
        self.server = StreamingServer(('0.0.0.0', stream_port), StreamingHandler)
        self.ws_receiver = WebSocketFrameReceiver(ws_port, filepath)
        self.ws_receiver.output = self.output
        self.is_running = False

    def start(self):
        self.is_running = True
        self.server_thread = Thread(target=self.run_server)
        self.server_thread.start()
        self.ws_thread = Thread(target=self.run_ws_server)
        self.ws_thread.start()
        self.default_frame_thread = Thread(target=self.stream_default_frame)
        self.default_frame_thread.start()

    def run_server(self):
        try:
            self.server.serve_forever()
        except Exception as e:
            print(f"Server error: {e}")
        finally:
            self.server.shutdown()

    def run_ws_server(self):
        asyncio.run(self.ws_receiver.start())

    def stream_default_frame(self):
        while self.is_running:
            if not self.ws_receiver.connected:
                self.output.update_frame(self.ws_receiver.default_frame)
            time.sleep(1)  # Adjust the sleep time as needed

    def stop(self):
        self.is_running = False
        self.server.shutdown()
        self.server_thread.join()
        self.ws_thread.join()
        self.default_frame_thread.join()


def main():
    config_manager = ConfigManager(config_file="localhost.conf", config_dir="../config")
    logging.basicConfig(filename='/tmp/websocket_streamer.log', level=logging.INFO)

    streamer = WebSocketStreamer(config_manager)
    try:
        streamer.start()
        while True:
            time.sleep(1)  # Keep the main thread alive
    except KeyboardInterrupt:
        streamer.stop()
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        streamer.stop()


if __name__ == "__main__":
    main()