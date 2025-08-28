"""
Order execution latency tracking and performance metrics.

This module provides comprehensive tracking of order lifecycle performance including
placement latency, fill times, cancellation speed, and execution quality metrics.
"""

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .performance_metrics import (
    ComponentType,
    get_performance_tracker,
)

logger = logging.getLogger(__name__)


class OrderType(Enum):
    """Order types for tracking."""

    LIMIT = "limit"
    MARKET = "market"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    """Order status for lifecycle tracking."""

    PENDING = "pending"
    PLACED = "placed"
    PARTIAL_FILL = "partial_fill"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class OrderExecutionMetric:
    """Individual order execution performance metric."""

    order_id: str
    order_type: OrderType
    market: str
    side: str
    quantity: float
    price: float | None

    # Timing metrics
    creation_time: float
    placement_time: float | None = None
    first_fill_time: float | None = None
    complete_fill_time: float | None = None
    cancellation_time: float | None = None

    # Performance metrics
    placement_latency_ms: float | None = None
    first_fill_latency_ms: float | None = None
    complete_fill_latency_ms: float | None = None
    cancellation_latency_ms: float | None = None

    # Execution quality
    requested_price: float | None = None
    average_fill_price: float | None = None
    slippage_bps: float | None = None
    fill_rate: float = 0.0

    # Status tracking
    status: OrderStatus = OrderStatus.PENDING
    error_message: str | None = None

    def calculate_latencies(self):
        """Calculate all latency metrics."""
        if self.placement_time:
            self.placement_latency_ms = (
                self.placement_time - self.creation_time
            ) * 1000

        if self.first_fill_time and self.placement_time:
            self.first_fill_latency_ms = (
                self.first_fill_time - self.placement_time
            ) * 1000

        if self.complete_fill_time and self.placement_time:
            self.complete_fill_latency_ms = (
                self.complete_fill_time - self.placement_time
            ) * 1000

        if self.cancellation_time and self.placement_time:
            self.cancellation_latency_ms = (
                self.cancellation_time - self.placement_time
            ) * 1000

    def calculate_slippage(self):
        """Calculate slippage in basis points."""
        if self.requested_price and self.average_fill_price:
            price_diff = abs(self.average_fill_price - self.requested_price)
            self.slippage_bps = (price_diff / self.requested_price) * 10000

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "order_type": self.order_type.value,
            "market": self.market,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "creation_time": self.creation_time,
            "placement_time": self.placement_time,
            "first_fill_time": self.first_fill_time,
            "complete_fill_time": self.complete_fill_time,
            "placement_latency_ms": self.placement_latency_ms,
            "first_fill_latency_ms": self.first_fill_latency_ms,
            "complete_fill_latency_ms": self.complete_fill_latency_ms,
            "requested_price": self.requested_price,
            "average_fill_price": self.average_fill_price,
            "slippage_bps": self.slippage_bps,
            "fill_rate": self.fill_rate,
            "status": self.status.value,
            "error_message": self.error_message,
        }


@dataclass
class ExecutionQualityStats:
    """Execution quality statistics."""

    market: str
    order_type: str
    total_orders: int
    successful_orders: int
    success_rate: float
    avg_placement_latency_ms: float
    avg_fill_latency_ms: float
    p95_placement_latency_ms: float
    p95_fill_latency_ms: float
    avg_slippage_bps: float
    p95_slippage_bps: float
    fill_rate: float
    rejection_rate: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "order_type": self.order_type,
            "total_orders": self.total_orders,
            "successful_orders": self.successful_orders,
            "success_rate": self.success_rate,
            "avg_placement_latency_ms": self.avg_placement_latency_ms,
            "avg_fill_latency_ms": self.avg_fill_latency_ms,
            "p95_placement_latency_ms": self.p95_placement_latency_ms,
            "p95_fill_latency_ms": self.p95_fill_latency_ms,
            "avg_slippage_bps": self.avg_slippage_bps,
            "p95_slippage_bps": self.p95_slippage_bps,
            "fill_rate": self.fill_rate,
            "rejection_rate": self.rejection_rate,
        }


class OrderExecutionMetrics:
    """Comprehensive order execution performance tracking."""

    def __init__(self):
        self.tracker = get_performance_tracker()
        self.active_orders: dict[str, OrderExecutionMetric] = {}
        self.completed_orders: deque = deque(maxlen=10000)
        self.execution_stats = defaultdict(dict)

        logger.info("Order execution metrics initialized")

    def start_order_tracking(
        self,
        order_id: str,
        order_type: OrderType,
        market: str,
        side: str,
        quantity: float,
        price: float | None = None,
    ) -> OrderExecutionMetric:
        """Start tracking a new order."""
        order_metric = OrderExecutionMetric(
            order_id=order_id,
            order_type=order_type,
            market=market,
            side=side,
            quantity=quantity,
            price=price,
            creation_time=time.time(),
        )

        self.active_orders[order_id] = order_metric

        # Record order creation
        tags = {"order_type": order_type.value, "market": market, "side": side}

        self.tracker.record_throughput(
            ComponentType.ORDER_CLIENT, "order_created", 1, tags=tags
        )

        return order_metric

    def record_order_placement(
        self, order_id: str, success: bool = True, error_message: str | None = None
    ):
        """Record order placement completion."""
        if order_id not in self.active_orders:
            logger.warning(f"Order {order_id} not found in active orders")
            return

        order_metric = self.active_orders[order_id]
        order_metric.placement_time = time.time()
        order_metric.calculate_latencies()

        if success:
            order_metric.status = OrderStatus.PLACED
        else:
            order_metric.status = OrderStatus.REJECTED
            order_metric.error_message = error_message

        # Record placement performance
        tags = {
            "order_type": order_metric.order_type.value,
            "market": order_metric.market,
            "side": order_metric.side,
            "success": str(success),
        }

        if order_metric.placement_latency_ms:
            self.tracker.record_latency(
                ComponentType.ORDER_CLIENT,
                "order_placement",
                order_metric.placement_latency_ms,
                success=success,
                tags=tags,
                metadata={
                    "order_id": order_id,
                    "quantity": order_metric.quantity,
                    "price": order_metric.price,
                },
            )

        self.tracker.record_throughput(
            ComponentType.ORDER_CLIENT,
            "order_placed" if success else "order_rejected",
            1,
            tags=tags,
        )

        if not success:
            self.tracker.record_error(
                ComponentType.ORDER_CLIENT,
                "order_placement",
                error_message or "placement_failed",
                tags=tags,
            )

    def record_order_fill(
        self,
        order_id: str,
        fill_price: float,
        fill_quantity: float,
        is_complete: bool = True,
    ):
        """Record order fill event."""
        if order_id not in self.active_orders:
            logger.warning(f"Order {order_id} not found in active orders")
            return

        order_metric = self.active_orders[order_id]
        current_time = time.time()

        # Update fill information
        if order_metric.first_fill_time is None:
            order_metric.first_fill_time = current_time

        if is_complete:
            order_metric.complete_fill_time = current_time
            order_metric.status = OrderStatus.FILLED
            order_metric.fill_rate = 1.0
        else:
            order_metric.status = OrderStatus.PARTIAL_FILL
            order_metric.fill_rate = fill_quantity / order_metric.quantity

        # Update pricing information
        if order_metric.average_fill_price is None:
            order_metric.average_fill_price = fill_price
        else:
            # Simple average (would be quantity-weighted in real implementation)
            order_metric.average_fill_price = (
                order_metric.average_fill_price + fill_price
            ) / 2

        if order_metric.requested_price is None:
            order_metric.requested_price = order_metric.price or fill_price

        order_metric.calculate_latencies()
        order_metric.calculate_slippage()

        # Record fill performance
        tags = {
            "order_type": order_metric.order_type.value,
            "market": order_metric.market,
            "side": order_metric.side,
            "fill_type": "complete" if is_complete else "partial",
        }

        metadata = {
            "order_id": order_id,
            "fill_price": fill_price,
            "fill_quantity": fill_quantity,
            "slippage_bps": order_metric.slippage_bps or 0,
        }

        # Record first fill latency
        if (
            order_metric.first_fill_latency_ms
            and order_metric.first_fill_time == current_time
        ):
            self.tracker.record_latency(
                ComponentType.ORDER_CLIENT,
                "first_fill",
                order_metric.first_fill_latency_ms,
                success=True,
                tags=tags,
                metadata=metadata,
            )

        # Record complete fill latency
        if is_complete and order_metric.complete_fill_latency_ms:
            self.tracker.record_latency(
                ComponentType.ORDER_CLIENT,
                "complete_fill",
                order_metric.complete_fill_latency_ms,
                success=True,
                tags=tags,
                metadata=metadata,
            )

        # Record slippage
        if order_metric.slippage_bps is not None:
            self.tracker.record_latency(
                ComponentType.ORDER_CLIENT,
                "slippage",
                order_metric.slippage_bps,
                success=True,
                tags=tags,
                metadata=metadata,
            )

        self.tracker.record_throughput(
            ComponentType.ORDER_CLIENT, "order_filled", 1, tags=tags
        )

        # Move to completed orders if fully filled
        if is_complete:
            self.completed_orders.append(order_metric)
            del self.active_orders[order_id]

    def record_order_cancellation(
        self, order_id: str, success: bool = True, error_message: str | None = None
    ):
        """Record order cancellation."""
        if order_id not in self.active_orders:
            logger.warning(f"Order {order_id} not found in active orders")
            return

        order_metric = self.active_orders[order_id]
        order_metric.cancellation_time = time.time()
        order_metric.calculate_latencies()

        if success:
            order_metric.status = OrderStatus.CANCELLED
        else:
            order_metric.error_message = error_message

        # Record cancellation performance
        tags = {
            "order_type": order_metric.order_type.value,
            "market": order_metric.market,
            "side": order_metric.side,
            "success": str(success),
        }

        if order_metric.cancellation_latency_ms:
            self.tracker.record_latency(
                ComponentType.ORDER_CLIENT,
                "order_cancellation",
                order_metric.cancellation_latency_ms,
                success=success,
                tags=tags,
                metadata={
                    "order_id": order_id,
                    "fill_rate_at_cancel": order_metric.fill_rate,
                },
            )

        self.tracker.record_throughput(
            ComponentType.ORDER_CLIENT, "order_cancelled", 1, tags=tags
        )

        if not success:
            self.tracker.record_error(
                ComponentType.ORDER_CLIENT,
                "order_cancellation",
                error_message or "cancellation_failed",
                tags=tags,
            )

        # Move to completed orders
        self.completed_orders.append(order_metric)
        del self.active_orders[order_id]

    def get_execution_quality_stats(
        self,
        market: str | None = None,
        order_type: OrderType | None = None,
        window_hours: int = 24,
    ) -> dict[str, ExecutionQualityStats]:
        """Get execution quality statistics."""
        cutoff_time = time.time() - (window_hours * 3600)

        # Filter completed orders
        filtered_orders = []
        for order in self.completed_orders:
            if order.creation_time >= cutoff_time:
                if market is None or order.market == market:
                    if order_type is None or order.order_type == order_type:
                        filtered_orders.append(order)

        # Group by market and order type
        grouped_orders = defaultdict(list)
        for order in filtered_orders:
            key = f"{order.market}:{order.order_type.value}"
            grouped_orders[key].append(order)

        # Calculate stats for each group
        stats = {}
        for key, orders in grouped_orders.items():
            market_name, order_type_name = key.split(":", 1)

            successful_orders = [
                o
                for o in orders
                if o.status in [OrderStatus.FILLED, OrderStatus.PARTIAL_FILL]
            ]
            placement_latencies = [
                o.placement_latency_ms for o in orders if o.placement_latency_ms
            ]
            fill_latencies = [
                o.complete_fill_latency_ms or o.first_fill_latency_ms
                for o in successful_orders
                if o.complete_fill_latency_ms or o.first_fill_latency_ms
            ]
            slippages = [
                o.slippage_bps for o in successful_orders if o.slippage_bps is not None
            ]

            stats[key] = ExecutionQualityStats(
                market=market_name,
                order_type=order_type_name,
                total_orders=len(orders),
                successful_orders=len(successful_orders),
                success_rate=(
                    len(successful_orders) / len(orders) * 100 if orders else 0
                ),
                avg_placement_latency_ms=(
                    sum(placement_latencies) / len(placement_latencies)
                    if placement_latencies
                    else 0
                ),
                avg_fill_latency_ms=(
                    sum(fill_latencies) / len(fill_latencies) if fill_latencies else 0
                ),
                p95_placement_latency_ms=(
                    self._percentile(sorted(placement_latencies), 95)
                    if placement_latencies
                    else 0
                ),
                p95_fill_latency_ms=(
                    self._percentile(sorted(fill_latencies), 95)
                    if fill_latencies
                    else 0
                ),
                avg_slippage_bps=sum(slippages) / len(slippages) if slippages else 0,
                p95_slippage_bps=(
                    self._percentile(sorted(slippages), 95) if slippages else 0
                ),
                fill_rate=(
                    sum(o.fill_rate for o in orders) / len(orders) if orders else 0
                ),
                rejection_rate=(
                    len([o for o in orders if o.status == OrderStatus.REJECTED])
                    / len(orders)
                    * 100
                    if orders
                    else 0
                ),
            )

        return stats

    def get_real_time_order_metrics(self) -> dict[str, Any]:
        """Get real-time order execution metrics."""
        current_time = time.time()

        # Analyze active orders
        active_analysis = {
            "total_active_orders": len(self.active_orders),
            "orders_by_status": defaultdict(int),
            "orders_by_type": defaultdict(int),
            "orders_by_market": defaultdict(int),
            "avg_age_seconds": 0.0,
            "oldest_order_age_seconds": 0.0,
        }

        if self.active_orders:
            ages = []
            for order in self.active_orders.values():
                age = current_time - order.creation_time
                ages.append(age)
                active_analysis["orders_by_status"][order.status.value] += 1
                active_analysis["orders_by_type"][order.order_type.value] += 1
                active_analysis["orders_by_market"][order.market] += 1

            active_analysis["avg_age_seconds"] = sum(ages) / len(ages)
            active_analysis["oldest_order_age_seconds"] = max(ages)

        # Get recent performance from tracker
        real_time_stats = self.tracker.get_real_time_stats()
        order_ops = {
            k: v
            for k, v in real_time_stats.get("active_operations", {}).items()
            if v.get("component") == ComponentType.ORDER_CLIENT.value
        }

        return {
            "timestamp": current_time,
            "active_orders": dict(active_analysis),
            "recent_performance": order_ops,
            "execution_health": self._assess_execution_health(
                active_analysis, order_ops
            ),
        }

    def get_comprehensive_order_performance(self) -> dict[str, Any]:
        """Get comprehensive order execution performance report."""
        execution_quality = self.get_execution_quality_stats()
        real_time_metrics = self.get_real_time_order_metrics()

        # Get performance stats from tracker
        performance_stats = self.tracker.get_comprehensive_stats(
            ComponentType.ORDER_CLIENT
        )

        return {
            "timestamp": datetime.now().isoformat(),
            "execution_quality": {k: v.to_dict() for k, v in execution_quality.items()},
            "real_time_metrics": real_time_metrics,
            "performance_statistics": performance_stats,
            "summary": self._generate_performance_summary(
                execution_quality, real_time_metrics
            ),
        }

    def _percentile(self, sorted_values: list[float], percentile: float) -> float:
        """Calculate percentile from sorted values."""
        if not sorted_values:
            return 0.0

        index = (percentile / 100.0) * (len(sorted_values) - 1)
        if index == int(index):
            return sorted_values[int(index)]
        else:
            lower = sorted_values[int(index)]
            upper = sorted_values[int(index) + 1]
            return lower + (upper - lower) * (index - int(index))

    def _assess_execution_health(
        self, active_analysis: dict, performance_ops: dict
    ) -> dict[str, Any]:
        """Assess overall execution health."""
        health_score = 100.0
        issues = []

        # Check for stuck orders
        oldest_age = active_analysis.get("oldest_order_age_seconds", 0)
        if oldest_age > 300:  # 5 minutes
            health_score -= 20
            issues.append(f"Order stuck for {oldest_age/60:.1f} minutes")
        elif oldest_age > 60:  # 1 minute
            health_score -= 10
            issues.append(f"Slow order processing: {oldest_age:.0f} seconds")

        # Check for high rejection rate
        pending_orders = active_analysis.get("orders_by_status", {}).get("pending", 0)
        total_active = active_analysis.get("total_active_orders", 1)
        if pending_orders / total_active > 0.5:
            health_score -= 15
            issues.append("High proportion of pending orders")

        # Check performance metrics
        for op_key, op_data in performance_ops.items():
            if "order_placement" in op_key:
                current_latency = op_data.get("current_latency_ms", 0)
                if current_latency > 1000:  # > 1 second
                    health_score -= 25
                    issues.append(
                        f"High order placement latency: {current_latency:.0f}ms"
                    )
                elif current_latency > 500:  # > 500ms
                    health_score -= 10
                    issues.append(
                        f"Elevated order placement latency: {current_latency:.0f}ms"
                    )

        # Determine health status
        if health_score >= 90:
            status = "excellent"
        elif health_score >= 70:
            status = "good"
        elif health_score >= 50:
            status = "fair"
        else:
            status = "poor"

        return {
            "health_score": max(0, health_score),
            "status": status,
            "issues": issues,
            "recommendations": self._generate_execution_recommendations(issues),
        }

    def _generate_execution_recommendations(self, issues: list[str]) -> list[str]:
        """Generate recommendations based on execution issues."""
        recommendations = []

        if any("stuck" in issue.lower() for issue in issues):
            recommendations.append("Review order management logic for stuck orders")
            recommendations.append("Consider implementing order timeout mechanisms")

        if any("latency" in issue.lower() for issue in issues):
            recommendations.append("Optimize order placement pathways")
            recommendations.append("Check network connectivity and API performance")

        if any("pending" in issue.lower() for issue in issues):
            recommendations.append("Investigate order processing bottlenecks")
            recommendations.append("Review order validation and routing logic")

        if not recommendations:
            recommendations.append("Order execution performance is optimal")

        return recommendations

    def _generate_performance_summary(
        self, execution_quality: dict, real_time_metrics: dict
    ) -> dict[str, Any]:
        """Generate performance summary from execution data."""
        if not execution_quality:
            return {"message": "No execution data available"}

        # Calculate aggregate statistics
        total_orders = sum(eq.total_orders for eq in execution_quality.values())
        avg_success_rate = sum(
            eq.success_rate for eq in execution_quality.values()
        ) / len(execution_quality)
        avg_placement_latency = sum(
            eq.avg_placement_latency_ms for eq in execution_quality.values()
        ) / len(execution_quality)
        avg_slippage = sum(
            eq.avg_slippage_bps for eq in execution_quality.values()
        ) / len(execution_quality)

        return {
            "total_orders_analyzed": total_orders,
            "average_success_rate": avg_success_rate,
            "average_placement_latency_ms": avg_placement_latency,
            "average_slippage_bps": avg_slippage,
            "active_orders": real_time_metrics.get("active_orders", {}).get(
                "total_active_orders", 0
            ),
            "execution_health": real_time_metrics.get("execution_health", {}).get(
                "status", "unknown"
            ),
        }


# Global order execution metrics instance
_order_metrics: OrderExecutionMetrics | None = None


def get_order_execution_metrics() -> OrderExecutionMetrics:
    """Get or create the global order execution metrics tracker."""
    global _order_metrics

    if _order_metrics is None:
        _order_metrics = OrderExecutionMetrics()

    return _order_metrics
