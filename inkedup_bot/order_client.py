from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any, cast
from datetime import datetime, timedelta

import backoff
from .config import BotConfig
from .state import StateManager

log = logging.getLogger("order_client")


class UnavailableClientError(Exception):
    """Raised when attempting to use the CLOB client while py-clob-client is not available."""
    pass


class StubClobClient:
    """No-op stub client that raises UnavailableClientError for any method call."""
    
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Accept any arguments to match ClobClient signature
        pass
    
    def create_order(self, *args: Any, **kwargs: Any) -> Any:
        raise UnavailableClientError("py-clob-client not available")
    
    def cancel_all(self, *args: Any, **kwargs: Any) -> list[Any]:
        raise UnavailableClientError("py-clob-client not available")
    
    def get_positions(self, *args: Any, **kwargs: Any) -> list[Any]:
        raise UnavailableClientError("py-clob-client not available")
    
    def __getattr__(self, name: str) -> Any:
        """Catch-all for any other method calls."""
        def method(*args: Any, **kwargs: Any) -> Any:
            raise UnavailableClientError("py-clob-client not available")
        return method


try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs

    PY_CLOB_CLIENT_INSTALLED = True
    log.debug("py-clob-client successfully imported")
except ImportError:
    ClobClient = StubClobClient  # Use stub instead of None
    OrderArgs = None  # type: ignore
    PY_CLOB_CLIENT_INSTALLED = False
    log.debug("py-clob-client not available; using stub client")


class OrderClient:
    def __init__(self, cfg: BotConfig, state: StateManager):
        self.cfg = cfg
        self.state = state
        
        if not PY_CLOB_CLIENT_INSTALLED:
            log.debug("Using stub client due to missing py-clob-client")
            self.client = StubClobClient()
        elif cfg.private_key:
            try:
                self.client = ClobClient(
                    host=self.cfg.api_base,
                    key=cfg.private_key,
                )
                log.debug("ClobClient initialized successfully")
            except Exception as e:
                log.error(f"Failed to initialize ClobClient: {e}")
                self.client = StubClobClient()
        else:
            log.debug("No private key provided, using stub client")
            self.client = StubClobClient()

    def ready(self) -> bool:
        return PY_CLOB_CLIENT_INSTALLED and self.client is not None and not isinstance(self.client, StubClobClient)

    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=3,
        max_time=30,
        giveup=lambda e: isinstance(e, ValueError) and "Invalid" in str(e)
    )
    def place_limit(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
        tif: str = "GTC",
        market_slug: str | None = None,
        outcome_type: str | None = None,
        notional_value: float | None = None,
        risk: Any | None = None,
    ) -> dict[str, Any] | None:
        """Place a limit order with retry logic and comprehensive error handling."""
        if not self.ready():
            log.debug("Trading functionality not available - py-clob-client not installed")
            return None
            
        if OrderArgs is None:
            log.debug("OrderArgs not available - py-clob-client not installed")
            return None
            
        if price <= 0 or size <= 0:
            log.error("Invalid price/size.")
            return None
            
        # Validate token_id
        if not token_id or not isinstance(token_id, str):
            log.error("Invalid token_id provided.")
            return None
            
        try:
            # Add timeout context
            order_args = OrderArgs(
                price=round(price, 4),
                size=round(size, 4),
                side=side.lower(),
                token_id=token_id,
            )
            
            # Execute order with timeout
            order = self.client.create_order(order_args)
            
            if order:
                order_dict = asdict(order)
                log.info(
                    f"Placed {side.upper()} size={size} price={price} token={token_id} id={order_dict.get('id')}"
                )
                
                # Ensure state is updated
                try:
                    self.state.add_order(order_dict)
                except Exception as e:
                    log.error(f"Failed to add order to state: {e}")
                
                # Atomic risk recording
                if risk and notional_value is not None:
                    try:
                        risk.record_trade(
                            token_id,
                            notional_value,
                            market_slug,
                            outcome_type,
                        )
                    except Exception as e:
                        log.error(f"Failed to record trade in risk manager: {e}")
                
                return order_dict
            else:
                log.warning("Order creation returned None")
                return None
                
        except UnavailableClientError:
            log.debug("Trading functionality not available - py-clob-client not installed")
            return None
        except ValueError as e:
            log.error(f"Order validation error: {e}")
            return None
        except ConnectionError as e:
            log.error(f"Connection error during order placement: {e}")
            return None
        except TimeoutError as e:
            log.error(f"Order placement timeout: {e}")
            return None
        except Exception as e:
            log.error(f"Unexpected order failure: {type(e).__name__}: {e}", exc_info=True)
            return None

    def cancel_all(self) -> list[Any]:
        if not self.ready():
            log.debug("Cancel all not available - py-clob-client not installed")
            return []
        try:
            res = self.client.cancel_all()
            log.info(f"Cancelled {len(res)} orders")
            return cast(list[Any], res)
        except UnavailableClientError:
            log.debug("Cancel all not available - py-clob-client not installed")
            return []
        except Exception as e:
            log.error(f"Cancel error: {e}")
            return []

    def get_positions(self) -> list[Any]:
        if not self.ready():
            log.debug("Get positions not available - py-clob-client not installed")
            return []
        try:
            # Type ignore because py-clob-client may not have perfect stubs
            positions = self.client.get_positions()  # type: ignore
            return cast(list[Any], positions)
        except UnavailableClientError:
            log.debug("Get positions not available - py-clob-client not installed")
            return []
        except Exception as e:
            log.error(f"Positions error: {e}")
            return []

    def exposure_usd(self) -> float:
        total = 0.0
        for p in self.get_positions():
            try:
                # Handle both dataclasses and dicts
                if hasattr(p, "__dataclass_fields__"):
                    p_dict = asdict(p)
                    total += float(p_dict.get("usd_value", 0))
                elif isinstance(p, dict):
                    total += float(p.get("usd_value", 0))
            except (ValueError, TypeError):
                pass
        return total
