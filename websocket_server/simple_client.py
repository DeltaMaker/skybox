"""
SimpleWebsocketClient - Base class for WebSocket clients with subscription support.

This class provides the foundation for creating WebSocket clients that can:
- Connect to a WebSocket server
- Send subscription configurations
- Receive messages (both text and binary)
- Handle connection errors and cleanup

Usage:
    Either inherit from this class or use it with composition pattern.
    See example_client.py and camera_viewer.py for usage examples.
"""

import websockets
import json
import asyncio
from typing import Optional, Dict, Any, Callable, Awaitable
import inspect

class SimpleWebsocketClient:
    def __init__(self, url: str):
        """Initialize websocket client with URL."""
        self.url = url
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        self.subscribed = False
        self.max_retries = 5
        self.retry_delay = 1.0  # Start with 1 second delay
        self.running = True  # Flag to control the receive loop
        self.subscription = None  # Store subscription config
        self.callback = None  # Store message callback
        self.debug = False  # Default debug setting
        
        # Default subscription handlers
        self._subscription_predicate = lambda resp: resp.get('status') == 'subscribed'
        self._notification_handler = None

    def set_debug(self, debug=True, log_file=None):
        """Enable or disable debug output.
        
        Args:
            debug (bool): Whether to enable debug output
            log_file (str): Optional path to a log file
        """
        self.debug = debug
        self.log_file = log_file
        if log_file:
            # Create or clear the log file
            with open(log_file, 'w') as f:
                f.write(f"Debug log started for {self.url}\n")
        return self

    def debug_log(self, message):
        """Log debug message if debug is enabled."""
        if self.debug:
            caller_frame = inspect.currentframe().f_back
            caller_func = caller_frame.f_code.co_name
            log_message = f"[DEBUG] {caller_func}(): {message}"
            
            # Print to console
            print(log_message)
            
            # Write to log file if specified
            if hasattr(self, 'log_file') and self.log_file:
                try:
                    with open(self.log_file, 'a') as f:
                        f.write(log_message + '\n')
                except Exception as e:
                    print(f"[ERROR] Failed to write to log file: {e}")

    def set_subscription_handlers(self, 
                                confirmation_predicate: Callable[[Dict], bool],
                                notification_handler: Optional[Callable[[Dict], Awaitable[None]]] = None):
        """Configure how to determine subscription success and handle notifications.
        
        Args:
            confirmation_predicate: Function that takes a response dict and returns True if subscription is confirmed
            notification_handler: Optional async function to handle non-confirmation messages during subscription
        """
        self._subscription_predicate = confirmation_predicate
        self._notification_handler = notification_handler

    async def start(self, callback, subscription: Dict[str, Any] = None):
        """Start client with callback for updates and optional subscription."""
        self.callback = callback
        self.subscription = subscription
        await self.connect()
        if self.subscription:
            await self.subscribe(self.subscription)
        asyncio.create_task(self.receive_loop())

    async def receive_loop(self):
        """Continuously receive and process messages with automatic reconnection"""
        self.debug_log("Starting receive loop")
        while self.running:
            try:
                if not self.is_connected:
                    self.debug_log(f"Not connected to {self.url}, attempting to reconnect")
                    try:
                        await self.connect()
                        if self.subscription:
                            self.debug_log("Resubscribing in receive loop")
                            await self.subscribe(self.subscription)
                    except Exception as e:
                        self.debug_log(f"EXCEPTION: Connection/subscription failed in receive loop: {type(e).__name__}: {str(e)}")
                        await asyncio.sleep(self.retry_delay)
                        continue
                
                self.debug_log("Connected, entering message processing loop")
                while self.is_connected and self.running:
                    try:
                        message = await self.receive()
                        if isinstance(message, str):
                            try:
                                data = json.loads(message)
                                if self.callback:
                                    self.debug_log("Calling callback with received data")
                                    await self.callback(data)
                            except json.JSONDecodeError as e:
                                self.debug_log(f"EXCEPTION: JSON decode error: {str(e)}")
                    except ConnectionError as e:
                        self.debug_log(f"EXCEPTION: Connection error in processing loop: {str(e)}")
                        break  # Break inner loop to reconnect
                    
                    await asyncio.sleep(0.1)
                    
            except websockets.exceptions.ConnectionClosed as e:
                self.debug_log(f"EXCEPTION: WebSocket connection closed: code={e.code}, reason='{e.reason}'")
                self.connected = False
                self.subscribed = False
            except Exception as e:
                self.debug_log(f"EXCEPTION: Unexpected error in receive loop: {type(e).__name__}: {str(e)}")
                self.connected = False
                self.subscribed = False
            
            # Wait before attempting to reconnect
            if self.running:
                backoff_delay = self.retry_delay
                self.debug_log(f"Waiting {backoff_delay:.1f}s before reconnection attempt")
                await asyncio.sleep(backoff_delay)

    async def stop(self):
        """Stop the client and clean up"""
        self.debug_log("Stopping client")
        self.running = False
        await self.disconnect()
        self.debug_log("Client stopped")

    async def connect(self) -> None:
        """Establish websocket connection with retries."""
        retries = 0
        while retries < self.max_retries and self.running:
            try:
                self.ws = await websockets.connect(
                    self.url,
                    ping_interval=30,  # Increased from 10
                    ping_timeout=60,   # Increased from 30
                    close_timeout=30,  # Added explicit close timeout
                    max_size=10 * 1024 * 1024  # 10MB max message size
                )
                self.connected = True
                self.debug_log(f"Successfully connected to {self.url}")
                return
            except Exception as e:
                retries += 1
                if retries < self.max_retries and self.running:
                    self.debug_log(f"EXCEPTION: Connection attempt {retries} failed: {type(e).__name__}: {str(e)}")
                    await asyncio.sleep(self.retry_delay * retries)  # Exponential backoff
                else:
                    error_msg = f"Failed to connect after {self.max_retries} attempts: {type(e).__name__}: {str(e)}"
                    self.debug_log(f"EXCEPTION: {error_msg}")
                    raise ConnectionError(error_msg) from e

    async def disconnect(self) -> None:
        """Close websocket connection if it exists."""
        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                self.debug_log(f"EXCEPTION: Error during disconnect: {type(e).__name__}: {str(e)}")
            finally:
                self.ws = None
        self.connected = False
        self.subscribed = False

    async def subscribe(self, config: Dict[str, Any]) -> None:
        """Send subscription configuration to the server with retries."""
        if not self.ws:
            error_msg = "Not connected to websocket"
            self.debug_log(f"EXCEPTION: {error_msg}")
            raise ConnectionError(error_msg)
        
        self.subscription = config  # Store subscription for reconnect
        retries = 0
        while retries < self.max_retries:
            try:
                # Send configuration message
                self.debug_log(f"Sending subscription: {config}")
                await self.ws.send(json.dumps(config))
                
                # Wait for confirmation message with timeout
                try:
                    while True:  # Keep reading messages until we get confirmation
                        self.debug_log("Waiting for subscription confirmation...")
                        response = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                        confirmation = json.loads(response)
                        
                        # Check if this confirms subscription
                        if self._subscription_predicate(confirmation):
                            self.subscribed = True
                            self.debug_log(f"Successfully subscribed to {self.url}")
                            return
                            
                        # If not confirmation, might be a notification
                        if self._notification_handler:
                            self.debug_log("Received non-confirmation message, handling as notification")
                            await self._notification_handler(confirmation)
                        else:
                            self.debug_log(f"Received non-confirmation message: {confirmation}")
                            
                except asyncio.TimeoutError:
                    self.debug_log("EXCEPTION: Subscription confirmation timeout after 5.0s")
                
                retries += 1
                if retries < self.max_retries:
                    self.debug_log(f"Subscription attempt {retries} failed, retrying...")
                    await asyncio.sleep(self.retry_delay * retries)
                else:
                    error_msg = f"Failed to subscribe after {self.max_retries} attempts"
                    self.debug_log(f"EXCEPTION: {error_msg}")
                    raise ConnectionError(error_msg)
            except Exception as e:
                if isinstance(e, ConnectionError) and str(e).startswith("Failed to subscribe after"):
                    raise  # Re-raise our own error
                
                retries += 1
                if retries < self.max_retries:
                    self.debug_log(f"EXCEPTION: Subscription error: {type(e).__name__}: {str(e)}, retrying...")
                    await asyncio.sleep(self.retry_delay * retries)
                else:
                    error_msg = f"Failed to subscribe: {type(e).__name__}: {str(e)}"
                    self.debug_log(f"EXCEPTION: {error_msg}")
                    raise ConnectionError(error_msg) from e

    async def receive(self):
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            if not self.ws or not self.connected:
                self.debug_log("Not connected or WebSocket is None, attempting to reconnect")
                try:
                    await self.reconnect()
                except Exception as e:
                    retry_count += 1
                    self.debug_log(f"EXCEPTION: Reconnect failed (attempt {retry_count}/{max_retries}): {type(e).__name__}: {str(e)}")
                    if retry_count >= max_retries:
                        error_msg = f"Failed to reconnect after {max_retries} attempts"
                        self.debug_log(f"EXCEPTION: {error_msg}")
                        raise ConnectionError(error_msg) from e
                    await asyncio.sleep(retry_count * 2)  # Backoff
                    continue
            
            try:
                # Use timeout to avoid hanging indefinitely
                self.debug_log("Waiting for message with 10.0s timeout...")
                message = await asyncio.wait_for(self.ws.recv(), timeout=10.0)
                self.debug_log("Message received successfully")
                return message
            except asyncio.TimeoutError as e:
                # Connection issue detected - timeout
                self.connected = False
                self.subscribed = False
                
                # Log the issue
                self.debug_log(f"EXCEPTION: Receive timeout after 10.0s: {str(e)}")
                
                retry_count += 1
                if retry_count >= max_retries:
                    error_msg = f"Failed to receive after {max_retries} attempts due to timeout"
                    self.debug_log(f"EXCEPTION: {error_msg}")
                    raise ConnectionError(error_msg) from e
                
                self.debug_log(f"Retrying receive after timeout (attempt {retry_count}/{max_retries})")
                await asyncio.sleep(retry_count * 2)  # Backoff
            except websockets.exceptions.ConnectionClosed as e:
                # Connection issue detected - connection closed
                self.connected = False
                self.subscribed = False
                
                # Log the issue
                self.debug_log(f"EXCEPTION: Connection closed: code={e.code}, reason='{e.reason}'")
                
                retry_count += 1
                if retry_count >= max_retries:
                    error_msg = f"Failed to receive after {max_retries} attempts due to connection closure"
                    self.debug_log(f"EXCEPTION: {error_msg}")
                    raise ConnectionError(error_msg) from e
                
                self.debug_log(f"Retrying receive after connection closed (attempt {retry_count}/{max_retries})")
                await asyncio.sleep(retry_count * 2)  # Backoff
            except Exception as e:
                # Other unexpected exception
                self.connected = False
                self.subscribed = False
                
                # Log the issue
                self.debug_log(f"EXCEPTION: Unexpected error during receive: {type(e).__name__}: {str(e)}")
                
                retry_count += 1
                if retry_count >= max_retries:
                    error_msg = f"Failed to receive after {max_retries} attempts due to {type(e).__name__}"
                    self.debug_log(f"EXCEPTION: {error_msg}")
                    raise ConnectionError(error_msg) from e
                
                self.debug_log(f"Retrying receive after error (attempt {retry_count}/{max_retries})")
                await asyncio.sleep(retry_count * 2)  # Backoff
                
        error_msg = "Failed to receive data after multiple attempts"
        self.debug_log(f"EXCEPTION: {error_msg}")
        raise ConnectionError(error_msg)

    async def reconnect(self):
        self.debug_log("Starting reconnection procedure")
        # Clean up existing connection
        if self.ws:
            try:
                self.debug_log("Closing existing connection")
                await self.ws.close()
            except Exception as e:
                self.debug_log(f"EXCEPTION: Error closing connection during reconnect: {type(e).__name__}: {str(e)}")
            finally:
                self.ws = None
        
        # Attempt to reconnect
        retry_count = 0
        max_reconnect_retries = 5
        
        while retry_count < max_reconnect_retries and not self.connected:
            try:
                self.debug_log(f"Reconnection attempt {retry_count+1}/{max_reconnect_retries}")
                await self.connect()
                
                # Resubscribe if we had an active subscription
                if self.subscription:
                    self.debug_log("Resubscribing after reconnection")
                    try:
                        await self.subscribe(self.subscription)
                        self.debug_log("Resubscription successful")
                    except Exception as e:
                        self.debug_log(f"EXCEPTION: Resubscription failed: {type(e).__name__}: {str(e)}")
                        # Continue even if resubscription fails - the caller will handle it
                
                self.debug_log("Reconnection successful")
                return
            except Exception as e:
                retry_count += 1
                self.debug_log(f"EXCEPTION: Reconnection attempt {retry_count} failed: {type(e).__name__}: {str(e)}")
                if retry_count >= max_reconnect_retries:
                    error_msg = f"Failed to reconnect after {max_reconnect_retries} attempts"
                    self.debug_log(f"EXCEPTION: {error_msg}")
                    raise ConnectionError(error_msg) from e
                
                backoff_delay = 1.0 * retry_count
                self.debug_log(f"Waiting {backoff_delay:.1f}s before next reconnection attempt")
                await asyncio.sleep(backoff_delay)  # Increasing delays
        
        error_msg = "Failed to reconnect after server restart"
        self.debug_log(f"EXCEPTION: {error_msg}")
        raise ConnectionError(error_msg)

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self.connected and self.ws and not self.ws.closed

    @property
    def is_subscribed(self) -> bool:
        """Check if client is subscribed."""
        return self.subscribed and self.is_connected