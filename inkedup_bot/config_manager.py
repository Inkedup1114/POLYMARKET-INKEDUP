"""
Configuration Manager with Hot Reload Integration.

This module provides a high-level interface for configuration management
with hot reload capabilities. It integrates the hot reload system with
existing components and provides utilities for configuration updates.
"""

import logging
from typing import Any, Protocol

from .config import BotConfig
from .config_hot_reload import (
    ConfigChangeEvent,
    get_hot_reload_manager,
)

log = logging.getLogger("config_manager")


class ConfigurableComponent(Protocol):
    """Protocol for components that can respond to configuration changes."""

    def update_config(self, new_config: BotConfig, changed_fields: set[str]) -> None:
        """
        Update component configuration.

        Args:
            new_config: The new configuration
            changed_fields: Set of field names that changed
        """
        ...


class ConfigManager:
    """
    High-level configuration manager with hot reload support.

    Provides a centralized way to manage configuration across the application
    with automatic hot reload capabilities and component notifications.
    """

    def __init__(self, env_file_path: str = ".env"):
        """
        Initialize configuration manager.

        Args:
            env_file_path: Path to the .env file to monitor
        """
        self.env_file_path = env_file_path
        self.hot_reload_manager = get_hot_reload_manager(env_file_path)
        self.registered_components: dict[str, ConfigurableComponent] = {}
        self.startup_config: BotConfig | None = None
        self.is_started = False

        # Register our callback
        self.hot_reload_manager.register_change_callback(self._on_config_changed)

        log.info("Configuration manager initialized")

    def start(self) -> None:
        """Start the configuration manager and hot reload monitoring."""
        if self.is_started:
            log.warning("Configuration manager is already started")
            return

        # Store initial configuration
        self.startup_config = self.hot_reload_manager.get_config()

        # Start file monitoring
        self.hot_reload_manager.start_monitoring()

        self.is_started = True
        log.info("Configuration manager started with hot reload monitoring")

    def stop(self) -> None:
        """Stop the configuration manager."""
        if not self.is_started:
            return

        self.hot_reload_manager.stop_monitoring()
        self.is_started = False
        log.info("Configuration manager stopped")

    def get_config(self) -> BotConfig:
        """Get the current configuration."""
        return self.hot_reload_manager.get_config()

    def register_component(self, name: str, component: ConfigurableComponent) -> None:
        """
        Register a component to receive configuration updates.

        Args:
            name: Unique name for the component
            component: Component implementing ConfigurableComponent protocol
        """
        self.registered_components[name] = component
        log.info(f"Registered configurable component: {name}")

        # Give the component the current configuration
        try:
            current_config = self.get_config()
            component.update_config(current_config, set())
        except Exception as e:
            log.error(f"Failed to initialize component {name} with current config: {e}")

    def unregister_component(self, name: str) -> None:
        """Unregister a component."""
        if name in self.registered_components:
            del self.registered_components[name]
            log.info(f"Unregistered configurable component: {name}")

    def reload_config(self) -> bool:
        """Manually trigger a configuration reload."""
        return self.hot_reload_manager.reload_config("manual_from_config_manager")

    def get_reload_stats(self) -> dict[str, Any]:
        """Get configuration reload statistics."""
        stats = self.hot_reload_manager.get_reload_stats()
        stats["registered_components"] = list(self.registered_components.keys())
        stats["is_started"] = self.is_started
        return stats

    def _on_config_changed(self, change_event: ConfigChangeEvent) -> None:
        """Handle configuration change events."""
        log.info(
            f"Configuration changed: {len(change_event.changed_fields)} fields updated"
        )
        log.debug(f"Changed fields: {', '.join(change_event.changed_fields)}")

        # Notify all registered components
        failed_components = []

        for name, component in self.registered_components.items():
            try:
                component.update_config(
                    change_event.new_config, change_event.changed_fields
                )
                log.debug(f"Updated component {name} with new configuration")
            except Exception as e:
                log.error(
                    f"Failed to update component {name} with new configuration: {e}"
                )
                failed_components.append(name)

        if failed_components:
            log.warning(
                f"Failed to update {len(failed_components)} components: {failed_components}"
            )
        else:
            log.info(
                f"Successfully updated {len(self.registered_components)} components"
            )


class ConfigurableOrderClient:
    """
    Wrapper for OrderClient that supports configuration hot reload.

    This is an example of how to make existing components configurable.
    """

    def __init__(self, order_client, initial_config: BotConfig):
        self.order_client = order_client
        self.current_config = initial_config

        # Fields that should trigger order client reconfiguration
        self.relevant_fields = {
            "api_timeout_seconds",
            "api_retry_attempts",
            "api_retry_delay_seconds",
            "rate_limit_orders_per_second",
            "rate_limit_orders_per_minute",
            "rate_limit_orders_per_hour",
            "rate_limit_orders_burst",
            "debug_mode",
        }

    def update_config(self, new_config: BotConfig, changed_fields: set[str]) -> None:
        """Update order client configuration."""
        # Check if any relevant fields changed
        relevant_changes = changed_fields & self.relevant_fields

        if not relevant_changes:
            return

        log.info(f"Updating OrderClient configuration: {relevant_changes}")

        # Update timeout settings
        if hasattr(self.order_client, "_session"):
            timeout = new_config.api_timeout_seconds
            if hasattr(self.order_client._session, "_timeout"):
                self.order_client._session._timeout = timeout

        # Update retry settings if available
        if hasattr(self.order_client, "retry_attempts"):
            self.order_client.retry_attempts = new_config.api_retry_attempts

        if hasattr(self.order_client, "retry_delay"):
            self.order_client.retry_delay = new_config.api_retry_delay_seconds

        # Update rate limiting if available
        if hasattr(self.order_client, "rate_limiter"):
            # This would require implementing rate limiter reconfiguration
            log.debug("Rate limiting configuration update not implemented yet")

        self.current_config = new_config
        log.info("OrderClient configuration updated successfully")


class ConfigurableScanner:
    """
    Wrapper for Scanner that supports configuration hot reload.
    """

    def __init__(self, scanner, initial_config: BotConfig):
        self.scanner = scanner
        self.current_config = initial_config

        # Fields that should trigger scanner reconfiguration
        self.relevant_fields = {
            "market_cache_ttl",
            "complement_arb_min_deviation",
            "complement_arb_max_size",
            "spread_alert_bps",
            "max_position_size",
            "enable_complement_arbitrage",
            "enable_spread_alerts",
        }

    def update_config(self, new_config: BotConfig, changed_fields: set[str]) -> None:
        """Update scanner configuration."""
        relevant_changes = changed_fields & self.relevant_fields

        if not relevant_changes:
            return

        log.info(f"Updating Scanner configuration: {relevant_changes}")

        # Update market cache TTL
        if "market_cache_ttl" in relevant_changes:
            if hasattr(self.scanner, "market_cache_ttl"):
                self.scanner.market_cache_ttl = new_config.market_cache_ttl

        # Update arbitrage settings
        if "complement_arb_min_deviation" in relevant_changes:
            if hasattr(self.scanner, "min_deviation"):
                self.scanner.min_deviation = new_config.complement_arb_min_deviation

        # Update risk settings
        if "max_position_size" in relevant_changes:
            if hasattr(self.scanner, "max_position_size"):
                self.scanner.max_position_size = new_config.max_position_size

        # Update strategy enablement
        if hasattr(self.scanner, "strategies"):
            if "enable_complement_arbitrage" in relevant_changes:
                # Enable/disable complement arbitrage strategy
                log.debug("Strategy enablement updates not fully implemented")

        self.current_config = new_config
        log.info("Scanner configuration updated successfully")


# Global configuration manager instance
_config_manager: ConfigManager | None = None


def get_config_manager(env_file_path: str = ".env") -> ConfigManager:
    """Get or create the global configuration manager."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(env_file_path)
    return _config_manager


def start_config_management() -> None:
    """Start the global configuration manager."""
    manager = get_config_manager()
    manager.start()


def stop_config_management() -> None:
    """Stop the global configuration manager."""
    if _config_manager is not None:
        _config_manager.stop()


def register_configurable_component(
    name: str, component: ConfigurableComponent
) -> None:
    """Register a component with the global configuration manager."""
    manager = get_config_manager()
    manager.register_component(name, component)
