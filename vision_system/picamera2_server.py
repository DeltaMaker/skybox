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
        
        # Get camera modes
        modes = self._get_camera_modes()
        if not modes:
            raise RuntimeError("No camera modes available")
            
        # Find first mode >= min_size
        base_size = min_size
        qualifying_modes = [m for m in modes if m['resolution'][0] >= min_size[0] and m['resolution'][1] >= min_size[1]]
        if qualifying_modes:
            best_mode = min(qualifying_modes, key=lambda m: m['resolution'][0] * m['resolution'][1])
            base_size = best_mode['resolution']
            if self.debug:
                print(f"\nSelected mode: {base_size[0]}x{base_size[1]} @ {best_mode['fps']:.2f}fps")
        else:
            largest_mode = max(modes, key=lambda m: m['resolution'][0] * m['resolution'][1])
            base_size = largest_mode['resolution']
            if self.debug:
                print(f"\nUsing largest mode: {base_size[0]}x{base_size[1]} @ {largest_mode['fps']:.2f}fps")
        
        super().__init__(host, port, base_size, debug=debug)
        
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
            print("\nAvailable camera modes:")
            raw_modes = self.picam2.sensor_modes
            for mode in raw_modes:
                size = mode.get('size', (0, 0))
                format = mode.get('format', 'Unknown')
                fps = mode.get('fps', 0)
                print(f"  {size[0]}x{size[1]} @ {fps:.2f}fps ({format})")
        
        # Return structured mode information
        modes = []
        try:
            raw_modes = self.picam2.sensor_modes
            for mode in raw_modes:
                size = mode.get('size', (0, 0))
                format = mode.get('format', 'Unknown')
                fps = mode.get('fps', 0)
                if size and fps:
                    modes.append({
                        'resolution': size,
                        'format': format,
                        'fps': fps
                    })
            return modes
            
        except Exception as e:
            logging.error(f"Failed to get camera modes: {e}")
            if self.debug:
                print(f"\nError getting camera modes: {e}")
            return []

    def _setup_camera(self):
        """Configure camera."""
        try:
            # Clean up any existing camera instance
            if self.picam2:
                if self.debug:
                    print(f"Cleaning up existing camera instance: {self.picam2}")
                try:
                    self.picam2.close()
                except Exception as e:
                    if self.debug:
                        print(f"Error during camera cleanup: {e}")
                self.picam2 = None
            
            # Create new camera instance
            if self.debug:
                print("Creating new Picamera2 instance...")
            self.picam2 = Picamera2()
            
            # Configure and start recording
            if self.debug:
                print(f"Configuring camera with size {self.base_size}")
                print(f"Camera state before config: {self.picam2.camera_properties if self.picam2 else 'No camera'}")
            
            # Ensure we have a valid base_size
            if not self.base_size:
                raise RuntimeError("Camera base_size not set")
            
            video_config = self.picam2.create_video_configuration(
                main={"size": self.base_size, "format": "RGB888"},
                buffer_count=4,
                controls={
                    "FrameDurationLimits": (33333, 33333),  # ~30fps
                }
            )
            
            if self.debug:
                print(f"Video config created: {video_config}")
            
            self.picam2.configure(video_config)
            if self.debug:
                print("Camera configured")
            
            self.picam2.start_recording(MJPEGEncoder(), FileOutput(self.output))
            if self.debug:
                print("Recording started")
                
        except Exception as e:
            logging.error(f"Failed to setup camera: {e}")
            if self.debug:
                print(f"Camera setup error: {e}")
                print(f"Camera state: {self.picam2.camera_properties if self.picam2 else 'No camera'}")
                print(f"Current base_size: {self.base_size}")
            if self.picam2:
                try:
                    self.picam2.close()
                    if self.debug:
                        print("Camera closed after error")
                except:
                    if self.debug:
                        print("Failed to close camera after error")
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
    parser.add_argument("--min-size", type=str, default="1400x900",
                      help="Minimum camera resolution in WxH format (default: 1400x900)")
    parser.add_argument("--debug", action="store_true",
                      help="Enable debug output")
    
    args = parser.parse_args()

    try:
        # Parse min_size
        w, h = map(int, args.min_size.split('x'))
        min_size = (w, h)
        
        logging.info(f"Starting Picamera2 server on {args.host}:{args.port}")
        server = Picamera2Server(
            host=args.host,
            port=args.port,
            min_size=min_size,
            debug=args.debug
        )
        server.run()
    except ValueError as e:
        logging.error(f"Invalid min-size format. Use WxH format (e.g., 1400x900)")
        sys.exit(1)
    except RuntimeError as e:
        if "busy" in str(e).lower():
            logging.error("Camera is in use by another process.")
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