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
        self.picam2 = None
        self.camera_modes = None
        self.output = StreamingOutput()
        super().__init__(host, port, debug)

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

    def _configure_camera(self, size=None, is_fallback=False):
        """Configure camera with given size or fallback configuration."""
        try:
            if self.debug:
                print(f"\n{'Fallback' if is_fallback else 'Initial'} configuration:")
                print("-" * 40)
                if size:
                    print(f"Configuring camera with size {size}")
            
            if size:
                video_config = self.picam2.create_video_configuration(
                    main={"size": size, "format": "RGB888"},
                    buffer_count=4,
                    controls={
                        "FrameDurationLimits": (33333, 33333),  # ~30fps
                    }
                )
            else:
                video_config = self.picam2.create_video_configuration()
            
            self.picam2.configure(video_config)
            self.picam2.start_recording(MJPEGEncoder(), FileOutput(self.output))
            
            self.base_size = size or self.picam2.camera_properties['ScalerCropMaximum'][:2]
            
            if self.debug:
                print(f"Camera configured successfully at {self.base_size}")
                print("-" * 40)
            
            return True
            
        except Exception as e:
            if not is_fallback:  # Only log warning if this isn't already the fallback attempt
                logging.warning(f"Failed to configure camera with {'initial' if size else 'fallback'} settings: {e}")
            return False

    def _setup_camera(self):
        if not self.picam2:
            self.picam2 = Picamera2()
        
        # Get available modes
        self.camera_modes = self._get_camera_modes()
        
        # Choose highest resolution mode with fps >= 30
        chosen_mode = None
        for mode in self.camera_modes:
            if mode['fps'] >= 30:
                if (not chosen_mode or 
                    mode['resolution'][0] * mode['resolution'][1] > 
                    chosen_mode['resolution'][0] * chosen_mode['resolution'][1]):
                    chosen_mode = mode

        # Fallback to first mode if no suitable mode found
        if not chosen_mode and self.camera_modes:
            chosen_mode = self.camera_modes[0]
        
        if self.debug:
            print("\nCamera configuration:")
            print("-" * 40)
            if chosen_mode:
                print(f"Selected mode: {chosen_mode['resolution'][0]}x{chosen_mode['resolution'][1]} @ {chosen_mode['fps']:.2f} fps")
            else:
                print("Using default fallback mode")
        
        initial_size = chosen_mode['resolution'] if chosen_mode else (1920, 1080)
        
        # Try initial configuration, fall back if it fails
        if not self._configure_camera(initial_size):
            if not self._configure_camera(is_fallback=True):
                raise RuntimeError("Failed to configure camera with both initial and fallback settings")

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
    except KeyboardInterrupt:
        logging.info("\nShutting down server...")
    except Exception as e:
        logging.error(f"Server error: {e}")
        raise

if __name__ == "__main__":
    import argparse
    import sys
    main() 