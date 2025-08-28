import os
import re
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveFloat,
    PositiveInt,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings

load_dotenv()

# Enhanced type definitions with stricter validation
BoundedInt = lambda min_val, max_val: Annotated[int, Field(ge=min_val, le=max_val)]
BoundedFloat = lambda min_val, max_val: Annotated[float, Field(ge=min_val, le=max_val)]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeFloat = Annotated[float, Field(ge=0)]
PercentageFloat = BoundedFloat(0.0, 1.0)
BasisPoints = BoundedInt(0, 10000)
PositivePercentage = BoundedFloat(0.01, 1.0)


# Business logic constants for validation
class ValidationConstants:
    """Constants for business logic validation."""

    MAX_API_TIMEOUT = 300  # 5 minutes
    MAX_RETRY_ATTEMPTS = 50
    MAX_BACKOFF_DELAY = 3600  # 1 hour
    MIN_EXPONENTIAL_BASE = 1.1
    MAX_EXPONENTIAL_BASE = 10.0

    MAX_POSITION_SIZE_USD = 1_000_000  # 1M USD
    MAX_ORDER_SIZE_USD = 100_000  # 100K USD
    MAX_RISK_CAP_USD = 10_000_000  # 10M USD

    MIN_SPREAD_BPS = 1  # 0.01%
    MAX_SPREAD_BPS = 10000  # 100%

    MIN_MARKET_CACHE_TTL = 1  # 1 second
    MAX_MARKET_CACHE_TTL = 86400  # 1 day

    MAX_SCAN_BATCH_SIZE = 1000
    MAX_MARKETS_PER_SCAN = 1000

    MIN_LIQUIDITY_USD = 1.0
    MAX_LIQUIDITY_USD = 1_000_000_000  # 1B USD


# Enums for better type safety
class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class OrderType(str, Enum):
    GTC = "GTC"
    FOK = "FOK"
    IOC = "IOC"
    MARKET = "MARKET"


class BackoffStrategy(str, Enum):
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    CONSTANT = "constant"


class LiquidityMethod(str, Enum):
    TOTAL_DEPTH = "total_depth"
    EFFECTIVE_SPREAD = "effective_spread"
    WEIGHTED_DEPTH = "weighted_depth"


class DatabaseScheme(str, Enum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"


# Remove custom types - we'll handle validation in field validators directly


class APIConfig(BaseModel):
    """API and authentication configuration."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    api_base: str = Field(
        default="https://clob.polymarket.com",
        description="Base URL for the Polymarket API",
    )
    ws_url: str = Field(
        default="wss://ws-subscriptions-clob.polymarket.com",
        description="WebSocket URL for Polymarket subscriptions",
    )
    public_key: str = Field(..., description="Ethereum public key for authentication")
    private_key: str = Field(
        ..., description="Ethereum private key for signing transactions"
    )

    # Timeout and retry configuration with enhanced validation
    api_timeout_seconds: BoundedInt(1, ValidationConstants.MAX_API_TIMEOUT) = Field(
        default=30, description="API request timeout in seconds"
    )
    api_retry_attempts: BoundedInt(0, ValidationConstants.MAX_RETRY_ATTEMPTS) = Field(
        default=3, description="Number of API retry attempts"
    )
    api_retry_delay_seconds: BoundedInt(1, 60) = Field(
        default=1, description="Initial delay between retries in seconds"
    )
    api_retry_max_delay_seconds: BoundedFloat(
        1.0, ValidationConstants.MAX_BACKOFF_DELAY
    ) = Field(default=60.0, description="Maximum delay between retries in seconds")
    api_retry_exponential_base: BoundedFloat(
        ValidationConstants.MIN_EXPONENTIAL_BASE,
        ValidationConstants.MAX_EXPONENTIAL_BASE,
    ) = Field(default=2.0, description="Base for exponential backoff")
    api_retry_jitter_enabled: bool = Field(
        default=True, description="Enable jitter in retry delays"
    )
    api_retry_jitter_range: PercentageFloat = Field(
        default=0.1, description="Jitter range as fraction of delay (0.0 to 1.0)"
    )
    api_retry_backoff_strategy: BackoffStrategy = Field(
        default=BackoffStrategy.EXPONENTIAL, description="Retry backoff strategy"
    )

    @field_validator("public_key")
    @classmethod
    def validate_public_key(cls, v: str) -> str:
        """Enhanced Ethereum public key validation."""
        if not v:
            raise ValueError("PUBLIC_KEY is required")
        if not v.startswith("0x"):
            raise ValueError("PUBLIC_KEY must start with '0x'")
        if len(v) != 42:
            raise ValueError(
                "PUBLIC_KEY must be exactly 42 characters (0x + 40 hex chars)"
            )
        if not re.match(r"^0x[0-9a-fA-F]{40}$", v):
            raise ValueError(
                "PUBLIC_KEY must contain only valid hexadecimal characters"
            )

        # Additional validation: check for common invalid addresses
        if v.lower() in ["0x0000000000000000000000000000000000000000"]:
            raise ValueError("PUBLIC_KEY cannot be the zero address")

        return v.lower()

    @field_validator("private_key")
    @classmethod
    def validate_private_key(cls, v: str) -> str:
        """Enhanced Ethereum private key validation."""
        if not v:
            raise ValueError("PRIVATE_KEY is required")
        if not v.startswith("0x"):
            raise ValueError("PRIVATE_KEY must start with '0x'")
        if len(v) != 66:
            raise ValueError(
                "PRIVATE_KEY must be exactly 66 characters (0x + 64 hex chars)"
            )
        if not re.match(r"^0x[0-9a-fA-F]{64}$", v):
            raise ValueError(
                "PRIVATE_KEY must contain only valid hexadecimal characters"
            )

        # Additional validation: check for common weak keys
        if v.lower() in [
            "0x0000000000000000000000000000000000000000000000000000000000000000",
            "0x0000000000000000000000000000000000000000000000000000000000000001",
        ]:
            raise ValueError("PRIVATE_KEY cannot be a trivial value")

        return v.lower()

    @field_validator("api_base", "ws_url")
    @classmethod
    def validate_urls(cls, v: str) -> str:
        """Enhanced URL validation with parsing."""
        if not v.startswith(("http://", "https://", "ws://", "wss://")):
            raise ValueError(
                f"URL must start with http://, https://, ws://, or wss://, got: {v}"
            )

        try:
            parsed = urlparse(v)
            if not parsed.netloc:
                raise ValueError("Invalid URL format: missing domain")
            if not parsed.scheme:
                raise ValueError("Invalid URL format: missing scheme")
        except Exception as e:
            raise ValueError(f"Invalid URL format: {e}")

        return v


class DatabaseConfig(BaseModel):
    """Database configuration with connection validation."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    database_url: str = Field(
        default="sqlite:///bot_data.db", description="Database connection URL"
    )
    database_echo: bool = Field(
        default=False, description="Enable database query logging"
    )
    database_pool_size: BoundedInt(1, 100) = Field(
        default=5, description="Database connection pool size"
    )
    database_max_overflow: BoundedInt(0, 100) = Field(
        default=10, description="Maximum overflow connections beyond pool size"
    )
    database_pool_timeout: BoundedInt(1, 300) = Field(
        default=30, description="Connection pool checkout timeout in seconds"
    )
    database_pool_recycle: BoundedInt(300, 86400) = Field(
        default=3600, description="Connection recycle time in seconds"
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Enhanced database URL validation."""
        valid_schemes = [scheme.value for scheme in DatabaseScheme]

        if not any(v.startswith(f"{scheme}:") for scheme in valid_schemes):
            raise ValueError(f"Database URL must use one of: {valid_schemes}")

        try:
            parsed = urlparse(v)
            if parsed.scheme == "sqlite":
                # Validate SQLite path
                if ":///" in v:
                    db_path = v.split("///", 1)[1]
                    if db_path and not db_path.startswith(":memory:"):
                        # Check if directory exists for file-based SQLite
                        db_dir = Path(db_path).parent
                        if not db_dir.exists() and str(db_dir) != ".":
                            raise ValueError(
                                f"SQLite database directory does not exist: {db_dir}"
                            )
            elif parsed.scheme in ["postgresql", "mysql"]:
                # Validate network database URL has required components
                if not parsed.hostname:
                    raise ValueError("Network database URL missing hostname")
        except Exception as e:
            raise ValueError(f"Invalid database URL: {e}")

        return v


class LoggingConfig(BaseModel):
    """Logging configuration with file system validation."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    log_level: LogLevel = Field(default=LogLevel.INFO, description="Logging level")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log message format string",
        min_length=10,
    )
    log_file: str | None = Field(
        default=None, description="Log file path (if None, logs to stdout)"
    )
    log_max_bytes: PositiveInt = Field(
        default=10485760,
        description="Maximum size of log file before rotation",  # 10MB
    )
    log_backup_count: BoundedInt(1, 100) = Field(
        default=5, description="Number of backup log files to keep"
    )
    log_rotation_enabled: bool = Field(
        default=True, description="Enable log file rotation"
    )
    log_compression: bool = Field(
        default=True, description="Compress rotated log files"
    )

    @field_validator("log_file")
    @classmethod
    def validate_log_file(cls, v: str | None) -> str | None:
        """Validate log file path and permissions."""
        if v is None:
            return v

        log_path = Path(v)

        # Check if parent directory exists or can be created
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            raise ValueError(f"Cannot create log directory {log_path.parent}: {e}")

        # Check write permissions
        if log_path.exists() and not os.access(log_path, os.W_OK):
            raise ValueError(f"Log file is not writable: {v}")

        # Check if parent directory is writable
        if not os.access(log_path.parent, os.W_OK):
            raise ValueError(f"Log directory is not writable: {log_path.parent}")

        return str(log_path)

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        """Validate log format string."""
        required_fields = ["levelname", "message"]
        for field in required_fields:
            if f"%({field})s" not in v:
                raise ValueError(f"Log format must include %({field})s")

        # Test the format string
        try:
            test_record = {
                "asctime": "2024-01-01 00:00:00",
                "name": "test",
                "levelname": "INFO",
                "message": "test message",
                "lineno": 1,
                "filename": "test.py",
                "funcName": "test_func",
            }
            v % test_record
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"Invalid log format string: {e}")

        return v


class RiskManagementConfig(BaseModel):
    """Risk management configuration with business logic validation."""

    model_config = ConfigDict(validate_assignment=True)

    # Position and order limits
    position_risk_cap: BoundedFloat(0.0, ValidationConstants.MAX_RISK_CAP_USD) = Field(
        default=0.0, description="Position risk cap in USD (0 = no limit)"
    )
    global_risk_cap: BoundedFloat(0.0, ValidationConstants.MAX_RISK_CAP_USD) = Field(
        default=0.0, description="Global risk cap in USD (0 = no limit)"
    )
    market_risk_cap: BoundedFloat(0.0, ValidationConstants.MAX_RISK_CAP_USD) = Field(
        default=0.0, description="Market risk cap in USD (0 = no limit)"
    )
    per_market_risk_cap: BoundedFloat(0.0, ValidationConstants.MAX_RISK_CAP_USD) = (
        Field(default=0.0, description="Per-market risk cap in USD (0 = no limit)")
    )
    per_outcome_risk_cap: BoundedFloat(0.0, ValidationConstants.MAX_RISK_CAP_USD) = (
        Field(default=0.0, description="Per-outcome risk cap in USD (0 = no limit)")
    )
    max_position_size: BoundedFloat(1.0, ValidationConstants.MAX_POSITION_SIZE_USD) = (
        Field(default=1000.0, description="Maximum position size in USD")
    )
    max_order_size: BoundedFloat(1.0, ValidationConstants.MAX_ORDER_SIZE_USD) = Field(
        default=100.0, description="Maximum order size in USD"
    )

    # Risk monitoring
    risk_check_frequency_seconds: BoundedInt(1, 300) = Field(
        default=10, description="Frequency of risk checks in seconds"
    )
    emergency_stop_enabled: bool = Field(
        default=True, description="Enable emergency stop functionality"
    )
    risk_alert_threshold_pct: PercentageFloat = Field(
        default=0.8, description="Risk alert threshold as percentage of limit"
    )

    @model_validator(mode="after")
    def validate_risk_hierarchy(self) -> "RiskManagementConfig":
        """Validate risk limit hierarchy makes business sense."""
        # Skip validation if limits are disabled (0)
        active_limits = {
            "global": self.global_risk_cap,
            "market": self.market_risk_cap,
            "per_market": self.per_market_risk_cap,
            "per_outcome": self.per_outcome_risk_cap,
            "position": self.position_risk_cap,
            "max_position": self.max_position_size,
            "max_order": self.max_order_size,
        }

        # Remove disabled limits (0 values)
        active_limits = {k: v for k, v in active_limits.items() if v > 0}

        # Validate hierarchy: global >= market >= per_market >= per_outcome
        hierarchy_checks = [
            ("global", "market", "Global risk cap must be >= market risk cap"),
            ("market", "per_market", "Market risk cap must be >= per-market risk cap"),
            (
                "per_market",
                "per_outcome",
                "Per-market risk cap must be >= per-outcome risk cap",
            ),
            (
                "per_outcome",
                "position",
                "Per-outcome risk cap must be >= position risk cap",
            ),
        ]

        for higher, lower, message in hierarchy_checks:
            if higher in active_limits and lower in active_limits:
                if active_limits[higher] < active_limits[lower]:
                    raise ValueError(message)

        # Order size should be <= position size
        if self.max_order_size > self.max_position_size:
            raise ValueError("Maximum order size must be <= maximum position size")

        return self


class MarketFilteringConfig(BaseModel):
    """Market filtering and threshold configuration."""

    model_config = ConfigDict(validate_assignment=True)

    market_filter: list[str] = Field(
        default_factory=list,
        description="List of markets to filter (empty means all markets)",
    )
    min_liquidity: BoundedFloat(0.0, ValidationConstants.MAX_LIQUIDITY_USD) = Field(
        default=0.0, description="Minimum liquidity threshold in USD"
    )
    min_volume_24h: NonNegativeFloat = Field(
        default=0.0, description="Minimum 24h volume threshold in USD"
    )
    min_spread_bps: BasisPoints = Field(
        default=0, description="Minimum spread in basis points"
    )
    max_spread_bps: BasisPoints = Field(
        default=10000, description="Maximum spread in basis points"
    )
    spread_alert_bps: BasisPoints = Field(
        default=0, description="Spread threshold for alerts in basis points"
    )

    # Advanced filtering
    min_market_age_hours: NonNegativeInt = Field(
        default=0, description="Minimum market age in hours before trading"
    )
    max_market_expiry_days: BoundedInt(1, 365) = Field(
        default=365, description="Maximum days until market expiry"
    )
    excluded_market_categories: list[str] = Field(
        default_factory=list, description="Market categories to exclude from trading"
    )
    required_market_tags: list[str] = Field(
        default_factory=list, description="Required tags for markets to be eligible"
    )

    @field_validator("market_filter")
    @classmethod
    def validate_market_filter(cls, v: list[str]) -> list[str]:
        """Validate market filter entries."""
        if not v:
            return v

        # Check for valid market identifiers
        for market_id in v:
            if not market_id.strip():
                raise ValueError("Market filter cannot contain empty strings")
            if len(market_id) > 200:
                raise ValueError(f"Market identifier too long: {market_id}")

        return [m.strip() for m in v]

    @model_validator(mode="after")
    def validate_spread_thresholds(self) -> "MarketFilteringConfig":
        """Validate spread threshold relationships."""
        if self.min_spread_bps >= self.max_spread_bps:
            raise ValueError("min_spread_bps must be less than max_spread_bps")

        if self.spread_alert_bps > 0 and self.spread_alert_bps < self.min_spread_bps:
            raise ValueError("spread_alert_bps must be >= min_spread_bps when enabled")

        return self


class TradingConfig(BaseModel):
    """Trading execution and strategy configuration."""

    model_config = ConfigDict(validate_assignment=True)

    # Order execution
    default_order_type: OrderType = Field(
        default=OrderType.GTC, description="Default order type"
    )
    order_timeout_seconds: BoundedInt(1, 300) = Field(
        default=30, description="Order execution timeout in seconds"
    )
    slippage_tolerance_bps: BasisPoints = Field(
        default=50, description="Slippage tolerance in basis points"
    )
    price_precision: BoundedInt(1, 18) = Field(
        default=4, description="Price decimal precision"
    )
    size_precision: BoundedInt(1, 18) = Field(
        default=4, description="Size decimal precision"
    )

    # Advanced execution settings
    partial_fill_enabled: bool = Field(
        default=True, description="Allow partial order fills"
    )
    post_only_orders: bool = Field(
        default=False, description="Use post-only orders (maker-only)"
    )
    reduce_only_enabled: bool = Field(
        default=False, description="Enable reduce-only orders"
    )
    order_rate_limit_per_second: BoundedFloat(0.1, 100.0) = Field(
        default=2.0, description="Maximum orders per second"
    )

    # Position management
    auto_close_positions: bool = Field(
        default=False, description="Automatically close positions at market close"
    )
    position_timeout_hours: BoundedInt(1, 168) = Field(
        default=24, description="Maximum position hold time in hours"
    )
    profit_taking_enabled: bool = Field(
        default=False, description="Enable automatic profit taking"
    )
    profit_taking_threshold_pct: PercentageFloat = Field(
        default=0.1, description="Profit taking threshold as percentage"
    )
    stop_loss_enabled: bool = Field(
        default=False, description="Enable automatic stop loss"
    )
    stop_loss_threshold_pct: PercentageFloat = Field(
        default=0.05, description="Stop loss threshold as percentage"
    )


class MarketMakingConfig(BaseModel):
    """Market making strategy configuration."""

    model_config = ConfigDict(validate_assignment=True)

    mm_enabled: bool = Field(default=False, description="Enable market making")
    mm_target_spread_bps: BoundedFloat(1.0, 10000.0) = Field(
        default=50.0, description="Target spread for market making in basis points"
    )
    mm_max_position_size: BoundedFloat(
        1.0, ValidationConstants.MAX_POSITION_SIZE_USD
    ) = Field(default=100.0, description="Maximum market making position size in USD")
    mm_quote_size: PositiveFloat = Field(
        default=10.0, description="Market making quote size in USD"
    )
    mm_min_spread_bps: BoundedFloat(1.0, 10000.0) = Field(
        default=20.0, description="Minimum market making spread in basis points"
    )
    mm_max_spread_bps: BoundedFloat(1.0, 10000.0) = Field(
        default=5000.0, description="Maximum market making spread in basis points"
    )
    mm_inventory_skew_factor: PercentageFloat = Field(
        default=0.1, description="Inventory skew factor for market making"
    )
    mm_edge_bps: BoundedFloat(0.0, 1000.0) = Field(
        default=5.0, description="Market making edge in basis points"
    )
    mm_min_liquidity: BoundedFloat(
        ValidationConstants.MIN_LIQUIDITY_USD, ValidationConstants.MAX_LIQUIDITY_USD
    ) = Field(default=1000.0, description="Minimum liquidity for market making")
    mm_enabled_markets: list[str] = Field(
        default_factory=list, description="Markets enabled for market making"
    )

    # Advanced market making settings
    mm_rebalance_frequency_seconds: BoundedInt(1, 300) = Field(
        default=30, description="Market making rebalance frequency in seconds"
    )
    mm_fair_value_method: Literal["mid", "weighted_mid", "external"] = Field(
        default="mid", description="Method for calculating fair value"
    )
    mm_risk_adjustment_enabled: bool = Field(
        default=True, description="Enable risk-based spread adjustments"
    )
    mm_volatility_adjustment_enabled: bool = Field(
        default=True, description="Enable volatility-based spread adjustments"
    )

    @model_validator(mode="after")
    def validate_mm_constraints(self) -> "MarketMakingConfig":
        """Validate market making constraints."""
        if not self.mm_enabled:
            return self

        if self.mm_min_spread_bps >= self.mm_max_spread_bps:
            raise ValueError("mm_min_spread_bps must be less than mm_max_spread_bps")

        if self.mm_target_spread_bps < self.mm_min_spread_bps:
            raise ValueError("mm_target_spread_bps must be >= mm_min_spread_bps")

        if self.mm_target_spread_bps > self.mm_max_spread_bps:
            raise ValueError("mm_target_spread_bps must be <= mm_max_spread_bps")

        if self.mm_quote_size > self.mm_max_position_size:
            raise ValueError("mm_quote_size must be <= mm_max_position_size")

        return self


class ComplementArbitrageConfig(BaseModel):
    """Complement arbitrage strategy configuration."""

    model_config = ConfigDict(validate_assignment=True)

    complement_arb_enabled: bool = Field(
        default=False, description="Enable complement arbitrage strategy"
    )
    complement_arb_min_deviation: PositivePercentage = Field(
        default=0.01, description="Minimum price deviation for complement arbitrage"
    )
    complement_arb_max_deviation: PositivePercentage = Field(
        default=0.20, description="Maximum price deviation for complement arbitrage"
    )
    complement_arb_base_size: PositiveFloat = Field(
        default=10.0, description="Base position size for complement arbitrage in USD"
    )
    complement_arb_max_size: PositiveFloat = Field(
        default=100.0,
        description="Maximum position size for complement arbitrage in USD",
    )
    complement_arb_size_scaling: PositiveFloat = Field(
        default=50.0, description="Size scaling factor for complement arbitrage"
    )

    # Advanced arbitrage settings
    complement_arb_gas_adjustment: BoundedFloat(0.0, 0.1) = Field(
        default=0.01, description="Gas cost adjustment as percentage of trade size"
    )
    complement_arb_min_profit_bps: BasisPoints = Field(
        default=10, description="Minimum profit threshold in basis points"
    )
    complement_arb_execution_delay_ms: BoundedInt(0, 10000) = Field(
        default=100, description="Execution delay in milliseconds for arbitrage"
    )

    @model_validator(mode="after")
    def validate_arbitrage_constraints(self) -> "ComplementArbitrageConfig":
        """Validate complement arbitrage constraints."""
        if not self.complement_arb_enabled:
            return self

        if self.complement_arb_min_deviation >= self.complement_arb_max_deviation:
            raise ValueError(
                "complement_arb_min_deviation must be less than complement_arb_max_deviation"
            )

        if self.complement_arb_base_size > self.complement_arb_max_size:
            raise ValueError(
                "complement_arb_base_size must be <= complement_arb_max_size"
            )

        return self


class MonitoringConfig(BaseModel):
    """System monitoring and health check configuration."""

    model_config = ConfigDict(validate_assignment=True)

    # Health checks
    health_check_enabled: bool = Field(default=True, description="Enable health checks")
    health_check_interval_seconds: BoundedInt(1, 3600) = Field(
        default=60, description="Health check interval in seconds"
    )
    health_check_timeout_seconds: BoundedInt(1, 120) = Field(
        default=10, description="Health check timeout in seconds"
    )

    # Performance monitoring
    performance_monitoring_enabled: bool = Field(
        default=True, description="Enable performance monitoring"
    )
    metrics_collection_interval_seconds: BoundedInt(1, 300) = Field(
        default=30, description="Metrics collection interval in seconds"
    )
    metrics_retention_days: BoundedInt(1, 365) = Field(
        default=30, description="Metrics retention period in days"
    )

    # Alerts and notifications
    alert_enabled: bool = Field(default=True, description="Enable alerting system")
    alert_cooldown_minutes: BoundedInt(1, 1440) = Field(
        default=15, description="Alert cooldown period in minutes"
    )
    critical_alert_enabled: bool = Field(
        default=True, description="Enable critical alerts"
    )

    # System resources
    max_memory_usage_mb: BoundedInt(100, 32768) = Field(
        default=2048, description="Maximum memory usage in MB"
    )
    max_cpu_usage_percent: BoundedInt(1, 100) = Field(
        default=80, description="Maximum CPU usage percentage"
    )
    disk_space_alert_threshold_gb: BoundedInt(1, 10000) = Field(
        default=5, description="Disk space alert threshold in GB"
    )


class BotConfigEnhanced(BaseSettings):
    """
    Enhanced comprehensive configuration for the Polymarket trading bot.

    This configuration uses separate pydantic models for each major section,
    providing enhanced type safety, validation, and error handling.
    """

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "validate_assignment": True,
        "extra": "ignore",
        "env_ignore_empty": True,
        "env_nested_delimiter": "__",
    }

    # Configuration sections
    api: APIConfig = Field(default_factory=APIConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    risk: RiskManagementConfig = Field(default_factory=RiskManagementConfig)
    filtering: MarketFilteringConfig = Field(default_factory=MarketFilteringConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    market_making: MarketMakingConfig = Field(default_factory=MarketMakingConfig)
    arbitrage: ComplementArbitrageConfig = Field(
        default_factory=ComplementArbitrageConfig
    )
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)

    # Scanner and WebSocket configuration (kept flat for simplicity)
    market_cache_ttl: BoundedInt(
        ValidationConstants.MIN_MARKET_CACHE_TTL,
        ValidationConstants.MAX_MARKET_CACHE_TTL,
    ) = Field(
        default=300,
        description="Market data cache TTL in seconds",
        env="MARKET_CACHE_TTL",
    )
    book_batch_size: BoundedInt(1, ValidationConstants.MAX_SCAN_BATCH_SIZE) = Field(
        default=120,
        description="Order book batch size for processing",
        env="BOOK_BATCH_SIZE",
    )
    scan_interval_seconds: BoundedInt(1, 3600) = Field(
        default=30,
        description="Market scanning interval in seconds",
        env="SCAN_INTERVAL_SECONDS",
    )
    max_markets_per_scan: BoundedInt(1, ValidationConstants.MAX_MARKETS_PER_SCAN) = (
        Field(
            default=15,
            description="Maximum markets to scan per iteration",
            env="MAX_MARKETS_PER_SCAN",
        )
    )

    ws_enabled: bool = Field(
        default=False, description="Enable WebSocket connections", env="WS_ENABLED"
    )
    ws_reconnect_attempts: BoundedInt(0, 100) = Field(
        default=5,
        description="WebSocket reconnection attempts",
        env="WS_RECONNECT_ATTEMPTS",
    )
    ws_reconnect_delay_seconds: BoundedInt(1, 300) = Field(
        default=5,
        description="Delay between WebSocket reconnection attempts",
        env="WS_RECONNECT_DELAY_SECONDS",
    )

    # Snapshot and liquidity configuration
    snapshot_enabled: bool = Field(
        default=True, description="Enable snapshot service", env="SNAPSHOT_ENABLED"
    )
    snapshot_interval_seconds: BoundedInt(60, 86400) = Field(
        default=300,
        description="Snapshot service interval in seconds",
        env="SNAPSHOT_INTERVAL_SECONDS",
    )
    snapshot_retention_days: BoundedInt(1, 365) = Field(
        default=7,
        description="Snapshot retention period in days",
        env="SNAPSHOT_RETENTION_DAYS",
    )

    liquidity_method: LiquidityMethod = Field(
        default=LiquidityMethod.TOTAL_DEPTH,
        description="Method for calculating liquidity",
        env="LIQUIDITY_METHOD",
    )
    liquidity_top_n_levels: BoundedInt(1, 20) = Field(
        default=3,
        description="Number of top order book levels to consider",
        env="LIQUIDITY_TOP_N_LEVELS",
    )
    liquidity_effective_spread_pct: PositivePercentage = Field(
        default=0.05,
        description="Effective spread percentage for liquidity calculation",
        env="LIQUIDITY_EFFECTIVE_SPREAD_PCT",
    )
    liquidity_min_price_threshold: PositivePercentage = Field(
        default=0.01,
        description="Minimum price threshold for liquidity calculation",
        env="LIQUIDITY_MIN_PRICE_THRESHOLD",
    )
    liquidity_max_price_threshold: BoundedFloat(0.5, 1.0) = Field(
        default=0.99,
        description="Maximum price threshold for liquidity calculation",
        env="LIQUIDITY_MAX_PRICE_THRESHOLD",
    )
    liquidity_cache_ttl_seconds: BoundedInt(1, 3600) = Field(
        default=30,
        description="Liquidity cache TTL in seconds",
        env="LIQUIDITY_CACHE_TTL_SECONDS",
    )
    liquidity_weight_decay_factor: PercentageFloat = Field(
        default=0.8,
        description="Weight decay factor for liquidity calculation",
        env="LIQUIDITY_WEIGHT_DECAY_FACTOR",
    )

    def __init__(self, **data):
        """Initialize with enhanced environment variable parsing."""
        # Handle nested environment variables manually since the BaseSettings
        # automatic parsing doesn't work well with our nested structure
        if not data or "api" not in data:
            # Only parse from environment if not explicitly provided
            env_api = {}

            # Check for required API fields from environment
            public_key = os.getenv("PUBLIC_KEY")
            private_key = os.getenv("PRIVATE_KEY")

            if public_key:
                env_api["public_key"] = public_key
            if private_key:
                env_api["private_key"] = private_key

            # Add other API fields if present
            if os.getenv("POLYMARKET_API_BASE"):
                env_api["api_base"] = os.getenv("POLYMARKET_API_BASE")
            if os.getenv("POLYMARKET_WS_URL"):
                env_api["ws_url"] = os.getenv("POLYMARKET_WS_URL")

            if env_api and "api" not in data:
                data["api"] = env_api

        super().__init__(**data)

    @model_validator(mode="after")
    def validate_global_constraints(self) -> "BotConfigEnhanced":
        """Validate constraints across configuration sections."""
        # Cross-section validations

        # Risk limits should be consistent with trading limits
        if (
            self.risk.max_order_size > 0
            and self.trading.order_rate_limit_per_second > 0
        ):
            max_theoretical_exposure = (
                self.risk.max_order_size * self.trading.order_rate_limit_per_second * 60
            )  # per minute
            if (
                self.risk.global_risk_cap > 0
                and max_theoretical_exposure > self.risk.global_risk_cap
            ):
                raise ValueError(
                    f"Order rate limit could exceed global risk cap: "
                    f"{max_theoretical_exposure:.0f} > {self.risk.global_risk_cap:.0f}"
                )

        # Market making position limits should respect global risk limits
        if self.market_making.mm_enabled and self.risk.global_risk_cap > 0:
            if self.market_making.mm_max_position_size > self.risk.global_risk_cap:
                raise ValueError(
                    "Market making max position size exceeds global risk cap"
                )

        # Cache TTL should be reasonable relative to scan interval
        if self.market_cache_ttl < self.scan_interval_seconds:
            raise ValueError(
                "Market cache TTL should be >= scan interval to avoid unnecessary API calls"
            )

        # Liquidity thresholds should be consistent
        if self.liquidity_min_price_threshold >= self.liquidity_max_price_threshold:
            raise ValueError(
                "liquidity_min_price_threshold must be < liquidity_max_price_threshold"
            )

        return self

    def get_validation_summary(self) -> dict[str, Any]:
        """Get a summary of configuration validation status."""
        return {
            "config_version": "2.0-enhanced",
            "validation_timestamp": "2024-08-24",
            "sections": {
                "api": {
                    "public_key_valid": bool(
                        self.api.public_key and len(self.api.public_key) == 42
                    ),
                    "private_key_valid": bool(
                        self.api.private_key and len(self.api.private_key) == 66
                    ),
                    "urls_valid": all(
                        [
                            self.api.api_base.startswith(("http://", "https://")),
                            self.api.ws_url.startswith(("ws://", "wss://")),
                        ]
                    ),
                },
                "risk_management": {
                    "limits_configured": any(
                        [
                            self.risk.global_risk_cap > 0,
                            self.risk.market_risk_cap > 0,
                            self.risk.position_risk_cap > 0,
                        ]
                    ),
                    "emergency_stop_ready": self.risk.emergency_stop_enabled,
                },
                "trading": {
                    "strategies_enabled": {
                        "market_making": self.market_making.mm_enabled,
                        "arbitrage": self.arbitrage.complement_arb_enabled,
                    }
                },
                "monitoring": {
                    "health_checks": self.monitoring.health_check_enabled,
                    "alerts": self.monitoring.alert_enabled,
                },
            },
        }

    def validate_runtime_safety(self) -> list[str]:
        """Perform runtime safety validation and return any warnings."""
        warnings = []

        # Check for potential security issues
        if self.api.public_key.lower() == "0x0000000000000000000000000000000000000000":
            warnings.append("SECURITY: Using zero address for public key")

        if self.api.private_key.lower().endswith("000000000000"):
            warnings.append(
                "SECURITY: Private key appears to be weak (ends with many zeros)"
            )

        # Check for performance issues
        if self.scan_interval_seconds < 5:
            warnings.append(
                "PERFORMANCE: Very low scan interval may cause rate limiting"
            )

        if self.book_batch_size > 500:
            warnings.append("PERFORMANCE: Large batch size may cause memory issues")

        # Check for configuration issues
        if not any(
            [self.market_making.mm_enabled, self.arbitrage.complement_arb_enabled]
        ):
            warnings.append("CONFIG: No trading strategies enabled")

        if self.risk.global_risk_cap == 0:
            warnings.append(
                "RISK: No global risk cap set - unlimited exposure possible"
            )

        return warnings
