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
    def __init__(self, host='0.0.0.0', port=7160, min_size=(1400, 900), debug=False):
        # Initialize our attributes first
        self.picam2 = None
        self.camera_modes = None
        self.output = StreamingOutput()
        self.debug = debug
        self.client_sizes = {}  # Track client window sizes
        
        # Get camera modes
        self.camera_modes = self._get_camera_modes()
        
        # Start with smallest available mode
        smallest_mode = min(self.camera_modes, key=lambda m: m['size'][0] * m['size'][1])
        self.camera_format = smallest_mode.get("unpacked_format", "XBGR8888")
        super().__init__(host, port, smallest_mode["size"], debug=debug)
        
        if self.debug:
            print(f"\nInitial mode: {self.base_size[0]}x{self.base_size[1]} @ {smallest_mode['fps']:.2f}fps")
            print(f"Format: {self.camera_format}")
        
       
        camera_info = self.picam2.camera_properties if self.picam2 else {}
        self.camera_name = camera_info.get('Model', 'Unknown')
        self.camera_id = camera_info.get('Location', 'Unknown')
 
    
    def _get_camera_modes(self):
        """Query available camera modes from Picamera2."""
        if not self.picam2:
            if self.debug:
                print("\nNo camera instance, creating new one for mode query")
            self.picam2 = Picamera2()
        
        if self.debug:
            print("\nQuerying camera capabilities:")
            print("----------------------------------------")
            cam_info = self.picam2.camera_properties
            print(f"Camera: {cam_info.get('Model', 'Unknown')} [{cam_info.get('PixelArraySize', ['?', '?'])[0]}x{cam_info.get('PixelArraySize', ['?', '?'])[1]}]")
            print(f"Location: {cam_info.get('Location', 'Unknown')}")
        
        sensor_modes = self.picam2.sensor_modes
        
        if not sensor_modes:
            raise RuntimeError("No valid camera modes found!")
            
        if self.debug:
            print("\nAvailable Modes:")
            for i, mode in enumerate(sensor_modes):
                crop = mode.get('crop_limits', (0, 0, 0, 0))
                print(f"Mode {i}: {mode.get('format', 'Unknown')} : {mode['size'][0]}x{mode['size'][1]} "
                      f"[{mode['fps']:.2f} fps - ({crop[0]}, {crop[1]})/{crop[2]}x{crop[3]} crop]")
            
            print("\nRaw camera properties:")
            for key, value in self.picam2.camera_properties.items():
                print(f"{key}: {value}")
            print("----------------------------------------")
        
        return sensor_modes

    def _setup_camera(self):
        """Configure camera."""
        try:
            # Clean up any existing camera instance
            if self.picam2:
                if self.debug:
                    print("Cleaning up existing camera instance")
                try:
                    self.picam2.stop_recording()
                    self.picam2.close()
                except Exception as e:
                    if self.debug:
                        print(f"Error during camera cleanup: {e}")
                self.picam2 = None
            
            # Create new camera instance
            self.picam2 = Picamera2()
            
            print(f"base_size before create_video_configuration: {self.base_size}")
            # Configure and start recording
            video_config = self.picam2.create_video_configuration(
                main={"size": self.base_size}, controls={'FrameRate':15})
        
            self.picam2.configure(video_config)
            self.picam2.start()
            self.picam2.start_recording(MJPEGEncoder(), FileOutput(self.output))
            
            if self.debug:
                print(f"Camera configured and started with resolution {self.base_size}")
                
        except Exception as e:
            logging.error(f"Failed to setup camera: {e}")
            if self.debug:
                print(f"Camera setup error: {e}")
            if self.picam2:
                try:
                    self.picam2.close()
                except:
                    pass
                self.picam2 = None
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
        """Ensure proper cleanup of camera resources."""
        if self.picam2:
            if self.debug:
                print("Cleaning up camera resources...")
            try:
                self.picam2.stop_recording()
                if self.debug:
                    print("Recording stopped")
            except Exception as e:
                logging.error(f"Error stopping recording: {e}")
                if self.debug:
                    print(f"Error stopping recording: {e}")
            try:
                self.picam2.close()
                if self.debug:
                    print("Camera closed")
            except Exception as e:
                logging.error(f"Error closing camera: {e}")
                if self.debug:
                    print(f"Error closing camera: {e}")
            self.picam2 = None

    def update_camera_mode(self, client_width, client_height):
        """Update camera mode based on client size requirements."""
        if not self.picam2:
            return False
            
        # Get current modes
        modes = self.picam2.sensor_modes
        if not modes:
            return False
            
        # Find smallest mode that satisfies the client size
        valid_modes = [m for m in modes 
                      if m['size'][0] >= client_width and m['size'][1] >= client_height]
        
        if not valid_modes:
            if self.debug:
                print(f"No mode available >= {client_width}x{client_height}, keeping current mode")
            return False
            
        # Get smallest valid mode
        best_mode = min(valid_modes, key=lambda m: m['size'][0] * m['size'][1])
        new_size = best_mode['size']
        
        # Only update if the size would change
        if new_size != self.base_size:
            if self.debug:
                print(f"Updating camera mode to {new_size[0]}x{new_size[1]} @ {best_mode['fps']:.2f}fps")
            
            self.base_size = new_size
            self.camera_format = best_mode.get("unpacked_format", "XBGR8888")
            
            # Reconfigure camera
            self._setup_camera()
            return True
            
        return False

    def handle_client_resize(self, client, width, height):
        """Handle client window resize event."""
        if self.debug:
            print(f"Client resize: {width}x{height}")
        
        # Track largest client size
        self.client_sizes[client] = (width, height)
        
        # Find largest client dimensions
        max_width = max(size[0] for size in self.client_sizes.values())
        max_height = max(size[1] for size in self.client_sizes.values())
        
        # Update camera mode if needed
        self.update_camera_mode(max_width, max_height)

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