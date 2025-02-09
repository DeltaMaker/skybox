"""
MJPEG Streaming Module

This module provides the core components for MJPEG streaming over HTTP, designed to be used by various camera implementations. It handles the streaming server infrastructure, allowing camera-specific implementations to focus on frame capture and processing.

Components:
- StreamingOutput: Manages frame buffer with thread-safe access
- StreamingHandler: HTTP request handler supporting both streaming and snapshot endpoints
- StreamingServer: Multi-threaded HTTP server for handling multiple client connections

Features:
- Thread-safe frame buffer management
- MJPEG streaming over HTTP
- Single frame snapshot endpoint (/snapshot)
- Support for multiple simultaneous clients
- No-cache headers for real-time viewing

Usage:
1. Create a StreamingOutput instance for frame buffer
2. Configure StreamingHandler with the output
3. Initialize StreamingServer with handler
4. Start server to begin streaming

Example:
    output = StreamingOutput()
    StreamingHandler.output = output
    server = StreamingServer((host, port), StreamingHandler)
    server.serve_forever()

Author: Bob Houston
Date: 2024-03-21
Version: 0.2
"""

import io
import logging
import socketserver
from http import server
from threading import Condition

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

    def log_message(self, format, *args):
        """Disable HTTP server logging."""
        pass

    def do_GET(self):
        if self.path == '/snapshot':
            self.serve_snapshot()
        else:
            self.serve_stream()

    def serve_snapshot(self):
        """Serve a single frame as a JPEG image."""
        try:
            with StreamingHandler.output.condition:
                if StreamingHandler.output.frame is None:
                    self.send_error(404)
                    return
                frame = StreamingHandler.output.frame
            
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', len(frame))
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, pre-check=0, post-check=0, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.end_headers()
            self.wfile.write(frame)
            
        except Exception as e:
            logging.warning('Snapshot client error %s: %s', self.client_address, str(e))
            self.send_error(500)

    def serve_stream(self):
        """Serve MJPEG stream."""
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
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            # Client disconnected, no need to log
            pass
        except Exception as e:
            # Log unexpected errors
            logging.error(f'Streaming error: {str(e)}')

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True
