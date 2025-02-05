import asyncio
import websockets
import json
import cv2
import numpy as np
import argparse

def draw_markers(frame, markers):
    """Draw detected markers on the frame."""
    if not markers:
        return frame
    
    for marker in markers:
        # Convert flat corner array into points array
        corners = np.array(marker['corners']).reshape(4, 2).astype(np.int32)
        
        # Draw marker outline
        cv2.polylines(frame, 
                     [corners.reshape(-1, 1, 2)],
                     isClosed=True,
                     color=(0, 255, 0),
                     thickness=2)
        
        # Draw marker ID
        marker_id = str(marker.get('id', '-'))
        text_pos = (int(corners[0][0]), int(corners[0][1] - 10))
        cv2.putText(frame,
                   f"{marker_id}",
                   text_pos,
                   cv2.FONT_HERSHEY_SIMPLEX,
                   0.75,
                   (0, 255, 0),
                   2)
        
        # Draw orientation indicator (red dot at first corner)
        cv2.circle(frame,
                  (int(corners[0][0]), int(corners[0][1])),
                  radius=3,
                  color=(0, 0, 255),
                  thickness=-1)
    return frame

def draw_hands(frame, hands):
    """Draw detected hand landmarks on the frame."""
    if not hands:
        return frame
    
    # Colors for each hand
    COLORS = [(0, 255, 0), (255, 0, 0)]  # Green for first hand, Red for second
    
    # Define finger connections
    HAND_CONNECTIONS = [
        # Thumb
        (0, 1), (1, 2), (2, 3), (3, 4),
        # Index finger
        (0, 5), (5, 6), (6, 7), (7, 8),
        # Middle finger
        (0, 9), (9, 10), (10, 11), (11, 12),
        # Ring finger
        (0, 13), (13, 14), (14, 15), (15, 16),
        # Pinky
        (0, 17), (17, 18), (18, 19), (19, 20),
        # Palm
        (0, 5), (5, 9), (9, 13), (13, 17)
    ]
    
    for hand_idx, hand_landmarks in enumerate(hands):
        color = COLORS[hand_idx % len(COLORS)]
        
        # Draw connections first (so they appear behind the points)
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
        
        # Draw landmark points on top
        for landmark in hand_landmarks:
            px = int(landmark['x'] * w)
            py = int(landmark['y'] * h)
            cv2.circle(frame, (px, py), 3, color, -1)
            
    return frame

async def receive_frames(ws_uri, width, height, fps, mirror, track_hands):
    try:
        async with websockets.connect(ws_uri, ping_interval=20, ping_timeout=20) as websocket:
            print(f"Connected to WebSocket server at {ws_uri}")

            # Send subscription configuration to the server
            subscription_message = json.dumps({
                "size": [width, height],
                "fps": fps,
                "mirror": mirror,
                "hands": track_hands
            })
            await websocket.send(subscription_message)
            print(f"Subscribed with size=({width}, {height}), fps={fps}, mirror={mirror}, track_hands={track_hands}")

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
            hands = []
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
                            # Draw markers if any were detected
                            frame = draw_markers(frame, markers)
                            # Draw hands if any were detected
                            frame = draw_hands(frame, hands)
                            
                            # Display the image in a window
                            cv2.imshow('Received Frame', frame)

                            # Break if the user presses 'q'
                            if cv2.waitKey(1) & 0xFF == ord('q'):
                                break
                    else:
                        # Handle marker data as JSON
                        json_data = json.loads(frame_data)
                        
                        markers = json_data.get('markers', [])
                        hands = json_data.get('hands', [])
                        if markers or hands:
                            print(f"JSON data: {json_data}")

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
    parser.add_argument("--hands", action="store_true", help="Track hands if set")


    args = parser.parse_args()

    # Run the WebSocket client
    asyncio.run(receive_frames(args.ws_uri, args.width, args.height, args.fps, args.mirror, args.hands))