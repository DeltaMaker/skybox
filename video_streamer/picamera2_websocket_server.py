import asyncio
import websockets
import time
from threading import Condition
from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput
import io
import logging
import json
import cv2
import numpy as np
from aiohttp import web


class Picamera2Server:
    def __init__(self, host='0.0.0.0', port=7160):
        self.host = host
        self.port = port
        self.picam2 = Picamera2()
        self.output = StreamingOutput()
        self.clients = {}  # Store clients with their configurations
        self.running = False
        self.base_size = None  # The camera's current resolution
        self.frame_cache = {}  # Cache to store resized frames by size

    async def start_server(self):
        """Start the combined HTTP and WebSocket server."""
        app = web.Application()

        # Add routes for WebSocket and HTTP requests
        app.router.add_route('GET', '/websocket', self.websocket_handler)
        app.router.add_route('GET', '/status', self.http_handler)

        runner = web.AppRunner(app)
        await runner.setup()

        # Start both WebSocket and HTTP on the same port
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()

        print(f"Server started on ws://{self.host}:{self.port} (WebSocket and HTTP)")

        while True:
            await asyncio.sleep(3600)

    async def websocket_handler(self, request):
        """Handle client subscriptions for camera frames."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        try:
            # Receive client subscription settings
            config_message = await ws.receive()

            # Check the message type
            if config_message.type == web.WSMsgType.TEXT:
                config = json.loads(config_message.data)

                # Extract custom frame size and FPS from client subscription
                custom_size = tuple(config.get('size', (640, 480)))  # Default to 640x480 if not provided
                custom_fps = config.get('fps', 15)  # Default to 15 FPS if not provided

                print(f"New client subscribed with size={custom_size}, fps={custom_fps}")

                # Start the camera with the first client's resolution
                if not self.running:
                    self.start_camera(custom_size, custom_fps)
                    self.base_size = custom_size  # Set the camera resolution

                # Add client to the list with their settings
                self.clients[ws] = {
                    'size': custom_size,
                    'fps': custom_fps
                }

                # Send subscription confirmation to the client
                confirmation_message = {
                    'status': 'subscribed',
                    'size': custom_size,
                    'fps': custom_fps
                }
                await ws.send_str(json.dumps(confirmation_message))

                # Continuously send frames to the client
                await self.send_frames(ws)

            elif config_message.type == web.WSMsgType.CLOSE:
                print("Client closed connection")

            else:
                print(f"Received unexpected WebSocket message type: {config_message.type}")

        except websockets.ConnectionClosed:
            print(f"Client disconnected")
        finally:
            # Remove client from the list
            if ws in self.clients:
                del self.clients[ws]

            # Stop the camera if no clients are connected
            if not self.clients:
                self.stop_camera()

        return ws

    async def send_frames(self, ws):
        """Send frames to a connected client."""
        try:
            while ws in self.clients:
                await asyncio.sleep(1 / self.clients[ws]['fps'])  # Adjust frame sending rate

                # Get the latest frame and resize it if necessary
                frame = self.output.frame
                if frame:
                    client_size = self.clients[ws]['size']

                    # Get the resized frame for the client's requested size from the cache
                    resized_frame = self.get_resized_frame(frame, client_size)

                    # Send the resized frame in binary format
                    await ws.send_bytes(resized_frame)
        except Exception as e:
            logging.error(f"Error sending frames: {e}")

    async def http_handler(self, request):
        """Handle HTTP requests to get the current status of connected clients."""
        clients_status = [{'size': client_info['size'], 'fps': client_info['fps']}
                          for client_info in self.clients.values()]
        return web.json_response({
            'status': 'running' if self.running else 'stopped',
            'subscribers': clients_status
        })

    def start_camera(self, size, frame_rate):
        """Start the camera with the specified size and frame rate."""
        video_config = self.picam2.create_video_configuration(
            main={"size": size}, controls={'FrameRate': frame_rate})
        self.picam2.configure(video_config)
        self.picam2.start_recording(MJPEGEncoder(), FileOutput(self.output))
        self.running = True
        print(f"Camera started with size={size}, frame_rate={frame_rate}")

    def stop_camera(self):
        """Stop the camera when no clients are connected."""
        self.picam2.stop_recording()
        self.running = False
        self.base_size = None
        self.frame_cache.clear()  # Clear cache when camera is stopped
        print("Camera stopped")

    def get_resized_frame(self, frame, client_size):
        """
        Resize the frame to match the client's requested size, using the cache.
        If the client's requested size matches the camera's base size, no resizing is done.
        """
        if self.base_size == client_size:
            return frame  # No resizing needed, return the original frame

        # Check if the resized frame is already in the cache
        if client_size in self.frame_cache:
            return self.frame_cache[client_size]

        # Convert the binary frame (MJPEG) to an image
        np_arr = np.frombuffer(frame, np.uint8)
        image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        # Resize the image to the client's requested size
        resized_image = cv2.resize(image, client_size)

        # Convert the resized image back to MJPEG format
        _, resized_frame = cv2.imencode('.jpg', resized_image)

        # Store the resized frame in the cache
        self.frame_cache[client_size] = resized_frame.tobytes()

        return self.frame_cache[client_size]

    def run(self):
        """Run the WebSocket server."""
        asyncio.run(self.start_server())


class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        """Save the latest frame."""
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

    def update_frame(self, frame):
        """Convert the frame to bytes and store it."""
        self.write(frame.tobytes())


def main():
    # Initialize and run the Picamera2 WebSocket and HTTP server
    camera_server = Picamera2Server(host='0.0.0.0', port=7160)

    try:
        # Start the WebSocket server
        camera_server.run()
    except KeyboardInterrupt:
        print("Stopping Picamera2 server...")


if __name__ == "__main__":
    main()