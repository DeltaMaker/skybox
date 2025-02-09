"""
VisionClient - WebSocket client for displaying vision results on video stream frames.

This client implementation provides:
- Real-time display of vision data
- Visualization of computer vision results
    - ArUco marker overlays
    - Hand tracking visualization
- Support for different stream configurations
    - Custom resolution
    - Frame rate control
    - Mirror mode
    - Vision processing toggles
- Clean shutdown handling

Usage:
    python vision_client.py [--ws_uri WS_URI] [--width WIDTH] [--fps FPS] 
                          [--mirror] [--hands] [--markers] [--debug]
"""

import asyncio
import json
import cv2
import numpy as np
import argparse
from simple_client import SimpleWebsocketClient


class VisionClient:
    def __init__(self, debug=False):
        """Initialize the VisionClient."""
        self.debug = debug
        self.markers = []
        self.hands = []

    def draw_markers(self, frame, markers):
        """Draw detected markers on the frame."""
        if not markers:
            return frame
        
        for marker in markers:
            corners = np.array(marker['corners']).reshape(4, 2).astype(np.int32)
            
            cv2.polylines(frame, 
                         [corners.reshape(-1, 1, 2)],
                         isClosed=True,
                         color=(0, 255, 0),
                         thickness=2)
            
            marker_id = str(marker.get('id', '-'))
            text_pos = (int(corners[0][0]), int(corners[0][1] - 10))
            cv2.putText(frame,
                       f"{marker_id}",
                       text_pos,
                       cv2.FONT_HERSHEY_SIMPLEX,
                       0.75,
                       (0, 255, 0),
                       2)
            
            cv2.circle(frame,
                      (int(corners[0][0]), int(corners[0][1])),
                      radius=3,
                      color=(0, 0, 255),
                      thickness=-1)
        return frame

    def draw_hands(self, frame, hands):
        """Draw detected hand landmarks on the frame."""
        if not hands:
            return frame
        
        COLORS = [(0, 255, 0), (255, 0, 0)]  # Green for first hand, Blue for second
        
        HAND_CONNECTIONS = [
            (0, 1), (1, 2), (2, 3), (3, 4),    # thumb
            (0, 5), (5, 6), (6, 7), (7, 8),    # index finger
            (0, 9), (9, 10), (10, 11), (11, 12),  # middle finger
            (0, 13), (13, 14), (14, 15), (15, 16),  # ring finger
            (0, 17), (17, 18), (18, 19), (19, 20),  # pinky
            (0, 5), (5, 9), (9, 13), (13, 17)  # palm
        ]
        
        h, w = frame.shape[:2]
        for hand_idx, hand_landmarks in enumerate(hands):
            color = COLORS[hand_idx % len(COLORS)]
            
            # Draw connections
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
            
            # Draw landmarks
            for landmark in hand_landmarks:
                px = int(landmark['x'] * w)
                py = int(landmark['y'] * h)
                cv2.circle(frame, (px, py), 3, color, -1)
                
        return frame

    def process_vision_data(self, data):
        """Process received vision data (frames, markers, hands)."""
        if isinstance(data, str):
            # Process JSON data (markers, hands)
            json_data = json.loads(data)
            self.markers = json_data.get('markers', [])
            self.hands = json_data.get('hands', [])
            if self.debug and (self.markers or self.hands):
                print(f"Vision data: {json_data}")
            return False
            
        elif isinstance(data, bytes):
            # Process frame data
            nparr = np.frombuffer(data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is not None:
                frame = self.draw_markers(frame, self.markers)
                frame = self.draw_hands(frame, self.hands)
                cv2.imshow('Vision Client', frame)
                return cv2.waitKey(1) & 0xFF == ord('q')
                
        return False


async def run_vision_client(ws_uri, width, fps, mirror, track_hands, track_markers, debug=False):
    """Main client coroutine."""
    client = SimpleWebsocketClient(ws_uri)
    viewer = VisionClient(debug=debug)
    
    try:
        # Connect to websocket
        await client.connect()
        
        # Configure subscription based on what data we want
        config = {
            'fps': fps,
            'mirror': mirror
        }
        
        # Only request frame data if we want to display frames
        if width:
            config['width'] = width
            
        # Only request hand data if we want to track hands
        if track_hands:
            config['hands'] = True
            
        # Only request marker data if we want to track markers
        if track_markers:
            config['markers'] = True
            
        await client.subscribe(config)

        # Main processing loop
        while True:
            try:
                vision_data = await client.receive()
                if viewer.process_vision_data(vision_data):
                    break
            except Exception as e:
                print(f"\nError processing vision data: {e}")
                break

    except KeyboardInterrupt:
        print("\nStopping client...")
    except Exception as e:
        print(f"\nConnection error: {e}")
    finally:
        print("\nCleaning up...")
        await client.disconnect()
        cv2.destroyAllWindows()
        print("Done.")


def main():
    """Entry point of the application."""
    parser = argparse.ArgumentParser(description="Vision WebSocket Client")
    parser.add_argument("--ws_uri", type=str, default="ws://192.168.1.248:7160/websocket")
    parser.add_argument("--width", type=int, default=640, help="Frame width (default: 640)")
    parser.add_argument("--fps", type=int, default=15, help="Frames per second (default: 15)")
    parser.add_argument("--mirror", action="store_true", help="Mirror the image if set")
    parser.add_argument("--hands", action="store_true", help="Track hands if set")
    parser.add_argument("--markers", action="store_true", help="Track markers if set")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    args = parser.parse_args()
    
    try:
        print(f"\nStarting Vision Client")
        print(f"WebSocket URI: {args.ws_uri}")
        print(f"Subscriptions:")
        print(f"  - Frames: {'Yes' if args.width else 'No'}")
        print(f"  - Hands: {'Yes' if args.hands else 'No'}")
        print(f"  - Markers: {'Yes' if args.markers else 'No'}")
        print("Press 'q' to quit.")
        
        asyncio.run(run_vision_client(
            args.ws_uri,
            args.width,
            args.fps,
            args.mirror,
            args.hands,
            args.markers,
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