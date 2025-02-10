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
import json
import time

class StreamingOutput(io.BufferedIOBase):
    """Streaming output buffer."""
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        """Write frame to buffer."""
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

class StreamingHandler(server.BaseHTTPRequestHandler):
    output = None
    # Class-level configuration
    camera_config = None  # Will be set by picamera2_streamer
    
    # Class-level FPS tracking
    stream_count = 0
    last_stream_time = time.time()
    stream_fps = 0
    
    # Snapshot FPS with 5-second window
    snapshot_window = 5  # seconds
    snapshot_count = 0
    last_snapshot_reset = time.time()
    client_snapshots = {}  # {client_addr: {'count': 0, 'fps': 0}}

    @classmethod
    def update_stream_fps(cls):
        """Update streaming FPS calculation."""
        cls.stream_count += 1
        current_time = time.time()
        time_diff = current_time - cls.last_stream_time
        
        if time_diff >= 1.0:
            cls.stream_fps = cls.stream_count / time_diff
            cls.stream_count = 0
            cls.last_stream_time = current_time

    @classmethod
    def update_snapshot_fps(cls, client_address):
        """Update snapshot FPS over 5-second window."""
        current_time = time.time()
        
        # Initialize or update client stats
        if client_address not in cls.client_snapshots:
            cls.client_snapshots[client_address] = {'count': 0, 'fps': 0}
        cls.client_snapshots[client_address]['count'] += 1
        
        # Reset counters every 5 seconds
        if current_time - cls.last_snapshot_reset >= cls.snapshot_window:
            # Update per-client FPS
            for client in cls.client_snapshots:
                cls.client_snapshots[client]['fps'] = cls.client_snapshots[client]['count'] / cls.snapshot_window
                cls.client_snapshots[client]['count'] = 0
            
            cls.last_snapshot_reset = current_time

    def log_message(self, format, *args):
        """Disable HTTP server logging."""
        pass

    def do_GET(self):
        """Handle GET requests for stream, snapshot, or status."""
        if 'snapshot' in self.path.lower():
            self.serve_snapshot()
        elif 'status' in self.path.lower():
            self.serve_status()
        else:
            self.serve_stream()

    def serve_status(self):
        """Serve status information as JSON."""
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.end_headers()
            
            # Calculate all stats from current counts
            current_time = time.time()
            window_time = min(current_time - self.last_snapshot_reset, self.snapshot_window)
            
            # Calculate FPS from current counts
            client_fps = []
            for stats in self.client_snapshots.values():
                fps = stats['count'] / window_time
                client_fps.append(fps)
            
            max_client_fps = max(client_fps) if client_fps else 0
            avg_client_fps = sum(client_fps) / len(client_fps) if client_fps else 0
            
            status = {
                'size': f"{self.camera_config['size'][0]}x{self.camera_config['size'][1]}",
                'stream_fps': round(self.stream_fps, 1),
                'snapshot_fps': {
                    'max_client': round(max_client_fps, 1),
                    'avg_client': round(avg_client_fps, 1),
                    'clients': len(self.client_snapshots)
                },
                'format': self.camera_config['format'],
                'target_fps': self.camera_config['frame_rate']
            }
            self.wfile.write(json.dumps(status).encode('utf-8'))
            
        except Exception as e:
            logging.error(f'Status endpoint error: {str(e)}')
            self.send_error(500)

    def serve_snapshot(self):
        """Serve a single frame as a JPEG image."""
        try:
            with StreamingHandler.output.condition:
                if StreamingHandler.output.frame is None:
                    self.send_error(404)
                    return
                frame = StreamingHandler.output.frame
            
            # Update snapshot FPS tracking with client address
            self.update_snapshot_fps(self.client_address[0])
            
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', len(frame))
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
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
                    
                # Update FPS after getting each frame
                self.update_stream_fps()
                
                self.wfile.write(b'--FRAME\r\n')
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', len(frame))
                self.end_headers()
                self.wfile.write(frame)
                self.wfile.write(b'\r\n')
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass
        except Exception as e:
            logging.error(f'Streaming error: {str(e)}')

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    
    @classmethod
    def create(cls, host='', start_port=8000, end_port=None):
        """Create server with automatic port assignment.
        
        Args:
            host (str): Host address to bind to
            start_port (int): Starting port number
            end_port (int, optional): Ending port number (inclusive). 
                                    If None, will only try start_port
            
        Returns:
            tuple: (server, port) - The created server and port it's using
            
        Raises:
            RuntimeError: If no ports are available in the range
        """
        if end_port is None:
            end_port = start_port
            
        for port in range(start_port, end_port + 1):
            try:
                server = cls((host, port), StreamingHandler)
                print(f"Streaming server started on port {port}")
                return server, port
            except OSError as e:
                if e.errno == 48:  # Address already in use
                    print(f"Port {port} is busy, trying {port + 1}...")
                    continue
                raise  # Re-raise other OSErrors
        
        raise RuntimeError(f"Could not find available port in range {start_port}-{end_port}")