import asyncio
import websockets
import cv2
import numpy as np
import json

WS_SERVER_URI = "ws://192.168.1.198:7160/websocket"

async def receive_frames():
    async with websockets.connect(WS_SERVER_URI) as websocket:
        print(f"Connected to WebSocket server at {WS_SERVER_URI}")

        # Send subscription configuration (e.g., frame size and fps)
        config = {
            'size': (640, 480),
            'fps': 15
        }
        await websocket.send(json.dumps(config))

        # Receive confirmation from server
        confirmation_message = await websocket.recv()
        print(f"Subscription confirmation: {confirmation_message}")

        # Continuously receive frames from the server
        while True:
            try:
                # Receive binary data (MJPEG frame)
                frame_data = await websocket.recv()

                # Convert the frame to a NumPy array and decode it into an image
                np_arr = np.frombuffer(frame_data, np.uint8)
                img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                # Display the image using OpenCV
                cv2.imshow('WebSocket Video', img)

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            except Exception as e:
                print(f"Error receiving or displaying frame: {e}")
                break

    cv2.destroyAllWindows()

asyncio.run(receive_frames())