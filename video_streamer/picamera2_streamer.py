"""
Picamera2 Vision System Server

This module implements a camera streamer specifically for Raspberry Pi cameras using the Picamera2 library. It provides dynamic resolution adjustment based on client requirements while maintaining optimal performance.

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
        host='0.0.0.0',           # Bind to all interfaces
        port=7160,                # Server port
        min_size=(1400, 900),     # Minimum resolution
        debug=False               # Debug output
    )
    streamer.run()

Author: Bob Houston
Date: 2024-03-21
Version: 0.2
"""

import signal
import socket
from threading import Thread
from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput

from streaming_module import StreamingOutput, StreamingHandler, StreamingServer


class Picamera2Streamer:
    def __init__(self, output_port=8000, size=(1280, 720), frame_rate=10):
        self.address = ('', output_port)
        self.size = size
        self.frame_rate = frame_rate
        self.picam2 = Picamera2()
        self.camera_modes = self.picam2.sensor_modes
        
        # Find valid modes
        valid_modes = [m for m in self.camera_modes 
                      if m['size'][0] >= size[0] and m['size'][1] >= size[1]]
        if not valid_modes:
            raise RuntimeError(f"No available camera modes larger than {size[0]}x{size[1]}")
        
        # Get best mode and its properties
        best_mode = min(valid_modes, key=lambda m: m['size'][0] * m['size'][1])
        self.base_size = best_mode["size"]
        self.camera_format = best_mode.get("unpacked_format", "XBGR8888")

        self.output = StreamingOutput()
        StreamingHandler.output = self.output
        self.server = StreamingServer(self.address, StreamingHandler)

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
        video_config = self.picam2.create_video_configuration(
            main={"size": self.base_size}, controls={'FrameRate': self.frame_rate})
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
    custom_port = 8000    # Example custom port
    custom_size = (640, 480)  # HD resolution specified using the 'size' parameter
    custom_fps = 30
    camera_streamer = Picamera2Streamer(output_port=custom_port, size=custom_size, frame_rate=custom_fps)
    try:
        camera_streamer.start()
        signal.pause()
    except KeyboardInterrupt:
        print("Stopping Picamera2 streamer...")
    finally:
        camera_streamer.stop()

if __name__ == "__main__":
    main()

