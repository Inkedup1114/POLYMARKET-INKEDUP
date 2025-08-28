import os
import re
from typing import Annotated, Any, Literal

from pydantic import (
    AnyUrl,
    Field,
    PositiveFloat,
    PositiveInt,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings

# Define custom type aliases for pydantic v2
NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeFloat = Annotated[float, Field(ge=0)]

from dotenv import load_dotenv

load_dotenv()


class BotConfig(BaseSettings):
    """
    Comprehensive configuration for the Polymarket trading bot with pydantic validation.

    All parameters can be set via environment variables or constructor arguments.

    **Environment Variables:**

    Required:
    - `PUBLIC_KEY`: Ethereum public key for authentication (must be 42 hex characters with '0x' prefix).
    - `PRIVATE_KEY`: Ethereum private key for signing transactions (must be 66 hex characters with '0x' prefix).

    Optional:
    - `POLYMARKET_API_BASE`: Base URL for the Polymarket API (default: "https://clob.polymarket.com").
    - `POLYMARKET_WS_URL`: WebSocket URL for Polymarket subscriptions (default: "wss://ws-subscriptions-clob.polymarket.com").
    - `API_TIMEOUT_SECONDS`: API request timeout in seconds (default: 30).
    - `API_RETRY_ATTEMPTS`: Number of API retry attempts (default: 3).
    - `API_RETRY_DELAY_SECONDS`: Initial delay between retries in seconds (default: 1).
    - `DATABASE_URL`: Database connection URL (default: "sqlite:///bot_data.db").
    - `LOG_LEVEL`: Logging level (default: "INFO").
    - `WS_ENABLED`: Enable WebSocket connections (default: False).
    ... and many more. See the source code for a full list of configurable parameters.
    """

    """
    Comprehensive configuration for the Polymarket trading bot with pydantic validation.
    
    This configuration class provides complete control over all aspects of the bot's
    behavior, from API settings and retry logic to risk management and trading strategies.
    All parameters can be set via environment variables or constructor arguments.
    
    Configuration Categories:
    - **API Configuration**: Connection settings for Polymarket platform
    - **Retry Logic**: Robust error handling and recovery mechanisms  
    - **Database Settings**: Persistent storage configuration
    - **Risk Management**: Position limits and exposure controls
    - **Strategy Parameters**: Trading algorithm settings
    - **Market Data**: Caching and refresh behavior
    - **System Settings**: Logging, monitoring, and performance tuning
    
    Environment Variable Support:
    All configuration parameters support environment variables with SCREAMING_SNAKE_CASE
    naming. For example, `api_base` can be set via `POLYMARKET_API_BASE` environment variable.
    
    Safety Features:
    - Pydantic validation ensures all parameters are within safe ranges
    - Required fields prevent accidental misconfiguration  
    - Type checking catches common errors at startup
    - Sensitive data (private keys) can be loaded from environment only
    
    Example Usage:
        >>> # Basic configuration with environment variables
        >>> import os
        >>> os.environ['PRIVATE_KEY'] = 'your_private_key_here'
        >>> os.environ['PUBLIC_KEY'] = 'your_public_key_here'  
        >>> cfg = BotConfig()
        >>> 
        >>> # Programmatic configuration with overrides
        >>> cfg = BotConfig(
        ...     # Risk management
        ...     global_risk_cap=5000.0,          # $5k max exposure
        ...     max_position_size=500.0,         # $500 per position
        ...     max_market_exposure=1250.0,      # $1.25k per market
        ...     
        ...     # Strategy tuning
        ...     complement_arb_min_deviation=0.02,  # 2% min arbitrage
        ...     spread_alert_bps=100,               # 100 bps spread alerts
        ...     
        ...     # System settings
        ...     market_cache_ttl=300,            # 5-minute cache
        ...     api_retry_attempts=5,            # More retries
        ...     log_level="DEBUG"                # Verbose logging
        ... )
        >>> 
        >>> # Validate configuration
        >>> print(f"Max risk per trade: ${cfg.max_position_size}")
        >>> print(f"Using {'LIVE' if cfg.private_key else 'STUB'} trading")
    
    Security Notes:
    - Private keys should ONLY be set via environment variables
    - Never commit private keys to version control
    - Use stub client (private_key=None) for testing
    - Consider using hardware wallets for production keys
    - Regularly rotate API keys and credentials
    
    Performance Tuning:
    - Increase `book_batch_size` for faster market scanning
    - Reduce `market_cache_ttl` for more responsive signals  
    - Tune `api_retry_*` settings based on network conditions
    - Adjust `complement_arb_*` thresholds based on market volatility
    
    Risk Management Guidelines:
    - Set `global_risk_cap` to maximum acceptable loss
    - Keep `max_position_size` under 10% of total capital
    - Use `max_market_exposure` to prevent concentration risk
    - Start with conservative settings and increase gradually
    - Monitor exposure regularly and adjust limits as needed
    """

    # API Configuration
    api_base: AnyUrl = Field(
        default="https://clob.polymarket.com",
        description="Base URL for the Polymarket API",
        env="POLYMARKET_API_BASE",
    )
    ws_url: AnyUrl = Field(
        default="wss://ws-subscriptions-clob.polymarket.com",
        description="WebSocket URL for Polymarket subscriptions",
        env="POLYMARKET_WS_URL",
    )
    public_key: str = Field(
        ...,
        description="Ethereum public key for authentication",
        env="PUBLIC_KEY",
        min_length=42,
        max_length=42,
    )
    private_key: str = Field(
        ...,
        description="Ethereum private key for signing transactions",
        env="PRIVATE_KEY",
        min_length=66,
        max_length=66,
    )

    # API Client Settings
    api_timeout_seconds: PositiveInt = Field(
        default=30,
        description="API request timeout in seconds",
        env="API_TIMEOUT_SECONDS",
        le=300,
    )
    api_retry_attempts: NonNegativeInt = Field(
        default=3,
        description="Number of API retry attempts",
        env="API_RETRY_ATTEMPTS",
        le=10,
    )
    api_retry_delay_seconds: PositiveInt = Field(
        default=1,
        description="Initial delay between retries in seconds",
        env="API_RETRY_DELAY_SECONDS",
        le=60,
    )

    # Enhanced Retry Configuration
    api_retry_max_delay_seconds: PositiveFloat = Field(
        default=60.0,
        description="Maximum delay between retries in seconds",
        env="API_RETRY_MAX_DELAY_SECONDS",
        le=3600.0,
    )
    api_retry_exponential_base: PositiveFloat = Field(
        default=2.0,
        description="Base for exponential backoff",
        env="API_RETRY_EXPONENTIAL_BASE",
        ge=1.1,
        le=10.0,
    )
    api_retry_jitter_enabled: bool = Field(
        default=True,
        description="Enable jitter in retry delays",
        env="API_RETRY_JITTER_ENABLED",
    )
    api_retry_jitter_range: PositiveFloat = Field(
        default=0.1,
        description="Jitter range as fraction of delay",
        env="API_RETRY_JITTER_RANGE",
        le=1.0,
    )
    api_retry_backoff_strategy: Literal["exponential", "linear", "constant"] = Field(
        default="exponential",
        description="Retry backoff strategy",
        env="API_RETRY_BACKOFF_STRATEGY",
    )

    # Circuit Breaker Configuration
    circuit_breaker_enabled: bool = Field(
        default=True,
        description="Enable circuit breaker pattern for API calls",
        env="CIRCUIT_BREAKER_ENABLED",
    )
    circuit_breaker_failure_threshold: NonNegativeInt = Field(
        default=5,
        description="Number of failures before opening circuit breaker",
        env="CIRCUIT_BREAKER_FAILURE_THRESHOLD",
        le=50,
    )
    circuit_breaker_recovery_timeout: PositiveFloat = Field(
        default=60.0,
        description="Seconds before attempting circuit breaker recovery",
        env="CIRCUIT_BREAKER_RECOVERY_TIMEOUT",
        le=3600.0,
    )
    circuit_breaker_half_open_calls: NonNegativeInt = Field(
        default=3,
        description="Maximum calls allowed in circuit breaker half-open state",
        env="CIRCUIT_BREAKER_HALF_OPEN_CALLS",
        le=20,
    )
    circuit_breaker_success_threshold: NonNegativeInt = Field(
        default=2,
        description="Successes needed to close circuit breaker from half-open",
        env="CIRCUIT_BREAKER_SUCCESS_THRESHOLD",
        le=10,
    )
    circuit_breaker_sliding_window_size: NonNegativeInt = Field(
        default=100,
        description="Number of calls to track in sliding window",
        env="CIRCUIT_BREAKER_SLIDING_WINDOW_SIZE",
        le=1000,
    )
    circuit_breaker_failure_rate_threshold: PositiveFloat = Field(
        default=0.5,
        description="Failure rate threshold (0-1) for opening circuit breaker",
        env="CIRCUIT_BREAKER_FAILURE_RATE_THRESHOLD",
        le=1.0,
    )

    # API Call Timeout Configuration
    api_call_timeout: PositiveFloat = Field(
        default=30.0,
        description="Individual API call timeout in seconds",
        env="API_CALL_TIMEOUT",
        le=300.0,
    )
    api_total_timeout: PositiveFloat = Field(
        default=300.0,
        description="Total timeout for all retry attempts in seconds",
        env="API_TOTAL_TIMEOUT",
        le=3600.0,
    )

    # Database Configuration
    database_url: str = Field(
        default="sqlite:///bot_data.db",
        description="Database connection URL",
        env="DATABASE_URL",
    )
    database_echo: bool = Field(
        default=False, description="Enable database query logging", env="DATABASE_ECHO"
    )

    # Connection Pooling Configuration
    database_pool_enabled: bool = Field(
        default=True,
        description="Enable connection pooling for improved performance",
        env="DATABASE_POOL_ENABLED",
    )
    database_pool_size: PositiveInt = Field(
        default=5,
        description="Database connection pool size (legacy, use min/max for finer control)",
        env="DATABASE_POOL_SIZE",
        le=50,
    )
    database_pool_min_connections: PositiveInt = Field(
        default=2,
        description="Minimum connections to maintain in pool",
        env="DATABASE_POOL_MIN_CONNECTIONS",
        le=20,
    )
    database_pool_max_connections: PositiveInt = Field(
        default=10,
        description="Maximum connections allowed in pool",
        env="DATABASE_POOL_MAX_CONNECTIONS",
        le=50,
    )
    database_connection_timeout: PositiveFloat = Field(
        default=30.0,
        description="Connection acquisition timeout in seconds",
        env="DATABASE_CONNECTION_TIMEOUT",
        le=300.0,
    )
    database_idle_timeout: PositiveFloat = Field(
        default=300.0,
        description="Connection idle timeout in seconds (5 minutes)",
        env="DATABASE_IDLE_TIMEOUT",
        le=3600.0,
    )
    database_max_connection_age: PositiveFloat = Field(
        default=3600.0,
        description="Maximum connection age in seconds (1 hour)",
        env="DATABASE_MAX_CONNECTION_AGE",
        le=86400.0,
    )
    database_health_check_interval: PositiveInt = Field(
        default=60,
        description="Health check interval in seconds",
        env="DATABASE_HEALTH_CHECK_INTERVAL",
        le=3600,
    )
    database_enable_wal_mode: bool = Field(
        default=True,
        description="Enable SQLite WAL mode for better concurrency",
        env="DATABASE_ENABLE_WAL_MODE",
    )
    database_enable_foreign_keys: bool = Field(
        default=True,
        description="Enable foreign key constraints",
        env="DATABASE_ENABLE_FOREIGN_KEYS",
    )

    # Logging Configuration
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level", env="LOG_LEVEL"
    )
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log message format string",
        env="LOG_FORMAT",
        min_length=10,
    )
    log_file: str | None = Field(
        default=None,
        description="Log file path (if None, logs to stdout)",
        env="LOG_FILE",
    )
    log_max_bytes: PositiveInt = Field(
        default=10485760,  # 10MB
        description="Maximum size of log file before rotation",
        env="LOG_MAX_BYTES",
    )
    log_backup_count: PositiveInt = Field(
        default=5,
        description="Number of backup log files to keep",
        env="LOG_BACKUP_COUNT",
        le=100,
    )

    # Market Filtering & Thresholds
    market_filter: list[str] = Field(
        default_factory=list,
        description="List of markets to filter (empty means all markets)",
    )
    min_liquidity: NonNegativeFloat = Field(
        default=0.0,
        description="Minimum liquidity threshold in USD",
        env="MIN_LIQUIDITY",
    )
    min_volume_24h: NonNegativeFloat = Field(
        default=0.0,
        description="Minimum 24h volume threshold in USD",
        env="MIN_VOLUME_24H",
    )
    min_spread_bps: NonNegativeInt = Field(
        default=0,
        description="Minimum spread in basis points",
        env="MIN_SPREAD_BPS",
        le=10000,
    )
    max_spread_bps: PositiveInt = Field(
        default=10000,
        description="Maximum spread in basis points",
        env="MAX_SPREAD_BPS",
        le=10000,
    )
    spread_alert_bps: NonNegativeInt = Field(
        default=0,
        description="Spread threshold for alerts in basis points",
        env="SPREAD_ALERT_BPS",
        le=10000,
    )

    # Complement Arbitrage Configuration
    complement_arb_min_deviation: PositiveFloat = Field(
        default=0.01,
        description="Minimum price deviation for complement arbitrage",
        env="COMPLEMENT_ARB_MIN_DEVIATION",
        ge=0.001,
        le=1.0,
    )
    complement_arb_max_deviation: PositiveFloat = Field(
        default=0.20,
        description="Maximum price deviation for complement arbitrage",
        env="COMPLEMENT_ARB_MAX_DEVIATION",
        ge=0.01,
        le=1.0,
    )
    complement_arb_base_size: PositiveFloat = Field(
        default=10.0,
        description="Base position size for complement arbitrage in USD",
        env="COMPLEMENT_ARB_BASE_SIZE_USD",
    )
    complement_arb_max_size: PositiveFloat = Field(
        default=100.0,
        description="Maximum position size for complement arbitrage in USD",
        env="COMPLEMENT_ARB_MAX_SIZE_USD",
    )
    complement_arb_size_scaling: PositiveFloat = Field(
        default=50.0,
        description="Size scaling factor for complement arbitrage",
        env="COMPLEMENT_ARB_SIZE_SCALING",
    )

    # Risk Management
    position_risk_cap: NonNegativeFloat = Field(
        default=0.0,
        description="Position risk cap in USD (0 = no limit)",
        env="POSITION_RISK_CAP_USD",
    )
    global_risk_cap: NonNegativeFloat = Field(
        default=0.0,
        description="Global risk cap in USD (0 = no limit)",
        env="GLOBAL_RISK_CAP_USD",
    )
    market_risk_cap: NonNegativeFloat = Field(
        default=0.0,
        description="Market risk cap in USD (0 = no limit)",
        env="MARKET_RISK_CAP_USD",
    )
    per_market_risk_cap: NonNegativeFloat = Field(
        default=0.0,
        description="Per-market risk cap in USD (0 = no limit)",
        env="PER_MARKET_RISK_CAP_USD",
    )
    per_outcome_risk_cap: NonNegativeFloat = Field(
        default=0.0,
        description="Per-outcome risk cap in USD (0 = no limit)",
        env="PER_OUTCOME_RISK_CAP_USD",
    )
    max_position_size: PositiveFloat = Field(
        default=1000.0,
        description="Maximum position size in USD",
        env="MAX_POSITION_SIZE_USD",
    )
    max_order_size: PositiveFloat = Field(
        default=100.0, description="Maximum order size in USD", env="MAX_ORDER_SIZE_USD"
    )

    # Scanner Configuration
    market_cache_ttl: PositiveInt = Field(
        default=300,
        description="Market data cache TTL in seconds",
        env="MARKET_CACHE_TTL",
        le=3600,
    )
    book_batch_size: PositiveInt = Field(
        default=120,
        description="Order book batch size for processing",
        env="BOOK_BATCH_SIZE",
        le=1000,
    )
    scan_interval_seconds: PositiveInt = Field(
        default=30,
        description="Market scanning interval in seconds",
        env="SCAN_INTERVAL_SECONDS",
        le=3600,
    )
    max_markets_per_scan: PositiveInt = Field(
        default=15,
        description="Maximum markets to scan per iteration",
        env="MAX_MARKETS_PER_SCAN",
        le=1000,
    )

    # WebSocket Configuration
    ws_enabled: bool = Field(
        default=False, description="Enable WebSocket connections", env="WS_ENABLED"
    )
    ws_reconnect_attempts: NonNegativeInt = Field(
        default=5,
        description="WebSocket reconnection attempts",
        env="WS_RECONNECT_ATTEMPTS",
        le=50,
    )
    ws_reconnect_delay_seconds: PositiveInt = Field(
        default=5,
        description="Delay between WebSocket reconnection attempts",
        env="WS_RECONNECT_DELAY_SECONDS",
        le=300,
    )

    # Order Execution Parameters
    default_order_type: Literal["GTC", "FOK", "IOC", "MARKET"] = Field(
        default="GTC", description="Default order type", env="DEFAULT_ORDER_TYPE"
    )
    order_timeout_seconds: PositiveInt = Field(
        default=30,
        description="Order execution timeout in seconds",
        env="ORDER_TIMEOUT_SECONDS",
        le=300,
    )
    slippage_tolerance_bps: NonNegativeInt = Field(
        default=50,
        description="Slippage tolerance in basis points",
        env="SLIPPAGE_TOLERANCE_BPS",
        le=10000,
    )
    price_precision: PositiveInt = Field(
        default=4, description="Price decimal precision", env="PRICE_PRECISION", le=18
    )
    size_precision: PositiveInt = Field(
        default=4, description="Size decimal precision", env="SIZE_PRECISION", le=18
    )

    # Signal Processing and Timeout Configuration
    signal_default_timeout_seconds: PositiveFloat = Field(
        default=10.0, description="Default signal timeout in seconds", le=300.0
    )
    signal_spread_timeout_seconds: PositiveFloat = Field(
        default=15.0, description="Spread signal timeout in seconds", le=300.0
    )
    signal_complement_timeout_seconds: PositiveFloat = Field(
        default=15.0,
        description="Complement arbitrage signal timeout in seconds",
        le=300.0,
    )
    signal_market_making_timeout_seconds: PositiveFloat = Field(
        default=60.0, description="Market making signal timeout in seconds", le=300.0
    )
    signal_cleanup_interval_seconds: PositiveFloat = Field(
        default=10.0, description="Interval for signal cleanup in seconds", le=60.0
    )
    signal_max_concurrent: PositiveInt = Field(
        default=10, description="Maximum concurrent signal processing", le=100
    )
    signal_enable_deduplication: bool = Field(
        default=True, description="Enable signal deduplication"
    )
    signal_deduplication_window_seconds: PositiveFloat = Field(
        default=5.0, description="Signal deduplication window in seconds", le=60.0
    )

    # Market Making Configuration
    mm_enabled: bool = Field(
        default=False, description="Enable market making", env="MM_ENABLED"
    )
    mm_target_spread_bps: PositiveFloat = Field(
        default=50.0,
        description="Target spread for market making in basis points",
        env="MM_TARGET_SPREAD_BPS",
        le=10000,
    )
    mm_max_position_size: PositiveFloat = Field(
        default=100.0,
        description="Maximum market making position size in USD",
        env="MM_MAX_POSITION_SIZE_USD",
    )
    mm_quote_size: PositiveFloat = Field(
        default=10.0,
        description="Market making quote size in USD",
        env="MM_QUOTE_SIZE_USD",
    )
    mm_min_spread_bps: PositiveFloat = Field(
        default=20.0,
        description="Minimum market making spread in basis points",
        env="MM_MIN_SPREAD_BPS",
        le=10000,
    )
    mm_max_spread_bps: PositiveFloat = Field(
        default=5000.0,
        description="Maximum market making spread in basis points",
        env="MM_MAX_SPREAD_BPS",
        le=10000,
    )
    mm_inventory_skew_factor: PositiveFloat = Field(
        default=0.1,
        description="Inventory skew factor for market making",
        env="MM_INVENTORY_SKEW_FACTOR",
        le=1.0,
    )
    mm_edge_bps: PositiveFloat = Field(
        default=5.0,
        description="Market making edge in basis points",
        env="MM_EDGE_BPS",
        le=10000,
    )
    mm_min_liquidity: PositiveFloat = Field(
        default=1000.0,
        description="Minimum liquidity for market making",
        env="MM_MIN_LIQUIDITY",
    )
    mm_enabled_markets: list[str] = Field(
        default_factory=list, description="Markets enabled for market making"
    )

    # Snapshot Service Configuration
    snapshot_interval_seconds: PositiveInt = Field(
        default=300,
        description="Snapshot service interval in seconds",
        env="SNAPSHOT_INTERVAL_SECONDS",
        le=86400,
    )
    snapshot_retention_days: PositiveInt = Field(
        default=7,
        description="Snapshot retention period in days",
        env="SNAPSHOT_RETENTION_DAYS",
        le=365,
    )
    snapshot_enabled: bool = Field(
        default=True, description="Enable snapshot service", env="SNAPSHOT_ENABLED"
    )

    # Health Check Configuration
    health_check_enabled: bool = Field(
        default=True, description="Enable health checks", env="HEALTH_CHECK_ENABLED"
    )
    health_check_interval_seconds: PositiveInt = Field(
        default=60,
        description="Health check interval in seconds",
        env="HEALTH_CHECK_INTERVAL_SECONDS",
        le=3600,
    )

    # Liquidity Calculation Configuration
    liquidity_method: Literal["total_depth", "effective_spread", "weighted_depth"] = (
        Field(
            default="total_depth",
            description="Method for calculating liquidity",
            env="LIQUIDITY_METHOD",
        )
    )
    liquidity_top_n_levels: PositiveInt = Field(
        default=3,
        description="Number of top order book levels to consider",
        env="LIQUIDITY_TOP_N_LEVELS",
        le=20,
    )
    liquidity_effective_spread_pct: PositiveFloat = Field(
        default=0.05,
        description="Effective spread percentage for liquidity calculation",
        env="LIQUIDITY_EFFECTIVE_SPREAD_PCT",
        le=1.0,
    )
    liquidity_min_price_threshold: PositiveFloat = Field(
        default=0.01,
        description="Minimum price threshold for liquidity calculation",
        env="LIQUIDITY_MIN_PRICE_THRESHOLD",
        le=0.5,
    )
    liquidity_max_price_threshold: PositiveFloat = Field(
        default=0.99,
        description="Maximum price threshold for liquidity calculation",
        env="LIQUIDITY_MAX_PRICE_THRESHOLD",
        ge=0.5,
        le=1.0,
    )
    liquidity_cache_ttl_seconds: PositiveInt = Field(
        default=30,
        description="Liquidity cache TTL in seconds",
        env="LIQUIDITY_CACHE_TTL_SECONDS",
        le=3600,
    )
    liquidity_weight_decay_factor: PositiveFloat = Field(
        default=0.8,
        description="Weight decay factor for liquidity calculation",
        env="LIQUIDITY_WEIGHT_DECAY_FACTOR",
        le=1.0,
    )

    # Liquidity Fallback Configuration
    liquidity_fallback_enabled: bool = Field(
        default=True,
        description="Enable fallback liquidity values when calculation fails",
        env="LIQUIDITY_FALLBACK_ENABLED",
    )
    liquidity_fallback_minimum: NonNegativeFloat = Field(
        default=0.0,
        description="Minimum fallback liquidity value in USD",
        env="LIQUIDITY_FALLBACK_MINIMUM",
    )
    liquidity_fallback_market_average: NonNegativeFloat = Field(
        default=500.0,
        description="Average market liquidity fallback value in USD",
        env="LIQUIDITY_FALLBACK_MARKET_AVERAGE",
    )
    liquidity_fallback_high_volume: NonNegativeFloat = Field(
        default=2000.0,
        description="High volume market liquidity fallback value in USD",
        env="LIQUIDITY_FALLBACK_HIGH_VOLUME",
    )
    liquidity_api_timeout_seconds: PositiveFloat = Field(
        default=5.0,
        description="Timeout for liquidity API calls in seconds",
        env="LIQUIDITY_API_TIMEOUT_SECONDS",
        le=30.0,
    )
    liquidity_max_retries: NonNegativeInt = Field(
        default=2,
        description="Maximum retries for liquidity calculation",
        env="LIQUIDITY_MAX_RETRIES",
        le=5,
    )

    # API Rate Limiting Configuration
    rate_limiting_enabled: bool = Field(
        default=True,
        description="Enable API rate limiting protection",
        env="RATE_LIMITING_ENABLED",
    )

    # Market Data Endpoints
    rate_limit_market_data_per_second: PositiveFloat = Field(
        default=10.0,
        description="Market data requests per second",
        env="RATE_LIMIT_MARKET_DATA_PER_SECOND",
        le=100.0,
    )
    rate_limit_market_data_per_minute: PositiveFloat = Field(
        default=100.0,
        description="Market data requests per minute",
        env="RATE_LIMIT_MARKET_DATA_PER_MINUTE",
        le=1000.0,
    )
    rate_limit_market_data_per_hour: PositiveFloat = Field(
        default=1000.0,
        description="Market data requests per hour",
        env="RATE_LIMIT_MARKET_DATA_PER_HOUR",
        le=10000.0,
    )
    rate_limit_market_data_burst: PositiveInt = Field(
        default=20,
        description="Market data burst limit",
        env="RATE_LIMIT_MARKET_DATA_BURST",
        le=100,
    )

    # Order Management Endpoints
    rate_limit_orders_per_second: PositiveFloat = Field(
        default=5.0,
        description="Order management requests per second",
        env="RATE_LIMIT_ORDERS_PER_SECOND",
        le=50.0,
    )
    rate_limit_orders_per_minute: PositiveFloat = Field(
        default=50.0,
        description="Order management requests per minute",
        env="RATE_LIMIT_ORDERS_PER_MINUTE",
        le=500.0,
    )
    rate_limit_orders_per_hour: PositiveFloat = Field(
        default=500.0,
        description="Order management requests per hour",
        env="RATE_LIMIT_ORDERS_PER_HOUR",
        le=2000.0,
    )
    rate_limit_orders_burst: PositiveInt = Field(
        default=10,
        description="Order management burst limit",
        env="RATE_LIMIT_ORDERS_BURST",
        le=50,
    )

    # Position Query Endpoints
    rate_limit_positions_per_second: PositiveFloat = Field(
        default=5.0,
        description="Position query requests per second",
        env="RATE_LIMIT_POSITIONS_PER_SECOND",
        le=50.0,
    )
    rate_limit_positions_per_minute: PositiveFloat = Field(
        default=50.0,
        description="Position query requests per minute",
        env="RATE_LIMIT_POSITIONS_PER_MINUTE",
        le=500.0,
    )
    rate_limit_positions_per_hour: PositiveFloat = Field(
        default=200.0,
        description="Position query requests per hour",
        env="RATE_LIMIT_POSITIONS_PER_HOUR",
        le=1000.0,
    )
    rate_limit_positions_burst: PositiveInt = Field(
        default=10,
        description="Position query burst limit",
        env="RATE_LIMIT_POSITIONS_BURST",
        le=50,
    )

    # Authentication Endpoints
    rate_limit_auth_per_second: PositiveFloat = Field(
        default=1.0,
        description="Authentication requests per second",
        env="RATE_LIMIT_AUTH_PER_SECOND",
        le=10.0,
    )
    rate_limit_auth_per_minute: PositiveFloat = Field(
        default=10.0,
        description="Authentication requests per minute",
        env="RATE_LIMIT_AUTH_PER_MINUTE",
        le=60.0,
    )
    rate_limit_auth_per_hour: PositiveFloat = Field(
        default=60.0,
        description="Authentication requests per hour",
        env="RATE_LIMIT_AUTH_PER_HOUR",
        le=300.0,
    )
    rate_limit_auth_burst: PositiveInt = Field(
        default=3,
        description="Authentication burst limit",
        env="RATE_LIMIT_AUTH_BURST",
        le=10,
    )

    # General Endpoints
    rate_limit_general_per_second: PositiveFloat = Field(
        default=8.0,
        description="General API requests per second",
        env="RATE_LIMIT_GENERAL_PER_SECOND",
        le=100.0,
    )
    rate_limit_general_per_minute: PositiveFloat = Field(
        default=80.0,
        description="General API requests per minute",
        env="RATE_LIMIT_GENERAL_PER_MINUTE",
        le=1000.0,
    )
    rate_limit_general_per_hour: PositiveFloat = Field(
        default=800.0,
        description="General API requests per hour",
        env="RATE_LIMIT_GENERAL_PER_HOUR",
        le=5000.0,
    )
    rate_limit_general_burst: PositiveInt = Field(
        default=15,
        description="General API burst limit",
        env="RATE_LIMIT_GENERAL_BURST",
        le=100,
    )

    # Rate Limiting Behavior Configuration
    rate_limit_queue_size: PositiveInt = Field(
        default=100,
        description="Maximum size of request queue",
        env="RATE_LIMIT_QUEUE_SIZE",
        le=1000,
    )
    rate_limit_queue_timeout: PositiveFloat = Field(
        default=30.0,
        description="Request queue timeout in seconds",
        env="RATE_LIMIT_QUEUE_TIMEOUT",
        le=300.0,
    )
    rate_limit_backoff_base: PositiveFloat = Field(
        default=1.0,
        description="Base backoff delay in seconds",
        env="RATE_LIMIT_BACKOFF_BASE",
        le=10.0,
    )
    rate_limit_backoff_max: PositiveFloat = Field(
        default=60.0,
        description="Maximum backoff delay in seconds",
        env="RATE_LIMIT_BACKOFF_MAX",
        le=300.0,
    )
    rate_limit_backoff_multiplier: PositiveFloat = Field(
        default=2.0,
        description="Backoff multiplier",
        env="RATE_LIMIT_BACKOFF_MULTIPLIER",
        ge=1.1,
        le=5.0,
    )
    rate_limit_max_retries: NonNegativeInt = Field(
        default=3,
        description="Maximum retries for rate limited requests",
        env="RATE_LIMIT_MAX_RETRIES",
        le=10,
    )
    rate_limit_fail_fast_on_queue_full: bool = Field(
        default=False,
        description="Fail fast when request queue is full",
        env="RATE_LIMIT_FAIL_FAST_ON_QUEUE_FULL",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "validate_assignment": True,
        "extra": "ignore",
        "env_ignore_empty": True,
    }

    @field_validator("public_key")
    @classmethod
    def validate_public_key(cls, v: str) -> str:
        """
        Validate Ethereum public key format with comprehensive checks.

        Args:
            v: Public key string from environment or config

        Returns:
            Validated and normalized public key

        Raises:
            ValueError: If public key format is invalid with specific error details
        """
        if not v or v.strip() == "":
            raise ValueError(
                "PUBLIC_KEY is required. Set the PUBLIC_KEY environment variable "
                "or pass public_key parameter. Expected format: 0x followed by 40 hex characters."
            )

        v = v.strip()  # Remove any whitespace

        if not v.startswith("0x"):
            raise ValueError(
                "PUBLIC_KEY must start with '0x' prefix. "
                f"Got: '{v[:10]}...' "
                "Expected format: 0x1234567890abcdef... (42 characters total)"
            )

        if len(v) != 42:
            raise ValueError(
                f"PUBLIC_KEY must be exactly 42 characters long (0x + 40 hex chars). "
                f"Got {len(v)} characters: '{v}'. "
                "Example valid key: 0x742d35Cc6634C0532925a3b8D0dd4d8b9C1e5D6E"
            )

        if not re.match(r"^0x[0-9a-fA-F]{40}$", v):
            # Find the first invalid character to help debugging
            hex_part = v[2:]
            invalid_chars = [c for c in hex_part if c not in "0123456789abcdefABCDEF"]
            if invalid_chars:
                raise ValueError(
                    f"PUBLIC_KEY contains invalid characters: {set(invalid_chars)}. "
                    f"Only hexadecimal characters (0-9, a-f, A-F) are allowed after '0x'. "
                    f"Got: '{v}'"
                )
            else:
                raise ValueError(
                    f"PUBLIC_KEY format is invalid. Must be 0x followed by 40 hex characters. "
                    f"Got: '{v}'"
                )

        return v.lower()  # Normalize to lowercase for consistency

    @field_validator("private_key")
    @classmethod
    def validate_private_key(cls, v: str) -> str:
        """
        Validate Ethereum private key format with comprehensive checks and security considerations.

        Args:
            v: Private key string from environment or config

        Returns:
            Validated and normalized private key

        Raises:
            ValueError: If private key format is invalid with specific error details
        """
        if not v or v.strip() == "":
            raise ValueError(
                "PRIVATE_KEY is required. Set the PRIVATE_KEY environment variable "
                "or pass private_key parameter. Expected format: 0x followed by 64 hex characters. "
                "SECURITY WARNING: Never commit private keys to code or version control!"
            )

        v = v.strip()  # Remove any whitespace

        if not v.startswith("0x"):
            raise ValueError(
                "PRIVATE_KEY must start with '0x' prefix. "
                f"Got key starting with: '{v[:4]}...' "
                "Expected format: 0x1234567890abcdef... (66 characters total)"
            )

        if len(v) != 66:
            raise ValueError(
                f"PRIVATE_KEY must be exactly 66 characters long (0x + 64 hex chars). "
                f"Got {len(v)} characters. "
                "Ethereum private keys are always 32 bytes (64 hex chars) plus the 0x prefix. "
                "Check your key format and ensure no extra characters or truncation."
            )

        # Security check - warn about common insecure patterns
        hex_part = v[2:]
        if hex_part == "0" * 64:
            raise ValueError(
                "PRIVATE_KEY appears to be all zeros, which is invalid and insecure. "
                "Please use a proper Ethereum private key generated by a secure wallet."
            )

        if not re.match(r"^0x[0-9a-fA-F]{64}$", v):
            # Find the first invalid character to help debugging
            invalid_chars = [c for c in hex_part if c not in "0123456789abcdefABCDEF"]
            if invalid_chars:
                raise ValueError(
                    f"PRIVATE_KEY contains invalid characters: {set(invalid_chars)}. "
                    f"Only hexadecimal characters (0-9, a-f, A-F) are allowed after '0x'. "
                    "Ensure the private key is properly formatted."
                )
            else:
                raise ValueError(
                    "PRIVATE_KEY format is invalid. Must be 0x followed by 64 hex characters. "
                    "Check that your private key is complete and properly formatted."
                )

        return v.lower()  # Normalize to lowercase for consistency

    @model_validator(mode="after")
    def validate_websocket_config(self) -> "BotConfig":
        """Validate WebSocket configuration."""
        if self.ws_enabled and self.ws_url.scheme not in ["ws", "wss"]:
            raise ValueError(
                "If ws_enabled is True, ws_url must be a WebSocket URL (ws:// or wss://)"
            )
        return self

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """
        Validate database URL format with detailed error reporting.

        Args:
            v: Database URL string

        Returns:
            Validated database URL

        Raises:
            ValueError: If database URL format is invalid
        """
        if not v or v.strip() == "":
            raise ValueError(
                "DATABASE_URL cannot be empty. "
                "Examples: 'sqlite:///bot_data.db', 'postgresql://user:pass@localhost/db'"
            )

        v = v.strip()
        valid_schemes = ["sqlite", "postgresql", "mysql"]

        if not any(v.startswith(f"{scheme}:") for scheme in valid_schemes):
            # Try to extract the scheme to provide better error message
            if ":" in v:
                actual_scheme = v.split(":")[0]
                raise ValueError(
                    f"Unsupported database scheme: '{actual_scheme}'. "
                    f"Supported schemes: {valid_schemes}. "
                    f"Got URL: '{v[:50]}{'...' if len(v) > 50 else ''}'"
                )
            else:
                raise ValueError(
                    f"Invalid database URL format. Must include a scheme. "
                    f"Supported schemes: {valid_schemes}. "
                    f"Examples: 'sqlite:///data.db', 'postgresql://localhost/db'. "
                    f"Got: '{v[:50]}{'...' if len(v) > 50 else ''}'"
                )

        return v

    def __init__(self, **data):
        """
        Initialize configuration with custom environment variable parsing and enhanced validation.

        This constructor provides fail-fast validation with comprehensive error reporting
        to help diagnose configuration issues quickly during bot startup.

        Args:
            **data: Configuration parameters (will be validated)

        Raises:
            ValidationError: If required environment variables are missing or invalid
            ValueError: If configuration values are inconsistent or invalid
        """
        try:
            # Parse market filter from environment
            market_filter_env = os.getenv("MARKET_FILTER", "").strip()
            if market_filter_env and "market_filter" not in data:
                data["market_filter"] = [
                    s.strip() for s in market_filter_env.split(",") if s.strip()
                ]

            # Parse MM enabled markets from environment
            mm_markets_env = os.getenv("MM_ENABLED_MARKETS", "").strip()
            if mm_markets_env and "mm_enabled_markets" not in data:
                data["mm_enabled_markets"] = [
                    s.strip() for s in mm_markets_env.split(",") if s.strip()
                ]

            # Validate configuration with enhanced error reporting
            super().__init__(**data)

        except ValidationError as e:
            # Enhance validation errors with configuration guidance
            error_details = []
            for error in e.errors():
                field = ".".join(str(loc) for loc in error["loc"])
                msg = error["msg"]
                error_details.append(f"  • {field}: {msg}")

            enhanced_message = (
                "\n" + "=" * 60 + "\n"
                "CONFIGURATION VALIDATION FAILED\n"
                "=" * 60 + "\n"
                "The bot configuration contains validation errors:\n\n"
                + "\n".join(error_details)
                + "\n\n"
                "Configuration Help:\n"
                "  • Set required environment variables in your .env file\n"
                "  • Check the BotConfig docstring for parameter details\n"
                "  • Ensure PUBLIC_KEY is 42 characters (0x + 40 hex)\n"
                "  • Ensure PRIVATE_KEY is 66 characters (0x + 64 hex)\n"
                "  • Verify database URL format (sqlite:///file.db)\n"
                "  • Check that numeric values are within valid ranges\n"
                "  • Ensure risk management settings are consistent\n\n"
                "Example .env file:\n"
                "  PUBLIC_KEY=0x742d35Cc6634C0532925a3b8D0dd4d8b9C1e5D6E\n"
                "  PRIVATE_KEY=0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef\n"
                "  DATABASE_URL=sqlite:///bot_data.db\n"
                "  LOG_LEVEL=INFO\n"
                "  MAX_POSITION_SIZE_USD=500.0\n"
                "\nTo check environment before initialization, use:\n"
                "  BotConfig.validate_environment()\n"
                "=" * 60
            )

            raise ValueError(enhanced_message) from e

        except Exception as e:
            # Handle any other initialization errors with context
            if isinstance(e, ValueError) and "=" * 60 in str(e):
                # Re-raise our enhanced validation errors as-is
                raise
            else:
                # Handle any other initialization errors with context
                raise ValueError(
                    f"Configuration initialization failed: {e}. "
                    "Check your environment variables and configuration parameters. "
                    "Run BotConfig.validate_environment() to check your setup."
                ) from e

    @model_validator(mode="after")
    def validate_spread_constraints(self) -> "BotConfig":
        """Validate spread-related constraints."""
        if self.min_spread_bps >= self.max_spread_bps:
            raise ValueError("min_spread_bps must be less than max_spread_bps")

        # Market making spread validation
        if self.mm_min_spread_bps >= self.mm_max_spread_bps:
            raise ValueError("mm_min_spread_bps must be less than mm_max_spread_bps")

        return self

    @model_validator(mode="after")
    def validate_complement_arb_constraints(self) -> "BotConfig":
        """Validate complement arbitrage constraints."""
        if self.complement_arb_min_deviation >= self.complement_arb_max_deviation:
            raise ValueError(
                "complement_arb_min_deviation must be less than complement_arb_max_deviation"
            )

        if self.complement_arb_base_size > self.complement_arb_max_size:
            raise ValueError(
                "complement_arb_base_size must be less than or equal to complement_arb_max_size"
            )

        return self

    @model_validator(mode="after")
    def validate_liquidity_thresholds(self) -> "BotConfig":
        """Validate liquidity threshold constraints."""
        if self.liquidity_min_price_threshold >= self.liquidity_max_price_threshold:
            raise ValueError(
                "liquidity_min_price_threshold must be less than liquidity_max_price_threshold"
            )

        return self

    @model_validator(mode="after")
    def validate_critical_configuration(self) -> "BotConfig":
        """
        Perform comprehensive validation of critical configuration parameters.

        This validator ensures that the bot has a safe, consistent configuration
        that won't cause runtime errors or dangerous trading behavior.

        Returns:
            Self if validation passes

        Raises:
            ValueError: If any critical configuration issues are detected
        """
        issues = []

        # Validate API endpoints are accessible
        try:
            if not str(self.api_base).startswith(("http://", "https://")):
                issues.append(
                    f"API base URL should use HTTP/HTTPS protocol. Got: {self.api_base}"
                )
        except Exception as e:
            issues.append(f"Invalid API base URL: {e}")

        # Validate risk management configuration
        if self.max_order_size > self.max_position_size:
            issues.append(
                f"max_order_size ({self.max_order_size}) cannot be greater than "
                f"max_position_size ({self.max_position_size})"
            )

        if self.global_risk_cap > 0 and self.max_position_size > self.global_risk_cap:
            issues.append(
                f"max_position_size ({self.max_position_size}) cannot be greater than "
                f"global_risk_cap ({self.global_risk_cap})"
            )

        # Validate timeout configurations
        if self.api_call_timeout >= self.api_total_timeout:
            issues.append(
                f"api_call_timeout ({self.api_call_timeout}) should be less than "
                f"api_total_timeout ({self.api_total_timeout})"
            )

        # Validate database connection pool settings
        if self.database_pool_min_connections > self.database_pool_max_connections:
            issues.append(
                f"database_pool_min_connections ({self.database_pool_min_connections}) "
                f"cannot be greater than database_pool_max_connections ({self.database_pool_max_connections})"
            )

        # Validate signal timeout configuration
        timeout_warnings = []
        if self.signal_default_timeout_seconds > 120:
            timeout_warnings.append(
                "signal_default_timeout_seconds is very high (>2min)"
            )
        if self.signal_max_concurrent > 50:
            timeout_warnings.append("signal_max_concurrent is very high (>50)")

        if timeout_warnings:
            issues.append(
                "Signal configuration warnings: " + ", ".join(timeout_warnings)
            )

        # Security validation
        security_issues = []
        if hasattr(self, "private_key") and self.private_key:
            # Don't log the actual key, just validate it's not a common test key
            if self.private_key.lower() in [
                "0x" + "0" * 64,
                "0x" + "1" * 64,
                "0x" + "f" * 64,
            ]:
                security_issues.append(
                    "Private key appears to use an insecure test pattern"
                )

        if security_issues:
            issues.append("SECURITY WARNINGS: " + ", ".join(security_issues))

        # Raise error if critical issues found
        if issues:
            error_msg = (
                "\n" + "=" * 60 + "\n"
                "CRITICAL CONFIGURATION ISSUES DETECTED\n"
                "=" * 60 + "\n" + "\n".join(f"  • {issue}" for issue in issues) + "\n"
                "\nPlease review and fix these configuration issues before starting the bot.\n"
                "=" * 60
            )
            raise ValueError(error_msg)

        return self

    @classmethod
    def validate_environment(cls) -> dict[str, Any]:
        """
        Validate that all required environment variables are present and properly formatted.

        This method can be called before instantiating BotConfig to check if the
        environment is properly configured, allowing for fail-fast behavior.

        Returns:
            Dict with validation results and detected environment variables

        Raises:
            ValueError: If required environment variables are missing or invalid
        """
        required_vars = {
            "PUBLIC_KEY": "Ethereum public key (42 hex chars with 0x prefix)",
            "PRIVATE_KEY": "Ethereum private key (66 hex chars with 0x prefix)",
        }

        optional_vars = {
            "POLYMARKET_API_BASE": "Polymarket API base URL",
            "DATABASE_URL": "Database connection URL",
            "LOG_LEVEL": "Logging level (DEBUG, INFO, WARNING, ERROR)",
            "MAX_POSITION_SIZE_USD": "Maximum position size in USD",
            "GLOBAL_RISK_CAP_USD": "Global risk cap in USD",
        }

        missing_required = []
        invalid_format = []
        detected_vars = {}

        # Check required variables
        for var, description in required_vars.items():
            value = os.getenv(var)
            if not value or value.strip() == "":
                missing_required.append(f"{var}: {description}")
            else:
                detected_vars[var] = "<present>"

                # Basic format validation for keys
                if var == "PUBLIC_KEY":
                    if not (value.startswith("0x") and len(value) == 42):
                        invalid_format.append(
                            f"{var}: Must be 42 characters starting with 0x"
                        )
                elif var == "PRIVATE_KEY":
                    if not (value.startswith("0x") and len(value) == 66):
                        invalid_format.append(
                            f"{var}: Must be 66 characters starting with 0x"
                        )

        # Check optional variables
        for var, description in optional_vars.items():
            value = os.getenv(var)
            if value and value.strip():
                detected_vars[var] = (
                    value if var not in ["PRIVATE_KEY"] else "<present>"
                )

        # Report issues
        if missing_required or invalid_format:
            error_parts = []

            if missing_required:
                error_parts.append(
                    "MISSING REQUIRED ENVIRONMENT VARIABLES:\n"
                    + "\n".join(f"  • {var}" for var in missing_required)
                )

            if invalid_format:
                error_parts.append(
                    "INVALID ENVIRONMENT VARIABLE FORMATS:\n"
                    + "\n".join(f"  • {var}" for var in invalid_format)
                )

            error_msg = (
                "\n" + "=" * 60 + "\n"
                "ENVIRONMENT VALIDATION FAILED\n"
                "=" * 60 + "\n" + "\n\n".join(error_parts) + "\n\n"
                "Please set the required environment variables in your .env file or environment.\n"
                "\nExample .env file:\n"
                "  PUBLIC_KEY=0x742d35Cc6634C0532925a3b8D0dd4d8b9C1e5D6E\n"
                "  PRIVATE_KEY=0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef\n"
                "  DATABASE_URL=sqlite:///bot_data.db\n"
                "  LOG_LEVEL=INFO\n"
                "=" * 60
            )

            raise ValueError(error_msg)

        return {
            "status": "valid",
            "detected_variables": detected_vars,
            "missing_optional": [var for var in optional_vars if not os.getenv(var)],
        }

    @property
    def rate_limiting(self) -> Any:
        """
        Create rate limiting configuration from bot config settings.

        Returns:
            Rate limiting configuration object with enabled status and endpoint-specific configs
        """
        from .rate_limiter import EndpointType, RateLimitConfig

        # Create a configuration object that mimics the expected structure
        class RateLimitingConfig:
            def __init__(self, cfg: "BotConfig"):
                self.enabled = cfg.rate_limiting_enabled
                self.endpoint_configs = {
                    EndpointType.MARKET_DATA: RateLimitConfig(
                        requests_per_second=cfg.rate_limit_market_data_per_second,
                        requests_per_minute=cfg.rate_limit_market_data_per_minute,
                        requests_per_hour=cfg.rate_limit_market_data_per_hour,
                        burst_limit=cfg.rate_limit_market_data_burst,
                    ),
                    EndpointType.ORDER_MANAGEMENT: RateLimitConfig(
                        requests_per_second=cfg.rate_limit_orders_per_second,
                        requests_per_minute=cfg.rate_limit_orders_per_minute,
                        requests_per_hour=cfg.rate_limit_orders_per_hour,
                        burst_limit=cfg.rate_limit_orders_burst,
                    ),
                    EndpointType.POSITION_QUERIES: RateLimitConfig(
                        requests_per_second=cfg.rate_limit_positions_per_second,
                        requests_per_minute=cfg.rate_limit_positions_per_minute,
                        requests_per_hour=cfg.rate_limit_positions_per_hour,
                        burst_limit=cfg.rate_limit_positions_burst,
                    ),
                    EndpointType.AUTHENTICATION: RateLimitConfig(
                        requests_per_second=cfg.rate_limit_auth_per_second,
                        requests_per_minute=cfg.rate_limit_auth_per_minute,
                        requests_per_hour=cfg.rate_limit_auth_per_hour,
                        burst_limit=cfg.rate_limit_auth_burst,
                    ),
                    EndpointType.GENERAL: RateLimitConfig(
                        requests_per_second=cfg.rate_limit_general_per_second,
                        requests_per_minute=cfg.rate_limit_general_per_minute,
                        requests_per_hour=cfg.rate_limit_general_per_hour,
                        burst_limit=cfg.rate_limit_general_burst,
                    ),
                }
                # Use general config as default for other endpoints
                self.default_config = self.endpoint_configs[EndpointType.GENERAL]

        return RateLimitingConfig(self)
