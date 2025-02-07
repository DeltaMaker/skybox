"""
CameraServer - WebSocket server for streaming camera frames and vision results.

This server implementation provides:
- Multi-camera support (Picamera2, OpenCV, HTTP cameras)
- Real-time computer vision processing
    - ArUco marker detection
    - Hand pose tracking
- Client-specific configurations
    - Resolution and FPS control
    - Frame mirroring
    - Vision processing options
- Efficient binary frame streaming
- JSON metadata for vision results

The server handles:
- Camera initialization and configuration
- Frame capture and processing
- Client subscription management
- Resource cleanup on shutdown

Usage:
    server = CameraServer(host='0.0.0.0', port=7160)
    server.run()

Pairs with camera_viewer.py for displaying the camera stream and vision results.
"""

import io
from threading import Condition
import json
import cv2
import numpy as np
from aiohttp import web
import logging
import time
from marker_tracker import MarkerTracker
from hand_tracker import HandTracker
from simple_server import SimpleWebsocketServer
import requests
from urllib.parse import urlparse
import asyncio

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
    def __init__(self, host='0.0.0.0', port=7160, camera_id=0, http_url=None, debug=False):
        """Initialize the camera server."""
        super().__init__(host, port, debug)
        self.camera_id = camera_id
        self.http_url = http_url
        self.base_size = None
        self.marker_tracker = MarkerTracker()
        self.hand_tracker = HandTracker()
        self.frame_count = 0
        self.last_fps_print = time.time()
       
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

        if self.debug:
            print(f"Camera initialized with type: {self.camera_type}")

    def initialize_picamera2(self):
        """Initialize Picamera2 if available."""
        try:
            if not self.picam2:
                if self.debug:
                    print("Creating new Picamera2 instance...")
                self.picam2 = Picamera2()
            
            # Start with a more modest resolution
            initial_size = (1296, 972)

            if self.debug:
                print(f"Configuring Picamera2 with size {initial_size}")

            try:
                video_config = self.picam2.create_video_configuration(
                    main={"size": initial_size, "format": "RGB888"},
                    buffer_count=4
                )
                self.picam2.configure(video_config)
                self.picam2.start()
                self.base_size = initial_size
                if self.debug:
                    print("Picamera2 configuration and start successful")

            except Exception as e:
                logging.error(f"Failed to configure camera with initial settings: {e}")
                if self.debug:
                    print("Falling back to default configuration...")
                # Fallback configuration
                video_config = self.picam2.create_video_configuration()
                self.picam2.configure(video_config)
                self.picam2.start()
                self.base_size = self.picam2.camera_properties['ScalerCropMaximum'][:2]
                print(f"Using fallback configuration with resolution {self.base_size}")

        except Exception as e:
            logging.error(f"Failed to initialize camera: {e}")
            if self.debug:
                print(f"Camera initialization error: {str(e)}")
            raise

    def get_current_frame(self):
        """Capture the current frame from the camera or HTTP stream."""
        try:
            if self.camera_type == "http":
                if self.debug:
                    print("Fetching HTTP frame...")
                response = requests.get(self.http_url, timeout=1.0)
                if response.status_code == 200:
                    np_arr = np.frombuffer(response.content, np.uint8)
                    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                    if frame is None:
                        raise ValueError("Failed to decode HTTP frame")
                    return frame
                else:
                    logging.error(f"Failed to fetch HTTP frame: {response.status_code}")
                    return None

            elif self.camera_type == "picamera2":
                if self.debug:
                    print("Capturing Picamera2 frame...")
                try:
                    if not self.picam2:
                        if self.debug:
                            print("Creating new Picamera2 instance...")
                        self.initialize_picamera2()
                    
                    # Try to capture a frame
                    frame = self.picam2.capture_array()
                    if frame is None:
                        raise ValueError("Failed to capture Picamera2 frame")
                    return frame
                    
                except Exception as e:
                    if self.debug:
                        print(f"Picamera2 capture failed, attempting restart: {e}")
                    try:
                        self.initialize_picamera2()
                        self.picam2.start()
                        frame = self.picam2.capture_array()
                        if frame is not None:
                            return frame
                    except Exception as e2:
                        raise ValueError(f"Failed to restart Picamera2: {e2}")

            else:  # opencv
                if self.debug:
                    print("Capturing OpenCV frame...")
                if not self.cap or not self.cap.isOpened():
                    if self.debug:
                        print("OpenCV camera not open, attempting to open...")
                    self.cap = cv2.VideoCapture(self.camera_id)
                    if not self.cap.isOpened():
                        raise ValueError("Failed to open OpenCV camera")
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    raise ValueError("Failed to read OpenCV frame")
                return frame

        except Exception as e:
            logging.error(f"Error capturing frame ({self.camera_type}): {e}")
            if self.debug:
                print(f"Frame capture error: {str(e)}")
            return None

    def extract_client_info(self, config):
        """Extract custom frame size, FPS, and mirror flag from client subscription."""
        client_info = {
            'size': tuple(config.get('size', (640, 480))),
            'fps': config.get('fps', 15),
            'mirror': config.get('mirror', False),
            'hands': config.get('hands', False)
        }
        if self.debug:
            print(f"New client subscribed with config: {client_info}")
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

    async def get_broadcast_data(self):
        """Get the current frame and process it."""
        # Sleep based on highest requested frame rate among clients
        if self.clients:
            fastest_fps = max(client.get('fps', 1) for client in self.clients.values())
            target_interval = 1 / fastest_fps
            
            if self.debug:
                self.frame_count += 1
                current_time = time.time()
                # Print FPS every second
                if current_time - self.last_fps_print >= 1.0:
                    actual_fps = self.frame_count / (current_time - self.last_fps_print)
                    print(f"Target FPS: {fastest_fps:.1f}, Actual FPS: {actual_fps:.1f}")
                    self.frame_count = 0
                    self.last_fps_print = current_time
            
            await asyncio.sleep(target_interval)
        
        frame = self.get_current_frame()
        if frame is not None:
            if self.debug:
                print(f"Frame shape: {frame.shape}, type: {frame.dtype}")
            return {
                'frame': frame,
                'timestamp': time.time()
            }
        return None

    async def format_client_message(self, message_data, client_info):
        """Format the frame and data for a specific client."""
        frame = message_data['frame']
        size = client_info['size']
        mirror = client_info['mirror']
        track_hands = client_info.get('hands', False)

        if self.debug:
            print(f"Processing frame for client: size={size}, mirror={mirror}, hands={track_hands}")

        # Resize frame
        resized_frame = self.get_resized_frame(frame, size)
        
        # Mirror if needed
        if mirror:
            resized_frame = cv2.flip(resized_frame, 1)

        # Process frame
        marker_data = self.marker_tracker.process_frame(resized_frame)
        hand_data = self.hand_tracker.process_frame(resized_frame) if track_hands else []

        # Encode frame
        _, encoded_frame = cv2.imencode('.jpg', resized_frame)
        frame_bytes = encoded_frame.tobytes()

        return {
            'data': {
                "markers": marker_data,
                "hands": hand_data if track_hands else []
            },
            'frame_bytes': frame_bytes
        }

    async def send_to_client(self, client_ws, message):
        """Send the formatted message to the client."""
        if not client_ws.closed:
            await client_ws.send_str(json.dumps(message['data']))
            await client_ws.send_bytes(message['frame_bytes'])

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
    camera_server = CameraServer(host='0.0.0.0', port=7160, debug=True) #, http_url=http_url)  # For HTTP camera

    try:
        camera_server.run()
    except KeyboardInterrupt:
        print("Stopping Camera Server...")


if __name__ == "__main__":
    main()