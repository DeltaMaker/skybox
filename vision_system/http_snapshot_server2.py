#!/usr/bin/env python3
"""
Simple HTTP Snapshot Server
==========================

A lightweight HTTP server that serves single camera frames as JPEG images.
It captures frames on-demand when the snapshot endpoint is accessed.

Usage:
------
1. Run the server:
   ```bash
   python http_snapshot_server.py --port 9000 --camera 0
   ```

2. Access snapshot:
   ```
   http://localhost:9000/snapshot
   ```

3. Resize image with query parameters:
   ```
   http://localhost:9000/snapshot?w=640&h=480  # Specific dimensions
   http://localhost:9000/snapshot?w=800        # Width only (height auto-calculated)
   http://localhost:9000/snapshot?h=600        # Height only (width auto-calculated)
   ```

Dependencies:
------------
- OpenCV (cv2)
- http.server (standard library)
"""

import os
import sys
import cv2
import time
import json
import argparse
from http import server
import socketserver
from threading import Thread, Lock
from urllib.parse import urlparse, parse_qs

# Add parent directory to path if running as script
if __name__ == "__main__":
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class CameraHandler:
    """Handles camera operations and frame capture."""
    
    def __init__(self, camera_id=0):
        self.camera_id = camera_id
        self.camera = None
        self.lock = Lock()
        self.last_access = time.time()
        
    def get_frame(self):
        """Capture a frame from the camera."""
        with self.lock:
            # Initialize camera if not done already
            if self.camera is None or not self.camera.isOpened():
                self.camera = cv2.VideoCapture(self.camera_id)
                if not self.camera.isOpened():
                    raise ValueError(f"Failed to open camera {self.camera_id}")
                    
            # Update last access time
            self.last_access = time.time()
            
            # Capture frame
            ret, frame = self.camera.read()
            if not ret:
                raise ValueError("Failed to capture frame")
                
            return frame
    
    def release(self):
        """Release the camera."""
        with self.lock:
            if self.camera is not None:
                self.camera.release()
                self.camera = None


class SnapshotHandler(server.BaseHTTPRequestHandler):
    """HTTP request handler for camera snapshot server."""
    
    def __init__(self, *args, camera_handler=None, **kwargs):
        self.camera_handler = camera_handler
        # Call the parent class constructor
        # This is done in a special way because of how BaseHTTPRequestHandler works
        server.BaseHTTPRequestHandler.__init__(self, *args, **kwargs)
    
    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        if path == '/snapshot':
            # Parse query parameters
            query = parse_qs(parsed_path.query)
            self.serve_snapshot(query)
        elif path == '/status':
            self.serve_status()
        else:
            self.serve_404()
    
    def serve_snapshot(self, query=None):
        """Serve a snapshot from the camera with optional resizing.
        
        Query parameters:
            w: Width of the image to return
            h: Height of the image to return
            
        If only one dimension is provided, the other will be calculated
        to maintain the original aspect ratio.
        """
        try:
            # Capture frame
            frame = self.camera_handler.get_frame()
            original_h, original_w = frame.shape[:2]
            
            # Process resize parameters if provided
            if query:
                # Get width parameter (if provided)
                if 'w' in query and query['w'][0].isdigit():
                    target_w = int(query['w'][0])
                else:
                    target_w = None
                
                # Get height parameter (if provided)
                if 'h' in query and query['h'][0].isdigit():
                    target_h = int(query['h'][0])
                else:
                    target_h = None
                
                # Resize the image if dimensions are specified
                if target_w or target_h:
                    # Calculate the missing dimension to maintain aspect ratio
                    if target_w and not target_h:
                        # Calculate height to maintain aspect ratio
                        aspect_ratio = original_h / original_w
                        target_h = int(target_w * aspect_ratio)
                    elif target_h and not target_w:
                        # Calculate width to maintain aspect ratio
                        aspect_ratio = original_w / original_h
                        target_w = int(target_h * aspect_ratio)
                    
                    # Resize the frame
                    frame = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
            
            # Convert to JPEG
            _, img_encoded = cv2.imencode('.jpg', frame)
            img_bytes = img_encoded.tobytes()
            
            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', str(len(img_bytes)))
            self.end_headers()
            self.wfile.write(img_bytes)
            
        except Exception as e:
            self.send_error(500, str(e))
    
    def serve_status(self):
        """Serve server status information."""
        try:
            # Get current frame dimensions
            frame = self.camera_handler.get_frame()
            height, width = frame.shape[:2]
            frame_info = {
                'width': width,
                'height': height,
                'aspect_ratio': round(width / height, 3)
            }
        except Exception:
            frame_info = {"error": "Could not get frame dimensions"}
        
        status = {
            'server': 'HTTP Snapshot Server',
            'camera_id': self.camera_handler.camera_id,
            'timestamp': time.time(),
            'uptime': time.time() - server_start_time,
            'frame': frame_info
        }
        
        # Convert to JSON and send
        response = json.dumps(status).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)
    
    def serve_404(self):
        """Serve 404 Not Found response."""
        self.send_error(404, 'Not Found')
        
    def log_message(self, format, *args):
        """Override log_message to provide custom logging."""
        print(f"{self.client_address[0]} - {args[0]}")


def create_handler_class(camera_handler):
    """Create a handler class with the camera_handler already set."""
    
    class CustomSnapshotHandler(SnapshotHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, camera_handler=camera_handler, **kwargs)
    
    return CustomSnapshotHandler


def cleanup_thread(camera_handler, interval=60, max_idle=300):
    """Thread that cleans up the camera if idle for too long."""
    while True:
        time.sleep(interval)
        idle_time = time.time() - camera_handler.last_access
        if idle_time > max_idle and camera_handler.camera is not None:
            print(f"Camera idle for {idle_time:.1f} seconds, releasing resources.")
            camera_handler.release()


def main():
    """Run the HTTP snapshot server."""
    global server_start_time
    server_start_time = time.time()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="HTTP Camera Snapshot Server")
    parser.add_argument('--port', type=int, default=9000, 
                        help='Port to listen on (default: 9000)')
    parser.add_argument('--camera', type=int, default=0,
                        help='Camera ID to use (default: 0)')
    parser.add_argument('--host', type=str, default='0.0.0.0',
                        help='Host to bind to (default: 0.0.0.0)')
    args = parser.parse_args()
    
    # Initialize camera handler
    camera_handler = CameraHandler(args.camera)
    
    # Create handler class with the camera handler
    handler_class = create_handler_class(camera_handler)
    
    # Start cleanup thread
    cleanup = Thread(target=cleanup_thread, args=(camera_handler,), daemon=True)
    cleanup.start()
    
    # Start HTTP server
    try:
        with socketserver.TCPServer((args.host, args.port), handler_class) as httpd:
            print(f"HTTP Snapshot Server started at http://{args.host}:{args.port}")
            print(f"Access snapshot at: http://{args.host}:{args.port}/snapshot")
            print(f"Access status at: http://{args.host}:{args.port}/status")
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
    except Exception as e:
        print(f"Server error: {e}")
    finally:
        # Clean up resources
        camera_handler.release()


if __name__ == "__main__":
    main()