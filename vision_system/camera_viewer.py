"""
CameraViewer - WebSocket client for displaying camera streams and vision results.

This viewer implementation provides:
- Real-time display of camera frames
- Visualization of computer vision results
    - ArUco marker overlays
    - Hand tracking visualization
- Support for different stream configurations
    - Custom resolution
    - Frame rate control
    - Mirror mode
    - Vision processing toggles
- Clean shutdown handling

The viewer uses composition with SimpleWebsocketClient to:
- Handle WebSocket communication
- Process binary frame data
- Parse JSON vision metadata
- Display frames with OpenCV

Usage:
    python camera_viewer.py [--ws_uri WS_URI] [--width WIDTH] [--height HEIGHT] 
                          [--fps FPS] [--mirror] [--hands] [--debug]

Pairs with camera_server.py for receiving the camera stream and vision results.
"""
import os
import sys
# Add the parent directory to sys.path if running as script
if __name__ == "__main__":
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import websockets
import json
import cv2
import numpy as np
import argparse
from websocket_server.simple_client import SimpleWebsocketClient


class CameraViewer:
    def __init__(self, debug: bool = False):
        """Initialize the CameraViewer with optional debug flag."""
        self.markers = []
        self.hands = []
        self.debug = debug

    def draw_markers(self, frame, markers):
        """Draw detected markers on the frame.
        
        Args:
            frame: OpenCV image to draw on
            markers: List of marker data with normalized coordinates (0-1)
            
        Returns:
            Frame with markers drawn
        """
        if not markers:
            return frame
        
        height, width = frame.shape[:2]
        
        for marker in markers:
            # Convert normalized coordinates back to pixel coordinates
            corners_norm = np.array(marker['corners']).reshape(4, 2)
            corners = np.zeros_like(corners_norm)
            corners[:, 0] = corners_norm[:, 0] * width  # x coordinates
            corners[:, 1] = corners_norm[:, 1] * height  # y coordinates
            corners = corners.astype(np.int32)
            marker_id = str(marker.get('id', '-'))
            self.draw_marker_polygon(frame, corners, marker_id)

        return frame

    def draw_marker_polygon(self, frame, corners, marker_id):
        """
        Draw a marker polygon with white fill, red outline, and ID text scaled to fit inside.
        
        Parameters:
            frame: The image to draw on
            corners: Array of corner points
            marker_id: ID number to display inside the polygon
        """
        # Reshape corners for OpenCV functions
        corners_array = corners.reshape(-1, 1, 2).astype(np.int32)
        
        # Fill polygon with white
        cv2.fillPoly(frame, [corners_array], color=(255, 255, 255))
        
        # Add thin red outline
        cv2.polylines(frame, 
                    [corners_array],
                    isClosed=True,
                    color=(0, 0, 0),  # Black color
                    thickness=1)         # Thin line
    
        # Calculate center of polygon
        center_x = int(np.mean(corners[:, 0]))
        center_y = int(np.mean(corners[:, 1]))
        
        # Calculate polygon size to scale text
        x_min = np.min(corners[:, 0])
        y_min = np.min(corners[:, 1])
        x_max = np.max(corners[:, 0])
        y_max = np.max(corners[:, 1])
        
        polygon_width = x_max - x_min
        polygon_height = y_max - y_min
        
        # Determine font scale based on polygon size
        font = cv2.FONT_HERSHEY_SIMPLEX
        id_text = str(marker_id)
        font_scale = min(polygon_width, polygon_height) / (40 * max(1, len(id_text)))
        font_scale = max(0.3, min(font_scale, 2.0))  # Limit scale between 0.3 and 2.0
        
        # Get text size
        text_size, _ = cv2.getTextSize(id_text, font, font_scale, 1)
        text_x = center_x - text_size[0] // 2  # Center text horizontally
        text_y = center_y + text_size[1] // 2   # Center text vertically
        
        # Draw text in black
        cv2.putText(frame, id_text, (text_x, text_y), font, font_scale, (0, 0, 255), 1, cv2.LINE_AA)


    def draw_hands(self, frame, hands):
        """Draw detected hand landmarks on the frame."""
        if not hands:
            return frame
        
        COLORS = [(0, 255, 0), (255, 0, 0)]
        
        HAND_CONNECTIONS = [
            (0, 1), (1, 2), (2, 3), (3, 4),
            (0, 5), (5, 6), (6, 7), (7, 8),
            (0, 9), (9, 10), (10, 11), (11, 12),
            (0, 13), (13, 14), (14, 15), (15, 16),
            (0, 17), (17, 18), (18, 19), (19, 20),
            (0, 5), (5, 9), (9, 13), (13, 17)
        ]
        
        for hand_idx, hand_landmarks in enumerate(hands):
            color = COLORS[hand_idx % len(COLORS)]
            
            h, w = frame.shape[:2]
            for connection in HAND_CONNECTIONS:
                start_idx, end_idx = connection
                if start_idx < len(hand_landmarks) and end_idx < len(hand_landmarks):
                    start_point = (
                        int(hand_landmarks[start_idx]['x'] * w),
                        int(hand_landmarks[start_idx]['y'] * h)
                    )
                    end_point = (
                        int(hand_landmarks[end_idx]['x'] * w),
                        int(hand_landmarks[end_idx]['y'] * h)
                    )
                    cv2.line(frame, start_point, end_point, color, 1)
            
            for landmark in hand_landmarks:
                px = int(landmark['x'] * w)
                py = int(landmark['y'] * h)
                cv2.circle(frame, (px, py), 3, color, -1)
                
        return frame

    def draw_dimensions(self, frame):
        """Draw the frame dimensions on the image."""
        height, width = frame.shape[:2]
        dimensions_text = f"{width}x{height}"
        
        # Draw text with dark background for better visibility
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        thickness = 2
        text_size = cv2.getTextSize(dimensions_text, font, font_scale, thickness)[0]
        
        # Position in top-left corner with padding
        padding = 10
        text_x = padding
        text_y = text_size[1] + padding
        
        # Draw dark background
        cv2.rectangle(frame, 
                     (text_x - 5, text_y - text_size[1] - 5), 
                     (text_x + text_size[0] + 5, text_y + 5), 
                     (0, 0, 0), 
                     -1)
        
        # Draw text in white
        cv2.putText(frame, dimensions_text, (text_x, text_y), font, 
                   font_scale, (255, 255, 255), thickness, cv2.LINE_AA)
                   
        return frame

    def process_frame(self, frame_data):
        """Process received frame data"""
        if isinstance(frame_data, bytes):
            frame_np = np.frombuffer(frame_data, dtype=np.uint8)
            frame = cv2.imdecode(frame_np, cv2.IMREAD_COLOR)
            
            if frame is not None:
                frame = self.draw_markers(frame, self.markers)
                frame = self.draw_hands(frame, self.hands)
                frame = self.draw_dimensions(frame)  # Add dimensions overlay
                cv2.imshow('Received Frame', frame)
                return cv2.waitKey(1) & 0xFF == ord('q')
            
        else:
            json_data = json.loads(frame_data)
            self.markers = json_data.get('markers', [])
            self.hands = json_data.get('hands', [])
            if self.debug and (self.markers or self.hands):
                print(f"JSON data: {json_data}")
        return False

async def run_camera_client(ws_uri, width, height, fps, mirror, track_hands, debug=False):
    """Main client coroutine that connects to the websocket server and processes camera frames."""
    client = SimpleWebsocketClient(ws_uri)
    viewer = CameraViewer(debug=debug)
    
    try:
        await client.connect()
        
        # Configure subscription
        config = {
            #"size": [width, height],
            "width": width,
            "fps": fps,
            "mirror": mirror,
            "hands": track_hands
        }
        await client.subscribe(config)

        # Main processing loop
        while True:
            try:
                frame_data = await client.receive()
                if viewer.process_frame(frame_data):
                    break
            except websockets.exceptions.ConnectionClosed:
                print("\nLost connection to server. Exiting...")
                break
            except Exception as e:
                print(f"\nError processing frame: {e}")
                break

    except Exception as e:
        print(f"\nConnection error: {e}")
    finally:
        print("\nCleaning up...")
        await client.disconnect()
        cv2.destroyAllWindows()
        print("Done.")

def main():
    """Entry point of the application."""
    parser = argparse.ArgumentParser(description="Camera WebSocket Client")
    parser.add_argument("--ws_uri", type=str, default="ws://192.168.1.230:7160/websocket")
    parser.add_argument("--width", type=int, default=960, help="Frame width (default: 640)")
    parser.add_argument("--height", type=int, default=400, help="Frame height (default: 400)")
    parser.add_argument("--fps", type=int, default=10, help="Frames per second (default: 10)")
    parser.add_argument("--mirror", action="store_true", help="Mirror the image if set")
    parser.add_argument("--hands", action="store_true", help="Track hands if set")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    args = parser.parse_args()  
    
    try:
        asyncio.run(run_camera_client(
            args.ws_uri, 
            args.width, 
            args.height, 
            args.fps, 
            args.mirror, 
            args.hands,
            args.debug
        ))
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
    finally:
        cv2.destroyAllWindows()
        print("Exited.")

if __name__ == "__main__":
    main()