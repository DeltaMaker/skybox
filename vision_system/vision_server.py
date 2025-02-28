"""
VisionServer - Vision processing server for HTTP snapshot cameras.
Provides frame processing and client handling with marker and hand tracking.
"""

import json
import logging
import time
import asyncio
import cv2
import numpy as np
import requests
from marker_tracker import MarkerTracker
from hand_tracker import HandTracker
from simple_server import SimpleWebsocketServer


class VisionServer(SimpleWebsocketServer):
    def __init__(self, snapshot_url, auth=None, timeout=5, host='0.0.0.0', port=7160, debug=False):
        """Initialize the vision server."""
        self.snapshot_url = snapshot_url
        self.timeout = timeout
        self.session = requests.Session()
        if auth:
            self.session.auth = auth
        
        self.marker_tracker = MarkerTracker()
        self.hand_tracker = HandTracker()
        self.frame_count = 0
        self.last_fps_print = time.time()
        
        super().__init__(host, port, debug)
        self._initialize_camera()

    def _initialize_camera(self):
        """Initialize connection to snapshot server."""
        try:
            if self.debug:
                print(f"Initializing {self.__class__.__name__}...")
            self._setup_camera()
            if self.debug:
                print(f"{self.__class__.__name__} initialization successful")
        except Exception as e:
            logging.error(f"Failed to initialize {self.__class__.__name__}: {e}")
            raise

    def _setup_camera(self):
        """Test connection to snapshot server."""
        try:
            frame = self.get_current_frame()
            if frame is None:
                raise RuntimeError("Failed to get initial frame")
            self.base_size = frame.shape[1], frame.shape[0]  # width, height
            if self.debug:
                print(f"Connected to snapshot source. Resolution: {self.base_size}")
        except Exception as e:
            raise RuntimeError(f"Failed to connect to snapshot source: {e}")

    def get_current_frame(self):
        """Capture current frame from HTTP snapshot."""
        try:
            response = self.session.get(self.snapshot_url, timeout=self.timeout)
            response.raise_for_status()
            
            nparr = np.frombuffer(response.content, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                raise ValueError("Failed to decode image from response")
            return frame
            
        except Exception as e:
            logging.error(f"Error capturing frame: {e}")
            return None

    async def get_broadcast_data(self):
        """Get the current frame and process it."""
        if self.clients:
            fastest_fps = max(client.get('fps', 1) for client in self.clients.values())
            target_interval = 1 / fastest_fps
            
            if self.debug:
                self._update_fps_stats()
            
            await asyncio.sleep(target_interval)
        
        frame = self.get_current_frame()
        if frame is not None:
            return {
                'frame': frame,
                'timestamp': time.time()
            }
        return None

    def _update_fps_stats(self):
        """Update and print FPS statistics."""
        self.frame_count += 1
        current_time = time.time()
        
        if current_time - self.last_fps_print >= 1.0:
            self.actual_fps = self.frame_count / (current_time - self.last_fps_print)
            fastest_fps = max(client.get('fps', 1) for client in self.clients.values())
            
            if self.debug:
                print(f"Target FPS: {fastest_fps:.1f}, Actual FPS: {self.actual_fps:.1f}")
            
            self.frame_count = 0
            self.last_fps_print = current_time

    def extract_client_info(self, config):
        """Extract client configuration."""
        client_info = {
            'fps': config.get('fps', 15),
            'mirror': config.get('mirror', False),
            'send_frames': False,
            'send_hands': False,
            'send_markers': False
        }
        
        # Check if client wants frames (indicated by width or size)
        if 'width' in config or 'size' in config:
            width = config.get('width', config.get('size', [640])[0])
            aspect_ratio = self.base_size[1] / self.base_size[0] if self.base_size else 0.75
            client_info.update({
                'size': (width, int(width * aspect_ratio)),
                'send_frames': True
            })
        
        # Check for vision data subscriptions
        if config.get('hands', False):
            client_info['send_hands'] = True
            
        if config.get('markers', False):
            client_info['send_markers'] = True
            
        return client_info

    async def format_client_message(self, message_data, client_info):
        """Format the frame and data for a specific client."""
        data = {"timestamp": message_data['timestamp']}
        frame_bytes = None  # Initialize as None
        
        if client_info['send_frames']:  # Only process frames if client requested them
            frame = message_data['frame']
            
            # Handle square cropping if requested
            if client_info.get('square', []):
                height, width = frame.shape[:2]
                size = min(width, height)
                
                # Calculate crop coordinates for center square
                start_x = (width - size) // 2
                start_y = (height - size) // 2
                frame = frame[start_y:start_y+size, start_x:start_x+size]
            
            # Resize after cropping
            resized_frame = cv2.resize(frame, client_info['size'])
            
            if client_info['mirror']:
                resized_frame = cv2.flip(resized_frame, 1)
                
            if client_info['send_markers']:
                marker_data = self.marker_tracker.process_frame(resized_frame)
                data["markers"] = marker_data
                
            if client_info['send_hands']:
                hand_data = self.hand_tracker.process_frame(resized_frame)
                data["hands"] = hand_data
                
            _, encoded_frame = cv2.imencode('.jpg', resized_frame)
            frame_bytes = encoded_frame.tobytes()
        else:
            # Process original frame if only vision data is requested
            if client_info['send_markers']:
                marker_data = self.marker_tracker.process_frame(message_data['frame'])
                data["markers"] = marker_data
                
            if client_info['send_hands']:
                hand_data = self.hand_tracker.process_frame(message_data['frame'])
                data["hands"] = hand_data

        return {
            'data': data,
            'frame_bytes': frame_bytes
        }

    async def send_to_client(self, client_ws, message):
        """Send the formatted message to the client."""
        if not client_ws.closed:
            await client_ws.send_str(json.dumps(message['data']))
            if message['frame_bytes'] is not None:  # Only send frame bytes if they exist
                await client_ws.send_bytes(message['frame_bytes'])

    def cleanup(self):
        """Clean up resources."""
        if hasattr(self, 'session'):
            self.session.close()

    def get_status_info(self):
        """Get server status information."""
        status = super().get_status_info()
        target_fps = max((client.get('fps', 1) for client in self.clients.values()), default=0)
        
        # Add vision-specific status info
        status.update({
            'snapshot_url': self.snapshot_url,
            'base_resolution': f"{self.base_size[0]}x{self.base_size[1]}",
            'clients': len(self.clients),
            'target_fps': target_fps,
            'actual_fps': round(getattr(self, 'actual_fps', 0), 1),
            'markers_enabled': True,
            'hands_enabled': True
        })
        
        return status


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Vision Server for HTTP snapshot cameras")
    parser.add_argument("--url", default="http://deltamaker-0409.local/webcam/?action=snapshot", help="URL of the snapshot endpoint")
    parser.add_argument("--auth", help="Basic auth in format username:password")
    parser.add_argument("--timeout", type=int, default=5, help="Request timeout in seconds")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=7160, help="Port to listen on")
    parser.add_argument("--debug", action="store_false", help="Enable debug output")
    
    args = parser.parse_args()
    
    auth = None
    if args.auth:
        username, password = args.auth.split(':', 1)
        auth = (username, password)
    
    try:
        print(f"\nStarting Vision Server")
        print(f"Snapshot URL: {args.url}")
        print(f"Server port: {args.port}")
        print("Press Ctrl-C to stop.")
        
        server = VisionServer(
            snapshot_url=args.url,
            auth=auth,
            timeout=args.timeout,
            host=args.host,
            port=args.port,
            debug=args.debug
        )
        server.run()
    except KeyboardInterrupt:
        print("\nStopping Vision Server...")
    except Exception as e:
        logging.error(f"Server error: {e}")
        raise

if __name__ == "__main__":
    main() 