import asyncio
import json
import signal
import sys
from aiohttp import web
from typing import Dict, Any, Set, Optional, List
import logging
from dataclasses import dataclass, field

@dataclass
class WebSocketClient:
    ws: web.WebSocketResponse
    subscriptions: Set[str] = field(default_factory=set)

class BaseWebSocketServer:
    def __init__(self, host: str = '0.0.0.0', port: int = 7120, debug: bool = True):
        """
        Initialize the WebSocket server.
        
        :param host: Host address to bind to
        :param port: Port to listen on
        :param debug: Enable debug logging
        """
        self.host = host
        self.port = port
        self.debug = debug
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.websockets: Dict[web.WebSocketResponse, WebSocketClient] = {}
        self.current_state: Dict[str, Any] = {}
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.running = False
        
        # Register startup/cleanup handlers
        self.app.on_startup.append(self.start_background_tasks)
        self.app.on_cleanup.append(self.cleanup_background_tasks)
        
        # Setup routes
        self.setup_routes()

    def setup_routes(self) -> None:
        """Setup server routes"""
        # WebSocket connections must use GET for the upgrade handshake
        self.app.router.add_get('/websocket', self.websocket_handler)
        self.add_custom_routes(self.app.router)

    def add_custom_routes(self, router: web.UrlDispatcher) -> None:
        """
        Add custom routes to the server.
        Override this method to add custom routes.
        """
        pass

    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections"""
        if self.debug:
            print(f"WebSocket connection attempt from {request.remote}")
            
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        # Create new client with empty subscriptions
        self.websockets[ws] = WebSocketClient(ws=ws)

        try:
            # Send initial state upon connection
            if self.current_state:
                await ws.send_json({
                    "method": "notify_status_update",
                    "params": [{
                        "status": self.current_state
                    }]
                })

            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        if 'method' in data and data['method'] == 'subscribe':
                            # Handle subscription
                            objects = data.get('params', {}).get('objects', {})
                            client = self.websockets[ws]
                            client.subscriptions.update(objects.keys())
                            if self.debug:
                                print(f"Client subscribed to: {client.subscriptions}")
                            
                            # Send current state for subscribed objects
                            state_update = {
                                key: self.current_state.get(key, {})
                                for key in client.subscriptions
                                if key in self.current_state
                            }
                            if state_update:
                                await ws.send_json({
                                    "method": "notify_status_update",
                                    "params": [{
                                        "status": state_update
                                    }]
                                })
                        
                        response = await self.handle_message(data)
                        if response:
                            await ws.send_json(response)
                    except json.JSONDecodeError:
                        await ws.send_json({"error": "Invalid JSON"})
                    except Exception as e:
                        await ws.send_json({"error": str(e)})
                elif msg.type == web.WSMsgType.ERROR:
                    if self.debug:
                        print(f'WebSocket connection closed with exception {ws.exception()}')
        finally:
            del self.websockets[ws]
            if self.debug:
                print("WebSocket connection closed")
        
        return ws

    async def handle_message(self, message: Dict) -> Optional[Dict]:
        """
        Handle incoming WebSocket messages.
        Override this method to implement custom message handling.
        """
        return None

    async def broadcast(self, message: Dict) -> None:
        """Broadcast message to subscribed clients"""
        if not self.websockets:
            return
            
        dead_sockets = set()
        
        # Determine which objects are being updated
        updated_objects = set()
        if 'method' in message and message['method'] == 'notify_status_update':
            status = message.get('params', [{}])[0].get('status', {})
            updated_objects = set(status.keys())

        for ws, client in self.websockets.items():
            # Only send to clients subscribed to the updated objects
            if not updated_objects or (updated_objects & client.subscriptions):
                try:
                    await ws.send_json(message)
                except Exception:
                    dead_sockets.add(ws)
        
        # Clean up dead connections
        for ws in dead_sockets:
            del self.websockets[ws]

    async def start_server(self) -> None:
        """Start the WebSocket server"""
        if self.debug:
            print(f"Starting WebSocket server on {self.host}:{self.port}")
        
        # Setup the application
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        
        # Register startup/cleanup handlers
        self.app.on_startup.append(self.start_background_tasks)
        self.app.on_cleanup.append(self.cleanup_background_tasks)
        
        # Start the site
        await self.site.start()
        self.running = True

    async def stop_server(self) -> None:
        """Stop the WebSocket server"""
        self.running = False
        
        if self.debug:
            print("Stopping WebSocket server...")
        
        # Close all WebSocket connections
        for ws in self.websockets:
            await ws.close()
        self.websockets.clear()
        
        # Cleanup server
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        
        self.site = None
        self.runner = None

    async def cleanup(self) -> None:
        """Cleanup all resources"""
        await self.stop_server()
        
        # Cancel all remaining tasks
        tasks = [t for t in asyncio.all_tasks(self.loop) 
                if t is not asyncio.current_task(self.loop)]
        for task in tasks:
            task.cancel()
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def signal_handler(self, sig, frame) -> None:
        """Handle shutdown signals"""
        if self.debug:
            print("\nShutdown signal received")
        
        if self.loop and self.loop.is_running():
            self.loop.create_task(self.cleanup())
            self.loop.stop()

    def start(self) -> None:
        """
        Start the server and set up signal handlers.
        This is the main entry point for the server.
        """
        try:
            # Set up signal handlers
            signal.signal(signal.SIGINT, self.signal_handler)
            signal.signal(signal.SIGTERM, self.signal_handler)
            
            # Get or create event loop
            try:
                self.loop = asyncio.get_event_loop()
            except RuntimeError:
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)
            
            if self.debug:
                print("Starting server...")
            
            # Run the application using the existing app instance
            web.run_app(self.app, host=self.host, port=self.port)
            
        except Exception as e:
            if self.debug:
                print(f"Error starting server: {e}")
            raise

    async def start_background_tasks(self) -> None:
        """
        Start any background tasks.
        Override this method to add custom background tasks.
        """
        pass

    async def __aenter__(self):
        """Async context manager entry"""
        await self.start_server()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.cleanup()