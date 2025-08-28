"""
Enhanced Risk Manager with Correlation Analysis Integration.

This module extends the existing risk management system with advanced
correlation-based risk controls, providing a comprehensive solution
that considers both individual position risks and portfolio-wide
correlation risks.

Integration Features:
- Seamless integration with existing RiskManager
- Correlation-adjusted position limits
- Enhanced portfolio risk assessment
- Backward compatibility with current risk controls
- Real-time correlation monitoring and alerts
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..config import BotConfig
from .correlation_risk_manager import (
    CorrelationRiskConfig,
    CorrelationRiskManager,
    RiskAdjustment,
)
from .manager import RiskManager, RiskSystemMode

logger = logging.getLogger("enhanced_risk")


@dataclass
class EnhancedRiskAssessment:
    """Enhanced risk assessment including correlation analysis."""

    is_approved: bool
    traditional_risk_approved: bool
    correlation_risk_approved: bool
    original_exposure: float
    correlation_adjusted_exposure: float
    correlation_adjustment: Optional[RiskAdjustment]
    risk_reasons: List[str]
    warnings: List[str]
    metadata: Dict[str, Any]


class EnhancedRiskManager:
    """
    Enhanced risk manager that combines traditional risk controls with
    advanced correlation analysis for superior risk management.

    This class extends the existing RiskManager with correlation-based
    risk controls while maintaining full backward compatibility.
    """

    def __init__(self, config: BotConfig, order_client=None, state_manager=None):
        """Initialize enhanced risk manager."""

        # Initialize traditional risk manager (only if we have required dependencies)
        self.traditional_risk_manager = None
        if state_manager is not None:
            self.traditional_risk_manager = RiskManager(
                config, order_client, state_manager
            )
        else:
            logger.warning(
                "Traditional risk manager not initialized - state_manager is required"
            )

        # Initialize correlation risk manager
        correlation_config = CorrelationRiskConfig(
            high_correlation_threshold=getattr(
                config, "correlation_high_threshold", 0.6
            ),
            moderate_correlation_threshold=getattr(
                config, "correlation_moderate_threshold", 0.4
            ),
            low_correlation_threshold=getattr(config, "correlation_low_threshold", 0.2),
            high_correlation_penalty=getattr(config, "correlation_high_penalty", 0.5),
            moderate_correlation_penalty=getattr(
                config, "correlation_moderate_penalty", 0.7
            ),
            low_correlation_penalty=getattr(config, "correlation_low_penalty", 0.9),
            max_correlated_exposure=getattr(config, "max_correlated_exposure", 0.4),
            correlation_concentration_limit=getattr(
                config, "correlation_concentration_limit", 0.6
            ),
        )

        self.correlation_risk_manager = CorrelationRiskManager(correlation_config)

        # Configuration
        self.config = config
        self.correlation_enabled = getattr(config, "correlation_risk_enabled", True)

        # State tracking
        self._running = False

        logger.info("Enhanced risk manager initialized with correlation analysis")

    async def start(self):
        """Start the enhanced risk management system."""
        if self._running:
            return

        # Start traditional risk manager if available
        if self.traditional_risk_manager:
            await self.traditional_risk_manager.start()

        # Start correlation risk manager if enabled
        if self.correlation_enabled:
            await self.correlation_risk_manager.start()

        self._running = True
        logger.info("Enhanced risk management system started")

    async def stop(self):
        """Stop the enhanced risk management system."""
        if not self._running:
            return

        # Stop correlation risk manager
        if self.correlation_enabled:
            await self.correlation_risk_manager.stop()

        # Stop traditional risk manager if available
        if self.traditional_risk_manager:
            await self.traditional_risk_manager.stop()

        self._running = False
        logger.info("Enhanced risk management system stopped")

    async def validate_order_enhanced(
        self, order_data: Dict[str, Any]
    ) -> EnhancedRiskAssessment:
        """
        Enhanced order validation with correlation analysis.

        Args:
            order_data: Order details including market, size, price, etc.

        Returns:
            Enhanced risk assessment with correlation considerations
        """

        # Extract order details
        market_slug = order_data.get("market_slug", "")
        token_id = order_data.get("token_id", "")
        side = order_data.get("side", "buy")
        size = float(order_data.get("size", 0))
        price = float(order_data.get("price", 0))

        # Calculate notional exposure
        notional_exposure = size * price if side == "buy" else size * (1 - price)

        # Initialize assessment
        risk_reasons = []
        warnings = []

        # 1. Traditional risk validation
        traditional_approved = True  # Default to approved if no traditional manager
        if self.traditional_risk_manager:
            traditional_approved = await self.traditional_risk_manager.validate_order(
                order_data
            )
            if not traditional_approved:
                risk_reasons.append("Traditional risk limits exceeded")
        else:
            warnings.append(
                "Traditional risk validation unavailable - using correlation analysis only"
            )

        # 2. Correlation-based risk assessment (if enabled)
        correlation_approved = True
        correlation_adjustment = None
        correlation_adjusted_exposure = notional_exposure

        if self.correlation_enabled and traditional_approved:
            # Get current positions
            current_positions = await self._get_current_positions()

            # Assess correlation risk
            correlation_adjustment = (
                await self.correlation_risk_manager.assess_position_correlation_risk(
                    market_slug, notional_exposure, current_positions
                )
            )

            correlation_adjusted_exposure = correlation_adjustment.adjusted_limit

            # Check if correlation adjustment makes position invalid
            if correlation_adjusted_exposure < notional_exposure:
                adjustment_pct = (1 - correlation_adjustment.adjustment_factor) * 100
                warnings.append(
                    f"Position limit reduced by {adjustment_pct:.0f}% due to correlation risk"
                )

                # If adjustment is too severe, reject the order
                if (
                    correlation_adjustment.adjustment_factor < 0.3
                ):  # More than 70% reduction
                    correlation_approved = False
                    risk_reasons.append(
                        f"Excessive correlation risk: {correlation_adjustment.reason}"
                    )

        # 3. Feed market data to correlation system for future analysis
        if self.correlation_enabled:
            market_metadata = {
                "sector": self._infer_market_sector(market_slug),
                "token_id": token_id,
            }
            self.correlation_risk_manager.add_market_data(
                market_slug, price, notional_exposure, market_metadata
            )

        # Overall approval
        is_approved = traditional_approved and correlation_approved

        return EnhancedRiskAssessment(
            is_approved=is_approved,
            traditional_risk_approved=traditional_approved,
            correlation_risk_approved=correlation_approved,
            original_exposure=notional_exposure,
            correlation_adjusted_exposure=correlation_adjusted_exposure,
            correlation_adjustment=correlation_adjustment,
            risk_reasons=risk_reasons,
            warnings=warnings,
            metadata={
                "market_slug": market_slug,
                "token_id": token_id,
                "side": side,
                "correlation_enabled": self.correlation_enabled,
            },
        )

    async def validate_order(self, order_data: Dict[str, Any]) -> bool:
        """
        Backward-compatible order validation method.

        This method provides backward compatibility with existing code
        while leveraging the enhanced correlation-based risk analysis.
        """
        assessment = await self.validate_order_enhanced(order_data)

        # Log warnings for visibility
        for warning in assessment.warnings:
            logger.warning(f"Risk warning: {warning}")

        # Log risk reasons if rejected
        if not assessment.is_approved:
            for reason in assessment.risk_reasons:
                logger.info(f"Order rejected: {reason}")

        return assessment.is_approved

    async def get_portfolio_risk_summary(self) -> Dict[str, Any]:
        """Get comprehensive portfolio risk summary including correlation analysis."""

        # Get traditional risk metrics if available
        traditional_summary = {}
        if self.traditional_risk_manager:
            traditional_summary = (
                await self.traditional_risk_manager.get_current_exposure()
            )

        # Get correlation analysis if enabled
        correlation_summary = {}
        if self.correlation_enabled:
            current_positions = await self._get_current_positions()
            if current_positions:
                correlation_summary = await self.correlation_risk_manager.get_portfolio_correlation_metrics(
                    current_positions
                )

        # Combine summaries
        enhanced_summary = {
            "traditional_risk": traditional_summary,
            "correlation_analysis": correlation_summary,
            "correlation_enabled": self.correlation_enabled,
            "system_status": "running" if self._running else "stopped",
        }

        # Add risk recommendations
        recommendations = []

        if correlation_summary:
            recommendations.extend(correlation_summary.get("recommendations", []))

            # Add specific enhanced recommendations
            avg_correlation = correlation_summary.get("avg_correlation", 0.0)
            if avg_correlation > 0.6:
                recommendations.append(
                    "Consider reducing position concentration in highly correlated markets"
                )

            diversification_score = correlation_summary.get(
                "diversification_score", 1.0
            )
            if diversification_score < 0.5:
                recommendations.append(
                    "Portfolio needs better diversification across uncorrelated markets"
                )

        enhanced_summary["recommendations"] = recommendations

        return enhanced_summary

    async def _get_current_positions(self) -> Dict[str, float]:
        """Get current position exposures by market."""
        try:
            # This would integrate with the actual position tracking system
            # For now, return a placeholder that would be replaced with real position data
            positions = {}

            # In a real implementation, this would query the state manager
            # for current positions and calculate notional exposures
            if self.traditional_risk_manager and hasattr(
                self.traditional_risk_manager, "state_manager"
            ):
                state_manager = self.traditional_risk_manager.state_manager
                if state_manager and hasattr(state_manager, "get_all_positions"):
                    all_positions = await state_manager.get_all_positions()

                    for position in all_positions:
                        market_slug = position.get("market_slug", "unknown")
                        notional = float(position.get("notional_value", 0))

                        if market_slug in positions:
                            positions[market_slug] += notional
                        else:
                            positions[market_slug] = notional

            return positions

        except Exception as e:
            logger.error(f"Error getting current positions: {e}")
            return {}

    def _infer_market_sector(self, market_slug: str) -> str:
        """Infer market sector from market slug."""
        market_lower = market_slug.lower()

        if any(
            keyword in market_lower
            for keyword in ["election", "politics", "vote", "president", "congress"]
        ):
            return "politics"
        elif any(
            keyword in market_lower
            for keyword in ["sports", "nfl", "nba", "soccer", "football", "baseball"]
        ):
            return "sports"
        elif any(
            keyword in market_lower
            for keyword in ["crypto", "bitcoin", "btc", "ethereum", "eth", "price"]
        ):
            return "crypto"
        elif any(
            keyword in market_lower
            for keyword in ["economy", "gdp", "inflation", "fed", "recession", "rate"]
        ):
            return "economics"
        else:
            return "other"

    async def emergency_halt(self, reason: str):
        """Emergency halt trading (delegates to traditional risk manager)."""
        if self.traditional_risk_manager:
            await self.traditional_risk_manager.emergency_halt(reason)
        else:
            logger.warning(
                f"Emergency halt requested but no traditional risk manager available: {reason}"
            )

    async def get_current_exposure(self):
        """Get current exposure (backward compatibility)."""
        if self.traditional_risk_manager:
            return await self.traditional_risk_manager.get_current_exposure()
        else:
            return {"total": 0.0, "available": 0.0, "utilization": 0.0}

    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status."""
        traditional_status = {}
        if self.traditional_risk_manager:
            traditional_status = self.traditional_risk_manager.get_system_status()

        correlation_status = {}
        if self.correlation_enabled:
            correlation_status = self.correlation_risk_manager.get_correlation_summary()

        return {
            "traditional_risk": traditional_status,
            "correlation_risk": correlation_status,
            "enhanced_features_enabled": self.correlation_enabled,
            "traditional_risk_available": self.traditional_risk_manager is not None,
            "running": self._running,
        }


# Factory function for easy integration
async def create_enhanced_risk_manager(
    config: BotConfig, order_client=None, state_manager=None
) -> EnhancedRiskManager:
    """Create and start an enhanced risk manager."""

    enhanced_manager = EnhancedRiskManager(config, order_client, state_manager)
    await enhanced_manager.start()

    logger.info("Enhanced risk manager created and started")
    return enhanced_manager
