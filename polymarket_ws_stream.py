#!/usr/bin/env python3
"""
Polymarket WebSocket Streaming Client

Production-ready script for connecting to Polymarket's WebSocket API with
automatic API key derivation and market/user channel subscription.

Usage:
    python polymarket_ws_stream.py
    HOST=wss://ws-subscriptions-clob.polymarket.com/ws python polymarket_ws_stream.py
"""

import asyncio
import json
import logging
import os
import signal
import sys
from typing import Any, Dict, Optional, Union

import aiohttp
import backoff
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Environment variables with defaults
ENV_VARS = {
    'HOST': 'wss://ws-subscriptions-clob.polymarket.com/ws',
    'KEY': None,
    'CHAIN_ID': 137,  # Polygon mainnet
    'POLYMARKET_PROXY_ADDRESS': None,
    'SIGNATURE_TYPE': None,
    'LOG_LEVEL': 'INFO'
}


class PolymarketWSClient:
    """Polymarket WebSocket client with automatic reconnection and graceful shutdown."""
    
    def __init__(self) -> None:
        self.ws_url = str(os.getenv('HOST') or ENV_VARS['HOST'])
        self.api_key = os.getenv('KEY') or ENV_VARS['KEY']
        self.chain_id = int(os.getenv('CHAIN_ID') or str(ENV_VARS['CHAIN_ID']))
        self.proxy_address = os.getenv('POLYMARKET_PROXY_ADDRESS') or ENV_VARS['POLYMARKET_PROXY_ADDRESS']
        self.signature_type = os.getenv('SIGNATURE_TYPE') or ENV_VARS['SIGNATURE_TYPE']
        
        # Configure logging level
        log_level = str(os.getenv('LOG_LEVEL') or str(ENV_VARS['LOG_LEVEL']))
        logging.getLogger().setLevel(getattr(logging, log_level.upper()))
        
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._stop_event = asyncio.Event()
        self._reconnect_attempt = 0
        self._max_reconnect_delay = 30  # seconds
        
    async def derive_api_key(self) -> str:
        """Derive Polymarket API key using py_clob_client with automatic initialization."""
        try:
            # Use provided API key if available
            if self.api_key:
                logger.info("Using provided API key")
                return str(self.api_key)
            
            # Get credentials from environment
            public_key = os.getenv('PUBLIC_KEY')
            private_key = os.getenv('PRIVATE_KEY')
            api_base = os.getenv('POLYMARKET_API_BASE', 'https://clob.polymarket.com')
            
            if not public_key or not private_key:
                raise ValueError(
                    "PUBLIC_KEY and PRIVATE_KEY environment variables are required "
                    "when KEY is not provided"
                )
            
            # Determine signature type
            sig_type = self.signature_type or "EOA"
            if isinstance(sig_type, str):
                # Map string signature types to py_clob_client constants
                sig_type_map = {
                    "EOA": 0,
                    "POLY_GNOSIS_SAFE": 1,
                    "POLY_PROXY": 2
                }
                sig_type_value = sig_type_map.get(sig_type, 0)
            else:
                sig_type_value = int(sig_type)
            
            # Initialize ClobClient based on configuration
            if self.proxy_address:
                logger.info(f"Using proxy address: {self.proxy_address}")
                client = ClobClient(
                    host=api_base,
                    chain_id=self.chain_id,
                    key=private_key,
                    signature_type=sig_type_value,
                    funder=self.proxy_address
                )
            else:
                logger.info("Using standard EOA initialization")
                client = ClobClient(
                    host=api_base,
                    chain_id=self.chain_id,
                    key=private_key,
                    signature_type=sig_type_value
                )
            
            # Create or get API credentials
            creds: ApiCreds = client.create_or_derive_api_creds()
            api_key = str(creds.api_key)
            
            logger.info("Successfully derived API key")
            return api_key
            
        except Exception as e:
            logger.error(f"Failed to derive API key: {e}")
            raise
    
    @backoff.on_exception(
        backoff.expo,
        (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError),
        max_time=300,
        max_value=30
    )
    async def _connect_websocket(self) -> None:
        """Establish WebSocket connection with authentication."""
        try:
            # Create session with appropriate timeout
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self._session = aiohttp.ClientSession(timeout=timeout)
            
            # Prepare headers with API key
            headers = {
                'Authorization': f'Bearer {await self.derive_api_key()}',
                'User-Agent': 'PolymarketWSClient/1.0'
            }
            
            logger.info(f"Connecting to WebSocket: {self.ws_url}")
            self._ws = await self._session.ws_connect(
                self.ws_url,
                headers=headers,
                heartbeat=25,
                compress=True,
                max_msg_size=0
            )
            
            logger.info("WebSocket connected successfully")
            
            # Subscribe to market and user channels
            await self._subscribe_channels()
            
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            if self._session and not self._session.closed:
                await self._session.close()
            raise
    
    async def _subscribe_channels(self) -> None:
        """Subscribe to market and user channels."""
        if not self._ws:
            raise ConnectionError("WebSocket not connected")
            
        subscriptions = [
            {"type": "subscribe", "channel": "market"},
            {"type": "subscribe", "channel": "user"}
        ]
        
        for sub in subscriptions:
            await self._ws.send_str(json.dumps(sub))
            logger.info(f"Subscribed to channel: {sub['channel']}")
    
    async def _handle_message(self, msg: aiohttp.WSMessage) -> None:
        """Handle incoming WebSocket messages."""
        if msg.type == aiohttp.WSMsgType.TEXT:
            try:
                # Parse and print as single-line JSON
                data = json.loads(msg.data)
                print(json.dumps(data, separators=(',', ':')), flush=True)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse message: {e}")
                
        elif msg.type == aiohttp.WSMsgType.BINARY:
            logger.debug("Received binary message, ignoring")
            
        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
            raise ConnectionError("WebSocket connection closed or error")
            
        elif msg.type == aiohttp.WSMsgType.PONG:
            logger.debug("Received WebSocket pong")
    
    async def _message_loop(self) -> None:
        """Main message processing loop."""
        if not self._ws:
            raise ConnectionError("WebSocket not connected")
            
        while not self._stop_event.is_set():
            try:
                msg = await asyncio.wait_for(
                    self._ws.receive(),
                    timeout=30.0
                )
                await self._handle_message(msg)
                
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                if self._ws and not self._ws.closed:
                    await self._ws.ping()
                    
            except Exception as e:
                logger.error(f"Error in message loop: {e}")
                raise
    
    async def run(self) -> None:
        """Main run loop with reconnection logic."""
        logger.info("Starting Polymarket WebSocket client")
        
        while not self._stop_event.is_set():
            try:
                await self._connect_websocket()
                self._reconnect_attempt = 0
                
                # Process messages
                await self._message_loop()
                
            except Exception as e:
                logger.warning(f"Connection lost, attempting reconnect: {e}")
                self._reconnect_attempt += 1
                
                # Cleanup
                if self._ws and not self._ws.closed:
                    await self._ws.close()
                if self._session and not self._session.closed:
                    await self._session.close()
                
                # Exponential backoff
                delay = min(2 ** self._reconnect_attempt, self._max_reconnect_delay)
                logger.info(f"Reconnecting in {delay} seconds...")
                await asyncio.sleep(delay)
    
    async def stop(self) -> None:
        """Graceful shutdown."""
        logger.info("Initiating graceful shutdown...")
        self._stop_event.set()
        
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        
        logger.info("WebSocket client stopped")


async def main() -> None:
    """Main entry point."""
    client = PolymarketWSClient()
    
    # Setup signal handlers
    def signal_handler(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(client.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await client.run()
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt")
    finally:
        await client.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass