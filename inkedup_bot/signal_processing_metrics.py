"""
Signal processing speed metrics and performance tracking.

This module provides detailed performance instrumentation for signal processing
operations including market data analysis, strategy calculations, and decision making.
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .performance_metrics import (
    ComponentType,
    get_performance_tracker,
    track_performance,
)

logger = logging.getLogger(__name__)


@dataclass
class SignalProcessingStats:
    """Signal processing performance statistics."""

    strategy_name: str
    total_signals_processed: int
    avg_processing_time_ms: float
    p95_processing_time_ms: float
    p99_processing_time_ms: float
    signals_per_second: float
    successful_signals: int
    failed_signals: int
    success_rate: float
    data_freshness_ms: float
    computation_complexity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "total_signals_processed": self.total_signals_processed,
            "avg_processing_time_ms": self.avg_processing_time_ms,
            "p95_processing_time_ms": self.p95_processing_time_ms,
            "p99_processing_time_ms": self.p99_processing_time_ms,
            "signals_per_second": self.signals_per_second,
            "successful_signals": self.successful_signals,
            "failed_signals": self.failed_signals,
            "success_rate": self.success_rate,
            "data_freshness_ms": self.data_freshness_ms,
            "computation_complexity": self.computation_complexity,
        }


class SignalProcessingMetrics:
    """Comprehensive signal processing performance tracking."""

    def __init__(self):
        self.tracker = get_performance_tracker()
        self.signal_stats = defaultdict(dict)
        self.processing_pipeline_stats = {}

        logger.info("Signal processing metrics initialized")

    @track_performance(ComponentType.SIGNAL_PROCESSOR, "market_data_ingestion")
    def record_market_data_processing(
        self,
        market: str,
        data_type: str,
        processing_time_ms: float,
        data_age_ms: float,
        records_processed: int,
        success: bool = True,
    ):
        """Record market data processing performance."""
        tags = {"market": market, "data_type": data_type, "success": str(success)}

        metadata = {
            "data_age_ms": data_age_ms,
            "records_processed": records_processed,
            "processing_rate": (
                records_processed / (processing_time_ms / 1000)
                if processing_time_ms > 0
                else 0
            ),
        }

        self.tracker.record_latency(
            ComponentType.SIGNAL_PROCESSOR,
            "market_data_ingestion",
            processing_time_ms,
            success=success,
            tags=tags,
            metadata=metadata,
        )

        self.tracker.record_throughput(
            ComponentType.SIGNAL_PROCESSOR,
            "market_data_ingestion",
            records_processed,
            tags=tags,
        )

        if not success:
            self.tracker.record_error(
                ComponentType.SIGNAL_PROCESSOR,
                "market_data_ingestion",
                "processing_failed",
                tags=tags,
                metadata=metadata,
            )

    @track_performance(ComponentType.SIGNAL_PROCESSOR, "strategy_calculation")
    def record_strategy_calculation(
        self,
        strategy_name: str,
        calculation_type: str,
        processing_time_ms: float,
        input_size: int,
        complexity_score: float,
        success: bool = True,
    ):
        """Record strategy calculation performance."""
        tags = {
            "strategy": strategy_name,
            "calculation_type": calculation_type,
            "success": str(success),
        }

        metadata = {
            "input_size": input_size,
            "complexity_score": complexity_score,
            "throughput_per_ms": (
                input_size / processing_time_ms if processing_time_ms > 0 else 0
            ),
        }

        self.tracker.record_latency(
            ComponentType.SIGNAL_PROCESSOR,
            "strategy_calculation",
            processing_time_ms,
            success=success,
            tags=tags,
            metadata=metadata,
        )

        if not success:
            self.tracker.record_error(
                ComponentType.SIGNAL_PROCESSOR,
                "strategy_calculation",
                "calculation_failed",
                tags=tags,
                metadata=metadata,
            )

    @track_performance(ComponentType.SIGNAL_PROCESSOR, "signal_generation")
    def record_signal_generation(
        self,
        strategy_name: str,
        signal_type: str,
        generation_time_ms: float,
        confidence: float,
        market_conditions: dict[str, Any],
        success: bool = True,
    ):
        """Record signal generation performance."""
        tags = {
            "strategy": strategy_name,
            "signal_type": signal_type,
            "confidence_tier": self._get_confidence_tier(confidence),
            "success": str(success),
        }

        metadata = {
            "confidence": confidence,
            "market_conditions": market_conditions,
            "volatility": market_conditions.get("volatility", 0),
            "liquidity": market_conditions.get("liquidity", 0),
        }

        self.tracker.record_latency(
            ComponentType.SIGNAL_PROCESSOR,
            "signal_generation",
            generation_time_ms,
            success=success,
            tags=tags,
            metadata=metadata,
        )

        self.tracker.record_throughput(
            ComponentType.SIGNAL_PROCESSOR, "signal_generation", 1, tags=tags
        )

        if not success:
            self.tracker.record_error(
                ComponentType.SIGNAL_PROCESSOR,
                "signal_generation",
                "generation_failed",
                tags=tags,
                metadata=metadata,
            )

    def record_pipeline_stage(
        self,
        stage_name: str,
        processing_time_ms: float,
        input_size: int,
        output_size: int,
        success: bool = True,
    ):
        """Record processing pipeline stage performance."""
        tags = {"stage": stage_name, "success": str(success)}

        metadata = {
            "input_size": input_size,
            "output_size": output_size,
            "compression_ratio": output_size / input_size if input_size > 0 else 0,
            "throughput": (
                output_size / (processing_time_ms / 1000)
                if processing_time_ms > 0
                else 0
            ),
        }

        self.tracker.record_latency(
            ComponentType.SIGNAL_PROCESSOR,
            f"pipeline_{stage_name}",
            processing_time_ms,
            success=success,
            tags=tags,
            metadata=metadata,
        )

        if not success:
            self.tracker.record_error(
                ComponentType.SIGNAL_PROCESSOR,
                f"pipeline_{stage_name}",
                "stage_failed",
                tags=tags,
                metadata=metadata,
            )

    def record_feature_extraction(
        self,
        feature_type: str,
        extraction_time_ms: float,
        feature_count: int,
        data_points: int,
        success: bool = True,
    ):
        """Record feature extraction performance."""
        tags = {"feature_type": feature_type, "success": str(success)}

        metadata = {
            "feature_count": feature_count,
            "data_points": data_points,
            "features_per_ms": (
                feature_count / extraction_time_ms if extraction_time_ms > 0 else 0
            ),
            "extraction_efficiency": (
                feature_count / data_points if data_points > 0 else 0
            ),
        }

        self.tracker.record_latency(
            ComponentType.SIGNAL_PROCESSOR,
            "feature_extraction",
            extraction_time_ms,
            success=success,
            tags=tags,
            metadata=metadata,
        )

        if not success:
            self.tracker.record_error(
                ComponentType.SIGNAL_PROCESSOR,
                "feature_extraction",
                "extraction_failed",
                tags=tags,
                metadata=metadata,
            )

    def get_signal_processing_performance(
        self, strategy_name: str | None = None
    ) -> dict[str, Any]:
        """Get comprehensive signal processing performance statistics."""
        stats = self.tracker.get_comprehensive_stats(ComponentType.SIGNAL_PROCESSOR)

        # Add signal-specific analysis
        signal_analysis = {
            "processing_efficiency": self._calculate_processing_efficiency(),
            "data_freshness_analysis": self._analyze_data_freshness(),
            "strategy_performance": self._analyze_strategy_performance(strategy_name),
            "pipeline_bottlenecks": self._identify_pipeline_bottlenecks(),
        }

        stats["signal_analysis"] = signal_analysis
        return stats

    def get_real_time_processing_stats(self) -> dict[str, Any]:
        """Get real-time signal processing statistics."""
        real_time_stats = self.tracker.get_real_time_stats()

        # Filter for signal processor operations
        signal_ops = {}
        for key, data in real_time_stats.get("active_operations", {}).items():
            if data.get("component") == ComponentType.SIGNAL_PROCESSOR.value:
                signal_ops[key] = data

        signal_throughput = {}
        for key, data in real_time_stats.get("current_throughput", {}).items():
            if data.get("component") == ComponentType.SIGNAL_PROCESSOR.value:
                signal_throughput[key] = data

        return {
            "timestamp": real_time_stats["timestamp"],
            "active_signal_operations": signal_ops,
            "signal_throughput": signal_throughput,
            "processing_health": self._assess_processing_health(
                signal_ops, signal_throughput
            ),
        }

    def _get_confidence_tier(self, confidence: float) -> str:
        """Categorize confidence level into tiers."""
        if confidence >= 0.8:
            return "high"
        elif confidence >= 0.6:
            return "medium"
        elif confidence >= 0.4:
            return "low"
        else:
            return "very_low"

    def _calculate_processing_efficiency(self) -> dict[str, float]:
        """Calculate overall processing efficiency metrics."""
        # Get latency stats for key operations
        operations = [
            "market_data_ingestion",
            "strategy_calculation",
            "signal_generation",
        ]
        efficiency = {}

        for op in operations:
            latency_stats = self.tracker.get_latency_stats(
                ComponentType.SIGNAL_PROCESSOR, op
            )
            throughput_stats = self.tracker.get_throughput_stats(
                ComponentType.SIGNAL_PROCESSOR, op
            )

            if latency_stats and throughput_stats:
                # Efficiency = throughput / latency (higher is better)
                efficiency[op] = throughput_stats.events_per_second / (
                    latency_stats.mean_latency / 1000
                )
            else:
                efficiency[op] = 0.0

        return efficiency

    def _analyze_data_freshness(self) -> dict[str, Any]:
        """Analyze data freshness across processing operations."""
        # This would analyze metadata from market data processing
        # to determine data age trends
        return {
            "avg_data_age_ms": 50.0,  # Placeholder
            "data_freshness_trend": "improving",
            "stale_data_percentage": 2.5,
        }

    def _analyze_strategy_performance(
        self, strategy_name: str | None
    ) -> dict[str, Any]:
        """Analyze performance by strategy."""
        strategy_stats = {}

        # Get all strategy calculation metrics
        all_stats = self.tracker.get_comprehensive_stats(ComponentType.SIGNAL_PROCESSOR)
        operations = (
            all_stats.get("components", {})
            .get(ComponentType.SIGNAL_PROCESSOR.value, {})
            .get("operations", {})
        )

        for op_name, op_data in operations.items():
            if "strategy_calculation" in op_name:
                latency = op_data.get("latency")
                throughput = op_data.get("throughput")
                error_rate = op_data.get("error_rate", {})

                if latency:
                    strategy_stats[op_name] = {
                        "avg_latency_ms": latency.get("mean_ms", 0),
                        "p95_latency_ms": latency.get("p95_ms", 0),
                        "throughput_per_sec": (
                            throughput.get("events_per_second", 0) if throughput else 0
                        ),
                        "error_rate_percent": error_rate.get("error_rate_percent", 0),
                    }

        return strategy_stats

    def _identify_pipeline_bottlenecks(self) -> list[dict[str, Any]]:
        """Identify potential bottlenecks in the processing pipeline."""
        bottlenecks = []

        # Analyze all pipeline operations
        all_stats = self.tracker.get_comprehensive_stats(ComponentType.SIGNAL_PROCESSOR)
        operations = (
            all_stats.get("components", {})
            .get(ComponentType.SIGNAL_PROCESSOR.value, {})
            .get("operations", {})
        )

        for op_name, op_data in operations.items():
            latency = op_data.get("latency")
            if latency:
                mean_latency = latency.get("mean_ms", 0)
                p95_latency = latency.get("p95_ms", 0)

                # Flag operations with high latency or high variance
                if mean_latency > 100:  # > 100ms average
                    bottlenecks.append(
                        {
                            "operation": op_name,
                            "issue": "high_average_latency",
                            "value": mean_latency,
                            "severity": "high" if mean_latency > 500 else "medium",
                        }
                    )

                if p95_latency > mean_latency * 3:  # High variance
                    bottlenecks.append(
                        {
                            "operation": op_name,
                            "issue": "high_latency_variance",
                            "value": p95_latency / mean_latency,
                            "severity": "medium",
                        }
                    )

        return bottlenecks

    def _assess_processing_health(
        self, active_ops: dict, throughput_data: dict
    ) -> dict[str, Any]:
        """Assess overall processing health."""
        health_score = 100.0
        issues = []

        # Check for high latency operations
        for op_key, op_data in active_ops.items():
            current_latency = op_data.get("current_latency_ms", 0)
            avg_latency = op_data.get("avg_latency_ms", 0)

            if current_latency > 1000:  # > 1 second
                health_score -= 20
                issues.append(f"High latency in {op_key}: {current_latency:.1f}ms")
            elif current_latency > avg_latency * 2:  # Significantly above average
                health_score -= 10
                issues.append(f"Elevated latency in {op_key}: {current_latency:.1f}ms")

        # Check for low throughput
        for tp_key, tp_data in throughput_data.items():
            events_per_sec = tp_data.get("events_per_second", 0)
            if events_per_sec < 0.1:  # Very low throughput
                health_score -= 15
                issues.append(
                    f"Low throughput in {tp_key}: {events_per_sec:.2f} events/sec"
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
            "recommendations": self._generate_health_recommendations(issues),
        }

    def _generate_health_recommendations(self, issues: list[str]) -> list[str]:
        """Generate recommendations based on health issues."""
        recommendations = []

        if any("High latency" in issue for issue in issues):
            recommendations.append("Consider optimizing high-latency operations")
            recommendations.append("Review algorithm complexity and data structures")

        if any("Low throughput" in issue for issue in issues):
            recommendations.append("Investigate throughput bottlenecks")
            recommendations.append("Consider parallel processing or caching")

        if any("Elevated latency" in issue for issue in issues):
            recommendations.append("Monitor for system resource constraints")
            recommendations.append("Check for data quality issues")

        if not recommendations:
            recommendations.append("Signal processing performance is optimal")

        return recommendations


# Global signal processing metrics instance
_signal_metrics: SignalProcessingMetrics | None = None


def get_signal_processing_metrics() -> SignalProcessingMetrics:
    """Get or create the global signal processing metrics tracker."""
    global _signal_metrics

    if _signal_metrics is None:
        _signal_metrics = SignalProcessingMetrics()

    return _signal_metrics


# Context managers for common signal processing operations
class MarketDataProcessingTimer:
    """Context manager for timing market data processing."""

    def __init__(self, market: str, data_type: str, records_count: int):
        self.market = market
        self.data_type = data_type
        self.records_count = records_count
        self.start_time = None
        self.metrics = get_signal_processing_metrics()

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        processing_time_ms = (time.time() - self.start_time) * 1000
        success = exc_type is None

        # Estimate data age (would be actual in real implementation)
        data_age_ms = 25.0  # Placeholder

        self.metrics.record_market_data_processing(
            self.market,
            self.data_type,
            processing_time_ms,
            data_age_ms,
            self.records_count,
            success,
        )


class StrategyCalculationTimer:
    """Context manager for timing strategy calculations."""

    def __init__(
        self,
        strategy_name: str,
        calculation_type: str,
        input_size: int,
        complexity: float,
    ):
        self.strategy_name = strategy_name
        self.calculation_type = calculation_type
        self.input_size = input_size
        self.complexity = complexity
        self.start_time = None
        self.metrics = get_signal_processing_metrics()

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        processing_time_ms = (time.time() - self.start_time) * 1000
        success = exc_type is None

        self.metrics.record_strategy_calculation(
            self.strategy_name,
            self.calculation_type,
            processing_time_ms,
            self.input_size,
            self.complexity,
            success,
        )
