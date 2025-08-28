#!/usr/bin/env python3
"""
Advanced Memory Profiler and Analysis Tools for InkedUp Bot

This module provides comprehensive memory profiling, analysis, and optimization
recommendations for identifying and resolving memory-related performance issues.
"""

import gc
import logging
import tracemalloc
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import psutil

logger = logging.getLogger(__name__)


class ProfileMode(Enum):
    """Memory profiling modes."""

    LIGHTWEIGHT = "lightweight"  # Basic memory tracking with minimal overhead
    STANDARD = "standard"  # Comprehensive tracking with moderate overhead
    DETAILED = "detailed"  # In-depth analysis with higher overhead
    DEBUG = "debug"  # Maximum detail for debugging


@dataclass
class MemorySnapshot:
    """A snapshot of memory usage at a specific point in time."""

    timestamp: datetime
    label: str
    process_memory_mb: float
    system_memory_percent: float
    objects_count: int
    gc_stats: tuple[int, int, int]
    tracemalloc_stats: dict[str, Any] | None = None
    stack_trace: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryLeak:
    """Information about a potential memory leak."""

    object_type: str
    count_increase: int
    size_increase_mb: float
    first_seen: datetime
    last_seen: datetime
    stack_traces: list[str] = field(default_factory=list)
    confidence: float = 0.0  # 0.0 to 1.0


@dataclass
class OptimizationRecommendation:
    """Memory optimization recommendation."""

    category: str
    priority: int  # 1 (highest) to 5 (lowest)
    description: str
    impact_estimate: str
    implementation_effort: str
    code_locations: list[str] = field(default_factory=list)


class AdvancedMemoryProfiler:
    """
    Advanced memory profiler with leak detection, allocation tracking,
    and optimization recommendations.
    """

    def __init__(self, mode: ProfileMode = ProfileMode.STANDARD):
        self.mode = mode
        self.profiling_active = False
        self.snapshots: list[MemorySnapshot] = []
        self.start_time: datetime | None = None

        # Leak detection
        self.object_tracking = defaultdict(list)  # type -> [counts over time]
        self.allocation_tracking = defaultdict(int)  # location -> count
        self.potential_leaks: list[MemoryLeak] = []

        # Performance tracking
        self.function_memory_usage = defaultdict(list)  # function -> [memory deltas]
        self.memory_hotspots: list[tuple[str, float]] = []  # (location, memory_mb)

        # Analysis state
        self.baseline_snapshot: MemorySnapshot | None = None
        self.peak_memory_mb = 0.0
        self.analysis_cache = {}

        # Configuration
        self.leak_detection_threshold = 1000  # objects
        self.leak_confidence_threshold = 0.7
        self.snapshot_interval = 60  # seconds

        # Enable tracemalloc for detailed modes
        if mode in [ProfileMode.DETAILED, ProfileMode.DEBUG]:
            if not tracemalloc.is_tracing():
                tracemalloc.start(25)  # Keep 25 frames

    def start_profiling(self, label: str = "session") -> None:
        """Start memory profiling session."""
        if self.profiling_active:
            logger.warning("Profiling already active")
            return

        self.profiling_active = True
        self.start_time = datetime.now()

        # Take baseline snapshot
        self.baseline_snapshot = self._take_snapshot(f"baseline_{label}")

        logger.info(
            f"Started memory profiling session: {label} (mode: {self.mode.value})"
        )

        # Start automatic snapshots for standard+ modes
        if self.mode in [ProfileMode.STANDARD, ProfileMode.DETAILED, ProfileMode.DEBUG]:
            self._schedule_automatic_snapshots()

    def stop_profiling(self) -> dict[str, Any]:
        """Stop profiling and return comprehensive analysis."""
        if not self.profiling_active:
            logger.warning("No active profiling session")
            return {}

        self.profiling_active = False

        # Take final snapshot
        final_snapshot = self._take_snapshot("final")

        # Perform analysis
        analysis = self._analyze_profiling_session()

        logger.info("Completed memory profiling session")
        return analysis

    def take_snapshot(self, label: str, metadata: dict | None = None) -> MemorySnapshot:
        """Take a manual memory snapshot."""
        snapshot = self._take_snapshot(label, metadata)

        if self.profiling_active:
            self.snapshots.append(snapshot)

            # Update peak memory
            if snapshot.process_memory_mb > self.peak_memory_mb:
                self.peak_memory_mb = snapshot.process_memory_mb

            # Perform leak detection if enough snapshots
            if len(self.snapshots) >= 3:
                self._detect_potential_leaks()

        return snapshot

    def _take_snapshot(
        self, label: str, metadata: dict | None = None
    ) -> MemorySnapshot:
        """Internal method to take a memory snapshot."""
        try:
            # System and process memory info
            process = psutil.Process()
            memory_info = process.memory_info()
            system_memory = psutil.virtual_memory()

            # Python object counts
            objects_count = len(gc.get_objects())
            gc_stats = gc.get_count()

            # Tracemalloc stats (if enabled)
            tracemalloc_stats = None
            if tracemalloc.is_tracing():
                current, peak = tracemalloc.get_traced_memory()
                tracemalloc_stats = {
                    "current_mb": current / (1024 * 1024),
                    "peak_mb": peak / (1024 * 1024),
                    "top_stats": self._get_top_tracemalloc_stats(),
                }

            # Stack trace for debug mode
            stack_trace = None
            if self.mode == ProfileMode.DEBUG:
                stack_trace = "".join(traceback.format_stack())

            return MemorySnapshot(
                timestamp=datetime.now(),
                label=label,
                process_memory_mb=memory_info.rss / (1024 * 1024),
                system_memory_percent=system_memory.percent,
                objects_count=objects_count,
                gc_stats=gc_stats,
                tracemalloc_stats=tracemalloc_stats,
                stack_trace=stack_trace,
                metadata=metadata or {},
            )

        except Exception as e:
            logger.error(f"Error taking memory snapshot: {e}")
            # Return minimal snapshot
            return MemorySnapshot(
                timestamp=datetime.now(),
                label=f"{label}_error",
                process_memory_mb=0.0,
                system_memory_percent=0.0,
                objects_count=0,
                gc_stats=(0, 0, 0),
            )

    def _get_top_tracemalloc_stats(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get top memory allocation statistics from tracemalloc."""
        if not tracemalloc.is_tracing():
            return []

        try:
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics("lineno")[:limit]

            result = []
            for stat in top_stats:
                result.append(
                    {
                        "filename": (
                            stat.traceback.format()[0] if stat.traceback else "unknown"
                        ),
                        "size_mb": stat.size / (1024 * 1024),
                        "count": stat.count,
                    }
                )

            return result

        except Exception as e:
            logger.error(f"Error getting tracemalloc stats: {e}")
            return []

    def _detect_potential_leaks(self):
        """Detect potential memory leaks based on object count trends."""
        if len(self.snapshots) < 3:
            return

        # Analyze object count trends
        recent_snapshots = self.snapshots[-5:]  # Last 5 snapshots

        for i in range(1, len(recent_snapshots)):
            prev_snapshot = recent_snapshots[i - 1]
            curr_snapshot = recent_snapshots[i]

            # Check for significant object count increases
            count_increase = curr_snapshot.objects_count - prev_snapshot.objects_count
            memory_increase = (
                curr_snapshot.process_memory_mb - prev_snapshot.process_memory_mb
            )

            if count_increase > self.leak_detection_threshold:
                # Potential leak detected
                confidence = min(
                    1.0, count_increase / (self.leak_detection_threshold * 5)
                )

                leak = MemoryLeak(
                    object_type="unknown",  # Would need more detailed tracking
                    count_increase=count_increase,
                    size_increase_mb=memory_increase,
                    first_seen=prev_snapshot.timestamp,
                    last_seen=curr_snapshot.timestamp,
                    confidence=confidence,
                )

                self.potential_leaks.append(leak)

                logger.warning(
                    f"Potential memory leak detected: "
                    f"{count_increase} objects, {memory_increase:.2f} MB increase"
                )

    def _schedule_automatic_snapshots(self):
        """Schedule automatic snapshots during profiling."""
        # This would be implemented with a background thread or async task
        # For now, just log that it would be scheduled
        logger.debug(f"Automatic snapshots scheduled every {self.snapshot_interval}s")

    def _analyze_profiling_session(self) -> dict[str, Any]:
        """Analyze the completed profiling session."""
        if not self.snapshots:
            return {"error": "No snapshots available for analysis"}

        # Basic statistics
        first_snapshot = self.snapshots[0]
        last_snapshot = self.snapshots[-1]
        duration = (last_snapshot.timestamp - first_snapshot.timestamp).total_seconds()

        memory_delta = (
            last_snapshot.process_memory_mb - first_snapshot.process_memory_mb
        )
        peak_memory = max(s.process_memory_mb for s in self.snapshots)
        avg_memory = sum(s.process_memory_mb for s in self.snapshots) / len(
            self.snapshots
        )

        # Object count analysis
        object_deltas = [
            self.snapshots[i].objects_count - self.snapshots[i - 1].objects_count
            for i in range(1, len(self.snapshots))
        ]
        avg_object_delta = (
            sum(object_deltas) / len(object_deltas) if object_deltas else 0
        )

        # Identify memory trends
        memory_trend = self._analyze_memory_trend()

        # Generate recommendations
        recommendations = self._generate_optimization_recommendations()

        # Leak analysis
        leak_summary = {
            "potential_leaks_found": len(self.potential_leaks),
            "high_confidence_leaks": len(
                [
                    l
                    for l in self.potential_leaks
                    if l.confidence > self.leak_confidence_threshold
                ]
            ),
            "leak_details": [
                {
                    "type": leak.object_type,
                    "confidence": leak.confidence,
                    "size_increase_mb": leak.size_increase_mb,
                }
                for leak in self.potential_leaks
            ],
        }

        return {
            "session_summary": {
                "duration_seconds": duration,
                "snapshots_taken": len(self.snapshots),
                "memory_delta_mb": memory_delta,
                "peak_memory_mb": peak_memory,
                "average_memory_mb": avg_memory,
                "average_object_delta": avg_object_delta,
            },
            "memory_trend": memory_trend,
            "leak_analysis": leak_summary,
            "optimization_recommendations": recommendations,
            "performance_metrics": self._calculate_performance_metrics(),
            "detailed_analysis": (
                self._detailed_analysis()
                if self.mode in [ProfileMode.DETAILED, ProfileMode.DEBUG]
                else {}
            ),
        }

    def _analyze_memory_trend(self) -> dict[str, Any]:
        """Analyze memory usage trends."""
        if len(self.snapshots) < 3:
            return {"trend": "insufficient_data"}

        memory_values = [s.process_memory_mb for s in self.snapshots]

        # Simple linear regression to identify trend
        n = len(memory_values)
        x_values = list(range(n))

        sum_x = sum(x_values)
        sum_y = sum(memory_values)
        sum_xy = sum(x * y for x, y in zip(x_values, memory_values, strict=False))
        sum_x2 = sum(x * x for x in x_values)

        if n * sum_x2 - sum_x * sum_x == 0:
            slope = 0
        else:
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)

        # Classify trend
        if abs(slope) < 0.1:
            trend = "stable"
        elif slope > 0.5:
            trend = "increasing_rapidly"
        elif slope > 0.1:
            trend = "increasing_slowly"
        elif slope < -0.5:
            trend = "decreasing_rapidly"
        else:
            trend = "decreasing_slowly"

        # Calculate variance
        mean_memory = sum(memory_values) / len(memory_values)
        variance = sum((x - mean_memory) ** 2 for x in memory_values) / len(
            memory_values
        )

        return {
            "trend": trend,
            "slope_mb_per_snapshot": slope,
            "variance": variance,
            "min_memory_mb": min(memory_values),
            "max_memory_mb": max(memory_values),
            "memory_range_mb": max(memory_values) - min(memory_values),
        }

    def _generate_optimization_recommendations(
        self,
    ) -> list[OptimizationRecommendation]:
        """Generate memory optimization recommendations based on analysis."""
        recommendations = []

        if not self.snapshots:
            return recommendations

        # Analyze memory growth
        if len(self.snapshots) >= 2:
            memory_growth = (
                self.snapshots[-1].process_memory_mb
                - self.snapshots[0].process_memory_mb
            )

            if memory_growth > 100:  # 100MB growth
                recommendations.append(
                    OptimizationRecommendation(
                        category="Memory Growth",
                        priority=1,
                        description=f"Significant memory growth detected ({memory_growth:.1f} MB). "
                        "Consider implementing object pooling or clearing unused references.",
                        impact_estimate="High - could prevent out-of-memory errors",
                        implementation_effort="Medium",
                    )
                )

        # Check for potential leaks
        if len(self.potential_leaks) > 0:
            high_confidence_leaks = [
                l
                for l in self.potential_leaks
                if l.confidence > self.leak_confidence_threshold
            ]

            if high_confidence_leaks:
                recommendations.append(
                    OptimizationRecommendation(
                        category="Memory Leaks",
                        priority=1,
                        description=f"Found {len(high_confidence_leaks)} high-confidence memory leaks. "
                        "Review object lifecycle management and ensure proper cleanup.",
                        impact_estimate="Critical - will cause memory exhaustion over time",
                        implementation_effort="High",
                    )
                )

        # Check peak memory usage
        if self.peak_memory_mb > 1000:  # 1GB
            recommendations.append(
                OptimizationRecommendation(
                    category="Peak Memory Usage",
                    priority=2,
                    description=f"Peak memory usage is high ({self.peak_memory_mb:.1f} MB). "
                    "Consider implementing streaming processing or memory-efficient data structures.",
                    impact_estimate="Medium - reduces resource requirements",
                    implementation_effort="Medium to High",
                )
            )

        # Analyze object count growth
        if len(self.snapshots) >= 2:
            object_growth = (
                self.snapshots[-1].objects_count - self.snapshots[0].objects_count
            )

            if object_growth > 50000:  # 50k objects
                recommendations.append(
                    OptimizationRecommendation(
                        category="Object Count Growth",
                        priority=2,
                        description=f"Large increase in object count ({object_growth:,}). "
                        "Consider object pooling, weak references, or lazy loading.",
                        impact_estimate="Medium - improves GC performance",
                        implementation_effort="Medium",
                    )
                )

        # Memory variance analysis
        if len(self.snapshots) >= 5:
            memory_values = [s.process_memory_mb for s in self.snapshots]
            mean_memory = sum(memory_values) / len(memory_values)
            variance = sum((x - mean_memory) ** 2 for x in memory_values) / len(
                memory_values
            )

            if variance > 10000:  # High variance
                recommendations.append(
                    OptimizationRecommendation(
                        category="Memory Volatility",
                        priority=3,
                        description="High memory usage volatility detected. "
                        "Consider implementing memory buffers or batch processing.",
                        impact_estimate="Low to Medium - improves stability",
                        implementation_effort="Low to Medium",
                    )
                )

        return sorted(recommendations, key=lambda r: r.priority)

    def _calculate_performance_metrics(self) -> dict[str, Any]:
        """Calculate performance metrics from profiling data."""
        if len(self.snapshots) < 2:
            return {}

        # Memory allocation rate
        duration = (
            self.snapshots[-1].timestamp - self.snapshots[0].timestamp
        ).total_seconds()
        memory_delta = (
            self.snapshots[-1].process_memory_mb - self.snapshots[0].process_memory_mb
        )

        allocation_rate = memory_delta / duration if duration > 0 else 0

        # Object creation rate
        object_delta = (
            self.snapshots[-1].objects_count - self.snapshots[0].objects_count
        )
        object_creation_rate = object_delta / duration if duration > 0 else 0

        # Memory efficiency (objects per MB)
        memory_efficiency = object_delta / memory_delta if memory_delta > 0 else 0

        return {
            "memory_allocation_rate_mb_per_sec": allocation_rate,
            "object_creation_rate_per_sec": object_creation_rate,
            "memory_efficiency_objects_per_mb": memory_efficiency,
            "profiling_overhead_estimate_mb": self._estimate_profiling_overhead(),
        }

    def _detailed_analysis(self) -> dict[str, Any]:
        """Perform detailed analysis for detailed/debug modes."""
        analysis = {}

        if tracemalloc.is_tracing():
            # Top memory allocations
            analysis["top_allocations"] = []

            for snapshot in self.snapshots[-3:]:  # Last 3 snapshots
                if snapshot.tracemalloc_stats:
                    analysis["top_allocations"].extend(
                        snapshot.tracemalloc_stats.get("top_stats", [])
                    )

        # GC statistics analysis
        gc_stats_history = [s.gc_stats for s in self.snapshots]
        if gc_stats_history:
            analysis["gc_analysis"] = {
                "gen0_collections": [stats[0] for stats in gc_stats_history],
                "gen1_collections": [stats[1] for stats in gc_stats_history],
                "gen2_collections": [stats[2] for stats in gc_stats_history],
                "collection_frequency": (
                    len(gc_stats_history) / len(self.snapshots) if self.snapshots else 0
                ),
            }

        return analysis

    def _estimate_profiling_overhead(self) -> float:
        """Estimate memory overhead of profiling itself."""
        base_overhead = len(self.snapshots) * 0.01  # ~10KB per snapshot

        if self.mode == ProfileMode.DETAILED:
            base_overhead *= 3
        elif self.mode == ProfileMode.DEBUG:
            base_overhead *= 5

        if tracemalloc.is_tracing():
            base_overhead += 10  # ~10MB for tracemalloc

        return base_overhead

    def export_analysis(self, filepath: str, format: str = "json") -> None:
        """Export profiling analysis to file."""
        analysis = self._analyze_profiling_session()

        if format.lower() == "json":
            import json

            # Convert datetime objects to strings for JSON serialization
            def serialize_datetime(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Object {obj} is not JSON serializable")

            with open(filepath, "w") as f:
                json.dump(analysis, f, indent=2, default=serialize_datetime)

        elif format.lower() == "csv":
            import csv

            # Export snapshots as CSV
            with open(filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "timestamp",
                        "label",
                        "memory_mb",
                        "objects_count",
                        "gc_gen0",
                        "gc_gen1",
                        "gc_gen2",
                    ]
                )

                for snapshot in self.snapshots:
                    writer.writerow(
                        [
                            snapshot.timestamp.isoformat(),
                            snapshot.label,
                            snapshot.process_memory_mb,
                            snapshot.objects_count,
                            snapshot.gc_stats[0],
                            snapshot.gc_stats[1],
                            snapshot.gc_stats[2],
                        ]
                    )

        logger.info(f"Profiling analysis exported to {filepath}")

    def get_summary_report(self) -> str:
        """Get a human-readable summary report."""
        analysis = self._analyze_profiling_session()

        if not analysis:
            return "No profiling data available"

        report = []
        report.append("=" * 60)
        report.append("MEMORY PROFILING SUMMARY REPORT")
        report.append("=" * 60)

        # Session summary
        summary = analysis.get("session_summary", {})
        report.append(f"Duration: {summary.get('duration_seconds', 0):.1f} seconds")
        report.append(f"Snapshots: {summary.get('snapshots_taken', 0)}")
        report.append(f"Memory Delta: {summary.get('memory_delta_mb', 0):+.2f} MB")
        report.append(f"Peak Memory: {summary.get('peak_memory_mb', 0):.2f} MB")
        report.append(f"Average Memory: {summary.get('average_memory_mb', 0):.2f} MB")
        report.append("")

        # Trend analysis
        trend = analysis.get("memory_trend", {})
        report.append(f"Memory Trend: {trend.get('trend', 'unknown')}")
        report.append(f"Memory Range: {trend.get('memory_range_mb', 0):.2f} MB")
        report.append("")

        # Leak analysis
        leak_info = analysis.get("leak_analysis", {})
        report.append(f"Potential Leaks: {leak_info.get('potential_leaks_found', 0)}")
        report.append(
            f"High Confidence Leaks: {leak_info.get('high_confidence_leaks', 0)}"
        )
        report.append("")

        # Recommendations
        recommendations = analysis.get("optimization_recommendations", [])
        if recommendations:
            report.append("TOP OPTIMIZATION RECOMMENDATIONS:")
            report.append("-" * 40)
            for i, rec in enumerate(recommendations[:3], 1):
                report.append(f"{i}. {rec['category']} (Priority {rec['priority']})")
                report.append(f"   {rec['description']}")
                report.append(f"   Impact: {rec['impact_estimate']}")
                report.append("")

        return "\n".join(report)


# Global memory profiler instance
advanced_memory_profiler = AdvancedMemoryProfiler()
