"""
Optimized Connection Pool Integration

Enhanced connection pool system that integrates dynamic optimization with the
existing connection pool infrastructure. Provides backward compatibility while
adding intelligent scaling capabilities.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from .connection_pool import (
    CircuitBreakerConfig,
    ConnectionPoolManager,
    PostgreSQLConnectionPool,
    SQLiteConnectionPool,
)
from .dynamic_connection_optimizer import (
    DynamicConnectionOptimizer,
    OptimizerConfig,
    create_connection_optimizer,
)

logger = logging.getLogger("optimized_connection_pool")


class OptimizedConnectionPoolManager:
    """
    Enhanced connection pool manager with dynamic optimization.

    Manages database connection pools with intelligent pool sizing
    based on real-time market activity and system performance.
    """

    def __init__(
        self,
        database_url: str,
        pool_size: int = 10,
        min_size: int = 1,
        max_size: int = 20,
        health_check_interval: int = 60,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        enable_optimization: bool = True,
        aggressive_scaling: bool = False,
        optimization_interval: int = 300,  # 5 minutes
    ):
        """
        Initialize optimized connection pool manager.

        Args:
            database_url: Database connection URL
            pool_size: Initial pool size
            min_size: Minimum pool size
            max_size: Maximum pool size
            health_check_interval: Health check interval in seconds
            circuit_breaker_config: Circuit breaker configuration
            enable_optimization: Enable dynamic optimization
            aggressive_scaling: Enable aggressive scaling behavior
            optimization_interval: Optimization check interval in seconds
        """
        # Store configuration
        self.database_url = database_url
        self.pool_size = pool_size
        self.min_size = min_size
        self.max_size = max_size
        self.health_check_interval = health_check_interval
        self.circuit_breaker_config = circuit_breaker_config

        # Create the actual connection pool using the factory
        self.pool = ConnectionPoolManager.create_pool(
            database_url=database_url,
            pool_size=pool_size,
            min_size=min_size,
            max_size=max_size,
            health_check_interval=health_check_interval,
            circuit_breaker_config=circuit_breaker_config,
        )

        # Dynamic optimization setup
        self.enable_optimization = enable_optimization
        self.optimization_interval = optimization_interval

        if self.enable_optimization:
            self.optimizer = create_connection_optimizer(
                aggressive_scaling=aggressive_scaling, enable_monitoring=True
            )
        else:
            self.optimizer = None

        # Pool tracking
        self._pool_id = f"pool_{id(self)}"
        self._optimization_started = False

        logger.info(
            f"OptimizedConnectionPoolManager initialized (optimization: {enable_optimization})"
        )

    async def get_connection(self):
        """Get a database connection from the pool."""
        return await self.pool.get_connection()

    def connection(self):
        """Context manager for getting a database connection."""
        return self.pool.connection()

    async def initialize(self):
        """Initialize the connection pool with optimization."""
        # Initialize the connection pool
        await self.pool.initialize()

        # Set up optimization if enabled
        if self.enable_optimization and self.optimizer and self.pool:
            # Register pool with optimizer
            current_min = getattr(self.pool, "min_size", 1)
            current_max = getattr(self.pool, "max_size", 20)

            self.optimizer.register_pool(
                pool_id=self._pool_id,
                pool_reference=self.pool,
                current_min_size=current_min,
                current_max_size=current_max,
            )

            # Start monitoring
            await self.optimizer.start_monitoring(self.optimization_interval)
            self._optimization_started = True

            logger.info(f"Dynamic optimization started for pool {self._pool_id}")

    def update_activity_metrics(
        self,
        signals_count: int = 0,
        orders_count: int = 0,
        websocket_messages_count: int = 0,
        market_data_requests_count: int = 0,
    ) -> None:
        """
        Update activity metrics for optimization decisions.

        Args:
            signals_count: Number of trading signals processed
            orders_count: Number of orders placed
            websocket_messages_count: Number of WebSocket messages
            market_data_requests_count: Number of market data requests
        """
        if self.optimizer:
            self.optimizer.update_activity_metrics(
                signals_count=signals_count,
                orders_count=orders_count,
                websocket_messages_count=websocket_messages_count,
                market_data_requests_count=market_data_requests_count,
            )

    async def force_optimization(self) -> Dict[str, Any]:
        """
        Force an immediate optimization check.

        Returns:
            Optimization decisions made
        """
        if not self.optimizer:
            return {}

        decisions = await self.optimizer.optimize_pool_sizes()
        logger.info(f"Forced optimization completed: {len(decisions)} decisions")
        return decisions

    def get_optimization_status(self) -> Dict[str, Any]:
        """
        Get current optimization status and statistics.

        Returns:
            Current optimization status
        """
        if not self.optimizer:
            return {"optimization_enabled": False, "status": "disabled"}

        stats = self.optimizer.get_optimization_stats()

        # Add current pool status
        pool_status = {}
        if self.pool:
            if hasattr(self.pool, "stats"):
                pool_stats = self.pool.stats
                pool_status = {
                    "current_connections_in_use": getattr(
                        pool_stats, "current_connections_in_use", 0
                    ),
                    "current_idle_connections": getattr(
                        pool_stats, "current_idle_connections", 0
                    ),
                    "total_connections_created": getattr(
                        pool_stats, "total_connections_created", 0
                    ),
                    "average_response_time_ms": getattr(
                        pool_stats, "average_response_time_ms", 0
                    ),
                    "pool_utilization": self._calculate_pool_utilization(),
                }

            pool_status.update(
                {
                    "min_size": getattr(self.pool, "min_size", 0),
                    "max_size": getattr(self.pool, "max_size", 0),
                    "state": (
                        getattr(self.pool, "state", "unknown").value
                        if hasattr(getattr(self.pool, "state", None), "value")
                        else "unknown"
                    ),
                }
            )

        return {
            "optimization_enabled": self.enable_optimization,
            "optimization_started": self._optimization_started,
            "pool_id": self._pool_id,
            "optimizer_stats": stats,
            "pool_status": pool_status,
            "last_updated": datetime.now().isoformat(),
        }

    def _calculate_pool_utilization(self) -> float:
        """Calculate current pool utilization percentage."""
        if not self.pool or not hasattr(self.pool, "stats"):
            return 0.0

        stats = self.pool.stats
        in_use = getattr(stats, "current_connections_in_use", 0)
        idle = getattr(stats, "current_idle_connections", 0)
        total = in_use + idle

        if total == 0:
            return 0.0

        return in_use / total

    async def close(self):
        """Close the pool and stop optimization."""
        # Stop optimization first
        if self.optimizer and self._optimization_started:
            await self.optimizer.stop_monitoring()
            logger.info(f"Stopped optimization for pool {self._pool_id}")

        # Close the connection pool
        await self.pool.close()

        logger.info(f"OptimizedConnectionPoolManager closed")


class OptimizedPostgreSQLPool(PostgreSQLConnectionPool):
    """PostgreSQL connection pool with dynamic optimization."""

    def __init__(
        self,
        database_url: str,
        pool_size: int = 10,
        min_size: int = 1,
        max_size: int = 20,
        health_check_interval: int = 60,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        enable_optimization: bool = True,
        aggressive_scaling: bool = False,
    ):
        super().__init__(
            database_url=database_url,
            pool_size=pool_size,
            min_size=min_size,
            max_size=max_size,
            health_check_interval=health_check_interval,
            circuit_breaker_config=circuit_breaker_config,
        )

        self.enable_optimization = enable_optimization
        if enable_optimization:
            self.optimizer = create_connection_optimizer(
                aggressive_scaling=aggressive_scaling
            )
            self._pool_id = f"postgresql_{id(self)}"
        else:
            self.optimizer = None

    async def initialize(self):
        """Initialize with optimization support."""
        await super().initialize()

        if self.optimizer:
            self.optimizer.register_pool(
                pool_id=self._pool_id,
                pool_reference=self,
                current_min_size=self.min_size,
                current_max_size=self.max_size,
            )
            await self.optimizer.start_monitoring(300)  # 5 minutes


class OptimizedSQLitePool(SQLiteConnectionPool):
    """SQLite connection pool with dynamic optimization."""

    def __init__(
        self,
        database_url: str,
        pool_size: int = 5,
        min_size: int = 1,
        max_size: int = 10,
        health_check_interval: int = 60,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        enable_optimization: bool = True,
        aggressive_scaling: bool = False,
    ):
        super().__init__(
            database_url=database_url,
            pool_size=pool_size,
            min_size=min_size,
            max_size=max_size,
            health_check_interval=health_check_interval,
            circuit_breaker_config=circuit_breaker_config,
        )

        self.enable_optimization = enable_optimization
        if enable_optimization:
            self.optimizer = create_connection_optimizer(
                aggressive_scaling=aggressive_scaling
            )
            self._pool_id = f"sqlite_{id(self)}"
        else:
            self.optimizer = None

    async def initialize(self):
        """Initialize with optimization support."""
        await super().initialize()

        if self.optimizer:
            self.optimizer.register_pool(
                pool_id=self._pool_id,
                pool_reference=self,
                current_min_size=self.min_size,
                current_max_size=self.max_size,
            )
            await self.optimizer.start_monitoring(300)  # 5 minutes


# Factory functions for easy migration
def create_optimized_pool_manager(
    database_url: str,
    pool_size: int = 10,
    min_size: int = 1,
    max_size: int = 20,
    enable_optimization: bool = True,
    aggressive_scaling: bool = False,
) -> OptimizedConnectionPoolManager:
    """
    Create an optimized connection pool manager with recommended settings.

    Args:
        database_url: Database connection URL
        pool_size: Initial pool size
        min_size: Minimum pool size
        max_size: Maximum pool size
        enable_optimization: Enable dynamic optimization
        aggressive_scaling: Enable aggressive scaling behavior

    Returns:
        Configured OptimizedConnectionPoolManager
    """
    return OptimizedConnectionPoolManager(
        database_url=database_url,
        pool_size=pool_size,
        min_size=min_size,
        max_size=max_size,
        enable_optimization=enable_optimization,
        aggressive_scaling=aggressive_scaling,
    )


def get_recommended_pool_sizes(database_type: str) -> Dict[str, int]:
    """
    Get recommended pool sizes based on database type and system resources.

    Args:
        database_type: 'postgresql' or 'sqlite'

    Returns:
        Dictionary with recommended min_size, max_size, and pool_size
    """
    if database_type.lower() == "sqlite":
        return {
            "min_size": 2,
            "max_size": 12,  # SQLite write concurrency limit
            "pool_size": 6,
        }
    else:  # PostgreSQL
        return {"min_size": 3, "max_size": 30, "pool_size": 12}  # Higher for PostgreSQL


logger.info("Optimized connection pool integration loaded successfully")
