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
import time
import cv2
import numpy as np
import asyncio
import argparse
import requests
from vision_system.marker_tracker import MarkerTracker
from vision_system.hand_tracker import HandTracker
from websocket_server.simple_server import SimpleWebsocketServer


def load_camera_calibration(calibration_file, debug=False):
    """
    Load camera calibration data from a JSON file.
    
    Args:
        calibration_file: Path to the calibration JSON file
        debug: Whether to print debug messages
        
    Returns:
        Tuple of (camera_matrix, distortion_coefficients)
    """
    try:
        with open(calibration_file, 'r') as f:
            calibration_data = json.load(f)
            
        camera_matrix = np.array(calibration_data['camera_matrix'])
        distortion_coeffs = np.array(calibration_data['distortion_coefficients'])
        
        if debug:
            print(f"Loaded camera calibration from {calibration_file}")
            print(f"Camera matrix: {camera_matrix}")
            print(f"Distortion coefficients: {distortion_coeffs}")
            
        return camera_matrix, distortion_coeffs
    except FileNotFoundError:
        if debug:
            print(f"Calibration file not found: {calibration_file}")
        raise
    except Exception as e:
        if debug:
            print(f"Error loading calibration: {e}")
        raise


class CameraServer(SimpleWebsocketServer):
    def __init__(self, host='0.0.0.0', port=7160, base_size=None, calibration_file="camera_calibration.json", 
                 apply_undistortion=False, undistort_alpha=0.8, undistort_sharpen=False, debug=False, debug_level=2):
        """Initialize the base camera server."""
        super().__init__(host, port, debug=debug, debug_level=debug_level)
        self.base_size = base_size  # Will be set during camera setup to actual capture resolution
        self.calibration_file = calibration_file
        self.apply_undistortion = apply_undistortion
        self.undistort_alpha = undistort_alpha
        self.undistort_sharpen = undistort_sharpen
        
        # Load camera calibration data if undistortion is needed
        self.camera_matrix = None
        self.distortion_coeffs = None
        
        # Load calibration data regardless, as it might be needed for marker tracking
        self._load_calibration()
        
        # Create marker tracker with the camera calibration matrices
        self.marker_tracker = MarkerTracker(
            marker_size=0.01,
            camera_matrix=self.camera_matrix,
            distortion_coeffs=self.distortion_coeffs,
            is_frame_undistorted=self.apply_undistortion,
            debug=self.debug
        )
        
        self.hand_tracker = HandTracker()
        self.frame_count = 0
        self.last_fps_print = time.time()
        self._initialize_camera()
        
    def _load_calibration(self):
        """Load camera calibration for undistortion."""
        try:
            self.camera_matrix, self.distortion_coeffs = load_camera_calibration(
                self.calibration_file, 
                debug=self.debug
            )
            self.debug_log(f"Camera calibration loaded for undistortion", 3)
        except Exception as e:
            self.debug_log(f"Failed to load calibration: {e}", 1)
            self.apply_undistortion = False
            self.debug_log(f"Undistortion disabled due to calibration error: {str(e)}", 2)

    def _undistort_frame(self, frame):
        """
        Apply undistortion to a frame using loaded calibration data.
        
        Uses configurable alpha parameter to control balance between:
        - Zoomed view (alpha=0) with all pixels valid but smaller FOV
        - Full FOV (alpha=1) with black regions but no cropping
        
        Optionally applies sharpening after undistortion to improve image quality.
        
        Returns:
            Undistorted frame if successful, original frame otherwise
        """
        # Early return if undistortion is disabled or calibration data is missing
        if not self.apply_undistortion or self.camera_matrix is None or self.distortion_coeffs is None:
            return frame
            
        try:
            h, w = frame.shape[:2]
            
            # Get optimal new camera matrix with configurable alpha parameter
            # - alpha=0: zoomed view with all pixels valid (tighter crop)
            # - alpha=1: full FOV with potentially black regions (no crop)
            new_camera_matrix, roi = cv2.getOptimalNewCameraMatrix(
                self.camera_matrix, 
                self.distortion_coeffs, 
                (w, h), 
                self.undistort_alpha,  # Configurable alpha parameter
                (w, h)
            )
            
            # Apply undistortion with higher quality interpolation
            undistorted = cv2.undistort(
                frame, 
                self.camera_matrix, 
                self.distortion_coeffs, 
                None, 
                new_camera_matrix,
            )
            
            # Only crop the image if alpha is close to 0 (which provides valid ROI)
            if self.undistort_alpha < 0.1:
                x, y, w, h = roi
                if all(v > 0 for v in [x, y, w, h]):  # Only crop if ROI is valid
                    undistorted = undistorted[y:y+h, x:x+w]
            
            # Apply sharpening if enabled
            if self.undistort_sharpen:
                # Create a sharpening kernel
                kernel = np.array([[-0.5, -0.5, -0.5],
                                  [-0.5,  5.0, -0.5],
                                  [-0.5, -0.5, -0.5]])
                undistorted = cv2.filter2D(undistorted, -1, kernel)
                
            # Log successful undistortion at verbose level
            self.debug_log(f"Frame undistorted successfully with alpha={self.undistort_alpha}", 4)
            return undistorted
            
        except Exception as e:
            self.debug_log(f"Error undistorting frame: {e}", 1)
            self.debug_log(f"Undistortion error: {str(e)}", 2)
            # Return original frame if undistortion fails
            return frame

    def _initialize_camera(self):
        """Template method for camera initialization."""
        try:
            self.debug_log(f"Initializing {self.__class__.__name__}...", 3)
            self._setup_camera()
            self.debug_log(f"{self.__class__.__name__} initialization successful", 3)
        except Exception as e:
            self.debug_log(f"Failed to initialize {self.__class__.__name__}: {e}", 1)
            self.debug_log(f"Camera initialization error: {str(e)}", 2)
            raise

    def _setup_camera(self):
        """Internal method for camera-specific setup."""
        raise NotImplementedError("Derived classes must implement _setup_camera")

    def get_current_frame(self):
        """Capture the current frame and apply undistortion if enabled."""
        try:
            self.debug_log(f"Capturing {self.__class__.__name__} frame...", 4)
            
            frame = self._capture_frame()
            
            if frame is None:
                raise ValueError(f"Failed to capture {self.__class__.__name__} frame")
                
            # Always apply undistortion if enabled - this ensures all frames are processed consistently
            if self.apply_undistortion and self.camera_matrix is not None and self.distortion_coeffs is not None:
                frame = self._undistort_frame(frame)
                
            return frame
            
        except Exception as e:
            self.debug_log(f"Error capturing {self.__class__.__name__} frame: {e}", 1)
            self.debug_log(f"Frame capture error: {str(e)}", 2)
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
            
            self._update_fps_stats()
            
            await asyncio.sleep(target_interval)
        
        frame = self.get_current_frame()
        if frame is not None:
            self.debug_log(f"Frame shape: {frame.shape}, type: {frame.dtype}", 4)
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
            self.debug_log(f"Target FPS: {fastest_fps:.1f}, Actual FPS: {actual_fps:.1f}", 3)
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
        self.debug_log(f"New client subscribed with config: {client_info}", 3)
        return client_info

    async def format_client_message(self, message_data, client_info):
        """Format the frame and data for a specific client."""
        frame = message_data['frame']
        size = client_info['size']
        mirror = client_info['mirror']
        track_hands = client_info.get('hands', False)

        self.debug_log(f"Processing frame for client: size={size}, mirror={mirror}, hands={track_hands}", 4)

        # Process the frame for marker detection
        # The frame at this point should already be undistorted if undistortion was enabled
        marker_data = self.marker_tracker.process_frame(frame)

        # Now resize and apply other transformations for the client display
        resized_frame = cv2.resize(frame, size)
        if mirror:
            resized_frame = cv2.flip(resized_frame, 1)

        # Process hand tracking on the resized frame
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
            self.debug_log(f"Cleaning up {self.__class__.__name__}", 3)
            self._cleanup_camera()
        except Exception as e:
            self.debug_log(f"Error cleaning up {self.__class__.__name__}: {e}", 1)

    def _cleanup_camera(self):
        """Internal method for camera-specific cleanup."""
        pass  # Optional cleanup, not all cameras need it

    def get_status_info(self):
        """Provide camera-specific status information."""
        return {
            'camera_type': self.__class__.__name__,
            'base_resolution': self.base_size,
            'undistortion': self.apply_undistortion,
            'fps_stats': {
                'target': max(client.get('fps', 1) for client in self.clients.values()) if self.clients else 0,
                'frame_count': self.frame_count
            }
        }


class OpenCVServer(CameraServer):
    """Camera server that uses OpenCV to capture frames from a webcam."""
    
    def __init__(self, camera_index=0, resolution=None, host='0.0.0.0', port=7160, 
                 calibration_file="camera_calibration.json", apply_undistortion=False, 
                 undistort_alpha=0.8, undistort_sharpen=False, fps=30, debug=False, debug_level=2):
        """Initialize the OpenCV camera server with the specified camera index."""
        self.camera_index = camera_index
        self.fps = fps
        self.resolution = resolution  # Can be None, (width, height), or "4k", "1080p", "720p", etc.
        super().__init__(host, port, base_size=resolution, calibration_file=calibration_file,
                        apply_undistortion=apply_undistortion, undistort_alpha=undistort_alpha,
                        undistort_sharpen=undistort_sharpen, debug=debug, debug_level=debug_level)

    def _setup_camera(self):
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            raise ValueError(f"Failed to open OpenCV camera {self.camera_index}")
        # Get the actual camera capture resolution
        self.base_size = (
            int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        )
        self.debug_log(f"Camera capture resolution: {self.base_size}", 3)

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
    """Camera server that captures frames from an HTTP stream."""
    
    def __init__(self, url, fps=10, host='0.0.0.0', port=7160, 
                 calibration_file="camera_calibration.json", apply_undistortion=False, 
                 undistort_alpha=0.8, undistort_sharpen=False, debug=False, debug_level=2):
        """Initialize the HTTP camera server with the specified URL."""
        self.url = url
        self.fps = fps
        super().__init__(host, port, calibration_file=calibration_file,
                        apply_undistortion=apply_undistortion, undistort_alpha=undistort_alpha,
                        undistort_sharpen=undistort_sharpen, debug=debug, debug_level=debug_level)

    def _setup_camera(self):
        response = requests.get(self.url, timeout=1.0)
        if response.status_code != 200:
            raise ValueError(f"Failed to connect to HTTP camera at {self.url}")
        # Get the size from first frame
        np_arr = np.frombuffer(response.content, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is not None:
            self.base_size = (frame.shape[1], frame.shape[0])  # width, height
            self.debug_log(f"HTTP stream resolution: {self.base_size}", 3)

    def _capture_frame(self):
        response = requests.get(self.url, timeout=1.0)
        if response.status_code != 200:
            raise ValueError(f"HTTP request failed: {response.status_code}")
        np_arr = np.frombuffer(response.content, np.uint8)
        return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    def _cleanup_camera(self):
        pass  # HTTP server does not need explicit cleanup


class StaticJPEGServer(CameraServer):
    """Camera server that serves a static JPEG image for testing."""
    
    def __init__(self, image_path, fps=10, host='0.0.0.0', port=7160, 
                 calibration_file="camera_calibration.json", apply_undistortion=False, 
                 undistort_alpha=0.8, undistort_sharpen=False, debug=False, debug_level=2):
        """Initialize the static JPEG server with the specified image path."""
        self.image_path = image_path
        self.fps = fps
        super().__init__(host, port, calibration_file=calibration_file,
                        apply_undistortion=apply_undistortion, undistort_alpha=undistort_alpha,
                        undistort_sharpen=undistort_sharpen, debug=debug, debug_level=debug_level)

    def _setup_camera(self):
        self.static_frame = cv2.imread(self.image_path)  
        if self.static_frame is None:
            raise ValueError(f"Failed to read JPEG file: {self.image_path}")
        self.base_size = (self.static_frame.shape[1], self.static_frame.shape[0])  # width, height
        self.debug_log(f"Static JPEG resolution: {self.base_size}", 3)

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
    parser.add_argument("--url", type=str, default="http://192.168.1.131/webcam/?action=snapshot",
                      help="Video stream URL")
    parser.add_argument("--camera", type=int, default=0,
                      help="Camera device ID for OpenCV (default: 0)")
    parser.add_argument("--calibration", type=str, default="camera_calibration.json",
                      help="Camera calibration file path (default: camera_calibration.json)")
    parser.add_argument("--undistort", action="store_true",
                      help="Apply camera undistortion to frames")
    parser.add_argument("--debug", action="store_true",
                      help="Enable debug output")
    parser.add_argument("--debug-level", type=int, default=2,
                      help="Debug level (1=error, 2=warning, 3=info, 4=verbose) (default: 2)")
    parser.add_argument("--jpeg", type=str, default=None,
                      help="Path to a static JPEG file to serve")
    args = parser.parse_args()

    try:
        if args.jpeg:
            server = StaticJPEGServer(
                image_path=args.jpeg,
                host=args.host,
                port=args.port,
                calibration_file=args.calibration,
                apply_undistortion=args.undistort,
                debug=args.debug,
                debug_level=args.debug_level
            )
            server.debug_log(f"Starting Static JPEG server on {args.host}:{args.port}", 2)
            server.run()
        elif args.url:
            server = HTTPServer(
                url=args.url,
                host=args.host,
                port=args.port,
                calibration_file=args.calibration,
                apply_undistortion=args.undistort,
                debug=args.debug,
                debug_level=args.debug_level
            )
            server.debug_log(f"Starting HTTP camera server on {args.host}:{args.port}", 2)
            server.run()
        else:
            server = OpenCVServer(
                camera_index=args.camera,
                host=args.host,
                port=args.port,
                calibration_file=args.calibration,
                apply_undistortion=args.undistort,
                debug=args.debug,
                debug_level=args.debug_level
            )
            server.debug_log(f"Starting OpenCV camera server on {args.host}:{args.port}", 2)
            server.run()
    except KeyboardInterrupt:
        if 'server' in locals():
            server.debug_log("\nShutting down server...", 2)
        else:
            print("\nShutting down server...")
    except Exception as e:
        if 'server' in locals():
            server.debug_log(f"Server error: {e}", 1)
        else:
            print(f"Server error: {e}")
        raise


if __name__ == "__main__":
    main()