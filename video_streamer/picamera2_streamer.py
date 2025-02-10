"""
Picamera2 Vision System Server

This module implements a camera streamer specifically for Raspberry Pi cameras using the Picamera2 library.
Requires picamera2 to be installed and a compatible camera to be connected.

Features:
- Automatic camera mode selection based on client requirements
- Dynamic resolution scaling
- Hardware-accelerated MJPEG encoding
- Support for both streaming and snapshot endpoints
- Efficient resource management

Key Components:
- Camera mode detection and selection
- Resolution management
- Format handling with native sensor support
- Client size tracking
- Automatic camera reconfiguration

Usage:
    streamer = Picamera2Streamer(
        output_port=8080,         # Server port
        min_size=(1400, 900),     # Minimum resolution
        frame_rate=30             # Target frame rate
    )
    streamer.run()

Author: Bob Houston
Date: 2024-03-21
Version: 0.2
"""

import signal
import socket
from threading import Thread
import sys
import time

try:
    from picamera2 import Picamera2
    from picamera2.encoders import MJPEGEncoder
    from picamera2.outputs import FileOutput
except ImportError:
    print("\nError: Picamera2 is required but not installed.")
    print("This module only works on Raspberry Pi with a compatible camera.")
    print("Please install picamera2: pip install picamera2")
    sys.exit(1)

from streaming_module import StreamingOutput, StreamingHandler, StreamingServer


class Picamera2Streamer:
    def __init__(self, output_port=8080, min_size=(1280, 720), frame_rate=30):
        self.address = ('', output_port)
        self.min_size = min_size
        self.frame_rate = frame_rate
        
        # Setup streaming components
        self.output = StreamingOutput()
        StreamingHandler.output = self.output
        
        self.server = StreamingServer(self.address, StreamingHandler)

        # Initialize camera
        self.picam2 = Picamera2()
        self.camera_modes = self.picam2.sensor_modes
        valid_modes = [m for m in self.camera_modes 
                  if m['size'][0] >= min_size[0] and m['size'][1] >= min_size[1]]
        if not valid_modes:
            raise RuntimeError(f"No available camera modes larger than {min_size[0]}x{min_size[1]}")
        
        # Get best mode and its properties
        best_mode = min(valid_modes, key=lambda m: m['size'][0] * m['size'][1])
        self.base_size = best_mode["size"]
        self.camera_format = "YUV420"

         # Configure handler with camera settings
        StreamingHandler.camera_config = {
            'size': self.base_size,
            'format': self.camera_format,
            'frame_rate': self.frame_rate
        }


    def get_host_ip(self):
        """Attempt to determine the IP address of the machine."""
        try:
            # This creates a dummy socket to connect to 8.8.8.8, and then get the socket's own address
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "localhost"

    def start(self):
        """Start the camera and server."""
        video_config = self.picam2.create_video_configuration(
            main={"size": self.base_size, "format": self.camera_format},
            controls={'FrameRate': self.frame_rate}
        )
        self.picam2.configure(video_config)
        self.picam2.start_recording(MJPEGEncoder(), FileOutput(self.output))
        
        server_thread = Thread(target=self.server.serve_forever)
        server_thread.start()

        # Display the streaming address
        host_ip = self.get_host_ip()
        print(f"Picamera2 streamer started. Stream at: http://{host_ip}:{self.address[1]}")
        print("Press Ctrl-C to stop.")

    def stop(self):
        self.picam2.stop_recording()
        self.server.shutdown()
        self.server.server_close()
        print("Picamera2 streamer stopped.")


def main():
    custom_port = 8080
    custom_min_size = (1000, 1000)
    custom_fps = 15
    camera_streamer = Picamera2Streamer(output_port=custom_port, min_size=custom_min_size, frame_rate=custom_fps)

    camera_streamer.start()
    try:
        signal.pause()
    except KeyboardInterrupt:
        print("Stopping Picamera2 streamer...")
    finally:
        camera_streamer.stop()

if __name__ == "__main__":
    main()

