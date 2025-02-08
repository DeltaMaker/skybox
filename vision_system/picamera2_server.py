"""
Picamera2Server - Camera server implementation for Raspberry Pi Camera.
Requires picamera2 package to be installed.
"""

import logging
import time
import io
from threading import Condition
import cv2
import numpy as np
import argparse

try:
    from picamera2 import Picamera2
    from picamera2.encoders import MJPEGEncoder
    from picamera2.outputs import FileOutput
    print("Picamera2 is available.")
except ImportError:
    print("Picamera2 is not available on this system.")
    raise

from camera_server import CameraServer

class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        """Save the latest frame."""
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

class Picamera2Server(CameraServer):
    def __init__(self, host='0.0.0.0', port=7160, debug=False):
        # Initialize parent class first to set debug attribute
        super().__init__(host, port, debug)
        
        self.picam2 = None
        self.camera_modes = None
        self.output = StreamingOutput()
        
        # Try to initialize camera, but don't fail if busy
        try:
            self.picam2 = Picamera2()
            if self.debug:
                print("Camera initialized successfully")
        except Exception as e:
            logging.warning(f"Camera initialization warning: {e}")
            if self.debug:
                print(f"Warning: {e}")
            # Continue initialization, will retry in _setup_camera

    def _get_camera_modes(self):
        """Query available camera modes from Picamera2."""
        if not self.picam2:
            self.picam2 = Picamera2()
        
        if self.debug:
            print("\nQuerying camera capabilities:")
            print("-" * 40)
            print(f"Camera Model: {self.picam2.camera_properties.get('Model', 'Unknown')}")
        
        camera_info = self.picam2.camera_properties
        if self.debug:
            print("\nRaw camera properties:")
            for key, value in camera_info.items():
                print(f"{key}: {value}")
            print("-" * 40)
        
        # Get available modes from camera properties
        modes = []
        try:
            for mode in camera_info.get('SensorModes', []):
                size = mode.get('Size', [0, 0])
                fps = mode.get('fps', 0)
                if size and fps:
                    modes.append({
                        'resolution': size,
                        'fps': fps
                    })
            
            if self.debug:
                print("\nAvailable camera modes:")
                print("-" * 40)
                for i, mode in enumerate(modes, 1):
                    res = mode['resolution']
                    print(f"Mode {i}: {res[0]}x{res[1]} @ {mode['fps']:.2f} fps")
                print("-" * 40)
            
            return modes
            
        except Exception as e:
            logging.error(f"Failed to get camera modes: {e}")
            if self.debug:
                print(f"\nError getting camera modes: {e}")
            return []

    def _setup_camera(self):
        """Configure camera."""
        try:
            if not self.picam2:
                self.picam2 = Picamera2()
            
            # Get available modes
            self.camera_modes = self._get_camera_modes()
            
            video_config = self.picam2.create_video_configuration(
                main={"size": (1296, 972), "format": "RGB888"},
                buffer_count=4,
                controls={
                    "FrameDurationLimits": (33333, 33333),  # ~30fps
                }
            )
            self.picam2.configure(video_config)
            self.picam2.start_recording(MJPEGEncoder(), FileOutput(self.output))
            self.base_size = (1296, 972)
            
            if self.debug:
                print("Camera setup successful")
                
        except Exception as e:
            logging.error(f"Failed to setup camera: {e}")
            raise

    def _capture_frame(self):
        if not self.picam2:
            self._setup_camera()
        
        frame = self.output.frame
        if frame:
            np_arr = np.frombuffer(frame, np.uint8)
            return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        return None

    def _cleanup_camera(self):
        if self.picam2:
            try:
                self.picam2.stop_recording()
            except Exception as e:
                logging.error(f"Error stopping recording: {e}")
            try:
                self.picam2.close()
            except Exception as e:
                logging.error(f"Error closing camera: {e}")

    def get_status_info(self):
        """Provide camera-specific status information."""
        camera_info = self.picam2.camera_properties if self.picam2 else {}
        return {
            'camera_type': self.__class__.__name__,
            'camera_name': camera_info.get('Model', 'Unknown'),
            'camera_id': camera_info.get('Location', 'Unknown'),
            'base_resolution': self.base_size,
            'available_modes': self._get_camera_modes(),
            'fps_stats': {
                'target': max(client.get('fps', 1) for client in self.clients.values()) if self.clients else 0,
                'frame_count': self.frame_count
            }
        }

def main():
    """Run the Picamera2 server with command line configuration."""
    parser = argparse.ArgumentParser(description="Picamera2 Vision System Server")
    parser.add_argument("--host", type=str, default="0.0.0.0",
                      help="Host address to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=7160,
                      help="Port number to listen on (default: 7160)")
    parser.add_argument("--debug", action="store_true",
                      help="Enable debug output")
    
    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    try:
        logging.info(f"Starting Picamera2 server on {args.host}:{args.port}")
        server = Picamera2Server(
            host=args.host,
            port=args.port,
            debug=args.debug
        )
        server.run()
    except RuntimeError as e:
        if "busy" in str(e).lower():
            logging.error("Camera is in use by another process. Please ensure no other camera applications are running.")
            if args.debug:
                logging.error("Try: 'sudo lsof /dev/video*' to see what's using the camera")
        else:
            logging.error(f"Runtime error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logging.info("\nShutting down server...")
    except Exception as e:
        logging.error(f"Server error: {e}")
        raise

if __name__ == "__main__":
    import argparse
    import sys
    main() 