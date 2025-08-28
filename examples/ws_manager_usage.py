"""
Example usage of the unified WebSocket manager.

This example demonstrates how to use the new WebSocket manager
to connect to Polymarket's streaming API and process messages.
"""

import asyncio
import logging
import os
from typing import Any

from dotenv import load_dotenv

from inkedup_bot.ws_manager import create_ws_manager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def on_connect() -> None:
    """Callback for when WebSocket connects."""
    logger.info("WebSocket connected!")


def on_disconnect() -> None:
    """Callback for when WebSocket disconnects."""
    logger.info("WebSocket disconnected!")


def on_error(error: Exception) -> None:
    """Callback for WebSocket errors."""
    logger.error(f"WebSocket error: {error}")


def on_message(data: dict[str, Any]) -> None:
    """Callback for processed messages."""
    logger.info(f"Processed message: {data}")


async def basic_usage_example() -> None:
    """Basic usage example with market subscriptions."""

    # Get credentials from environment
    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        logger.error("PRIVATE_KEY not found in environment")
        return

    # Create WebSocket manager
    ws_manager = await create_ws_manager(
        private_key=private_key,
        signature_type="EOA",
        ws_url="wss://ws-subscriptions-clob.polymarket.com/ws",
        max_reconnect_attempts=5,
        reconnect_delay=1.0,
    )

    # Add callbacks
    ws_manager.add_connect_callback(on_connect)
    ws_manager.add_disconnect_callback(on_disconnect)
    ws_manager.add_error_callback(on_error)
    ws_manager.add_message_callback(on_message)

    try:
        # Start the manager
        await ws_manager.start()

        # Subscribe to market data
        market_address = (
            "0x1234567890abcdef1234567890abcdef12345678"  # Replace with actual market
        )
        await ws_manager.subscribe_market(
            market_address, ["trade", "book", "price_change"]
        )

        # Keep running for 30 seconds
        await asyncio.sleep(30)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await ws_manager.stop()


async def main() -> None:
    """Run basic example."""
    print("WebSocket Manager Usage Example")
    print("===============================")
    await basic_usage_example()


if __name__ == "__main__":
    asyncio.run(main())
