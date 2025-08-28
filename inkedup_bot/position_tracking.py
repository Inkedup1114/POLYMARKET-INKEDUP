"""
Enhanced position tracking module for comprehensive exposure calculation and management.

This module provides the EnhancedExposureTracker class which replaces the simple
exposure_usd() function with comprehensive position parsing, P&L calculation,
and detailed exposure analysis.
"""

import logging
from dataclasses import asdict
from decimal import Decimal
from typing import Any

from .position_manager import PositionManager
from .position_models import Position

logger = logging.getLogger(__name__)


class EnhancedExposureTracker:
    """Enhanced exposure tracker with comprehensive position parsing and P&L calculation."""

    def __init__(self, position_manager: PositionManager | None = None):
        """Initialize the enhanced exposure tracker.

        Args:
            position_manager: Optional position manager for database operations
        """
        self.position_manager = position_manager
        self.logger = logging.getLogger(__name__)

    async def exposure_usd(self, detailed: bool = False) -> dict[str, Any]:
        """Calculate USD exposure with comprehensive position analysis.

        Args:
            detailed: Whether to include detailed breakdown by market/outcome

        Returns:
            Dictionary containing exposure data and position details
        """
        try:
            # Get all open positions
            positions = await self._get_all_positions()

            # Calculate exposure breakdown
            if detailed:
                return await self._get_detailed_exposure(positions)
            else:
                return await self._get_simple_exposure(positions)

        except Exception as e:
            self.logger.error(f"Error calculating exposure: {e}")
            return {"total_exposure": Decimal("0"), "error": str(e)}

    async def _get_all_positions(self) -> list[Position]:
        """Get all open positions from position manager."""
        positions = []

        if self.position_manager:
            positions = self.position_manager.get_open_positions()

        return positions

    async def _get_simple_exposure(self, positions: list[Position]) -> dict[str, Any]:
        """Calculate simple total exposure."""
        total_exposure = Decimal("0")

        for position in positions:
            total_exposure += abs(position.notional_value)

        return {"total_exposure": total_exposure, "position_count": len(positions)}

    async def _get_detailed_exposure(self, positions: list[Position]) -> dict[str, Any]:
        """Calculate detailed exposure breakdown by market and outcome."""
        total_exposure = Decimal("0")
        long_exposure = Decimal("0")
        short_exposure = Decimal("0")

        market_breakdown = {}

        for position in positions:
            exposure = abs(position.notional_value)
            total_exposure += exposure

            # Track long/short exposure
            if position.size > 0:
                long_exposure += exposure
            else:
                short_exposure += exposure

            # Build market breakdown
            market = position.market_slug
            outcome = position.outcome_type

            if market not in market_breakdown:
                market_breakdown[market] = {
                    "total_exposure": Decimal("0"),
                    "long_exposure": Decimal("0"),
                    "short_exposure": Decimal("0"),
                    "outcomes": {},
                }

            market_breakdown[market]["total_exposure"] += exposure

            if position.size > 0:
                market_breakdown[market]["long_exposure"] += exposure
            else:
                market_breakdown[market]["short_exposure"] += exposure

            if outcome not in market_breakdown[market]["outcomes"]:
                market_breakdown[market]["outcomes"][outcome] = {
                    "exposure": Decimal("0"),
                    "size": Decimal("0"),
                    "unrealized_pnl": Decimal("0"),
                    "positions": [],
                }

            market_breakdown[market]["outcomes"][outcome]["exposure"] += exposure
            market_breakdown[market]["outcomes"][outcome]["size"] += position.size
            market_breakdown[market]["outcomes"][outcome][
                "unrealized_pnl"
            ] += position.unrealized_pnl
            market_breakdown[market]["outcomes"][outcome]["positions"].append(
                asdict(position)
            )

        return {
            "total_exposure": total_exposure,
            "long_exposure": long_exposure,
            "short_exposure": short_exposure,
            "net_exposure": long_exposure - short_exposure,
            "market_breakdown": market_breakdown,
            "position_count": len(positions),
            "positions": [asdict(p) for p in positions],
        }

    async def get_position_summary(self) -> dict[str, Any]:
        """Get comprehensive position summary with P&L and risk metrics."""
        positions = await self._get_all_positions()

        if not positions:
            return {
                "total_positions": 0,
                "total_exposure": Decimal("0"),
                "total_unrealized_pnl": Decimal("0"),
                "total_realized_pnl": Decimal("0"),
                "total_fees": Decimal("0"),
            }

        total_exposure = Decimal("0")
        total_unrealized_pnl = Decimal("0")
        total_realized_pnl = Decimal("0")
        total_fees = Decimal("0")

        for position in positions:
            total_exposure += abs(position.notional_value)
            total_unrealized_pnl += position.unrealized_pnl
            total_realized_pnl += position.realized_pnl
            total_fees += position.fees

        return {
            "total_positions": len(positions),
            "total_exposure": total_exposure,
            "total_unrealized_pnl": total_unrealized_pnl,
            "total_realized_pnl": total_realized_pnl,
            "total_fees": total_fees,
            "net_pnl": total_unrealized_pnl + total_realized_pnl - total_fees,
            "positions": [asdict(p) for p in positions],
        }

    def get_total_exposure(self) -> Decimal:
        """Get total exposure across all open positions."""
        if not self.position_manager:
            return Decimal("0")

        positions = self.position_manager.get_open_positions()
        return sum((p.notional_value for p in positions), Decimal("0"))

    def get_exposure_by_market(self, market_slug: str) -> Decimal:
        """Get total exposure for a specific market."""
        if not self.position_manager:
            return Decimal("0")

        positions = self.position_manager.get_positions_by_market(market_slug)
        return sum((p.notional_value for p in positions if p.is_open), Decimal("0"))

    def get_pnl_summary(self) -> dict[str, Decimal]:
        """Get P&L summary across all positions."""
        if not self.position_manager:
            return {
                "total_unrealized_pnl": Decimal("0"),
                "total_realized_pnl": Decimal("0"),
                "total_fees": Decimal("0"),
                "total_pnl": Decimal("0"),
            }

        positions = self.position_manager.get_open_positions()
        total_unrealized = sum((p.unrealized_pnl for p in positions), Decimal("0"))
        total_realized = sum((p.realized_pnl for p in positions), Decimal("0"))
        total_fees = sum((p.fees for p in positions), Decimal("0"))

        return {
            "total_unrealized_pnl": total_unrealized,
            "total_realized_pnl": total_realized,
            "total_fees": total_fees,
            "total_pnl": total_unrealized + total_realized - total_fees,
        }
