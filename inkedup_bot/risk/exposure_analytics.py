"""
Exposure history tracking and analytics module.

Provides historical analysis, trend detection, performance metrics,
and predictive analytics for risk management decisions.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..database import DatabaseManager

log = logging.getLogger("exposure_analytics")


@dataclass
class ExposureSnapshot:
    """Historical exposure snapshot."""

    timestamp: float
    total_exposure: float
    net_exposure: float
    market_exposures: dict[str, float]
    outcome_exposures: dict[str, float]
    position_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExposureAnalytics:
    """Comprehensive exposure analytics results."""

    period_start: float
    period_end: float
    snapshots_count: int

    # Trend metrics
    exposure_trend: str  # "increasing", "decreasing", "stable"
    trend_strength: float  # 0-1, strength of trend
    volatility: float

    # Statistical metrics
    mean_exposure: float
    max_exposure: float
    min_exposure: float
    std_deviation: float

    # Risk metrics
    var_95: float  # 95% Value at Risk
    max_drawdown: float
    sharpe_ratio: float

    # Market concentration metrics
    market_concentration_trend: dict[str, float]
    outcome_concentration_trend: dict[str, float]

    # Alerts and insights
    risk_alerts: list[dict[str, Any]]
    insights: list[str]

    metadata: dict[str, Any] = field(default_factory=dict)


class ExposureHistoryTracker:
    """
    Historical exposure tracking and analytics engine.

    Features:
    - Continuous exposure history logging
    - Trend analysis and pattern detection
    - Risk metric calculation over time
    - Predictive analytics for risk management
    - Performance attribution analysis
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        max_snapshots: int = 10000,
        snapshot_interval: float = 60.0,  # 1 minute
        analytics_window: int = 1440,  # 24 hours in minutes
    ):
        self.db = db_manager
        self.max_snapshots = max_snapshots
        self.snapshot_interval = snapshot_interval
        self.analytics_window = analytics_window

        # In-memory circular buffer for recent snapshots
        self._recent_snapshots: deque = deque(maxlen=max_snapshots)
        self._last_snapshot_time = 0.0

        # Background tasks
        self._running = False
        self._tasks: list[asyncio.Task] = []

        # Analytics cache
        self._analytics_cache: dict[str, tuple[ExposureAnalytics, float]] = {}
        self._cache_ttl = 300.0  # 5 minutes

    async def start(self) -> None:
        """Start the exposure history tracking."""
        if self._running:
            return

        self._running = True
        log.info("Starting exposure history tracker")

        # Load recent history from database
        await self._load_recent_history()

        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._snapshot_collector()),
            asyncio.create_task(self._periodic_analysis()),
        ]

    async def stop(self) -> None:
        """Stop the exposure history tracking."""
        if not self._running:
            return

        self._running = False
        log.info("Stopping exposure history tracker")

        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def record_exposure_snapshot(self, snapshot: ExposureSnapshot) -> None:
        """
        Record a new exposure snapshot.

        Args:
            snapshot: Exposure data to record
        """
        # Add to in-memory buffer
        self._recent_snapshots.append(snapshot)
        self._last_snapshot_time = snapshot.timestamp

        # Persist to database
        try:
            await self._persist_snapshot(snapshot)
        except Exception as e:
            log.error(f"Failed to persist exposure snapshot: {e}")

        # Invalidate analytics cache
        self._analytics_cache.clear()

    async def get_exposure_analytics(
        self, lookback_hours: int = 24, use_cache: bool = True
    ) -> ExposureAnalytics:
        """
        Get comprehensive exposure analytics for the specified period.

        Args:
            lookback_hours: Number of hours to analyze
            use_cache: Whether to use cached results

        Returns:
            Comprehensive analytics results
        """
        cache_key = f"analytics_{lookback_hours}h"

        if use_cache and cache_key in self._analytics_cache:
            analytics, cache_time = self._analytics_cache[cache_key]
            if time.time() - cache_time < self._cache_ttl:
                return analytics

        # Calculate analytics
        end_time = time.time()
        start_time = end_time - (lookback_hours * 3600)

        snapshots = await self._get_snapshots_in_range(start_time, end_time)
        analytics = await self._calculate_analytics(snapshots, start_time, end_time)

        # Cache results
        self._analytics_cache[cache_key] = (analytics, time.time())

        return analytics

    async def get_exposure_trends(
        self,
        dimension: str = "total",  # total, market, outcome
        lookback_hours: int = 24,
    ) -> dict[str, list[tuple[float, float]]]:
        """
        Get exposure trends over time for specified dimension.

        Args:
            dimension: Exposure dimension to analyze
            lookback_hours: Time period to analyze

        Returns:
            Dictionary mapping entities to (timestamp, value) lists
        """
        end_time = time.time()
        start_time = end_time - (lookback_hours * 3600)

        snapshots = await self._get_snapshots_in_range(start_time, end_time)

        if dimension == "total":
            return {
                "total_exposure": [(s.timestamp, s.total_exposure) for s in snapshots],
                "net_exposure": [(s.timestamp, s.net_exposure) for s in snapshots],
            }
        elif dimension == "market":
            market_trends = defaultdict(list)
            for snapshot in snapshots:
                for market, exposure in snapshot.market_exposures.items():
                    market_trends[market].append((snapshot.timestamp, exposure))
            return dict(market_trends)
        elif dimension == "outcome":
            outcome_trends = defaultdict(list)
            for snapshot in snapshots:
                for outcome, exposure in snapshot.outcome_exposures.items():
                    outcome_trends[outcome].append((snapshot.timestamp, exposure))
            return dict(outcome_trends)
        else:
            raise ValueError(f"Unknown dimension: {dimension}")

    async def detect_exposure_anomalies(
        self, lookback_hours: int = 24, std_threshold: float = 2.0
    ) -> list[dict[str, Any]]:
        """
        Detect anomalous exposure events using statistical methods.

        Args:
            lookback_hours: Time period to analyze
            std_threshold: Standard deviations for anomaly detection

        Returns:
            List of detected anomalies
        """
        end_time = time.time()
        start_time = end_time - (lookback_hours * 3600)

        snapshots = await self._get_snapshots_in_range(start_time, end_time)
        if len(snapshots) < 10:
            return []

        # Calculate rolling statistics
        exposures = [s.total_exposure for s in snapshots]
        mean_exposure = statistics.mean(exposures)
        std_exposure = statistics.stdev(exposures) if len(exposures) > 1 else 0

        anomalies = []
        for i, snapshot in enumerate(snapshots):
            if std_exposure > 0:
                z_score = abs(snapshot.total_exposure - mean_exposure) / std_exposure

                if z_score > std_threshold:
                    anomalies.append(
                        {
                            "timestamp": snapshot.timestamp,
                            "type": (
                                "exposure_spike"
                                if snapshot.total_exposure > mean_exposure
                                else "exposure_drop"
                            ),
                            "value": snapshot.total_exposure,
                            "z_score": z_score,
                            "severity": "high" if z_score > 3.0 else "medium",
                            "context": {
                                "mean_exposure": mean_exposure,
                                "std_exposure": std_exposure,
                                "position_count": snapshot.position_count,
                            },
                        }
                    )

        return anomalies

    async def calculate_exposure_correlation_matrix(
        self, lookback_hours: int = 24
    ) -> dict[str, dict[str, float]]:
        """
        Calculate correlation matrix between different exposure dimensions.

        Args:
            lookback_hours: Time period for correlation analysis

        Returns:
            Correlation matrix between markets/outcomes
        """
        end_time = time.time()
        start_time = end_time - (lookback_hours * 3600)

        snapshots = await self._get_snapshots_in_range(start_time, end_time)
        if len(snapshots) < 10:
            return {}

        # Collect all markets and outcomes
        all_markets = set()
        all_outcomes = set()

        for snapshot in snapshots:
            all_markets.update(snapshot.market_exposures.keys())
            all_outcomes.update(snapshot.outcome_exposures.keys())

        # Build time series for each market/outcome
        time_series = {}

        for market in all_markets:
            series = [
                snapshot.market_exposures.get(market, 0.0) for snapshot in snapshots
            ]
            if any(x != 0 for x in series):  # Only non-zero series
                time_series[f"market_{market}"] = np.array(series)

        for outcome in all_outcomes:
            series = [
                snapshot.outcome_exposures.get(outcome, 0.0) for snapshot in snapshots
            ]
            if any(x != 0 for x in series):  # Only non-zero series
                time_series[f"outcome_{outcome}"] = np.array(series)

        # Calculate correlations
        correlations = {}
        entities = list(time_series.keys())

        for i, entity_a in enumerate(entities):
            correlations[entity_a] = {}
            for entity_b in entities:
                if len(time_series[entity_a]) > 1 and len(time_series[entity_b]) > 1:
                    corr = np.corrcoef(time_series[entity_a], time_series[entity_b])[
                        0, 1
                    ]
                    correlations[entity_a][entity_b] = (
                        float(corr) if not np.isnan(corr) else 0.0
                    )
                else:
                    correlations[entity_a][entity_b] = 0.0

        return correlations

    async def get_performance_attribution(
        self, lookback_hours: int = 24
    ) -> dict[str, Any]:
        """
        Calculate performance attribution across markets and outcomes.

        Args:
            lookback_hours: Time period for attribution analysis

        Returns:
            Performance attribution breakdown
        """
        end_time = time.time()
        start_time = end_time - (lookback_hours * 3600)

        snapshots = await self._get_snapshots_in_range(start_time, end_time)
        if len(snapshots) < 2:
            return {"error": "Insufficient data for attribution"}

        # Calculate exposure changes over period
        start_snapshot = snapshots[0]
        end_snapshot = snapshots[-1]

        market_changes = {}
        for market in set(
            list(start_snapshot.market_exposures.keys())
            + list(end_snapshot.market_exposures.keys())
        ):
            start_exp = start_snapshot.market_exposures.get(market, 0.0)
            end_exp = end_snapshot.market_exposures.get(market, 0.0)
            market_changes[market] = end_exp - start_exp

        outcome_changes = {}
        for outcome in set(
            list(start_snapshot.outcome_exposures.keys())
            + list(end_snapshot.outcome_exposures.keys())
        ):
            start_exp = start_snapshot.outcome_exposures.get(outcome, 0.0)
            end_exp = end_snapshot.outcome_exposures.get(outcome, 0.0)
            outcome_changes[outcome] = end_exp - start_exp

        total_change = end_snapshot.total_exposure - start_snapshot.total_exposure

        return {
            "period": {"start": start_time, "end": end_time, "hours": lookback_hours},
            "total_exposure_change": total_change,
            "market_attribution": market_changes,
            "outcome_attribution": outcome_changes,
            "largest_increases": sorted(
                [(k, v) for k, v in market_changes.items() if v > 0],
                key=lambda x: x[1],
                reverse=True,
            )[:5],
            "largest_decreases": sorted(
                [(k, v) for k, v in market_changes.items() if v < 0], key=lambda x: x[1]
            )[:5],
        }

    async def predict_exposure_trend(
        self, hours_ahead: int = 4, lookback_hours: int = 24
    ) -> dict[str, Any]:
        """
        Simple trend prediction based on historical patterns.

        Args:
            hours_ahead: Hours to predict ahead
            lookback_hours: Historical period for prediction basis

        Returns:
            Trend prediction results
        """
        end_time = time.time()
        start_time = end_time - (lookback_hours * 3600)

        snapshots = await self._get_snapshots_in_range(start_time, end_time)
        if len(snapshots) < 10:
            return {"error": "Insufficient data for prediction"}

        # Simple linear trend analysis
        timestamps = np.array([s.timestamp for s in snapshots])
        exposures = np.array([s.total_exposure for s in snapshots])

        # Fit linear regression
        z = np.polyfit(timestamps, exposures, 1)
        trend_slope = z[0]

        # Predict future values
        future_time = end_time + (hours_ahead * 3600)
        predicted_exposure = np.polyval(z, future_time)

        # Calculate confidence based on recent volatility
        recent_exposures = exposures[-10:]  # Last 10 snapshots
        volatility = np.std(recent_exposures) if len(recent_exposures) > 1 else 0

        confidence = max(0.0, 1.0 - (volatility / max(np.mean(recent_exposures), 1.0)))

        return {
            "prediction_time": future_time,
            "predicted_exposure": float(predicted_exposure),
            "trend_direction": "increasing" if trend_slope > 0 else "decreasing",
            "trend_strength": abs(float(trend_slope)),
            "confidence": float(confidence),
            "current_exposure": float(exposures[-1]),
            "volatility": float(volatility),
        }

    # Private helper methods

    async def _snapshot_collector(self) -> None:
        """Background task to collect exposure snapshots."""
        while self._running:
            try:
                # This would integrate with the main exposure calculator
                # For now, we'll just sleep until the interval
                await asyncio.sleep(self.snapshot_interval)

                # Record would be called by the main system
                # self._record_current_exposure()

            except Exception as e:
                log.error(f"Error in snapshot collector: {e}")
                await asyncio.sleep(1.0)

    async def _periodic_analysis(self) -> None:
        """Background task for periodic analysis."""
        while self._running:
            try:
                await asyncio.sleep(300)  # 5 minutes

                # Detect anomalies
                anomalies = await self.detect_exposure_anomalies()
                if anomalies:
                    log.warning(f"Detected {len(anomalies)} exposure anomalies")

            except Exception as e:
                log.error(f"Error in periodic analysis: {e}")

    async def _load_recent_history(self) -> None:
        """Load recent exposure history from database."""
        try:
            # Load last N snapshots from database
            # This would integrate with actual database schema
            log.info("Loaded recent exposure history from database")
        except Exception as e:
            log.error(f"Failed to load exposure history: {e}")

    async def _persist_snapshot(self, snapshot: ExposureSnapshot) -> None:
        """Persist snapshot to database."""
        try:
            # This would integrate with actual database schema
            # await self.db.insert_exposure_snapshot(snapshot)
            pass
        except Exception as e:
            log.error(f"Failed to persist snapshot: {e}")

    async def _get_snapshots_in_range(
        self, start_time: float, end_time: float
    ) -> list[ExposureSnapshot]:
        """Get snapshots within time range."""
        # Filter in-memory snapshots
        snapshots = [
            s for s in self._recent_snapshots if start_time <= s.timestamp <= end_time
        ]

        # If we need more history, query database
        if not snapshots and self._recent_snapshots:
            # For now, return what we have in memory
            return list(self._recent_snapshots)

        return snapshots

    async def _calculate_analytics(
        self, snapshots: list[ExposureSnapshot], start_time: float, end_time: float
    ) -> ExposureAnalytics:
        """Calculate comprehensive analytics from snapshots."""
        if not snapshots:
            return ExposureAnalytics(
                period_start=start_time,
                period_end=end_time,
                snapshots_count=0,
                exposure_trend="stable",
                trend_strength=0.0,
                volatility=0.0,
                mean_exposure=0.0,
                max_exposure=0.0,
                min_exposure=0.0,
                std_deviation=0.0,
                var_95=0.0,
                max_drawdown=0.0,
                sharpe_ratio=0.0,
                market_concentration_trend={},
                outcome_concentration_trend={},
                risk_alerts=[],
                insights=[],
            )

        exposures = [s.total_exposure for s in snapshots]
        net_exposures = [s.net_exposure for s in snapshots]

        # Basic statistics
        mean_exposure = statistics.mean(exposures)
        max_exposure = max(exposures)
        min_exposure = min(exposures)
        std_deviation = statistics.stdev(exposures) if len(exposures) > 1 else 0.0

        # Trend analysis
        if len(snapshots) > 1:
            start_exp = snapshots[0].total_exposure
            end_exp = snapshots[-1].total_exposure
            trend_change = (end_exp - start_exp) / max(start_exp, 1.0)

            if trend_change > 0.1:
                trend = "increasing"
                trend_strength = min(abs(trend_change), 1.0)
            elif trend_change < -0.1:
                trend = "decreasing"
                trend_strength = min(abs(trend_change), 1.0)
            else:
                trend = "stable"
                trend_strength = 0.0
        else:
            trend = "stable"
            trend_strength = 0.0

        # Risk metrics
        var_95 = np.percentile(exposures, 95) if exposures else 0.0

        # Calculate max drawdown
        max_drawdown = 0.0
        peak = 0.0
        for exp in exposures:
            if exp > peak:
                peak = exp
            drawdown = (peak - exp) / max(peak, 1.0)
            max_drawdown = max(max_drawdown, drawdown)

        # Simple Sharpe ratio approximation
        returns = []
        if len(net_exposures) > 1:
            for i in range(1, len(net_exposures)):
                if net_exposures[i - 1] != 0:
                    ret = (net_exposures[i] - net_exposures[i - 1]) / abs(
                        net_exposures[i - 1]
                    )
                    returns.append(ret)

        sharpe_ratio = 0.0
        if returns:
            mean_return = statistics.mean(returns)
            std_return = statistics.stdev(returns) if len(returns) > 1 else 0.0
            sharpe_ratio = mean_return / max(std_return, 0.001)

        # Generate insights
        insights = []
        risk_alerts = []

        if trend == "increasing" and trend_strength > 0.5:
            insights.append(
                f"Strong increasing exposure trend (+{trend_strength*100:.1f}%)"
            )
            if mean_exposure > max_exposure * 0.8:
                risk_alerts.append(
                    {
                        "type": "high_exposure_trend",
                        "severity": "warning",
                        "message": "Exposure approaching historical highs",
                    }
                )

        if std_deviation / mean_exposure > 0.3:  # High volatility
            insights.append("High exposure volatility detected")
            risk_alerts.append(
                {
                    "type": "high_volatility",
                    "severity": "warning",
                    "message": f"Exposure volatility: {std_deviation:.2f}",
                }
            )

        if max_drawdown > 0.2:  # 20% drawdown
            risk_alerts.append(
                {
                    "type": "large_drawdown",
                    "severity": "critical",
                    "message": f"Maximum drawdown: {max_drawdown*100:.1f}%",
                }
            )

        return ExposureAnalytics(
            period_start=start_time,
            period_end=end_time,
            snapshots_count=len(snapshots),
            exposure_trend=trend,
            trend_strength=trend_strength,
            volatility=std_deviation / max(mean_exposure, 1.0),
            mean_exposure=mean_exposure,
            max_exposure=max_exposure,
            min_exposure=min_exposure,
            std_deviation=std_deviation,
            var_95=var_95,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            market_concentration_trend={},  # Would calculate from snapshots
            outcome_concentration_trend={},  # Would calculate from snapshots
            risk_alerts=risk_alerts,
            insights=insights,
        )
