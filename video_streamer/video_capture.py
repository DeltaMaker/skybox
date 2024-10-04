"""
Author: Bob Houston
Date: 2024-9-21
Version: 0.2
"""
import asyncio
import websockets
import cv2
import requests
import numpy as np
import json, base64

class VideoCapture:
    def __init__(self, source, timeout=1):
        try:    # Convert source to an integer if possible (for camera index)
            self.source = int(source)
        except ValueError:
            self.source = source
        self.timeout = timeout
        self.is_snapshot = self.check_if_snapshot(self.source)
        if not self.is_snapshot:
            self.cap = cv2.VideoCapture(self.source)

    def check_if_snapshot(self, source):
        """Check if the source is an image URL by attempting to fetch it."""
        if isinstance(source, str) and (source.startswith('http://') or source.startswith('https://')):
            try:
                response = requests.get(source, stream=True, timeout=self.timeout)
                return 'image' in response.headers['Content-Type']
            except Exception:
                return False
        return False

    def isOpened(self):
        return self.is_snapshot or self.cap.isOpened()

    def read(self):
        """Fetch the next frame from the source."""
        if self.is_snapshot:
            return self.fetch_snapshot()
        else:
            return self.cap.read()

    def fetch_snapshot(self):
        """Fetch the latest image from the snapshot URL."""
        try:
            response = requests.get(self.source, timeout=self.timeout)
            image_array = np.frombuffer(response.content, dtype=np.uint8)
            frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            return True, frame
        except Exception as e:
            print(f"Error fetching snapshot: {e}")
            return False, None

    def release(self):
        """Release the video capture object."""
        if not self.is_snapshot:
            self.cap.release()

# Example usage - Streaming a video source to a websocket with overlay graphics

# Define the shapes list with ratio values for coordinates and radius (0 to 1)
overlay_shapes = [
    {"type": "text", "pos": (0.1, 0.5), "txt": "Hello World", "scale": 1, "col": (255, 255, 255),
     "th": 2},  # White text
    {"type": "circ", "c": (0.2, 0.5), "col": (0, 255, 0), "th": -1},
    # Filled green circle
    {"type": "circ", "c": (0.3, 0.3), "r": 0.1, "col": (255, 0, 0), "th": 3},
    # Red circle with thickness 3
    {"type": "rect", "tl": (0.1, 0.1), "br": (0.3, 0.3), "col": (0, 255, 255), "th": 5},
    # Yellow rectangle with thickness 5
    {"type": "poly", "points": [(0.6, 0.8), (0.7, 0.9), (0.8, 0.8), (0.7, 0.7)],
     "col": (0, 255, 255), "closed": True, "th": 2}  # Yellow closed polyline with thickness 2
]

async def send_frames(websocket_url, video_source):
    capture = VideoCapture(video_source)
    if not capture.isOpened():
        print("Error: Unable to open video source")
        return
    try:
        async with websockets.connect(websocket_url) as websocket:
            try:
                while True:
                    ret, frame = capture.read()
                    if not ret:
                        continue
                    _, buffer = cv2.imencode('.jpg', frame)
                    frame_data = base64.b64encode(buffer).decode('utf-8')

                    # may send with the raw frame or json with frame and overlay
                    #message = buffer.tobytes() # raw frame data
                    data = { "frame": frame_data, "overlay": overlay_shapes }
                    message = json.dumps(data)  # json message

                    await websocket.send(message)
                    await asyncio.sleep(0.1)  # Adjust sleep time to control frame rate
            except Exception as e:
                print(f"Error in sending frames: {e}")
            finally:
                capture.release()
    except (websockets.ConnectionClosedError, websockets.InvalidURI, websockets.InvalidHandshake, OSError) as e:
        print(f"Error connecting to WebSocket URL: {websocket_url}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Send video frames via WebSocket")
    parser.add_argument('--ws-url', type=str, default="ws://localhost:7130/websocket", help='WebSocket URL to send frames to')
    parser.add_argument('--video-source', type=str, default='1', help='Video source')
    args = parser.parse_args()

    asyncio.run(send_frames(args.ws_url, args.video_source))
