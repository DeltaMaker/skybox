import json
import asyncio
import websockets

# Define the shapes list
overlays = [
    [
        {"type": "circ", "c": (0.5, 0.5), "r": 0.2, "col": (0, 255, 0), "th": 3},  # Green filled circle
        {"type": "rect", "tl": (0.1, 0.1), "br": (0.3, 0.3), "col": (255, 0, 0), "th": 2},  # Red rectangle
    ],
    [{"type": "text", "pos": (0.5, 0.1), "txt": "Hello World", "scale": 1, "col": (255, 255, 255), "th": 2}],  # White text
    [
        {"type": "poly", "points": [(0.6, 0.8), (0.7, 0.9), (0.8, 0.8), (0.7, 0.7)], "col": (0, 255, 255), "closed": True, "th": 2},  # Yellow closed polyline
        {"type": "rect", "tl": (0.1,0.9), "h": 0.03, "w": 0.03, "col": (255, 0, 255), "th": -1},
        {"type": "text", "pos": (0.1, 0.1), "th": 2},  # White text
    ]]

async def send_shapes():
    # Connect to the WebSocket server (replace 'ws://your-websocket-url' with your server URL)
    uri = "ws://localhost:7130/websocket"
    uri = "ws://192.168.1.198:7130/websocket"
    async with websockets.connect(uri) as websocket:
        while True:
          for shapes in overlays:
            # Convert shapes list to JSON
            data = {
                # "frame": frame_data,
                "overlay": shapes,
                #"overlay": [{}]
            }
            message_json = json.dumps(data)
            # Send the shapes data
            print(f"Sending shapes: {message_json}")
            await websocket.send(message_json)

            await asyncio.sleep(1.0)

if __name__ == "__main__":
    # Run the WebSocket client
    asyncio.run(send_shapes())

    #asyncio.get_event_loop().run_until_complete(send_shapes())