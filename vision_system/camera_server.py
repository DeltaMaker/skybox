""" import asyncio
import websockets
import io
from threading import Condition
import json
import cv2
import numpy as np
from aiohttp import web
import logging
#from vision_system.marker_tracker import MarkerTracker
from marker_tracker import MarkerTracker
from hand_tracker import HandTracker
import requests
from urllib.parse import urlparse
from simple_server import SimpleWebsocketServer

# Attempt to import Picamera2
try:
    from picamera2 import Picamera2
    from picamera2.encoders import MJPEGEncoder
    from picamera2.outputs import FileOutput

    PICAMERA2_AVAILABLE = True
    print("Picamera2 is available.")
except ImportError:
    PICAMERA2_AVAILABLE = False
    print("Picamera2 not available. Using OpenCV's VideoCapture instead.")  

class CameraServer(SimpleWebsocketServer):
    def __init__(self, host='0.0.0.0', port=7160, camera_id=0, http_url=None):
        super().__init__(host, port)
        self.base_size = None
        self.marker_tracker = MarkerTracker()
        self.hand_tracker = HandTracker()
        self.camera_id = camera_id
        self.http_url = http_url
        self.camera_type = None
        self.picam2 = None
        self.cap = None
        self.output = None """

import asyncio
import websockets
import io
from threading import Condition
import json
import cv2
import numpy as np
from aiohttp import web
import logging

from marker_tracker import MarkerTracker
from hand_tracker import HandTracker
from simple_server import SimpleWebsocketServer
import requests
from urllib.parse import urlparse

# Attempt to import Picamera2
try:
    from picamera2 import Picamera2
    from picamera2.encoders import MJPEGEncoder
    from picamera2.outputs import FileOutput

    PICAMERA2_AVAILABLE = True
    print("Picamera2 is available.")
except ImportError:
    PICAMERA2_AVAILABLE = False
    print("Picamera2 not available. Using OpenCV's VideoCapture instead.")


class CameraServer(SimpleWebsocketServer):
    def __init__(self, host='0.0.0.0', port=7160, camera_id=0, http_url=None):
        
        super().__init__(host, port)
        self.camera_id = camera_id
        self.http_url = http_url
        
        self.base_size = None
        self.marker_tracker = MarkerTracker()
        self.hand_tracker = HandTracker()
       
        self.camera_type = None
        self.picam2 = None
        self.cap = None
        self.output = None

        # Initialize camera based on configuration
        if http_url:
            print(f"Using HTTP camera at {http_url}")
            self.camera_type = "http"
        elif PICAMERA2_AVAILABLE:
            try:
                print("Initializing Picamera2...")
                self.picam2 = Picamera2()
                if not self.picam2:
                    raise Exception("Failed to create Picamera2 instance")
                self.output = StreamingOutput()
                self.initialize_picamera2()
                self.camera_type = "picamera2"
                print("Picamera2 initialization successful")
            except Exception as e:
                print(f"Failed to initialize Picamera2: {e}")
                print("Falling back to OpenCV")
                self.camera_type = "opencv"
                self.picam2 = None
                self.cap = cv2.VideoCapture(camera_id)
        else:
            self.camera_type = "opencv"
            self.cap = cv2.VideoCapture(camera_id)
            if not self.cap.isOpened():
                raise Exception("Error: Camera not accessible using cv2.VideoCapture.")

    def initialize_picamera2(self):
        """Initialize Picamera2 if available."""
        try:
            if not self.picam2:
                self.picam2 = Picamera2()
            
            # Start with 1920x1080 resolution
            initial_size = (1920, 1080)

            # Create basic configuration without relying on sensor modes
            video_config = self.picam2.create_video_configuration(
                main={"size": initial_size, "format": "RGB888"},
                buffer_count=4,
                controls={
                    "FrameDurationLimits": (33333, 33333),  # ~30fps
                    "NoiseReductionMode": 2,
                    "Sharpness": 2.0,
                    "Brightness": 0.0,
                    "Contrast": 1.0,
                    "Saturation": 1.0,
                    "ExposureValue": 0,
                    "AwbEnable": 1,
                    "AeEnable": 1,
                }
            )
            self.picam2.configure(video_config)
            self.base_size = initial_size
            print(f"Camera initialized with resolution {initial_size}")

        except Exception as e:
            logging.error(f"Failed to initialize camera: {e}")
            raise

    def get_current_frame(self):
        """Capture the current frame from the camera or HTTP stream."""
        if self.camera_type == "http":
            try:
                response = requests.get(self.http_url)
                if response.status_code == 200:
                    # Convert the image data to numpy array
                    np_arr = np.frombuffer(response.content, np.uint8)
                    return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                else:
                    logging.error(f"Failed to fetch frame from HTTP: {response.status_code}")
                    return None
            except Exception as e:
                logging.error(f"Error fetching HTTP frame: {e}")
                return None
        elif self.camera_type == "picamera2":
            frame = self.output.frame
            if frame:
                np_arr = np.frombuffer(frame, np.uint8)
                return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        else:  # opencv
            ret, frame = self.cap.read()
            if ret:
                return frame
        return None


    def extract_client_info(self, config : dict):
        # Extract custom frame size, FPS, and mirror flag from client subscription
        custom_size = tuple(config.get('size', (640, 480)))
        custom_fps = config.get('fps', 15)
        mirror = config.get('mirror', False)
        track_hands = config.get('hands', False)
        client_info = {
            'size': custom_size,
            'fps': custom_fps,
            'mirror': mirror,
            'hands': track_hands
        }
        print(f"New client subscribed with size={custom_size}, fps={custom_fps}, mirror={mirror}")
        return client_info
    

    def start_picamera2(self, size, fps):
        """Start the Picamera2 camera with the specified settings."""
        try:
            # Update base_size to match the largest client request
            self.base_size = size
            
            video_config = self.picam2.create_video_configuration(
                main={"size": size, "format": "RGB888"},
                buffer_count=4,
                controls={
                    "FrameDurationLimits": (int(1/fps * 1000000), int(1/fps * 1000000)),
                    "NoiseReductionMode": 2,
                    "Sharpness": 2.0,
                    "Brightness": 0.0,
                    "Contrast": 1.0,
                    "Saturation": 1.0,
                    "ExposureValue": 0,
                    "AwbEnable": 1,
                    "AeEnable": 1,
                }
            )
            self.picam2.configure(video_config)
            self.picam2.start_recording(MJPEGEncoder(), FileOutput(self.output))
            print(f"Picamera2 started with size={size}, fps={fps}")

        except Exception as e:
            logging.error(f"Failed to start camera: {e}")
            raise

    async def send_broadcast_function(self):
        """Send frames to connected clients, resizing once per unique size and sending marker data."""
        try:
            while self.clients:
                # Find the largest requested size among all clients
                largest_size = max(
                    (client_info['size'] for client_info in self.clients.values()),
                    key=lambda s: s[0] * s[1]
                )

                # Update camera configuration if the largest size has changed
                if largest_size != self.base_size:
                    if PICAMERA2_AVAILABLE:
                        print(f"Reconfiguring camera for new largest size: {largest_size}")
                        self.picam2.stop_recording()
                        self.start_picamera2(largest_size, 
                                          min(client['fps'] for client in self.clients.values()))
                    else:
                        self.base_size = largest_size

                frame = self.get_current_frame()

                if frame is not None:
                    # Group clients by their requested size
                    clients_by_size = {}
                    for client_ws, client_info in self.clients.items():
                        size = client_info['size']
                        if size not in clients_by_size:
                            clients_by_size[size] = {
                                'mirror': [], 
                                'no_mirror': [],
                                'hands': False,
                                'size': size
                            }
                        if client_info.get('mirror', False):
                            clients_by_size[size]['mirror'].append(client_ws)
                        else:
                            clients_by_size[size]['no_mirror'].append(client_ws)
                        if client_info.get('hands', False):
                            clients_by_size[size]['hands'] = True

                    # Process each unique size
                    for size, size_info in clients_by_size.items():
                        resized_frame = self.get_resized_frame(frame, size)
                        
                        # Process non-mirrored frame
                        if size_info['no_mirror']:
                            marker_data = self.marker_tracker.process_frame(resized_frame)
                            hand_data = self.hand_tracker.process_frame(resized_frame) if size_info['hands'] else []
                            
                            _, encoded_frame = cv2.imencode('.jpg', resized_frame)
                            frame_bytes = encoded_frame.tobytes()
                            
                            for client_ws in size_info['no_mirror']:
                                if not client_ws.closed:
                                    try:
                                        await client_ws.send_str(json.dumps({
                                            "markers": marker_data,
                                            "hands": hand_data if self.clients[client_ws]['hands'] else []
                                        }))
                                        await client_ws.send_bytes(frame_bytes)
                                    except Exception as e:
                                        logging.error(f"Error sending frame/data: {e}")
                                        if client_ws in self.clients:
                                            del self.clients[client_ws]

                        # Process mirrored frame
                        if size_info['mirror']:
                            mirrored_frame = cv2.flip(resized_frame, 1)
                            marker_data = self.marker_tracker.process_frame(mirrored_frame)
                            hand_data = self.hand_tracker.process_frame(mirrored_frame) if size_info['hands'] else []
                            
                            _, encoded_frame = cv2.imencode('.jpg', mirrored_frame)
                            frame_bytes = encoded_frame.tobytes()
                            
                            for client_ws in size_info['mirror']:
                                if not client_ws.closed:
                                    try:
                                        await client_ws.send_str(json.dumps({
                                            "markers": marker_data,
                                            "hands": hand_data if self.clients[client_ws]['hands'] else []
                                        }))
                                        await client_ws.send_bytes(frame_bytes)
                                    except Exception as e:
                                        logging.error(f"Error sending frame/data: {e}")
                                        if client_ws in self.clients:
                                            del self.clients[client_ws]

                # Adjust sleep rate for frame sending based on FPS
                if self.clients:
                    await asyncio.sleep(1 / min(client['fps'] for client in self.clients.values()))
                else:
                    await asyncio.sleep(1)  # Sleep to avoid a busy loop if no clients connected

        except Exception as e:
            logging.error(f"Error sending frames: {e}")



    def get_resized_frame(self, frame, client_size):
        """Resize the frame to match the client's requested size."""
        resized_frame = cv2.resize(frame, client_size)
        return resized_frame

    def stop_camera(self):
        """Stop the camera when no clients are connected."""
        if PICAMERA2_AVAILABLE:
            self.picam2.stop_recording()
        else:
            self.cap.release()
        self.running = False
        print("Camera stopped")

    def status_message(self):
        """Handle HTTP requests to get the current status of connected clients."""
        clients_status = [{'size': client_info['size'], 'fps': client_info['fps'], 
                           'mirror': client_info['mirror'], 'hands': client_info['hands']}
                          for client_info in self.clients.values()]
        return clients_status



class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        """Save the latest frame."""
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


def main():
    # Example of using HTTP camera
    http_url = "http://localhost/webcam/?action=snapshot"  # Replace with your camera URL
    
    # Initialize and run the Camera WebSocket and HTTP server
    # Use either:
    # camera_server = CameraServer(host='0.0.0.0', port=7160)  # For local camera
    # or:
    camera_server = CameraServer(host='0.0.0.0', port=7160) #, http_url=http_url)  # For HTTP camera

    try:
        camera_server.run()
    except KeyboardInterrupt:
        print("Stopping Camera Server...")


if __name__ == "__main__":
    main()