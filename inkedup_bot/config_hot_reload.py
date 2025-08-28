"""
Configuration Hot Reload System for InkedUp Trading Bot.

This module provides hot reloading capabilities for configuration changes,
allowing the bot to pick up new settings without requiring a restart.

Key Features:
- File system monitoring for .env file changes
- In-memory configuration updates
- Component notification system for config changes
- Validation of new configurations before applying
- Rollback capabilities for invalid configurations
- Thread-safe configuration access

The hot reload system monitors the .env file and triggers configuration
updates when changes are detected. Components can register callbacks to
be notified of configuration changes and update their behavior accordingly.
"""

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .config import BotConfig

log = logging.getLogger("config_hot_reload")


class ConfigChangeEvent:
    """Represents a configuration change event."""

    def __init__(
        self,
        timestamp: datetime,
        old_config: BotConfig,
        new_config: BotConfig,
        changed_fields: set[str],
        trigger: str = "file_change",
    ):
        self.timestamp = timestamp
        self.old_config = old_config
        self.new_config = new_config
        self.changed_fields = changed_fields
        self.trigger = trigger


class ConfigValidator:
    """Validates configuration changes before applying them."""

    @staticmethod
    def validate_critical_fields(
        old_config: BotConfig, new_config: BotConfig
    ) -> list[str]:
        """
        Check if critical fields have changed that require restart.

        Returns:
            List of critical field names that changed
        """
        critical_fields = [
            "public_key",
            "private_key",
            "database_url",
            "polymarket_api_base",
        ]

        changed_critical = []
        for field in critical_fields:
            old_value = getattr(old_config, field, None)
            new_value = getattr(new_config, field, None)
            if old_value != new_value:
                changed_critical.append(field)

        return changed_critical

    @staticmethod
    def validate_config_integrity(config: BotConfig) -> tuple[bool, list[str]]:
        """
        Validate that the configuration is internally consistent.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        try:
            # Test that pydantic validation passes
            config.model_validate(config.model_dump())
        except Exception as e:
            errors.append(f"Pydantic validation failed: {e}")

        # Custom validation logic
        if config.api_timeout_seconds <= 0:
            errors.append("API timeout must be positive")

        if config.api_retry_attempts < 0:
            errors.append("API retry attempts cannot be negative")

        if config.market_cache_ttl <= 0:
            errors.append("Market cache TTL must be positive")

        # Trading validation
        if config.max_position_size <= 0:
            errors.append("Maximum position size must be positive")

        if config.complement_arb_min_deviation < 0:
            errors.append("Complement arbitrage deviation cannot be negative")

        return len(errors) == 0, errors


class ConfigHotReloadManager:
    """
    Manages hot reloading of configuration files.

    Monitors .env file changes and provides a thread-safe way to access
    the current configuration while allowing components to register for
    change notifications.
    """

    def __init__(self, env_file_path: str = ".env"):
        """
        Initialize the hot reload manager.

        Args:
            env_file_path: Path to the .env file to monitor
        """
        self.env_file_path = Path(env_file_path).resolve()
        self.current_config = BotConfig()
        self.config_lock = threading.RLock()

        # Change tracking
        self.change_callbacks: list[Callable[[ConfigChangeEvent], None]] = []
        self.last_reload_time: datetime | None = None
        self.reload_count = 0

        # File monitoring
        self.observer: Observer | None = None
        self.file_handler: EnvFileHandler | None = None
        self.is_monitoring = False

        # Validation
        self.validator = ConfigValidator()

        # Stats
        self.successful_reloads = 0
        self.failed_reloads = 0

        log.info(
            f"Configuration hot reload manager initialized (watching: {self.env_file_path})"
        )

    def get_config(self) -> BotConfig:
        """Get the current configuration thread-safely."""
        with self.config_lock:
            return self.current_config

    def register_change_callback(
        self, callback: Callable[[ConfigChangeEvent], None]
    ) -> None:
        """
        Register a callback to be called when configuration changes.

        Args:
            callback: Function to call with ConfigChangeEvent when config changes
        """
        self.change_callbacks.append(callback)
        log.info(f"Registered config change callback: {callback.__name__}")

    def unregister_change_callback(
        self, callback: Callable[[ConfigChangeEvent], None]
    ) -> None:
        """Unregister a previously registered callback."""
        if callback in self.change_callbacks:
            self.change_callbacks.remove(callback)
            log.info(f"Unregistered config change callback: {callback.__name__}")

    def start_monitoring(self) -> None:
        """Start monitoring the .env file for changes."""
        if self.is_monitoring:
            log.warning("File monitoring is already active")
            return

        if not self.env_file_path.exists():
            log.warning(
                f"Environment file {self.env_file_path} does not exist, creating empty file"
            )
            self.env_file_path.touch()

        # Setup file system monitoring
        self.file_handler = EnvFileHandler(self)
        self.observer = Observer()
        self.observer.schedule(
            self.file_handler, str(self.env_file_path.parent), recursive=False
        )

        self.observer.start()
        self.is_monitoring = True

        log.info(f"Started monitoring {self.env_file_path} for configuration changes")

    def stop_monitoring(self) -> None:
        """Stop monitoring the .env file."""
        if not self.is_monitoring:
            return

        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None

        self.file_handler = None
        self.is_monitoring = False

        log.info("Stopped configuration file monitoring")

    def reload_config(self, trigger: str = "manual") -> bool:
        """
        Manually reload configuration from file.

        Args:
            trigger: Description of what triggered the reload

        Returns:
            True if reload was successful, False otherwise
        """
        log.info(f"Reloading configuration (trigger: {trigger})")

        try:
            with self.config_lock:
                # Load new configuration
                old_config = self.current_config

                # Force reload environment variables
                if self.env_file_path.exists():
                    from dotenv import load_dotenv

                    load_dotenv(self.env_file_path, override=True)

                new_config = BotConfig()

                # Validate new configuration
                is_valid, errors = self.validator.validate_config_integrity(new_config)
                if not is_valid:
                    log.error(f"Configuration validation failed: {errors}")
                    self.failed_reloads += 1
                    return False

                # Check for critical changes
                critical_changes = self.validator.validate_critical_fields(
                    old_config, new_config
                )
                if critical_changes:
                    log.warning(
                        f"Critical configuration fields changed: {critical_changes}"
                    )
                    log.warning(
                        "Some changes may require a restart to take full effect"
                    )

                # Detect all changes
                changed_fields = self._detect_changes(old_config, new_config)

                if not changed_fields:
                    log.info("No configuration changes detected")
                    return True

                # Apply new configuration
                self.current_config = new_config
                self.last_reload_time = datetime.now()
                self.reload_count += 1
                self.successful_reloads += 1

                log.info(
                    f"Configuration reloaded successfully ({len(changed_fields)} fields changed)"
                )
                log.debug(f"Changed fields: {', '.join(changed_fields)}")

                # Notify callbacks
                change_event = ConfigChangeEvent(
                    timestamp=self.last_reload_time,
                    old_config=old_config,
                    new_config=new_config,
                    changed_fields=changed_fields,
                    trigger=trigger,
                )

                self._notify_callbacks(change_event)

                return True

        except Exception as e:
            log.error(f"Failed to reload configuration: {e}")
            self.failed_reloads += 1
            return False

    def _detect_changes(self, old_config: BotConfig, new_config: BotConfig) -> set[str]:
        """Detect which configuration fields have changed."""
        changed_fields = set()

        old_dict = old_config.model_dump()
        new_dict = new_config.model_dump()

        # Compare all fields
        all_fields = set(old_dict.keys()) | set(new_dict.keys())

        for field in all_fields:
            old_value = old_dict.get(field)
            new_value = new_dict.get(field)

            if old_value != new_value:
                changed_fields.add(field)

        return changed_fields

    def _notify_callbacks(self, change_event: ConfigChangeEvent) -> None:
        """Notify all registered callbacks of configuration changes."""
        for callback in self.change_callbacks:
            try:
                callback(change_event)
            except Exception as e:
                log.error(f"Error in config change callback {callback.__name__}: {e}")

    def get_reload_stats(self) -> dict[str, Any]:
        """Get statistics about configuration reloads."""
        return {
            "monitoring": self.is_monitoring,
            "env_file_path": str(self.env_file_path),
            "env_file_exists": self.env_file_path.exists(),
            "last_reload_time": (
                self.last_reload_time.isoformat() if self.last_reload_time else None
            ),
            "total_reloads": self.reload_count,
            "successful_reloads": self.successful_reloads,
            "failed_reloads": self.failed_reloads,
            "registered_callbacks": len(self.change_callbacks),
            "current_config_hash": hash(str(self.current_config.model_dump())),
        }


class EnvFileHandler(FileSystemEventHandler):
    """File system event handler for .env file changes."""

    def __init__(self, reload_manager: ConfigHotReloadManager):
        super().__init__()
        self.reload_manager = reload_manager
        self.last_modification_time = 0
        self.debounce_seconds = 1.0  # Prevent multiple rapid reloads

    def on_modified(self, event):
        """Handle file modification events."""
        if event.is_directory:
            return

        # Check if it's our .env file
        if Path(event.src_path).resolve() == self.reload_manager.env_file_path:
            current_time = time.time()

            # Debounce multiple rapid changes
            if current_time - self.last_modification_time < self.debounce_seconds:
                return

            self.last_modification_time = current_time

            log.info(f"Environment file changed: {event.src_path}")

            # Reload configuration in background thread to avoid blocking file watcher
            threading.Thread(
                target=self.reload_manager.reload_config,
                args=("file_change",),
                daemon=True,
            ).start()


# Global hot reload manager instance
_hot_reload_manager: ConfigHotReloadManager | None = None


def get_hot_reload_manager(env_file_path: str = ".env") -> ConfigHotReloadManager:
    """Get or create the global hot reload manager."""
    global _hot_reload_manager
    if _hot_reload_manager is None:
        _hot_reload_manager = ConfigHotReloadManager(env_file_path)
    return _hot_reload_manager


def get_current_config() -> BotConfig:
    """Get the current configuration (hot-reloadable)."""
    manager = get_hot_reload_manager()
    return manager.get_config()


def register_config_change_callback(
    callback: Callable[[ConfigChangeEvent], None]
) -> None:
    """Register a callback for configuration changes."""
    manager = get_hot_reload_manager()
    manager.register_change_callback(callback)


def start_config_monitoring() -> None:
    """Start monitoring configuration files for changes."""
    manager = get_hot_reload_manager()
    manager.start_monitoring()


def stop_config_monitoring() -> None:
    """Stop monitoring configuration files for changes."""
    manager = get_hot_reload_manager()
    manager.stop_monitoring()


def reload_config_now() -> bool:
    """Manually trigger a configuration reload."""
    manager = get_hot_reload_manager()
    return manager.reload_config("manual_trigger")


def get_config_reload_stats() -> dict[str, Any]:
    """Get statistics about configuration reloads."""
    manager = get_hot_reload_manager()
    return manager.get_reload_stats()
