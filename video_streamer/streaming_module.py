"""
MJPEG Streaming Server

This script implements a basic MJPEG streaming server capable of serving live video feeds over HTTP. It is designed to work with a variety of video capture sources by providing frames to the StreamingOutput class, which are then streamed to connected clients through HTTP. The server streams the video using the MJPEG format, allowing for real-time viewing in web browsers or video clients that support the MJPEG content type.

Features:
- Implements an MJPEG streaming server using standard Python libraries.
- Utilizes threading to handle multiple simultaneous client connections without blocking the main video capture process.
- Supports dynamic frame updates from a video capture source, streaming the latest frame to all connected clients.

Components:
- StreamingOutput: A class that holds the latest video frame to be streamed. It uses threading conditions to synchronize frame updates with streaming requests.
- StreamingHandler: A subclass of BaseHTTPRequestHandler for handling HTTP requests. It streams the video frames as a multipart/x-mixed-replace response, suitable for real-time video streaming in web browsers.
- StreamingServer: A class combining ThreadingMixIn with HTTPServer to serve video streams in a multi-threaded manner, allowing multiple clients to connect simultaneously.

Usage:
To use this MJPEG streaming server, integrate it with a video capture source by periodically updating the frame in the StreamingOutput instance. Start the server, and clients can connect to the specified address and port to view the live video feed. The server runs indefinitely until manually stopped, gracefully handling shutdown requests to release resources properly.

Note:
This script requires Python 3 and has been tested on Linux-based systems. Adaptations may be necessary for other environments or specific video capture requirements.

Author: Bob Houston
Date: 2024-3-21
Version: 0.1
"""

import io
import logging
import signal
import socketserver
from http import server
from threading import Condition, Thread

class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

    def update_frame(self, frame):
        self.write(frame.tobytes())

class StreamingHandler(server.BaseHTTPRequestHandler):
    output = None

    def do_GET(self):
        self.send_response(200)
        self.send_header('Age', 0)
        self.send_header('Cache-Control', 'no-cache, private')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
        self.end_headers()
        try:
            while True:
                with StreamingHandler.output.condition:
                    StreamingHandler.output.condition.wait()
                    frame = StreamingHandler.output.frame
                self.wfile.write(b'--FRAME\r\n')
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', len(frame))
                self.end_headers()
                self.wfile.write(frame)
                self.wfile.write(b'\r\n')
        except Exception as e:
            logging.warning('Removed streaming client %s: %s', self.client_address, str(e))

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True
