#!/usr/bin/env python3
"""
Configuration and API Response Caching for InkedUp Bot

This module provides caching for:
- Application configuration data
- API response caching
- Environment variable caching
- Static reference data
- Trading rules and constraints
"""

import hashlib
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .cache import CacheConfig, CacheStrategy, cache_manager, cached
from .config import BotConfig

logger = logging.getLogger("config_cache")


@dataclass
class ConfigCacheSettings:
    """Configuration for config and API response caching."""

    # Configuration caching
    config_ttl: float = 3600.0  # 1 hour for config data
    env_var_ttl: float = 1800.0  # 30 minutes for environment variables
    trading_rules_ttl: float = 7200.0  # 2 hours for trading rules

    # API response caching
    api_response_ttl: float = 300.0  # 5 minutes default API TTL
    static_api_ttl: float = 3600.0  # 1 hour for static API responses
    dynamic_api_ttl: float = 60.0  # 1 minute for dynamic API responses

    # Reference data caching
    reference_data_ttl: float = 86400.0  # 24 hours for reference data
    market_rules_ttl: float = 14400.0  # 4 hours for market rules

    # Cache sizes
    max_config_entries: int = 500
    max_api_entries: int = 2000
    max_reference_entries: int = 1000

    # Advanced features
    enable_config_versioning: bool = True
    enable_api_compression: bool = True
    enable_response_validation: bool = True

    # File watching for config changes
    enable_file_watching: bool = True
    watched_config_files: list[str] = None


class ConfigurationCache:
    """
    Intelligent caching system for configuration data and API responses.
    """

    def __init__(
        self, bot_config: BotConfig = None, settings: ConfigCacheSettings = None
    ):
        self.bot_config = bot_config
        self.settings = settings or ConfigCacheSettings()

        # Initialize cache instances
        self._init_caches()

        # Configuration versioning
        self._config_versions: dict[str, str] = {}
        self._file_timestamps: dict[str, float] = {}

        # API response validation
        self._api_validators: dict[str, Callable] = {}

        # File watching
        if self.settings.enable_file_watching:
            self._setup_file_watching()

        logger.info("Initialized configuration cache system")

    def _init_caches(self):
        """Initialize specialized cache instances."""

        # Configuration data cache
        config_cache_config = CacheConfig(
            max_size=self.settings.max_config_entries,
            default_ttl=self.settings.config_ttl,
            strategy=CacheStrategy.TTL,
            enable_background_refresh=True,
            refresh_threshold=0.9,
        )
        self.config_cache = cache_manager.get_cache(
            "configuration", config_cache_config
        )

        # API response cache
        api_cache_config = CacheConfig(
            max_size=self.settings.max_api_entries,
            default_ttl=self.settings.api_response_ttl,
            strategy=CacheStrategy.LRU,
            enable_background_refresh=True,
            refresh_threshold=0.8,
        )
        self.api_cache = cache_manager.get_cache("api_responses", api_cache_config)

        # Reference data cache
        reference_cache_config = CacheConfig(
            max_size=self.settings.max_reference_entries,
            default_ttl=self.settings.reference_data_ttl,
            strategy=CacheStrategy.TTL,
            enable_background_refresh=False,
        )
        self.reference_cache = cache_manager.get_cache(
            "reference_data", reference_cache_config
        )

    def _setup_file_watching(self):
        """Setup file system watching for configuration changes."""
        if not self.settings.watched_config_files:
            # Default files to watch
            self.settings.watched_config_files = [".env", "config.py", "pyproject.toml"]

        for config_file in self.settings.watched_config_files:
            if os.path.exists(config_file):
                self._file_timestamps[config_file] = os.path.getmtime(config_file)

    # Configuration Data Caching

    async def get_config_value(
        self, key: str, default: Any = None, refresh_if_changed: bool = True
    ) -> Any:
        """
        Get cached configuration value.

        Args:
            key: Configuration key
            default: Default value if not found
            refresh_if_changed: Check for config file changes

        Returns:
            Configuration value
        """
        cache_key = f"config:{key}"

        # Check for file changes if enabled
        if refresh_if_changed and self._config_files_changed():
            await self.invalidate_config_cache()

        value = await self.config_cache.get(cache_key, default)

        if value is None and self.bot_config:
            # Fallback to bot config
            try:
                value = getattr(self.bot_config, key, default)
                if value is not None:
                    await self.set_config_value(key, value)
            except AttributeError:
                pass

        return value

    async def set_config_value(
        self,
        key: str,
        value: Any,
        ttl_override: float | None = None,
        version: str | None = None,
    ) -> bool:
        """
        Cache configuration value with versioning.

        Args:
            key: Configuration key
            value: Value to cache
            ttl_override: Override default TTL
            version: Configuration version

        Returns:
            True if cached successfully
        """
        cache_key = f"config:{key}"
        ttl = ttl_override or self.settings.config_ttl

        # Handle versioning
        if self.settings.enable_config_versioning:
            if version:
                self._config_versions[key] = version
            else:
                # Generate version based on value hash
                value_str = json.dumps(value, sort_keys=True, default=str)
                version = hashlib.md5(value_str.encode()).hexdigest()[:8]
                self._config_versions[key] = version

        tags = {"configuration", "static"}
        if version:
            tags.add(f"version:{version}")

        result = await self.config_cache.set(cache_key, value, ttl=ttl, tags=tags)

        if result:
            logger.debug(f"Cached config value: {key} = {value} (version: {version})")

        return result

    async def get_environment_variable(
        self, env_var: str, default: Any = None, cache_default: bool = True
    ) -> Any:
        """
        Get environment variable with caching.

        Args:
            env_var: Environment variable name
            default: Default value if not found
            cache_default: Whether to cache the default value

        Returns:
            Environment variable value
        """
        cache_key = f"env:{env_var}"

        # Try cache first
        cached_value = await self.config_cache.get(cache_key)
        if cached_value is not None:
            return cached_value

        # Get from environment
        value = os.environ.get(env_var, default)

        # Cache the value (including defaults if enabled)
        if value is not None and (value != default or cache_default):
            await self.config_cache.set(
                cache_key,
                value,
                ttl=self.settings.env_var_ttl,
                tags={"environment", "config"},
            )

        return value

    async def get_trading_rules(self, market_id: str | None = None) -> dict[str, Any]:
        """
        Get cached trading rules for a market or globally.

        Args:
            market_id: Specific market ID, or None for global rules

        Returns:
            Trading rules dictionary
        """
        if market_id:
            cache_key = f"rules:market:{market_id}"
        else:
            cache_key = "rules:global"

        rules = await self.config_cache.get(cache_key)

        if rules is None:
            # Load default rules
            rules = await self._load_default_trading_rules(market_id)
            if rules:
                await self.set_trading_rules(rules, market_id)

        return rules or {}

    async def set_trading_rules(
        self, rules: dict[str, Any], market_id: str | None = None
    ) -> bool:
        """
        Cache trading rules.

        Args:
            rules: Trading rules dictionary
            market_id: Specific market ID, or None for global rules

        Returns:
            True if cached successfully
        """
        if market_id:
            cache_key = f"rules:market:{market_id}"
            tags = {"trading_rules", "market_specific", f"market:{market_id}"}
        else:
            cache_key = "rules:global"
            tags = {"trading_rules", "global"}

        return await self.config_cache.set(
            cache_key, rules, ttl=self.settings.trading_rules_ttl, tags=tags
        )

    # API Response Caching

    async def get_api_response(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """
        Get cached API response.

        Args:
            endpoint: API endpoint
            params: Request parameters
            headers: Request headers

        Returns:
            Cached API response
        """
        cache_key = self._generate_api_cache_key(endpoint, params, headers)
        return await self.api_cache.get(cache_key)

    async def set_api_response(
        self,
        endpoint: str,
        response_data: dict[str, Any],
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        ttl_override: float | None = None,
        is_static: bool = False,
    ) -> bool:
        """
        Cache API response.

        Args:
            endpoint: API endpoint
            response_data: Response data to cache
            params: Request parameters
            headers: Request headers
            ttl_override: Override default TTL
            is_static: Whether this is static data

        Returns:
            True if cached successfully
        """
        cache_key = self._generate_api_cache_key(endpoint, params, headers)

        # Validate response if validator exists
        if (
            self.settings.enable_response_validation
            and endpoint in self._api_validators
        ):
            validator = self._api_validators[endpoint]
            if not validator(response_data):
                logger.warning(f"API response validation failed for {endpoint}")
                return False

        # Determine TTL
        if ttl_override:
            ttl = ttl_override
        elif is_static:
            ttl = self.settings.static_api_ttl
        else:
            ttl = self._determine_api_ttl(endpoint)

        # Compress if enabled
        if self.settings.enable_api_compression:
            response_data = self._compress_response(response_data)

        tags = {"api_response"}
        if is_static:
            tags.add("static")
        else:
            tags.add("dynamic")

        # Add endpoint-specific tag
        endpoint_tag = endpoint.replace("/", "_").replace("?", "")
        tags.add(f"endpoint:{endpoint_tag}")

        result = await self.api_cache.set(cache_key, response_data, ttl=ttl, tags=tags)

        if result:
            logger.debug(f"Cached API response: {endpoint} (TTL: {ttl}s)")

        return result

    async def invalidate_api_cache(
        self, endpoint_pattern: str | None = None, tags: set[str] | None = None
    ) -> int:
        """
        Invalidate API response cache.

        Args:
            endpoint_pattern: Pattern to match endpoints
            tags: Tags to invalidate

        Returns:
            Number of entries invalidated
        """
        invalidated = 0

        if endpoint_pattern:
            pattern = f"api:*{endpoint_pattern}*"
            invalidated += await self.api_cache.invalidate_by_pattern(pattern)

        if tags:
            for tag in tags:
                invalidated += await self.api_cache.invalidate_by_tag(tag)

        if invalidated > 0:
            logger.info(f"Invalidated {invalidated} API cache entries")

        return invalidated

    # Reference Data Caching

    async def get_reference_data(self, data_type: str, key: str) -> Any | None:
        """
        Get cached reference data.

        Args:
            data_type: Type of reference data
            key: Specific key

        Returns:
            Reference data value
        """
        cache_key = f"ref:{data_type}:{key}"
        return await self.reference_cache.get(cache_key)

    async def set_reference_data(
        self, data_type: str, key: str, value: Any, ttl_override: float | None = None
    ) -> bool:
        """
        Cache reference data.

        Args:
            data_type: Type of reference data
            key: Specific key
            value: Value to cache
            ttl_override: Override default TTL

        Returns:
            True if cached successfully
        """
        cache_key = f"ref:{data_type}:{key}"
        ttl = ttl_override or self.settings.reference_data_ttl

        tags = {"reference_data", data_type}

        return await self.reference_cache.set(cache_key, value, ttl=ttl, tags=tags)

    # Cache Management

    async def invalidate_config_cache(self) -> int:
        """Invalidate all configuration cache entries."""
        return await self.config_cache.invalidate_by_tag("configuration")

    async def warm_configuration_cache(self):
        """Warm configuration cache with common values."""
        if not self.bot_config:
            return

        # Common configuration values to pre-load
        config_keys = [
            "api_base",
            "database_url",
            "market_cache_ttl",
            "book_batch_size",
            "max_concurrent_scans",
            "default_spread_threshold",
            "min_profit_threshold",
            "rate_limiting_enabled",
            "debug",
        ]

        warming_tasks = []
        for key in config_keys:
            try:
                value = getattr(self.bot_config, key, None)
                if value is not None:
                    warming_tasks.append(self.set_config_value(key, value))
            except AttributeError:
                continue

        if warming_tasks:
            await asyncio.gather(*warming_tasks, return_exceptions=True)
            logger.info(f"Warmed configuration cache with {len(warming_tasks)} values")

    def register_api_validator(self, endpoint: str, validator: Callable[[dict], bool]):
        """
        Register a validator function for API responses.

        Args:
            endpoint: API endpoint
            validator: Function that returns True if response is valid
        """
        self._api_validators[endpoint] = validator
        logger.debug(f"Registered API validator for {endpoint}")

    def _config_files_changed(self) -> bool:
        """Check if any watched config files have changed."""
        if not self.settings.enable_file_watching:
            return False

        for config_file, last_timestamp in self._file_timestamps.items():
            if os.path.exists(config_file):
                current_timestamp = os.path.getmtime(config_file)
                if current_timestamp > last_timestamp:
                    self._file_timestamps[config_file] = current_timestamp
                    logger.info(f"Configuration file changed: {config_file}")
                    return True

        return False

    def _generate_api_cache_key(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        """Generate cache key for API request."""
        key_parts = [f"api:{endpoint}"]

        if params:
            # Sort params for consistent key generation
            param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            key_parts.append(
                f"params:{hashlib.md5(param_str.encode()).hexdigest()[:8]}"
            )

        if headers:
            # Only include non-auth headers in cache key
            cache_headers = {
                k: v
                for k, v in headers.items()
                if k.lower() not in ["authorization", "x-api-key"]
            }
            if cache_headers:
                header_str = "&".join(
                    f"{k}={v}" for k, v in sorted(cache_headers.items())
                )
                key_parts.append(
                    f"headers:{hashlib.md5(header_str.encode()).hexdigest()[:8]}"
                )

        return ":".join(key_parts)

    def _determine_api_ttl(self, endpoint: str) -> float:
        """Determine TTL for API endpoint based on endpoint characteristics."""
        endpoint_lower = endpoint.lower()

        # Static data endpoints
        if any(keyword in endpoint_lower for keyword in ["market", "token", "info"]):
            return self.settings.static_api_ttl

        # Dynamic data endpoints
        if any(
            keyword in endpoint_lower for keyword in ["price", "book", "trade", "order"]
        ):
            return self.settings.dynamic_api_ttl

        # Default TTL
        return self.settings.api_response_ttl

    def _compress_response(self, response_data: dict[str, Any]) -> dict[str, Any]:
        """Compress response data if beneficial."""

        # Simple compression: remove None values and empty collections
        def clean_dict(d):
            if isinstance(d, dict):
                return {
                    k: clean_dict(v)
                    for k, v in d.items()
                    if v is not None and v != {} and v != []
                }
            elif isinstance(d, list):
                return [clean_dict(item) for item in d if item is not None]
            else:
                return d

        return clean_dict(response_data)

    async def _load_default_trading_rules(
        self, market_id: str | None
    ) -> dict[str, Any] | None:
        """Load default trading rules from configuration."""
        if not self.bot_config:
            return None

        try:
            # Load from bot configuration
            rules = {
                "max_position_size": getattr(
                    self.bot_config, "max_position_size", 1000
                ),
                "min_profit_threshold": getattr(
                    self.bot_config, "min_profit_threshold", 0.01
                ),
                "max_spread": getattr(self.bot_config, "max_spread_threshold", 0.1),
                "risk_limits": {
                    "global_risk_cap": getattr(
                        self.bot_config, "global_risk_cap", 10000
                    ),
                    "per_market_risk_cap": getattr(
                        self.bot_config, "per_market_risk_cap", 1000
                    ),
                    "per_outcome_risk_cap": getattr(
                        self.bot_config, "per_outcome_risk_cap", 500
                    ),
                },
                "timeouts": {
                    "order_timeout": getattr(
                        self.bot_config, "order_timeout_seconds", 30
                    ),
                    "scan_interval": getattr(
                        self.bot_config, "scan_interval_seconds", 5
                    ),
                },
            }

            return rules

        except Exception as e:
            logger.error(f"Failed to load default trading rules: {e}")
            return None

    def get_cache_stats(self) -> dict[str, Any]:
        """Get comprehensive cache statistics."""
        return {
            "config_cache": self.config_cache.get_stats(),
            "api_cache": self.api_cache.get_stats(),
            "reference_cache": self.reference_cache.get_stats(),
            "config_versions": len(self._config_versions),
            "watched_files": len(self._file_timestamps),
            "api_validators": len(self._api_validators),
            "settings": {
                "config_ttl": self.settings.config_ttl,
                "api_response_ttl": self.settings.api_response_ttl,
                "enable_versioning": self.settings.enable_config_versioning,
                "enable_compression": self.settings.enable_api_compression,
                "enable_file_watching": self.settings.enable_file_watching,
            },
        }

    async def shutdown(self):
        """Shutdown configuration cache system."""
        logger.info("Shutting down configuration cache")

        await self.config_cache.shutdown()
        await self.api_cache.shutdown()
        await self.reference_cache.shutdown()


# Global configuration cache instance
_config_cache_instance = None


def get_config_cache(
    bot_config: BotConfig = None, settings: ConfigCacheSettings = None
) -> ConfigurationCache:
    """Get global configuration cache instance."""
    global _config_cache_instance

    if _config_cache_instance is None:
        _config_cache_instance = ConfigurationCache(bot_config, settings)

    return _config_cache_instance


# Convenient decorators for configuration caching
def cache_config_value(ttl: float = 3600.0):
    """Decorator for caching configuration values."""
    return cached("configuration", ttl=ttl, tags={"configuration", "static"})


def cache_api_response(ttl: float = 300.0, is_static: bool = False):
    """Decorator for caching API responses."""
    cache_ttl = ttl if not is_static else 3600.0
    tags = {"api_response", "static" if is_static else "dynamic"}
    return cached("api_responses", ttl=cache_ttl, tags=tags)


def cache_reference_data(ttl: float = 86400.0):
    """Decorator for caching reference data."""
    return cached("reference_data", ttl=ttl, tags={"reference_data", "static"})
