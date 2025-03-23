"""
Camera Server Implementation
==========================

A flexible and extensible camera streaming server that supports multiple camera types
and provides real-time computer vision capabilities.

Key Features:
------------
- Supports multiple camera types (OpenCV, HTTP stream)
- Real-time video streaming over WebSocket
- Marker tracking for ArUco markers
- Hand tracking capabilities
- Configurable frame rates and resolutions per client
- Automatic frame resizing and mirroring
- FPS monitoring and performance statistics
- Asynchronous client handling

Architecture:
------------
- Base CameraServer class providing core functionality
- Specialized implementations for different camera types:
  * OpenCVServer: For local camera devices
  * HTTPServer: For IP cameras or HTTP video streams

Usage:
------
1. Direct usage:
   ```python
   server = OpenCVServer(camera_id=0, port=7160)
   server.run()
   ```

2. Command line:
   ```bash
   python camera_server.py --port 7160 --camera 0 --debug
   ```

Dependencies:
------------
- OpenCV (cv2)
- NumPy
- websockets
- requests (for HTTP cameras)
- vision_system.marker_tracker
- vision_system.hand_tracker

Author: Bob Houston
Version: 0.1
Date: 2025-03-22
"""
import os
import sys
# Add the parent directory to sys.path if running as script
if __name__ == "__main__":
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
import logging
import time
import cv2
import numpy as np
import asyncio
import argparse
import requests
from vision_system.marker_tracker import MarkerTracker
from vision_system.hand_tracker import HandTracker
from websocket_server.simple_server import SimpleWebsocketServer


class CameraServer(SimpleWebsocketServer):
    def __init__(self, host='0.0.0.0', port=7160, base_size=None, debug=False):
        """Initialize the base camera server."""
        super().__init__(host, port, debug)
        self.base_size = base_size  # Will be set during camera setup to actual capture resolution
        self.marker_tracker = MarkerTracker()
        self.hand_tracker = HandTracker()
        self.frame_count = 0
        self.last_fps_print = time.time()
        self._initialize_camera()

    def _initialize_camera(self):
        """Template method for camera initialization."""
        try:
            if self.debug:
                print(f"Initializing {self.__class__.__name__}...")
            self._setup_camera()
            if self.debug:
                print(f"{self.__class__.__name__} initialization successful")
        except Exception as e:
            logging.error(f"Failed to initialize {self.__class__.__name__}: {e}")
            if self.debug:
                print(f"Camera initialization error: {str(e)}")
            raise

    def _setup_camera(self):
        """Internal method for camera-specific setup."""
        raise NotImplementedError("Derived classes must implement _setup_camera")

    def get_current_frame(self):
        """Template method to capture the current frame."""
        try:
            if self.debug:
                print(f"Capturing {self.__class__.__name__} frame...")
            
            frame = self._capture_frame()
            
            if frame is None:
                raise ValueError(f"Failed to capture {self.__class__.__name__} frame")
            return frame
            
        except Exception as e:
            logging.error(f"Error capturing {self.__class__.__name__} frame: {e}")
            if self.debug:
                print(f"Frame capture error: {str(e)}")
            return None

    def _capture_frame(self):
        """Internal method that each camera type must implement."""
        raise NotImplementedError("Derived classes must implement _capture_frame")

    def fastest_fps(self):
        """Hook method to allow derived classes to override the FPS calculation."""
        return max(client.get('fps', 1) for client in self.clients.values())

    async def get_broadcast_data(self):
        """Get the current frame and process it."""
        if self.clients:
            fastest_fps = self.fastest_fps()
            target_interval = 1 / fastest_fps
            
            if self.debug:
                self._update_fps_stats()
            
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

    def _update_fps_stats(self):
        """Update and print FPS statistics."""
        self.frame_count += 1
        current_time = time.time()
        if current_time - self.last_fps_print >= 1.0:
            actual_fps = self.frame_count / (current_time - self.last_fps_print)
            fastest_fps = self.fastest_fps()
            print(f"Target FPS: {fastest_fps:.1f}, Actual FPS: {actual_fps:.1f}")
            self.frame_count = 0
            self.last_fps_print = current_time

    def extract_client_info(self, config):
        """Extract custom frame size, FPS, and mirror flag from client subscription."""
        # Calculate height to preserve aspect ratio from base_size
        aspect_ratio = self.base_size[1] / self.base_size[0] if self.base_size else 0.75
        if 'width' in config:
            width = config['width']
        elif 'size' in config:
            width = config['size'][0]
        else:
            width = 640
        size = (width, int(width * aspect_ratio))
        client_info = {
            'size': size,
            'fps': config.get('fps', 15),
            'mirror': config.get('mirror', False),
            'hands': config.get('hands', False)
        }
        if self.debug:
            print(f"New client subscribed with config: {client_info}")
        return client_info

    async def format_client_message(self, message_data, client_info):
        """Format the frame and data for a specific client."""
        frame = message_data['frame']
        size = client_info['size']
        mirror = client_info['mirror']
        track_hands = client_info.get('hands', False)

        if self.debug:
            print(f"Processing frame for client: size={size}, mirror={mirror}, hands={track_hands}")

        resized_frame = cv2.resize(frame, size)
        if mirror:
            resized_frame = cv2.flip(resized_frame, 1)

        marker_data = self.marker_tracker.process_frame(frame) # use original frame for marker tracking
        hand_data = self.hand_tracker.process_frame(resized_frame) if track_hands else []

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

    def perform_cleanup(self):
        """Template method for cleanup tasks."""
        try:
            if self.debug:
                print(f"Cleaning up {self.__class__.__name__}")
            self._cleanup_camera()
        except Exception as e:
            logging.error(f"Error cleaning up {self.__class__.__name__}: {e}")

    def _cleanup_camera(self):
        """Internal method for camera-specific cleanup."""
        pass  # Optional cleanup, not all cameras need it

    def get_status_info(self):
        """Provide camera-specific status information."""
        return {
            'camera_type': self.__class__.__name__,
            'base_resolution': self.base_size,
            'fps_stats': {
                'target': max(client.get('fps', 1) for client in self.clients.values()) if self.clients else 0,
                'frame_count': self.frame_count
            }
        }


class OpenCVServer(CameraServer):
    def __init__(self, camera_id=0, host='0.0.0.0', port=7160, debug=False):
        self.camera_id = camera_id
        self.cap = None
        super().__init__(host, port, debug)

    def _setup_camera(self):
        self.cap = cv2.VideoCapture(self.camera_id)
        if not self.cap.isOpened():
            raise ValueError(f"Failed to open OpenCV camera {self.camera_id}")
        # Get the actual camera capture resolution
        self.base_size = (
            int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        )
        if self.debug:
            print(f"Camera capture resolution: {self.base_size}")

    def _capture_frame(self):
        if not self.cap or not self.cap.isOpened():
            self._setup_camera()
        ret, frame = self.cap.read()
        if not ret:
            raise ValueError("Failed to read OpenCV frame")
        return frame

    def _cleanup_camera(self):
        if self.cap:
            self.cap.release()


class HTTPServer(CameraServer):
    def __init__(self, url, host='0.0.0.0', port=7160, debug=False):
        self.url = url
        super().__init__(host, port, debug)

    def _setup_camera(self):
        response = requests.get(self.url, timeout=1.0)
        if response.status_code != 200:
            raise ValueError(f"Failed to connect to HTTP camera at {self.url}")
        # Get the size from first frame
        np_arr = np.frombuffer(response.content, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is not None:
            self.base_size = (frame.shape[1], frame.shape[0])  # width, height
            if self.debug:
                print(f"HTTP stream resolution: {self.base_size}")

    def _capture_frame(self):
        response = requests.get(self.url, timeout=1.0)
        if response.status_code != 200:
            raise ValueError(f"HTTP request failed: {response.status_code}")
        np_arr = np.frombuffer(response.content, np.uint8)
        return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

class StaticJPEGServer(CameraServer):
    def __init__(self, jpeg_path, host='0.0.0.0', port=7160, debug=False):
        self.jpeg_path = jpeg_path
        super().__init__(host, port, debug)

    def _setup_camera(self):
        self.static_frame = cv2.imread(self.jpeg_path)  
        if self.static_frame is None:
            raise ValueError(f"Failed to read JPEG file: {self.jpeg_path}")
        self.base_size =  self.base_size = (self.static_frame.shape[1], self.static_frame.shape[0])  # width, height

    def fastest_fps(self):
        """Set the FPS to 1 for static JPEG server."""
        return 1

    def _capture_frame(self):
        return self.static_frame.copy()

def main():
    """Run the OpenCV camera server with command line configuration."""
    parser = argparse.ArgumentParser(description="Vision System Camera Server")
    parser.add_argument("--host", type=str, default="0.0.0.0",
                      help="Host address to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=7160,
                      help="Port number to listen on (default: 7160)")
    parser.add_argument("--camera", type=int, default=0,
                      help="Camera device ID for OpenCV (default: 0)")
    parser.add_argument("--debug", action="store_true",
                      help="Enable debug output")
    parser.add_argument("--jpeg", type=str, default=None,
                      help="Path to a static JPEG file to serve")
    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    try:
        if args.jpeg:
            logging.info(f"Starting Static JPEG server on {args.host}:{args.port}")
            server = StaticJPEGServer(
                jpeg_path=args.jpeg,
                host=args.host,
                port=args.port,
                debug=args.debug
            )
            server.run()
        else:
            logging.info(f"Starting OpenCV camera server on {args.host}:{args.port}")
            server = OpenCVServer(
            camera_id=args.camera,
            host=args.host,
            port=args.port,
            debug=args.debug
        )
        server.run()
    except KeyboardInterrupt:
        logging.info("\nShutting down server...")
    except Exception as e:
        logging.error(f"Server error: {e}")
        raise


if __name__ == "__main__":
    main()