import time
import asyncio
import websockets
import json
import cv2
import logging
import numpy as np
from threading import Thread
import base64
import sys
import os

# Add the root directory of your project to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Importing the necessary classes from streaming_module
from video_streamer.streaming_module import StreamingOutput, StreamingHandler, StreamingServer
# Assuming ConfigManager is in the same directory or adjust the import path accordingly
from config.config_manager import ConfigManager
from video_streamer.overlay_manager import OverlayManager  # Import the new OverlayManager class

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

    async def handler(self, websocket, path):
        self.connected = True
        async for message in websocket:
            try:
                # initialize frame if message does not include a new frame
                #frame = self.current_frame
                # Check if the message is a JSON string or raw binary data
                if isinstance(message, str):
                    data = json.loads(message)
                    if 'frame' in data:
                        frame_data = base64.b64decode(data['frame'])
                        self.current_frame = cv2.imdecode(np.frombuffer(frame_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if 'overlay' in data:
                        self.current_overlay = data['overlay']
                        #frame = self.overlay_manager.draw_overlay_shapes(frame, data['overlay'])
                else:
                    frame_data = np.frombuffer(message, dtype=np.uint8)
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

    async def start(self):
        server = await websockets.serve(self.handler, '0.0.0.0', self.port)
        await server.wait_closed()

class WebSocketStreamer:
    def __init__(self, config_manager):
        # Read configuration values
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
    # Initialize ConfigManager
    config_manager = ConfigManager(config_file="localhost.conf", config_dir="../config")
    # Create log file (in /var/log or /tmp)
    logging.basicConfig(filename='/tmp/websocket_streamer.log', level=logging.INFO)

    # Initialize and start the WebSocketStreamer
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
