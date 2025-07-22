from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable

import aiohttp
import backoff

from .config import BotConfig

log = logging.getLogger("ws")


class WSStream:
    """
    Market channel WebSocket stream.
    - Subscribes to list of token_ids
    - Emits order book snapshot/delta events to callback
    """

    def __init__(
        self, cfg: BotConfig, token_ids: list[str], on_book: Callable[[dict], None]
    ):
        self.cfg = cfg
        self.token_ids = token_ids
        self.on_book = on_book
        self._ws = None
        self._stop = asyncio.Event()

    @backoff.on_exception(
        backoff.expo, (aiohttp.ClientError, asyncio.TimeoutError), max_time=300
    )
    async def _connect(self):
        """Establish WebSocket connection with comprehensive error handling."""
        url = self.cfg.ws_url.rstrip("/") + "/ws/"
        
        try:
            # Create session with timeout
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            session = aiohttp.ClientSession(timeout=timeout)
            
            # Connect with retry and timeout
            self._ws = await session.ws_connect(
                url,
                heartbeat=25,
                compress=True,
                max_msg_size=0
            )
            log.info("WS connected successfully.")
            
            # Subscribe to market data
            subscribe = {
                "type": "subscribe",
                "channel": "market",
                "tokens": self.token_ids,
                "initial_dump": True,
            }
            await self._ws.send_str(json.dumps(subscribe))
            
            # Message processing loop with timeout
            while not self._stop.is_set():
                try:
                    msg = await asyncio.wait_for(
                        self._ws.receive(),
                        timeout=30.0  # 30 second timeout for messages
                    )
                    
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_message(msg)
                    elif msg.type == aiohttp.WSMsgType.BINARY:
                        log.debug("Received binary message, ignoring")
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        raise ConnectionError("WS closed/error - triggering reconnect")
                    elif msg.type == aiohttp.WSMsgType.PONG:
                        log.debug("Received WS pong")
                    else:
                        log.debug(f"Received unexpected message type: {msg.type}")
                        
                except asyncio.TimeoutError:
                    log.warning("WebSocket receive timeout - sending ping")
                    if self._ws and not self._ws.closed:
                        await self._ws.ping()
                        
                except Exception as e:
                    log.error(f"Error processing WebSocket message: {e}")
                    raise
                    
        except asyncio.TimeoutError:
            log.error("WebSocket connection timeout")
            raise
        except aiohttp.ClientError as e:
            log.error(f"WebSocket client error: {e}")
            raise
        except Exception as e:
            log.error(f"Unexpected WebSocket connection error: {e}")
            raise
        finally:
            if session and not session.closed:
                await session.close()

    async def run(self):
        while not self._stop.is_set():
            try:
                await self._connect()
            except Exception as e:
                log.warning(f"WS reconnect due to: {e}")
                await asyncio.sleep(2)

    async def stop(self):
        self._stop.set()
        if self._ws:
            await self._ws.close()
