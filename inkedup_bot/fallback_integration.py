"""
Integration utilities for adding fallback support to existing StateManager.

This module provides utilities to upgrade the existing StateManager with
fallback capabilities while maintaining backward compatibility.
"""

import logging
from typing import Any

from .enhanced_state import EnhancedStateManager

log = logging.getLogger("fallback_integration")


class FallbackIntegration:
    """
    Integration utility to add fallback support to existing StateManager instances.

    This class wraps the existing StateManager and provides fallback capabilities
    without breaking existing API contracts.
    """

    def __init__(
        self,
        original_state_manager,
        enable_fallback: bool = True,
        auto_upgrade: bool = False,
    ):
        """
        Initialize fallback integration.

        Args:
            original_state_manager: Existing StateManager instance
            enable_fallback: Whether to enable fallback functionality
            auto_upgrade: Whether to automatically upgrade to EnhancedStateManager
        """
        self.original_manager = original_state_manager
        self.enable_fallback = enable_fallback
        self.auto_upgrade = auto_upgrade

        # Enhanced manager (created on-demand)
        self._enhanced_manager: EnhancedStateManager | None = None
        self._upgrade_in_progress = False

    async def get_manager(self):
        """
        Get the appropriate state manager.

        Returns either the original manager or an enhanced one with fallback support.
        """
        if not self.enable_fallback:
            return self.original_manager

        if (
            self.auto_upgrade
            and not self._enhanced_manager
            and not self._upgrade_in_progress
        ):
            await self._upgrade_to_enhanced()

        return self._enhanced_manager or self.original_manager

    async def _upgrade_to_enhanced(self):
        """Upgrade to EnhancedStateManager with fallback support."""
        if self._upgrade_in_progress:
            return

        self._upgrade_in_progress = True
        log.info("Upgrading StateManager to EnhancedStateManager with fallback support")

        try:
            # Create enhanced manager with same database path
            db_path = getattr(self.original_manager.db, "db_path", "bot_data.db")

            self._enhanced_manager = EnhancedStateManager(
                db_path=str(db_path),
                enable_fallback=True,
                enable_auto_recovery=True,
            )

            await self._enhanced_manager.initialize()

            # Migrate in-memory data if available
            await self._migrate_in_memory_data()

            log.info("Successfully upgraded to EnhancedStateManager")

        except Exception as e:
            log.error(f"Failed to upgrade StateManager: {e}")
            self._enhanced_manager = None
        finally:
            self._upgrade_in_progress = False

    async def _migrate_in_memory_data(self):
        """Migrate in-memory data from original to enhanced manager."""
        if not self._enhanced_manager or not hasattr(
            self.original_manager, "open_orders"
        ):
            return

        try:
            # Migrate orders
            for order_id, order_data in self.original_manager.open_orders.items():
                if self._enhanced_manager.fallback_manager:
                    self._enhanced_manager.fallback_manager.memory_store.insert_order(
                        order_data
                    )

            # Migrate positions
            for token_id, position_data in self.original_manager.positions.items():
                if self._enhanced_manager.fallback_manager:
                    self._enhanced_manager.fallback_manager.memory_store.upsert_position(
                        position_data
                    )

            log.info(
                f"Migrated {len(self.original_manager.open_orders)} orders and "
                f"{len(self.original_manager.positions)} positions"
            )

        except Exception as e:
            log.error(f"Failed to migrate in-memory data: {e}")

    async def force_fallback_mode(self, reason: str = "Manual override"):
        """Force fallback mode if enhanced manager is available."""
        manager = await self.get_manager()
        if hasattr(manager, "force_fallback_mode"):
            await manager.force_fallback_mode(reason)
        else:
            log.warning("Fallback mode not available in current manager")

    async def get_fallback_status(self) -> dict[str, Any]:
        """Get fallback status if available."""
        manager = await self.get_manager()
        if hasattr(manager, "get_fallback_status"):
            return manager.get_fallback_status()
        else:
            return {"fallback_enabled": False, "mode": "legacy"}

    async def shutdown(self):
        """Shutdown all managers properly."""
        if self._enhanced_manager:
            await self._enhanced_manager.shutdown()
        # Note: Don't shutdown original manager as it may be used elsewhere


def create_fallback_wrapper(state_manager, enable_fallback: bool = True):
    """
    Create a fallback-enabled wrapper for an existing StateManager.

    This is a convenience function to quickly add fallback support to
    existing StateManager instances.

    Args:
        state_manager: Existing StateManager instance
        enable_fallback: Whether to enable fallback functionality

    Returns:
        FallbackIntegration wrapper
    """
    return FallbackIntegration(
        state_manager,
        enable_fallback=enable_fallback,
        auto_upgrade=True,
    )


async def upgrade_state_manager_with_fallback(
    state_manager,
    db_path: str | None = None,
    enable_auto_recovery: bool = True,
) -> EnhancedStateManager:
    """
    Upgrade an existing StateManager to EnhancedStateManager with fallback support.

    Args:
        state_manager: Existing StateManager to upgrade
        db_path: Database path (auto-detected if not provided)
        enable_auto_recovery: Whether to enable automatic recovery

    Returns:
        New EnhancedStateManager instance with fallback support
    """
    log.info("Upgrading StateManager to EnhancedStateManager")

    # Determine database path
    if db_path is None:
        db_path = getattr(state_manager.db, "db_path", "bot_data.db")

    # Create enhanced manager
    enhanced_manager = EnhancedStateManager(
        db_path=str(db_path),
        enable_fallback=True,
        enable_auto_recovery=enable_auto_recovery,
    )

    await enhanced_manager.initialize()

    # Copy risk manager reference if available
    if hasattr(state_manager, "_risk_manager") and state_manager._risk_manager:
        enhanced_manager.set_risk_manager(state_manager._risk_manager)

    # Migrate in-memory data if available
    if hasattr(state_manager, "open_orders") and state_manager.open_orders:
        for order_id, order_data in state_manager.open_orders.items():
            if enhanced_manager.fallback_manager:
                enhanced_manager.fallback_manager.memory_store.insert_order(order_data)
        log.info(f"Migrated {len(state_manager.open_orders)} orders")

    if hasattr(state_manager, "positions") and state_manager.positions:
        for token_id, position_data in state_manager.positions.items():
            if enhanced_manager.fallback_manager:
                enhanced_manager.fallback_manager.memory_store.upsert_position(
                    position_data
                )
        log.info(f"Migrated {len(state_manager.positions)} positions")

    log.info("StateManager upgrade completed successfully")
    return enhanced_manager


class FallbackStateManagerProxy:
    """
    A proxy that provides fallback functionality while maintaining the original StateManager API.

    This proxy delegates all method calls to either the original StateManager or
    an enhanced version with fallback support, depending on configuration and conditions.
    """

    def __init__(self, original_manager, enable_fallback: bool = True):
        self._original = original_manager
        self._enhanced: EnhancedStateManager | None = None
        self._enable_fallback = enable_fallback
        self._fallback_active = False

    def __getattr__(self, name):
        """Delegate method calls to the appropriate manager."""
        # Get the active manager
        active_manager = (
            self._enhanced
            if (self._enhanced and self._fallback_active)
            else self._original
        )

        # Get the method from the active manager
        method = getattr(active_manager, name)

        # If it's a method that should be wrapped for fallback support
        if self._enable_fallback and name in [
            "add_order",
            "update_order",
            "update_position",
            "get_order",
            "get_position",
        ]:
            return self._wrap_method_with_fallback(method, name)

        return method

    def _wrap_method_with_fallback(self, method, method_name):
        """Wrap a method with fallback functionality."""

        def wrapper(*args, **kwargs):
            try:
                # Try the original method first
                result = method(*args, **kwargs)
                return result
            except Exception as e:
                # If not already using enhanced manager, try to create one
                if not self._enhanced and not self._fallback_active:
                    try:
                        # This would need to be implemented to create enhanced manager
                        log.warning(
                            f"Method {method_name} failed, but fallback not fully implemented in proxy"
                        )
                    except Exception as fallback_error:
                        log.error(
                            f"Fallback implementation failed for method {method_name}: {fallback_error}",
                            exc_info=True,
                        )

                # Re-raise the original exception if fallback fails
                raise e

        return wrapper

    async def enable_fallback(self):
        """Enable fallback functionality by creating enhanced manager."""
        if not self._enable_fallback or self._enhanced:
            return

        try:
            self._enhanced = await upgrade_state_manager_with_fallback(self._original)
            log.info("Fallback functionality enabled via proxy")
        except Exception as e:
            log.error(f"Failed to enable fallback functionality: {e}")

    async def activate_fallback(self, reason: str = "Proxy activation"):
        """Activate fallback mode."""
        if self._enhanced:
            await self._enhanced.force_fallback_mode(reason)
            self._fallback_active = True
            log.info(f"Fallback mode activated: {reason}")

    def get_fallback_status(self):
        """Get current fallback status."""
        if self._enhanced:
            return self._enhanced.get_fallback_status()
        else:
            return {"fallback_enabled": False, "mode": "proxy_original"}


# Convenience function for quick fallback integration
def add_fallback_to_state_manager(state_manager, enable_fallback: bool = True):
    """
    Add fallback functionality to an existing StateManager instance.

    This is the simplest way to add fallback support to existing code.

    Args:
        state_manager: Existing StateManager instance
        enable_fallback: Whether to enable fallback functionality

    Returns:
        Proxy with fallback support
    """
    return FallbackStateManagerProxy(state_manager, enable_fallback)
