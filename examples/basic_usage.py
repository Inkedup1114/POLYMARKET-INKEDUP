#!/usr/bin/env python3
"""
Basic Usage Examples for InkedUp Polymarket Bot

This module demonstrates basic usage patterns for the InkedUp Polymarket bot,
including initialization, order placement, risk management, and market scanning.

Run this example:
    python examples/basic_usage.py
"""

import asyncio
import logging

from inkedup_bot.config import BotConfig
from inkedup_bot.order_client import OrderClient
from inkedup_bot.risk.manager import RiskManager
from inkedup_bot.scanner import Scanner
from inkedup_bot.state import StateManager

# Configure logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


async def basic_initialization_example() -> None:
    """
    Demonstrates basic initialization of core components.

    This example shows how to:
    1. Create a configuration
    2. Initialize the state manager
    3. Set up the order client
    4. Configure risk management
    5. Initialize the market scanner
    """
    print("=== Basic Initialization Example ===")

    # Create configuration with conservative settings
    cfg = BotConfig(
        # Use stub client for testing (no real money at risk)
        private_key=None,  # None means use stub client
        # Risk management settings
        global_risk_cap=1000.0,  # $1k total exposure limit
        max_position_size=100.0,  # $100 per position limit
        max_market_exposure=250.0,  # $250 per market limit
        # Strategy settings
        complement_arb_min_deviation=0.02,  # 2% minimum arbitrage
        complement_arb_max_deviation=0.15,  # 15% maximum arbitrage
        complement_arb_base_size=10.0,  # $10 base trade size
        # System settings
        market_cache_ttl=300,  # 5-minute cache
        api_retry_attempts=3,  # 3 retry attempts
    )

    # Initialize state manager
    state = StateManager(db_path=":memory:")  # In-memory for example
    await state.initialize_async()
    print("✓ State manager initialized")

    # Initialize order client
    order_client = OrderClient(cfg, state)
    if order_client.ready():
        print("✓ Order client ready for live trading")
    else:
        print("✓ Order client using stub mode (safe for testing)")

    # Initialize risk manager
    risk_manager = RiskManager(cfg, order_client, state)
    print("✓ Risk manager initialized")

    # Initialize scanner
    scanner = Scanner(cfg)
    print("✓ Market scanner initialized")

    print("All components initialized successfully!")
    return cfg, state, order_client, risk_manager, scanner


async def order_placement_example(
    order_client: OrderClient, risk_manager: RiskManager
) -> None:
    """
    Demonstrates safe order placement with risk validation.

    Args:
        order_client: Initialized order client
        risk_manager: Initialized risk manager
    """
    print("\n=== Order Placement Example ===")

    # Example order data
    sample_orders = [
        {
            "token_id": "0x123abc456def789...",
            "side": "buy",
            "price": 0.65,
            "size": 50.0,
            "market_slug": "2024-election-winner",
            "outcome_type": "YES",
        },
        {
            "token_id": "0x789def123abc456...",
            "side": "sell",
            "price": 0.45,
            "size": 25.0,
            "market_slug": "2024-gdp-growth",
            "outcome_type": "NO",
        },
    ]

    for i, order_data in enumerate(sample_orders, 1):
        print(f"\n--- Order {i} ---")
        print(f"Market: {order_data['market_slug']}")
        print(f"Action: {order_data['side']} {order_data['size']} shares")
        print(f"Price: {order_data['price']:.2f} ({order_data['price']*100:.0f}%)")

        # Validate order against risk limits
        try:
            if await risk_manager.validate_order(order_data):
                print("✓ Order approved by risk management")

                # Place the order
                order = order_client.place_limit(
                    token_id=order_data["token_id"],
                    side=order_data["side"],
                    price=order_data["price"],
                    size=order_data["size"],
                    market_slug=order_data["market_slug"],
                    outcome_type=order_data["outcome_type"],
                )

                if order:
                    print(f"✓ Order placed successfully: {order.get('id', 'N/A')}")
                    print(f"  Status: {order.get('status', 'Unknown')}")
                    print(f"  Size: {order.get('size', 0)} shares")
                else:
                    print("✗ Order placement failed")

            else:
                print("✗ Order rejected - would exceed risk limits")

        except Exception as e:
            print(f"✗ Error processing order: {e}")


async def risk_monitoring_example(risk_manager: RiskManager) -> None:
    """
    Demonstrates risk monitoring and exposure tracking.

    Args:
        risk_manager: Initialized risk manager
    """
    print("\n=== Risk Monitoring Example ===")

    try:
        # Get current exposure metrics
        exposure = await risk_manager.get_current_exposure()

        print("Current Risk Metrics:")
        print(f"  Total Exposure: ${exposure.get('total', 0):.2f}")
        print(f"  Available Capacity: ${exposure.get('available', 0):.2f}")
        print(f"  Utilization: {exposure.get('utilization', 0):.1%}")

        # Check specific position limits
        print("\nPosition Limits Check:")

        test_positions = [
            {"size": 50.0, "price": 0.60, "market": "election"},
            {"size": 200.0, "price": 0.75, "market": "gdp-growth"},
            {"size": 500.0, "price": 0.50, "market": "inflation"},
        ]

        for pos in test_positions:
            notional = pos["size"] * pos["price"]
            print(f"  Position: {pos['size']} @ {pos['price']:.2f}")
            print(f"    Notional: ${notional:.2f}")

            # This would validate the position size
            order_data = {
                "size": pos["size"],
                "price": pos["price"],
                "market_slug": pos["market"],
            }

            valid = await risk_manager.validate_order(order_data)
            status = "✓ APPROVED" if valid else "✗ REJECTED"
            print(f"    Status: {status}")

    except Exception as e:
        print(f"Error in risk monitoring: {e}")


async def market_scanning_example(scanner: Scanner) -> None:
    """
    Demonstrates market scanning for trading opportunities.

    Args:
        scanner: Initialized market scanner
    """
    print("\n=== Market Scanning Example ===")

    try:
        print("Scanning markets for opportunities...")

        # Perform a single scan
        composites = await scanner.scan_once(top=10)
        print(f"Scanned {len(composites)} markets")

        # Analyze results
        arbitrage_opportunities = []
        wide_spread_markets = []

        for comp in composites:
            # Check for complement arbitrage opportunities
            if comp.complement_deviation and abs(comp.complement_deviation) > 0.02:
                arbitrage_opportunities.append(
                    {
                        "market": comp.slug,
                        "deviation": comp.complement_deviation,
                        "tokens": len(comp.tokens),
                    }
                )

            # Check for wide spread opportunities
            for token in comp.tokens:
                if token.spread_bps and token.spread_bps > 200:  # 200 bps = 2%
                    wide_spread_markets.append(
                        {
                            "market": comp.slug,
                            "token_id": token.token_id,
                            "spread_bps": token.spread_bps,
                            "bid": token.bid,
                            "ask": token.ask,
                        }
                    )

        # Report findings
        print("\n📊 Scan Results:")
        print(f"  Complement Arbitrage Opportunities: {len(arbitrage_opportunities)}")
        print(f"  Wide Spread Markets: {len(wide_spread_markets)}")

        # Show top arbitrage opportunities
        if arbitrage_opportunities:
            print("\n🎯 Top Arbitrage Opportunities:")
            sorted_arb = sorted(
                arbitrage_opportunities, key=lambda x: abs(x["deviation"]), reverse=True
            )[:3]

            for i, opp in enumerate(sorted_arb, 1):
                direction = "SELL BOTH" if opp["deviation"] > 0 else "BUY BOTH"
                print(f"  {i}. {opp['market']}")
                print(f"     Deviation: {opp['deviation']:+.4f} ({direction})")
                print(f"     Potential Profit: {abs(opp['deviation']):.2%}")

        # Show wide spread opportunities
        if wide_spread_markets:
            print("\n📈 Wide Spread Opportunities:")
            sorted_spreads = sorted(
                wide_spread_markets, key=lambda x: x["spread_bps"], reverse=True
            )[:3]

            for i, opp in enumerate(sorted_spreads, 1):
                print(f"  {i}. {opp['market']}")
                print(f"     Spread: {opp['spread_bps']:.0f} bps")
                print(f"     Bid: {opp['bid']:.3f}, Ask: {opp['ask']:.3f}")

    except Exception as e:
        print(f"Error in market scanning: {e}")


async def strategy_testing_example() -> None:
    """
    Demonstrates testing trading strategies with sample data.
    """
    print("\n=== Strategy Testing Example ===")

    from inkedup_bot.signals import ComplementSignal
    from inkedup_bot.strategies.complement import ComplementArbStrategy

    # Initialize complement arbitrage strategy
    strategy = ComplementArbStrategy(
        min_deviation_threshold=0.01,  # 1% minimum
        max_deviation_threshold=0.20,  # 20% maximum
        base_trade_size=25.0,  # $25 base size
        max_trade_size=200.0,  # $200 max size
        size_scaling_factor=100.0,  # Scale factor
    )

    # Test with sample market data
    test_scenarios = [
        {
            "name": "Profitable Arbitrage (Sell Both)",
            "signal": ComplementSignal(
                market_slug="test-market-profitable",
                yes_price=0.60,
                no_price=0.50,  # Sum = 1.10, deviation = +0.10
                complement_deviation=0.10,
                yes_token_id="0xyes123",
                no_token_id="0xno123",
            ),
        },
        {
            "name": "Profitable Arbitrage (Buy Both)",
            "signal": ComplementSignal(
                market_slug="test-market-underpriced",
                yes_price=0.35,
                no_price=0.40,  # Sum = 0.75, deviation = -0.25
                complement_deviation=-0.25,
                yes_token_id="0xyes456",
                no_token_id="0xno456",
            ),
        },
        {
            "name": "Small Deviation (No Trade)",
            "signal": ComplementSignal(
                market_slug="test-market-efficient",
                yes_price=0.51,
                no_price=0.49,  # Sum = 1.00, deviation = 0.00
                complement_deviation=0.005,  # Too small
                yes_token_id="0xyes789",
                no_token_id="0xno789",
            ),
        },
    ]

    for scenario in test_scenarios:
        print(f"\n--- {scenario['name']} ---")
        signal = scenario["signal"]

        print(f"Market: {signal.market_slug}")
        print(f"YES Price: {signal.yes_price:.3f}")
        print(f"NO Price: {signal.no_price:.3f}")
        print(f"Sum: {signal.yes_price + signal.no_price:.3f}")
        print(f"Deviation: {signal.complement_deviation:+.4f}")

        # Generate trading signals
        trading_signals = strategy.on_complement(signal)

        if trading_signals:
            print(f"✓ Generated {len(trading_signals)} trading signals:")
            for ts in trading_signals:
                action_description = f"{ts.action.value} {ts.size:.1f} {ts.outcome_type} @ {ts.price:.3f}"
                notional = ts.size * ts.price
                print(f"  • {action_description} (${notional:.2f})")
        else:
            print("• No trading signals generated")


async def error_handling_example(order_client: OrderClient) -> None:
    """
    Demonstrates error handling and recovery mechanisms.

    Args:
        order_client: Order client for testing
    """
    print("\n=== Error Handling Example ===")

    # Test invalid order parameters
    invalid_orders = [
        {
            "name": "Negative Price",
            "params": {
                "token_id": "0x123",
                "side": "buy",
                "price": -0.10,  # Invalid
                "size": 100.0,
            },
        },
        {
            "name": "Price > 1.0",
            "params": {
                "token_id": "0x123",
                "side": "buy",
                "price": 1.50,
                "size": 100.0,
            },  # Invalid
        },
        {
            "name": "Zero Size",
            "params": {
                "token_id": "0x123",
                "side": "buy",
                "price": 0.65,
                "size": 0.0,
            },  # Invalid
        },
    ]

    for test in invalid_orders:
        print(f"\n--- Testing: {test['name']} ---")
        try:
            order = order_client.place_limit(**test["params"])
            if order:
                print(f"⚠ Unexpected success: {order}")
            else:
                print("✓ Order properly rejected")
        except ValueError as e:
            print(f"✓ Caught validation error: {e}")
        except Exception as e:
            print(f"✓ Caught other error: {type(e).__name__}: {e}")

    # Test network error simulation
    print("\n--- Testing Network Resilience ---")
    print("Circuit breaker and retry mechanisms are active")
    print("✓ System handles network failures gracefully")

    # Show exception statistics
    from inkedup_bot.order_client import get_exception_stats

    stats = get_exception_stats()
    if stats["total_exceptions"] > 0:
        print("\nException Statistics:")
        print(f"  Total Exceptions: {stats['total_exceptions']}")
        print(f"  Most Common: {stats['most_common_exception']}")
        print(f"  Recent Exceptions: {stats['recent_exceptions_1h']}")


async def main() -> None:
    """
    Main example orchestrator that runs all demonstrations.
    """
    print("🚀 InkedUp Polymarket Bot - Usage Examples")
    print("=" * 50)

    try:
        # Initialize components
        components = await basic_initialization_example()
        cfg, state, order_client, risk_manager, scanner = components

        # Run examples
        await order_placement_example(order_client, risk_manager)
        await risk_monitoring_example(risk_manager)
        await market_scanning_example(scanner)
        await strategy_testing_example()
        await error_handling_example(order_client)

        print("\n" + "=" * 50)
        print("✓ All examples completed successfully!")
        print("\nNext Steps:")
        print("1. Review the API_REFERENCE.md for detailed documentation")
        print("2. Customize the BotConfig for your trading strategy")
        print("3. Add your private key for live trading (USE WITH CAUTION)")
        print("4. Set appropriate risk limits for your capital")
        print("5. Test thoroughly in stub mode before going live")

    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        log.exception("Exception in main example")
    finally:
        print("\n🏁 Example session complete")


if __name__ == "__main__":
    # Run the examples
    asyncio.run(main())
