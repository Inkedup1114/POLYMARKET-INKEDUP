"""
Graceful Shutdown Manager for InkedUp Trading Bot.

This module provides comprehensive shutdown handling that ensures:
- All active trades and operations complete cleanly
- Database connections are properly closed
- WebSocket connections are gracefully terminated
- System state is persisted before shutdown
- Resources are properly cleaned up

The shutdown manager integrates with signal handlers to respond to
SIGTERM, SIGINT, and other shutdown signals while giving components
time to finish critical operations.
"""

import asyncio
import logging
import signal
import time
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any

log = logging.getLogger("shutdown_manager")


class ShutdownState(Enum):
    """Shutdown process states."""

    RUNNING = "running"
    SHUTTING_DOWN = "shutting_down"
    CLEANUP = "cleanup"
    STOPPED = "stopped"


class ShutdownPriority(Enum):
    """Component shutdown priorities."""

    CRITICAL = 0  # Must complete (active trades, db writes)
    HIGH = 1  # Should complete (open connections)
    NORMAL = 2  # Can interrupt (background tasks)
    LOW = 3  # Force stop (caches, metrics)


class ShutdownComponent:
    """Represents a component that needs graceful shutdown."""

    def __init__(
        self,
        name: str,
        shutdown_func: Callable[[], Any],
        priority: ShutdownPriority = ShutdownPriority.NORMAL,
        timeout: float = 10.0,
        description: str = "",
    ):
        self.name = name
        self.shutdown_func = shutdown_func
        self.priority = priority
        self.timeout = timeout
        self.description = description
        self.shutdown_start_time: float | None = None
        self.shutdown_complete: bool = False
        self.shutdown_error: Exception | None = None


class GracefulShutdownManager:
    """
    Manages graceful shutdown of all system components.

    Provides coordinated shutdown handling with:
    - Priority-based component shutdown ordering
    - Configurable timeouts per component
    - Force shutdown if graceful shutdown fails
    - Detailed shutdown status reporting
    - Signal handling integration
    """

    def __init__(self, shutdown_timeout: float = 30.0):
        """
        Initialize shutdown manager.

        Args:
            shutdown_timeout: Maximum time to wait for all components to shut down
        """
        self.shutdown_timeout = shutdown_timeout
        self.components: list[ShutdownComponent] = []
        self.shutdown_state = ShutdownState.RUNNING
        self.shutdown_start_time: float | None = None
        self.shutdown_triggered_by: str | None = None
        self.force_shutdown = False

        # Event to coordinate shutdown
        self.shutdown_event = asyncio.Event()

        # Setup default signal handlers
        self._setup_signal_handlers()

        log.info("Graceful shutdown manager initialized")

    def register_component(
        self,
        name: str,
        shutdown_func: Callable[[], Any],
        priority: ShutdownPriority = ShutdownPriority.NORMAL,
        timeout: float = 10.0,
        description: str = "",
    ) -> None:
        """
        Register a component for graceful shutdown.

        Args:
            name: Unique component name
            shutdown_func: Async function to call for shutdown
            priority: Shutdown priority level
            timeout: Maximum time to wait for this component
            description: Human-readable description
        """
        component = ShutdownComponent(
            name=name,
            shutdown_func=shutdown_func,
            priority=priority,
            timeout=timeout,
            description=description,
        )

        self.components.append(component)
        log.info(
            f"Registered shutdown component: {name} (priority={priority.name}, timeout={timeout}s)"
        )

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""

        def signal_handler(signum: int, frame: Any) -> None:
            signal_name = signal.Signals(signum).name
            log.info(f"Received shutdown signal: {signal_name}")

            # Trigger graceful shutdown
            asyncio.create_task(self.trigger_shutdown(f"Signal {signal_name}"))

        # Register handlers for common shutdown signals
        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

            # Handle additional signals on Unix systems
            if hasattr(signal, "SIGHUP"):
                signal.signal(signal.SIGHUP, signal_handler)

            log.info("Signal handlers registered for graceful shutdown")
        except Exception as e:
            log.warning(f"Could not register signal handlers: {e}")

    async def trigger_shutdown(self, reason: str = "Manual trigger") -> None:
        """
        Trigger graceful shutdown process.

        Args:
            reason: Reason for shutdown (for logging)
        """
        if self.shutdown_state != ShutdownState.RUNNING:
            log.warning(
                f"Shutdown already in progress (state: {self.shutdown_state.value})"
            )
            return

        log.info(f"Triggering graceful shutdown: {reason}")
        self.shutdown_state = ShutdownState.SHUTTING_DOWN
        self.shutdown_start_time = time.time()
        self.shutdown_triggered_by = reason

        # Signal all waiting tasks that shutdown has started
        self.shutdown_event.set()

        # Start shutdown process
        await self._execute_shutdown()

    async def _execute_shutdown(self) -> None:
        """Execute the shutdown process."""
        try:
            log.info("Starting graceful shutdown process")

            # Sort components by priority (critical first)
            sorted_components = sorted(
                self.components, key=lambda c: (c.priority.value, c.name)
            )

            # Group components by priority for parallel shutdown within priority levels
            priority_groups: dict[ShutdownPriority, list[ShutdownComponent]] = {}
            for component in sorted_components:
                if component.priority not in priority_groups:
                    priority_groups[component.priority] = []
                priority_groups[component.priority].append(component)

            # Shutdown components by priority group
            total_start_time = time.time()
            for priority in [
                ShutdownPriority.CRITICAL,
                ShutdownPriority.HIGH,
                ShutdownPriority.NORMAL,
                ShutdownPriority.LOW,
            ]:

                if priority not in priority_groups:
                    continue

                components = priority_groups[priority]
                log.info(
                    f"Shutting down {len(components)} components with priority {priority.name}"
                )

                # Start all components in this priority group concurrently
                tasks = []
                for component in components:
                    task = asyncio.create_task(self._shutdown_component(component))
                    tasks.append(task)

                # Wait for all components in this priority group to complete
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

                # Check if we've exceeded total shutdown timeout
                elapsed = time.time() - total_start_time
                if elapsed > self.shutdown_timeout:
                    log.warning(
                        f"Shutdown timeout exceeded ({elapsed:.1f}s > {self.shutdown_timeout}s)"
                    )
                    self.force_shutdown = True
                    break

            # Move to cleanup phase
            self.shutdown_state = ShutdownState.CLEANUP
            await self._final_cleanup()

            # Mark shutdown complete
            self.shutdown_state = ShutdownState.STOPPED
            shutdown_duration = time.time() - total_start_time
            log.info(f"Graceful shutdown completed in {shutdown_duration:.1f}s")

        except Exception as e:
            log.error(f"Error during shutdown process: {e}")
            self.shutdown_state = ShutdownState.STOPPED
            raise

    async def _shutdown_component(self, component: ShutdownComponent) -> None:
        """Shutdown a single component with timeout handling."""
        log.info(f"Shutting down component: {component.name}")
        component.shutdown_start_time = time.time()

        try:
            # Call the shutdown function with timeout
            if asyncio.iscoroutinefunction(component.shutdown_func):
                await asyncio.wait_for(
                    component.shutdown_func(), timeout=component.timeout
                )
            else:
                # Handle sync shutdown functions
                await asyncio.wait_for(
                    asyncio.to_thread(component.shutdown_func),
                    timeout=component.timeout,
                )

            component.shutdown_complete = True
            duration = time.time() - component.shutdown_start_time
            log.info(
                f"Component {component.name} shut down successfully in {duration:.1f}s"
            )

        except TimeoutError:
            duration = time.time() - component.shutdown_start_time
            log.warning(
                f"Component {component.name} shutdown timed out after {duration:.1f}s"
            )
            component.shutdown_error = TimeoutError(
                f"Shutdown timeout after {duration:.1f}s"
            )

        except Exception as e:
            duration = time.time() - component.shutdown_start_time
            log.error(
                f"Component {component.name} shutdown failed after {duration:.1f}s: {e}"
            )
            component.shutdown_error = e

    async def _final_cleanup(self) -> None:
        """Perform final cleanup operations."""
        log.info("Performing final cleanup")

        try:
            # Get all tasks except the current one
            current_task = asyncio.current_task()
            all_tasks = asyncio.all_tasks()

            pending_tasks = []
            for task in all_tasks:
                if task != current_task and not task.done():
                    # Avoid canceling shutdown-related tasks
                    task_name = getattr(task, "get_name", lambda: "unknown")()
                    if "shutdown" not in task_name.lower():
                        pending_tasks.append(task)

            if pending_tasks:
                log.info(f"Cancelling {len(pending_tasks)} pending tasks")
                for task in pending_tasks:
                    if not task.done():
                        task.cancel()

                # Wait for tasks to cancel, but don't use gather to avoid recursion
                cleanup_timeout = 3.0
                start_time = asyncio.get_event_loop().time()

                while (
                    pending_tasks
                    and (asyncio.get_event_loop().time() - start_time) < cleanup_timeout
                ):
                    # Check which tasks are still running
                    still_running = [task for task in pending_tasks if not task.done()]
                    if not still_running:
                        break
                    pending_tasks = still_running
                    await asyncio.sleep(0.1)

                if pending_tasks:
                    log.warning(
                        f"{len(pending_tasks)} tasks did not cancel within timeout"
                    )

            log.info("Final cleanup completed")

        except Exception as e:
            log.error(f"Error during final cleanup: {e}")

    def get_shutdown_status(self) -> dict[str, Any]:
        """
        Get detailed shutdown status.

        Returns:
            Dictionary containing shutdown status information
        """
        timing: dict[str, Any] = {}
        if self.shutdown_start_time:
            timing["started_at"] = datetime.fromtimestamp(
                self.shutdown_start_time
            ).isoformat()
            timing["duration"] = time.time() - self.shutdown_start_time

            if self.shutdown_state == ShutdownState.STOPPED:
                timing["completed_at"] = datetime.now().isoformat()

        component_details: list[dict[str, Any]] = []
        for component in self.components:
            comp_status: dict[str, Any] = {
                "name": component.name,
                "priority": component.priority.name,
                "timeout": component.timeout,
                "description": component.description,
                "completed": component.shutdown_complete,
                "error": (
                    str(component.shutdown_error) if component.shutdown_error else None
                ),
            }

            if component.shutdown_start_time:
                comp_status["duration"] = time.time() - component.shutdown_start_time

            component_details.append(comp_status)

        status: dict[str, Any] = {
            "state": self.shutdown_state.value,
            "triggered_by": self.shutdown_triggered_by,
            "force_shutdown": self.force_shutdown,
            "components": {
                "total": len(self.components),
                "completed": sum(1 for c in self.components if c.shutdown_complete),
                "failed": sum(
                    1 for c in self.components if c.shutdown_error is not None
                ),
                "in_progress": sum(
                    1
                    for c in self.components
                    if c.shutdown_start_time
                    and not c.shutdown_complete
                    and not c.shutdown_error
                ),
            },
            "timing": timing,
            "component_details": component_details,
        }

        return status

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown to be triggered."""
        await self.shutdown_event.wait()

    def is_shutting_down(self) -> bool:
        """Check if shutdown is in progress."""
        return self.shutdown_state != ShutdownState.RUNNING

    def is_shutdown_complete(self) -> bool:
        """Check if shutdown is complete."""
        return self.shutdown_state == ShutdownState.STOPPED


# Global shutdown manager instance
_shutdown_manager: GracefulShutdownManager | None = None


def get_shutdown_manager(timeout: float = 30.0) -> GracefulShutdownManager:
    """Get or create the global shutdown manager."""
    global _shutdown_manager
    if _shutdown_manager is None:
        _shutdown_manager = GracefulShutdownManager(timeout)
    return _shutdown_manager


def register_shutdown_component(
    name: str,
    shutdown_func: Callable[[], Any],
    priority: ShutdownPriority = ShutdownPriority.NORMAL,
    timeout: float = 10.0,
    description: str = "",
) -> None:
    """Register a component with the global shutdown manager."""
    manager = get_shutdown_manager()
    manager.register_component(name, shutdown_func, priority, timeout, description)


async def trigger_graceful_shutdown(reason: str = "Manual trigger") -> None:
    """Trigger graceful shutdown using the global manager."""
    manager = get_shutdown_manager()
    await manager.trigger_shutdown(reason)


async def wait_for_shutdown() -> None:
    """Wait for shutdown to be triggered."""
    manager = get_shutdown_manager()
    await manager.wait_for_shutdown()


def is_shutting_down() -> bool:
    """Check if system is shutting down."""
    if _shutdown_manager is None:
        return False
    return _shutdown_manager.is_shutting_down()
