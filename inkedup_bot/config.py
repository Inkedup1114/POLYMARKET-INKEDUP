import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()


@dataclass(slots=True)
class BotConfig:
    """Comprehensive configuration for the Polymarket trading bot."""
    
    # API Configuration
    api_base: str = os.getenv("POLYMARKET_API_BASE", "https://clob.polymarket.com")
    ws_url: str = os.getenv(
        "POLYMARKET_WS_URL", "wss://ws-subscriptions-clob.polymarket.com"
    )
    public_key: str | None = os.getenv("PUBLIC_KEY")
    private_key: str | None = os.getenv("PRIVATE_KEY")
    
    # API Client Settings
    api_timeout_seconds: int = int(os.getenv("API_TIMEOUT_SECONDS", 30))
    api_retry_attempts: int = int(os.getenv("API_RETRY_ATTEMPTS", 3))
    api_retry_delay_seconds: int = int(os.getenv("API_RETRY_DELAY_SECONDS", 1))
    
    # Database Configuration
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///bot_data.db")
    database_echo: bool = os.getenv("DATABASE_ECHO", "false").lower() == "true"
    database_pool_size: int = int(os.getenv("DATABASE_POOL_SIZE", 5))
    
    # Logging Configuration
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_format: str = os.getenv(
        "LOG_FORMAT", 
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    log_file: str | None = os.getenv("LOG_FILE")
    log_max_bytes: int = int(os.getenv("LOG_MAX_BYTES", 10485760))  # 10MB
    log_backup_count: int = int(os.getenv("LOG_BACKUP_COUNT", 5))
    
    # Market Filtering & Thresholds
    market_filter: List[str] = field(default_factory=list)
    min_liquidity: float = float(os.getenv("MIN_LIQUIDITY", 0))
    min_volume_24h: float = float(os.getenv("MIN_VOLUME_24H", 0))
    min_spread_bps: int = int(os.getenv("MIN_SPREAD_BPS", 0))
    max_spread_bps: int = int(os.getenv("MAX_SPREAD_BPS", 10000))
    spread_alert_bps: int = int(os.getenv("SPREAD_ALERT_BPS", 0))
    
    # Risk Management
    position_risk_cap: float = float(os.getenv("POSITION_RISK_CAP_USD", 0))
    global_risk_cap: float = float(os.getenv("GLOBAL_RISK_CAP_USD", 0))
    market_risk_cap: float = float(os.getenv("MARKET_RISK_CAP_USD", 0))
    per_market_risk_cap: float = float(os.getenv("PER_MARKET_RISK_CAP_USD", 0))
    per_outcome_risk_cap: float = float(os.getenv("PER_OUTCOME_RISK_CAP_USD", 0))
    max_position_size: float = float(os.getenv("MAX_POSITION_SIZE_USD", 1000))
    max_order_size: float = float(os.getenv("MAX_ORDER_SIZE_USD", 100))
    
    # Scanner Configuration
    market_cache_ttl: int = int(os.getenv("MARKET_CACHE_TTL", 300))
    book_batch_size: int = int(os.getenv("BOOK_BATCH_SIZE", 120))
    scan_interval_seconds: int = int(os.getenv("SCAN_INTERVAL_SECONDS", 30))
    max_markets_per_scan: int = int(os.getenv("MAX_MARKETS_PER_SCAN", 15))
    
    # WebSocket Configuration
    ws_enabled: bool = os.getenv("WS_ENABLED", "false").lower() == "true"
    ws_reconnect_attempts: int = int(os.getenv("WS_RECONNECT_ATTEMPTS", 5))
    ws_reconnect_delay_seconds: int = int(os.getenv("WS_RECONNECT_DELAY_SECONDS", 5))
    
    # Order Execution Parameters
    default_order_type: str = os.getenv("DEFAULT_ORDER_TYPE", "GTC")
    order_timeout_seconds: int = int(os.getenv("ORDER_TIMEOUT_SECONDS", 30))
    slippage_tolerance_bps: int = int(os.getenv("SLIPPAGE_TOLERANCE_BPS", 50))
    price_precision: int = int(os.getenv("PRICE_PRECISION", 4))
    size_precision: int = int(os.getenv("SIZE_PRECISION", 4))
    
    # Market Making Configuration
    mm_enabled: bool = os.getenv("MM_ENABLED", "false").lower() == "true"
    mm_target_spread_bps: float = float(os.getenv("MM_TARGET_SPREAD_BPS", 50))
    mm_max_position_size: float = float(os.getenv("MM_MAX_POSITION_SIZE_USD", 100))
    mm_quote_size: float = float(os.getenv("MM_QUOTE_SIZE_USD", 10))
    mm_min_spread_bps: float = float(os.getenv("MM_MIN_SPREAD_BPS", 20))
    mm_max_spread_bps: float = float(os.getenv("MM_MAX_SPREAD_BPS", 5000))
    mm_inventory_skew_factor: float = float(os.getenv("MM_INVENTORY_SKEW_FACTOR", 0.1))
    mm_edge_bps: float = float(os.getenv("MM_EDGE_BPS", 5))
    mm_min_liquidity: float = float(os.getenv("MM_MIN_LIQUIDITY", 1000))
    mm_enabled_markets: List[str] = field(default_factory=list)
    
    # Snapshot Service Configuration
    snapshot_interval_seconds: int = int(os.getenv("SNAPSHOT_INTERVAL_SECONDS", 300))
    snapshot_retention_days: int = int(os.getenv("SNAPSHOT_RETENTION_DAYS", 7))
    snapshot_enabled: bool = os.getenv("SNAPSHOT_ENABLED", "true").lower() == "true"
    
    # Health Check Configuration
    health_check_enabled: bool = os.getenv("HEALTH_CHECK_ENABLED", "true").lower() == "true"
    health_check_interval_seconds: int = int(os.getenv("HEALTH_CHECK_INTERVAL_SECONDS", 60))
    
    def __post_init__(self) -> None:
        """Post-initialization processing for configuration."""
        # Parse market filter
        filt = os.getenv("MARKET_FILTER", "").strip()
        if filt:
            self.market_filter = [s.strip() for s in filt.split(",")]
        
        # Parse market making enabled markets
        mm_markets = os.getenv("MM_ENABLED_MARKETS", "").strip()
        if mm_markets:
            self.mm_enabled_markets = [s.strip() for s in mm_markets.split(",")]
        
        # Validate configuration
        self._validate_configuration()
    
    def _validate_configuration(self) -> None:
        """Validate configuration parameters."""
        if self.api_timeout_seconds <= 0:
            raise ValueError("API_TIMEOUT_SECONDS must be positive")
        if self.api_retry_attempts < 0:
            raise ValueError("API_RETRY_ATTEMPTS must be non-negative")
        if self.scan_interval_seconds <= 0:
            raise ValueError("SCAN_INTERVAL_SECONDS must be positive")
        if self.max_position_size < 0:
            raise ValueError("MAX_POSITION_SIZE_USD must be non-negative")
        if self.max_order_size < 0:
            raise ValueError("MAX_ORDER_SIZE_USD must be non-negative")
