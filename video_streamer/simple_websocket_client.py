import asyncio
import websockets
import cv2
import numpy as np
import argparse
import json


async def receive_frames(ws_server_uri, size, fps):
    async with websockets.connect(ws_server_uri) as websocket:
        print(f"Connected to WebSocket server at {ws_server_uri}")

        # Send subscription configuration (size and fps) to the server
        config = {
            'size': size,
            'fps': fps
        }
        await websocket.send(json.dumps(config))
        print(f"Subscribed with size={size} and fps={fps}")

        while True:
            try:
                # Receive binary data (MJPEG frame)
                frame_data = await websocket.recv()

                # Ensure the received data is in binary format
                if isinstance(frame_data, str):
                    print(f"Received unexpected text message: {frame_data}")
                    continue  # Skip non-binary data

                # Convert binary data to numpy array for display with OpenCV
                np_arr = np.frombuffer(frame_data, np.uint8)
                image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                # Display the image using OpenCV
                cv2.imshow('Camera Stream', image)

                # Break on 'q' key press
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

            except Exception as e:
                print(f"Error receiving or displaying frames: {e}")
                break

        cv2.destroyAllWindows()

if __name__ == "__main__":
    # Command line argument parser
    parser = argparse.ArgumentParser(description="Picamera2 WebSocket Client")
    #parser.add_argument("--ws_uri", type=str, required=True, help="WebSocket server URI (e.g. ws://localhost:7160/websocket)")
    parser.add_argument("--ws_uri", type=str, default="ws://192.168.1.198:7160/websocket")
    parser.add_argument("--width", type=int, default=640, help="Frame width (default: 640)")
    parser.add_argument("--height", type=int, default=480, help="Frame height (default: 480)")
    parser.add_argument("--fps", type=int, default=15, help="Frames per second (default: 15)")

    args = parser.parse_args()

    # Define the frame size and fps from command-line arguments
    size = (args.width, args.height)
    fps = args.fps

    # Run the WebSocket client
    asyncio.run(receive_frames(args.ws_uri, size, fps))