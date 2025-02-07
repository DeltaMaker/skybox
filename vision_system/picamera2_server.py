"""
Picamera2Server - Camera server implementation for Raspberry Pi Camera.
Requires picamera2 package to be installed.
"""

import logging
import time

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

from camera_server import CameraServer

class Picamera2Server(CameraServer):
    def __init__(self, host='0.0.0.0', port=7160, debug=False):
        if not PICAMERA2_AVAILABLE:
            raise ImportError("Picamera2 is not available on this system")
        self.picam2 = None
        self.camera_modes = None
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
                print("Using default fallback mode: 1920x1080")
        
        initial_size = chosen_mode['resolution'] if chosen_mode else (1920, 1080)
        
        try:
            if self.debug:
                print(f"Configuring camera with size {initial_size}")
            
            video_config = self.picam2.create_video_configuration(
                main={"size": initial_size, "format": "RGB888"},
                buffer_count=4,
                controls={
                    "FrameDurationLimits": (33333, 33333),  # ~30fps
                }
            )
            self.picam2.configure(video_config)
            self.picam2.start()
            self.base_size = initial_size
            if self.debug:
                print(f"Camera configured successfully at {initial_size}")
                print("-" * 40)
                
        except Exception as e:
            logging.warning(f"Failed to configure camera with initial settings: {e}")
            if self.debug:
                print("\nFalling back to default configuration:")
                print("-" * 40)
            video_config = self.picam2.create_video_configuration()
            self.picam2.configure(video_config)
            self.picam2.start()
            self.base_size = self.picam2.camera_properties['ScalerCropMaximum'][:2]
            if self.debug:
                print(f"Using fallback configuration: {self.base_size}")
                print("-" * 40)

    def _capture_frame(self):
        if not self.picam2:
            self._setup_camera()
        return self.picam2.capture_array()

    def _cleanup_camera(self):
        if self.picam2:
            self.picam2.stop()
            self.picam2.close() 