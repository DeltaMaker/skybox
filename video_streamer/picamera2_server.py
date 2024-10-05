"""
Picamera2 Server for MJPEG Streaming

This Python script sets up a server that streams video from a Raspberry Pi camera using the MJPEG format, utilizing the Picamera2 library for accessing camera hardware. This approach leverages hardware acceleration available on Raspberry Pi for efficient video encoding and streaming, providing a robust solution for real-time video streaming applications.

Features:
- Streams MJPEG video directly from the Raspberry Pi camera to connected clients, supporting real-time video applications.
- Does not require a specific path for the video stream, allowing clients to connect directly to the server's root URL for ease of access.
- Offers configurable server address and video frame size, enabling flexibility in deployment scenarios and streaming quality according to network conditions and requirements.
- Implements graceful shutdown handling to ensure that resources are properly released when the server is stopped, preventing potential resource leaks or hardware issues.

Usage:
- To start the server, run this script. It will automatically begin streaming video from the connected Raspberry Pi camera.
- Clients can access the video stream by connecting to the server's URL at the specified port. The stream is accessible directly from the server's root URL.
- To stop the server and release camera resources cleanly, press Ctrl-C.

Requirements:
- The script requires the Picamera2 library and its dependencies to be installed on the Raspberry Pi. Ensure that your system is compatible and that the necessary library versions are installed.
- A compatible Raspberry Pi camera module must be connected to the Raspberry Pi and enabled in the Raspberry Pi configuration settings.

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

from video_streamer.streaming_module import StreamingOutput, StreamingHandler, StreamingServer


class Picamera2Server:
    def __init__(self, output_port=8000, size=(1280, 720), frame_rate=10):
        self.address = ('', output_port)
        self.size = size
        self.frame_rate = frame_rate
        self.picam2 = Picamera2()
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
            main={"size": self.size}, controls={'FrameRate': self.frame_rate})
        self.picam2.configure(video_config)
        self.picam2.start_recording(MJPEGEncoder(), FileOutput(self.output))
        server_thread = Thread(target=self.server.serve_forever)
        server_thread.start()

        # Display the streaming address
        host_ip = self.get_host_ip()
        print(f"Picamera2 server started. Stream at: http://{host_ip}:{self.address[1]}")
        print("Press Ctrl-C to stop.")

    def stop(self):
        self.picam2.stop_recording()
        self.server.shutdown()
        self.server.server_close()
        print("Picamera2 server stopped.")


def main():
    custom_port = 8000    # Example custom port
    custom_size = (640, 480)  # HD resolution specified using the 'size' parameter
    custom_fps = 30
    camera_server = Picamera2Server(output_port=custom_port,  size=custom_size, frame_rate=custom_fps)
    try:
        camera_server.start()
        signal.pause()
    except KeyboardInterrupt:
        print("Stopping Picamera2 server...")
    finally:
        camera_server.stop()

if __name__ == "__main__":
    main()

