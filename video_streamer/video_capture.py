"""
Author: Bob Houston
Date: 2024--21
Version: 0.1
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

# Example usage - Streaming a video source to a websocket

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

                    ####
                    # Add overlay data
                    h, w = frame.shape[:2]
                    overlay = [
                        {"t": "rect", "x1": 50 / w, "y1": 50 / h, "x2": 100 / w, "y2": 100 / h,
                         "col": [255, 0, 0], "th": 2},
                        {"t": "circ", "x": 150 / w, "y": 150 / h, "r": 20, "col": [0, 255, 0],
                         "th": -1},
                        {"t": "circ", "x": 200 / w, "col": [0, 255, 255]},
                        {"t": "text", "x": 250 / w, "txt": "Hello", "fs": 1,
                         "col": [0, 0, 255], "th": 2}
                    ]
                    overlay = [
                        ["rect", 50 / w, 50 / h, 100 / w, 100 / h,
                          [255, 0, 0], 2],
                        ["circ", 150 / w, 150 / h, 20, [0, 255, 0], -1],
                        ["circ", 200 / w, 50 / h, 30, [0, 255, 255], 2],
                        ["text", 250 / w, 150 / h, "Hello", 1,[0, 0, 255], 2]
                    ]

                    # Define the shapes list with ratio values for coordinates and radius (0 to 1)
                    shapes = [
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


                    _, buffer = cv2.imencode('.jpg', frame)
                    frame_data = base64.b64encode(buffer).decode('utf-8')
                    message = buffer.tobytes() # raw frame data

                    data = {
                        "frame": frame_data,
                        #"overlay": shapes
                    }
                    #message = json.dumps(data)  # json message

                    await websocket.send(message)
                    ####
                    #_, buffer = cv2.imencode('.jpg', frame)
                    #await websocket.send(buffer.tobytes())
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
    parser.add_argument('--ws-url', type=str, default="ws://localhost:7130", help='WebSocket URL to send frames to')
    parser.add_argument('--video-source', type=str, default='1', help='Video source')
    args = parser.parse_args()

    asyncio.run(send_frames(args.ws_url, args.video_source))
