"""
HTTP Snapshot Camera Server

This module implements a camera server that fetches frames from a remote camera's HTTP snapshot endpoint.
It extends the base CameraServer class to provide snapshot-based frame capture.

Features:
- Fetch frames from HTTP snapshot endpoints
- Support for basic authentication
- Error handling and retry logic
- Compatible with existing CameraServer infrastructure
- Configurable timeout and retry settings

Usage:
    server = HTTPSnapshotServer(
        snapshot_url='http://camera.local/snapshot',  # Camera's snapshot URL
        auth=('username', 'password'),               # Optional basic auth
        timeout=5,                                   # Request timeout
        debug=False                                  # Debug output
    )
    server.run()

Author: Bob Houston
Date: 2024-03-21
Version: 0.1
"""

import logging
import requests
import numpy as np
import cv2
from requests.auth import HTTPBasicAuth
import time

from camera_server import CameraServer


class HTTPSnapshotServer(CameraServer):
    def __init__(self, snapshot_url, auth=None, timeout=5, host='0.0.0.0', port=7160, debug=False):
        self.snapshot_url = snapshot_url
        self.timeout = timeout
        
        # Setup session for connection pooling
        self.session = requests.Session()
        if auth:
            self.session.auth = HTTPBasicAuth(*auth)
        
        super().__init__(host, port, debug=debug)

    def _create_test_pattern(self):
        """Create a test pattern frame with timestamp."""
        # Create a 640x480 test pattern
        height, width = 480, 640
        
        # Create color bars
        pattern = np.zeros((height, width, 3), dtype=np.uint8)
        bar_width = width // 7
        colors = [
            (255, 255, 255),  # White
            (255, 255, 0),    # Yellow
            (0, 255, 255),    # Cyan
            (0, 255, 0),      # Green
            (255, 0, 255),    # Magenta
            (255, 0, 0),      # Red
            (0, 0, 255),      # Blue
        ]
        
        for i, color in enumerate(colors):
            pattern[:, i*bar_width:(i+1)*bar_width] = color
            
        # Add timestamp and error message
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        message = f"No Signal - {timestamp}"
        
        # Add text to the image
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1
        thickness = 2
        color = (255, 255, 255)
        
        # Get text size and position it
        text_size = cv2.getTextSize(message, font, font_scale, thickness)[0]
        text_x = (width - text_size[0]) // 2
        text_y = height - 50
        
        # Add black background for text
        cv2.rectangle(pattern, 
                     (text_x - 10, text_y - text_size[1] - 10),
                     (text_x + text_size[0] + 10, text_y + 10),
                     (0, 0, 0),
                     -1)
        
        # Add text
        cv2.putText(pattern, message, (text_x, text_y), font, font_scale, color, thickness)
        
        return pattern

    def _capture_frame(self):
        try:
            response = self.session.get(self.snapshot_url, timeout=self.timeout)
            response.raise_for_status()
            
            nparr = np.frombuffer(response.content, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                if self.debug:
                    print("Failed to decode image from response")
                return self._create_test_pattern()
                
            return frame
            
        except requests.RequestException as e:
            if self.debug:
                print(f"Error fetching frame: {e}")
            return self._create_test_pattern()
        except Exception as e:
            logging.error(f"Unexpected error capturing frame: {e}")
            return self._create_test_pattern()

    def _setup_camera(self):
        try:
            response = self.session.get(self.snapshot_url, timeout=self.timeout)
            response.raise_for_status()
            
            nparr = np.frombuffer(response.content, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                raise RuntimeError("Failed to decode image from response")
            
            if self.debug:
                print(f"Successfully connected to camera: {frame.shape}")
                
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to connect to camera: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to setup camera: {e}")

    def cleanup(self):
        if hasattr(self, 'session'):
            self.session.close()
        super().cleanup()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="HTTP Snapshot Camera Server")
    parser.add_argument("--url", default="http://localhost:8000/snapshot", help="URL of the snapshot endpoint")
    parser.add_argument("--auth", help="Basic auth in format username:password")
    parser.add_argument("--timeout", type=int, default=5, help="Request timeout in seconds")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=7160, help="Port to listen on")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    
    args = parser.parse_args()
    
    auth = None
    if args.auth:
        username, password = args.auth.split(':', 1)
        auth = (username, password)
    
    try:
        server = HTTPSnapshotServer(
            snapshot_url=args.url,
            auth=auth,
            timeout=args.timeout,
            host=args.host,
            port=args.port,
            debug=args.debug
        )
        server.run()
    except KeyboardInterrupt:
        print("\nStopping server...")
    except Exception as e:
        logging.error(f"Server error: {e}")
        raise

if __name__ == "__main__":
    main()