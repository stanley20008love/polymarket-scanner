"""WebSocket Client for real-time Polymarket data"""
import json
import logging
import threading
import time
from typing import Callable, Optional

import websocket

logger = logging.getLogger(__name__)


class PolymarketWebSocket:
    """
    WebSocket client for real-time Polymarket market data.
    
    Connects to Polymarket's CLOB WebSocket to receive:
    - Price updates
    - Order book changes
    - Trade executions
    """
    
    def __init__(self, config: dict):
        self.ws_url = config.get("polymarket_ws_url", "wss://ws-subscriptions-clob.polymarket.com/ws")
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._callbacks: dict[str, list[Callable]] = {}
        self._reconnect_count = 0
        self._max_reconnects = 10
    
    def on_price_update(self, callback: Callable):
        """Register callback for price updates"""
        self._callbacks.setdefault("price_update", []).append(callback)
    
    def on_book_update(self, callback: Callable):
        """Register callback for order book updates"""
        self._callbacks.setdefault("book_update", []).append(callback)
    
    def on_trade(self, callback: Callable):
        """Register callback for trade events"""
        self._callbacks.setdefault("trade", []).append(callback)
    
    def connect(self, token_ids: list[str] = None):
        """Connect to WebSocket and subscribe to markets"""
        self._running = True
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                msg_type = data.get("type", "")
                
                if msg_type == "price_change":
                    self._dispatch("price_update", data)
                elif msg_type == "book_update":
                    self._dispatch("book_update", data)
                elif msg_type == "trade":
                    self._dispatch("trade", data)
                else:
                    logger.debug(f"Unknown message type: {msg_type}")
                    
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received: {message[:100]}")
            except Exception as e:
                logger.error(f"Error processing message: {e}")
        
        def on_error(ws, error):
            logger.error(f"WebSocket error: {error}")
        
        def on_close(ws, close_status_code, close_msg):
            logger.info(f"WebSocket closed: {close_status_code} - {close_msg}")
            if self._running and self._reconnect_count < self._max_reconnects:
                self._reconnect_count += 1
                wait = min(2 ** self._reconnect_count, 30)
                logger.info(f"Reconnecting in {wait}s (attempt {self._reconnect_count})")
                time.sleep(wait)
                self.connect(token_ids)
        
        def on_open(ws):
            logger.info("WebSocket connected")
            self._reconnect_count = 0
            
            # Subscribe to markets
            if token_ids:
                subscribe_msg = {
                    "type": "subscribe",
                    "tokens": token_ids
                }
                ws.send(json.dumps(subscribe_msg))
                logger.info(f"Subscribed to {len(token_ids)} tokens")
        
        def run_ws():
            self._ws = websocket.WebSocketApp(
                self.ws_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )
            self._ws.run_forever(ping_interval=30, ping_timeout=10)
        
        self._thread = threading.Thread(target=run_ws, daemon=True)
        self._thread.start()
    
    def disconnect(self):
        """Disconnect from WebSocket"""
        self._running = False
        if self._ws:
            self._ws.close()
        logger.info("WebSocket disconnected")
    
    def _dispatch(self, event_type: str, data: dict):
        """Dispatch event to registered callbacks"""
        for callback in self._callbacks.get(event_type, []):
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Callback error for {event_type}: {e}")
    
    @property
    def is_connected(self) -> bool:
        return self._ws is not None and self._running
