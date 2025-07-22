"""
Market data integration for risk management system.
Provides real-time market data, volatility calculations, liquidity analysis, and market status checking.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import time
from collections import defaultdict

from ..ws_stream import WSStream
from ..order_client import OrderClient
from ..config import BotConfig

logger = logging.getLogger(__name__)


@dataclass
class MarketData:
    """Market data snapshot for risk calculations."""
    market_id: str
    price: float
    volume_24h: float
    spread: float
    depth_5_pct: float
    depth_10_pct: float
    last_trade_time: datetime
    bid_ask_spread: float
    mid_price: float


@dataclass
class VolatilityMetrics:
    """Volatility calculation results."""
    market_id: str
    volatility_1h: float
    volatility_24h: float
    volatility_7d: float
    atr_14d: float
    risk_adjustment_factor: float
    last_updated: datetime


@dataclass
class LiquidityMetrics:
    """Liquidity analysis results."""
    market_id: str
    total_liquidity: float
    available_liquidity: float
    slippage_1k: float
    slippage_10k: float
    depth_score: float
    liquidity_ratio: float
    last_updated: datetime


@dataclass
class MarketStatus:
    """Market status information."""
    market_id: str
    is_active: bool
    is_suspended: bool
    is_settled: bool
    settlement_price: Optional[float]
    settlement_time: Optional[datetime]
    last_price_update: datetime
    status_reason: Optional[str]


class MarketDataProvider:
    """Provides real-time market data with caching and fallback mechanisms."""
    
    def __init__(self, ws_stream: WSStream, order_client: OrderClient, config: BotConfig):
        self.ws_stream = ws_stream
        self.order_client = order_client
        self.config = config
        self._cache: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self._cache_ttl = {
            'market_data': 5,  # 5 seconds
            'volatility': 60,  # 1 minute
            'liquidity': 30,   # 30 seconds
            'status': 10      # 10 seconds
        }
        
    async def get_market_data(self, market_id: str) -> Optional[MarketData]:
        """Get current market data with caching."""
        cache_key = f"market_data:{market_id}"
        cached = self._get_from_cache(cache_key)
        
        if cached and not self._is_expired(cached, self._cache_ttl['market_data']):
            return cached['data']
            
        try:
            # Get market data from order client
            market_info = await self._get_market_info(market_id)
            if market_info:
                market_data = self._parse_market_info(market_info)
                self._set_cache(cache_key, market_data)
                return market_data
                
        except Exception as e:
            logger.error(f"Failed to get market data for {market_id}: {e}")
            
        # Return stale data if available
        if cached:
            logger.warning(f"Using stale market data for {market_id}")
            return cached['data']
            
        return None
    
    async def _get_market_info(self, market_id: str) -> Optional[Dict[str, Any]]:
        """Get market information from order client."""
        try:
            # This would need to be implemented based on actual API
            # For now, return mock data structure
            return {
                'market_id': market_id,
                'price': 0.5,
                'volume24h': 100000.0,
                'spread': 0.01,
                'lastTradeTime': datetime.now().isoformat(),
                'bestBid': 0.49,
                'bestAsk': 0.51
            }
        except Exception as e:
            logger.debug(f"Market info unavailable for {market_id}: {e}")
            return None
    
    def _parse_market_info(self, data: Dict[str, Any]) -> MarketData:
        """Parse market information into MarketData."""
        return MarketData(
            market_id=data.get('market_id', ''),
            price=float(data.get('price', 0)),
            volume_24h=float(data.get('volume24h', 0)),
            spread=float(data.get('spread', 0)),
            depth_5_pct=0.0,  # Placeholder
            depth_10_pct=0.0,  # Placeholder
            last_trade_time=datetime.now(),
            bid_ask_spread=float(data.get('spread', 0)),
            mid_price=(float(data.get('bestBid', 0)) + float(data.get('bestAsk', 0))) / 2
        )
    
    def _get_from_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """Get data from cache."""
        return self._cache.get(key)
    
    def _set_cache(self, key: str, data: Any):
        """Set data in cache with timestamp."""
        self._cache[key] = {
            'data': data,
            'timestamp': time.time()
        }
    
    def _is_expired(self, cached: Dict[str, Any], ttl_seconds: int) -> bool:
        """Check if cached data is expired."""
        return time.time() - cached['timestamp'] > ttl_seconds


class VolatilityCalculator:
    """Calculates volatility metrics for risk adjustment."""
    
    def __init__(self, market_data_provider: MarketDataProvider):
        self.market_data_provider = market_data_provider
        self._price_history: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
        self._max_history_length = 1000
        
    async def calculate_volatility(self, market_id: str) -> Optional[VolatilityMetrics]:
        """Calculate volatility metrics for a market."""
        cache_key = f"volatility:{market_id}"
        cached = self.market_data_provider._get_from_cache(cache_key)
        
        if cached and not self.market_data_provider._is_expired(cached, 60):
            return cached['data']
            
        try:
            # Get current market data
            market_data = await self.market_data_provider.get_market_data(market_id)
            if not market_data:
                return None
                
            # Update price history with mock data for now
            self._update_price_history(market_id, market_data.price)
            
            # Calculate mock volatility metrics
            volatility_1h = 0.05  # 5% hourly volatility
            volatility_24h = 0.15  # 15% daily volatility
            volatility_7d = 0.25  # 25% weekly volatility
            atr_14d = 0.10  # 10% ATR
            
            # Calculate risk adjustment factor
            risk_adjustment_factor = min(2.0, max(0.5, volatility_24h / 0.15))
            
            metrics = VolatilityMetrics(
                market_id=market_id,
                volatility_1h=volatility_1h,
                volatility_24h=volatility_24h,
                volatility_7d=volatility_7d,
                atr_14d=atr_14d,
                risk_adjustment_factor=risk_adjustment_factor,
                last_updated=datetime.now()
            )
            
            self.market_data_provider._set_cache(cache_key, metrics)
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to calculate volatility for {market_id}: {e}")
            return None
    
    def _update_price_history(self, market_id: str, price: float):
        """Update price history for volatility calculations."""
        now = time.time()
        self._price_history[market_id].append((price, now))
        
        # Limit history length
        if len(self._price_history[market_id]) > self._max_history_length:
            self._price_history[market_id] = self._price_history[market_id][-self._max_history_length:]


class LiquidityAnalyzer:
    """Analyzes liquidity for position sizing."""
    
    def __init__(self, market_data_provider: MarketDataProvider):
        self.market_data_provider = market_data_provider
        
    async def analyze_liquidity(self, market_id: str) -> Optional[LiquidityMetrics]:
        """Analyze liquidity for a market."""
        cache_key = f"liquidity:{market_id}"
        cached = self.market_data_provider._get_from_cache(cache_key)
        
        if cached and not self.market_data_provider._is_expired(cached, 30):
            return cached['data']
            
        try:
            # Get market data
            market_data = await self.market_data_provider.get_market_data(market_id)
            if not market_data:
                return None
                
            # Calculate mock liquidity metrics
            total_liquidity = market_data.volume_24h
            available_liquidity = total_liquidity * 0.1  # Assume 10% available
            slippage_1k = 0.001  # 0.1% slippage for $1k
            slippage_10k = 0.005  # 0.5% slippage for $10k
            depth_score = min(1.0, available_liquidity / 10000)
            liquidity_ratio = available_liquidity / max(total_liquidity, 1)
            
            metrics = LiquidityMetrics(
                market_id=market_id,
                total_liquidity=total_liquidity,
                available_liquidity=available_liquidity,
                slippage_1k=slippage_1k,
                slippage_10k=slippage_10k,
                depth_score=depth_score,
                liquidity_ratio=liquidity_ratio,
                last_updated=datetime.now()
            )
            
            self.market_data_provider._set_cache(cache_key, metrics)
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to analyze liquidity for {market_id}: {e}")
            return None


class MarketStatusChecker:
    """Checks market status for validation."""
    
    def __init__(self, market_data_provider: MarketDataProvider):
        self.market_data_provider = market_data_provider
        
    async def check_market_status(self, market_id: str) -> Optional[MarketStatus]:
        """Check market status."""
        cache_key = f"status:{market_id}"
        cached = self.market_data_provider._get_from_cache(cache_key)
        
        if cached and not self.market_data_provider._is_expired(cached, 10):
            return cached['data']
            
        try:
            # Mock market status - in real implementation, this would check API
            status = MarketStatus(
                market_id=market_id,
                is_active=True,
                is_suspended=False,
                is_settled=False,
                settlement_price=None,
                settlement_time=None,
                last_price_update=datetime.now(),
                status_reason=None
            )
            
            self.market_data_provider._set_cache(cache_key, status)
            return status
            
        except Exception as e:
            logger.error(f"Failed to check market status for {market_id}: {e}")
            return None


# Factory function to create market data components
def create_market_data_components(ws_stream: WSStream, order_client: OrderClient, config: BotConfig):
    """Create and configure market data components."""
    provider = MarketDataProvider(ws_stream, order_client, config)
    volatility_calc = VolatilityCalculator(provider)
    liquidity_analyzer = LiquidityAnalyzer(provider)
    status_checker = MarketStatusChecker(provider)
    
    return {
        'provider': provider,
        'volatility_calc': volatility_calc,
        'liquidity_analyzer': liquidity_analyzer,
        'status_checker': status_checker
    }