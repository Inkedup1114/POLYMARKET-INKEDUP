"""
Fallback management system for seamless database failover.

This package provides comprehensive fallback capabilities for database
operations, ensuring continued operation even when the primary database
becomes unavailable.
"""

from .manager import (
    DatabaseHealthMonitor,
    FallbackManager,
    FallbackMetrics,
    FallbackMode,
    HealthStatus,
    InMemoryStateStore,
)

__all__ = [
    "FallbackManager",
    "FallbackMode",
    "HealthStatus",
    "FallbackMetrics",
    "DatabaseHealthMonitor",
    "InMemoryStateStore",
]
