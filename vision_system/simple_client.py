import asyncio
import websockets
import json
import cv2
import numpy as np
import argparse

async def receive_frames(ws_uri, width, height, fps, mirror):
    try:
        async with websockets.connect(ws_uri, ping_interval=20, ping_timeout=20) as websocket:
            print(f"Connected to WebSocket server at {ws_uri}")

            # Send subscription configuration to the server
            subscription_message = json.dumps({
                "size": [width, height],
                "fps": fps,
                "mirror": mirror
            })
            await websocket.send(subscription_message)
            print(f"Subscribed with size=({width}, {height}), fps={fps}, mirror={mirror}")

            # First, wait for and handle the subscription confirmation
            confirmation_message = await websocket.recv()

            try:
                confirmation_data = json.loads(confirmation_message)
                print(f"Received confirmation message: {confirmation_data}")
            except json.JSONDecodeError:
                print(f"Received unexpected message format: {confirmation_message}")
                return

            # Now, continuously receive frames and marker data
            markers = []
            while True:
                try:
                    # Receive binary frame data (MJPEG)
                    frame_data = await websocket.recv()

                    if isinstance(frame_data, bytes):
                        # Convert the binary data into a numpy array
                        frame_np = np.frombuffer(frame_data, dtype=np.uint8)

                        # Decode the image using OpenCV
                        frame = cv2.imdecode(frame_np, cv2.IMREAD_COLOR)

                        if frame is not None:
                            if markers:
                                for marker in markers:
                                    corners = np.array(marker.get('corners', []), dtype=np.int32).reshape(-1, 1, 2)
                                    cv2.polylines(frame, [corners], True, (0, 255, 0), 1)
                            # Display the image in a window
                            cv2.imshow('Received Frame', frame)

                            # Break if the user presses 'q'
                            if cv2.waitKey(1) & 0xFF == ord('q'):
                                break
                    else:
                        # Handle marker data as JSON
                        marker_data = json.loads(frame_data)
                        markers = marker_data.get('markers', [])
                        if markers:
                            print(f"Marker data: {markers}")

                except websockets.ConnectionClosed:
                    print("Connection closed by server")
                    break
                except Exception as e:
                    print(f"Error processing frame: {e}")
                    break

    except websockets.ConnectionClosed:
        print("Connection closed")
    except Exception as e:
        print(f"Connection error: {e}")
    finally:
        cv2.destroyAllWindows()

if __name__ == "__main__":
    # Command line argument parser
    parser = argparse.ArgumentParser(description="Camera WebSocket Client")
    parser.add_argument("--ws_uri", type=str, default="ws://localhost:7160/websocket")
    parser.add_argument("--width", type=int, default=640, help="Frame width (default: 640)")
    parser.add_argument("--height", type=int, default=480, help="Frame height (default: 480)")
    parser.add_argument("--fps", type=int, default=15, help="Frames per second (default: 15)")
    parser.add_argument("--mirror", action="store_true", help="Mirror the image if set")

    args = parser.parse_args()

    # Run the WebSocket client
    asyncio.run(receive_frames(args.ws_uri, args.width, args.height, args.fps, args.mirror))