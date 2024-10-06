import asyncio
import websockets
import time
import socket
from threading import Thread, Condition
from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput
import io
import logging

class Picamera2Client:
    def __init__(self, ws_uri, size=(640, 480), frame_rate=5):
        self.ws_uri = ws_uri
        self.size = size
        self.frame_rate = frame_rate
        self.picam2 = Picamera2()
        self.output = StreamingOutput()
        self.connected = False

    def start_camera(self):
        video_config = self.picam2.create_video_configuration(
            main={"size": self.size}, controls={'FrameRate': self.frame_rate})
        self.picam2.configure(video_config)
        self.picam2.start_recording(MJPEGEncoder(), FileOutput(self.output))

    def stop_camera(self):
        self.picam2.stop_recording()

    async def connect_to_ws(self):
        async with websockets.connect(self.ws_uri) as websocket:
            self.connected = True
            print(f"Connected to WebSocket server at {self.ws_uri}")
            await self.send_frames(websocket)

    async def send_frames(self, websocket):
        """Continuously send frames to the WebSocket server."""
        try:
            while self.connected:
                # Throttle the frame sending to match the frame rate
                await asyncio.sleep(1 / self.frame_rate)

                # Get the latest frame
                frame = self.output.frame

                if frame:
                    await websocket.send(frame)  # Ensure the frame is binary
        except Exception as e:
            logging.error(f"Error sending frames to WebSocket server: {e}")
        finally:
            self.connected = False

    async def start(self):
        """Start the client and connect to the WebSocket server."""
        self.start_camera()
        try:
            await self.connect_to_ws()
        except Exception as e:
            print(f"Error connecting to WebSocket server: {e}")
        finally:
            self.stop_camera()

    def run(self):
        """Run the client asynchronously."""
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.start())

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
    # WebSocket URI of the external server to send frames to
    ws_uri = 'ws://192.168.1.198:7130/websocket'
    custom_size = (640, 480)  # Frame resolution
    custom_fps = 15  # Frame rate

    # Initialize the client
    camera_client = Picamera2Client(ws_uri=ws_uri, size=custom_size, frame_rate=custom_fps)

    try:
        # Start the camera client
        camera_client.run()
    except KeyboardInterrupt:
        print("Stopping Picamera2 client...")
    finally:
        camera_client.stop_camera()

if __name__ == "__main__":
    main()
