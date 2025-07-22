from inkedup_bot.signals import (
    ComplementSignal,
    OutcomeType,
    SignalAction,
    SpreadSignal,
    TradingSignal,
)
from inkedup_bot.strategies import ComplementArbStrategy, WideSpreadAlertStrategy
from inkedup_bot.strategies.spread_arbitrage import SpreadArb


def test_spread_strategy() -> None:
    strat = WideSpreadAlertStrategy(50)
    sig = SpreadSignal("m", "t", 0.40, 0.60, (0.60 - 0.40) / 0.50 * 10000)
    assert strat.on_spread(sig) is not None


def test_complement_strategy() -> None:
    strat = ComplementArbStrategy()
    sig = ComplementSignal("m", "yes", "no", 0.55, 0.50, 0.05)
    assert strat.on_complement(sig) is not None


def test_spread_arb_strategy() -> None:
    """
    Tests the SpreadArb strategy to ensure it correctly identifies an arbitrage
    opportunity and generates the appropriate SELL signals.
    """
    # 1. Configure and instantiate the strategy
    strategy_config = {"min_spread": 0.05}
    strategy = SpreadArb(strategy_config)

    # 2. Create mock market data that triggers the arbitrage condition
    # (0.60 + 0.50) - 1 = 0.10, which is > min_spread (0.05)
    mock_market_data = {
        "market_snapshots": [
            {
                "market_slug": "test-market-1",
                "yes_price": 0.60,
                "no_price": 0.50,
                "outcomes": [
                    {"id": "yes-token-id", "name": "Yes"},
                    {"id": "no-token-id", "name": "No"},
                ],
            }
        ]
    }

    # 3. Call the evaluate method
    signals = strategy.evaluate(mock_market_data)

    # 4. Define the expected signals
    expected_signals = [
        TradingSignal(
            market_slug="test-market-1",
            token_id="yes-token-id",
            side=SignalAction.SELL.value,
            price=0.60,
            size=1.0,
            outcome_type=OutcomeType.YES,
        ),
        TradingSignal(
            market_slug="test-market-1",
            token_id="no-token-id",
            side=SignalAction.SELL.value,
            price=0.50,
            size=1.0,
            outcome_type=OutcomeType.NO,
        ),
    ]

    # 5. Assert that the generated signals match the expected ones
    assert len(signals) == 2, "Should generate two signals"
    assert signals[0] == expected_signals[0], "First signal should be a 'Yes' sell"
    assert signals[1] == expected_signals[1], "Second signal should be a 'No' sell"
