"""Tests for the market making strategy."""

from inkedup_bot.signals import SignalAction, TradingSignal
from inkedup_bot.strategies.market_making import (
    MarketMakingConfig,
    MarketMakingStrategy,
)


def test_market_making_strategy_creation():
    """Test that MarketMakingStrategy can be created with default config."""
    config = MarketMakingConfig()
    strategy = MarketMakingStrategy(config)
    assert strategy.config.target_spread_bps == 50.0
    assert strategy.config.max_position_size == 100.0


def test_market_making_no_signals_on_insufficient_liquidity():
    """Test that no signals are generated when liquidity is too low."""
    config = MarketMakingConfig(min_liquidity=1000.0)
    strategy = MarketMakingStrategy(config)

    market_data = {
        "market_snapshots": [
            {
                "market_slug": "test-market",
                "liquidity": 500.0,  # Below minimum
                "outcomes": [
                    {"id": "yes-token", "name": "Yes"},
                    {"id": "no-token", "name": "No"},
                ],
                "yes_book": {"bids": [{"price": "0.45"}], "asks": [{"price": "0.55"}]},
                "no_book": {"bids": [{"price": "0.40"}], "asks": [{"price": "0.50"}]},
            }
        ]
    }

    signals = strategy.evaluate(market_data)
    assert len(signals) == 0


def test_market_making_signal_generation():
    """Test that market making signals are generated correctly."""
    config = MarketMakingConfig(
        target_spread_bps=50.0,
        min_spread_bps=20.0,
        max_spread_bps=5000.0,  # Allow wide spreads for market making opportunities
        min_liquidity=500.0,
        quote_size=10.0,
        max_position_size=100.0,
    )
    strategy = MarketMakingStrategy(config)

    market_data = {
        "market_snapshots": [
            {
                "market_slug": "test-market",
                "liquidity": 1000.0,
                "outcomes": [
                    {"id": "yes-token", "name": "Yes"},
                    {"id": "no-token", "name": "No"},
                ],
                "yes_book": {"bids": [{"price": "0.45"}], "asks": [{"price": "0.55"}]},
                "no_book": {"bids": [{"price": "0.40"}], "asks": [{"price": "0.50"}]},
            }
        ]
    }

    signals = strategy.evaluate(market_data)

    # Should generate signals for both Yes and No tokens
    assert len(signals) > 0

    # Check that signals have correct structure
    for signal in signals:
        assert isinstance(signal, TradingSignal)
        assert signal.market_slug == "test-market"
        assert signal.token_id in ["yes-token", "no-token"]
        assert signal.side in [SignalAction.BUY.value, SignalAction.SELL.value]
        assert 0.01 <= signal.price <= 0.99
        assert signal.size > 0


def test_market_making_spread_filtering():
    """Test that signals are not generated when spreads are too tight or wide."""
    config = MarketMakingConfig(
        min_spread_bps=100.0,  # High minimum spread
        max_spread_bps=1500.0,  # Set below the test data spread (~2000 bps)
        min_liquidity=500.0,
    )
    strategy = MarketMakingStrategy(config)

    # Market with spread too tight (around 22 bps)
    market_data = {
        "market_snapshots": [
            {
                "market_slug": "tight-spread-market",
                "liquidity": 1000.0,
                "outcomes": [
                    {"id": "yes-token", "name": "Yes"},
                    {"id": "no-token", "name": "No"},
                ],
                "yes_book": {
                    "bids": [{"price": "0.499"}],
                    "asks": [{"price": "0.5005"}],
                },
                "no_book": {
                    "bids": [{"price": "0.4988"}],
                    "asks": [{"price": "0.5002"}],
                },
            }
        ]
    }

    signals = strategy.evaluate(market_data)
    # Should generate no signals due to tight spreads
    assert len(signals) == 0


def test_market_making_position_limits():
    """Test that position limits are respected."""
    config = MarketMakingConfig(
        max_position_size=50.0, quote_size=10.0
    )  # Small position limit
    strategy = MarketMakingStrategy(config)

    # Set up a large position that exceeds limits
    strategy.positions["yes-token"] = 60.0  # Above limit

    market_data = {
        "market_snapshots": [
            {
                "market_slug": "test-market",
                "liquidity": 1000.0,
                "outcomes": [
                    {"id": "yes-token", "name": "Yes"},
                    {"id": "no-token", "name": "No"},
                ],
                "yes_book": {"bids": [{"price": "0.45"}], "asks": [{"price": "0.55"}]},
                "no_book": {"bids": [{"price": "0.40"}], "asks": [{"price": "0.50"}]},
            }
        ]
    }

    signals = strategy.evaluate(market_data)

    # Should not generate signals for yes-token due to position limit
    yes_signals = [s for s in signals if s.token_id == "yes-token"]
    assert len(yes_signals) == 0

    # Should still generate signals for no-token
    no_signals = [s for s in signals if s.token_id == "no-token"]
    assert len(no_signals) > 0


def test_market_making_position_tracking():
    """Test position tracking functionality."""
    config = MarketMakingConfig()
    strategy = MarketMakingStrategy(config)

    # Test initial position
    assert strategy.get_position("test-token") == 0.0

    # Test position update
    strategy.update_position("test-token", 25.0)
    assert strategy.get_position("test-token") == 25.0

    # Test position accumulation
    strategy.update_position("test-token", 15.0)
    assert strategy.get_position("test-token") == 40.0

    # Test negative position
    strategy.update_position("test-token", -50.0)
    assert strategy.get_position("test-token") == -10.0


def test_market_making_enabled_markets_filter():
    """Test that only enabled markets are processed."""
    config = MarketMakingConfig(enabled_markets=["allowed-market"], min_liquidity=500.0)
    strategy = MarketMakingStrategy(config)

    market_data = {
        "market_snapshots": [
            {
                "market_slug": "forbidden-market",  # Not in enabled list
                "liquidity": 1000.0,
                "outcomes": [
                    {"id": "yes-token", "name": "Yes"},
                    {"id": "no-token", "name": "No"},
                ],
                "yes_book": {"bids": [{"price": "0.45"}], "asks": [{"price": "0.55"}]},
                "no_book": {"bids": [{"price": "0.40"}], "asks": [{"price": "0.50"}]},
            },
            {
                "market_slug": "allowed-market",  # In enabled list
                "liquidity": 1000.0,
                "outcomes": [
                    {"id": "yes-token-2", "name": "Yes"},
                    {"id": "no-token-2", "name": "No"},
                ],
                "yes_book": {"bids": [{"price": "0.45"}], "asks": [{"price": "0.55"}]},
                "no_book": {"bids": [{"price": "0.40"}], "asks": [{"price": "0.50"}]},
            },
        ]
    }

    signals = strategy.evaluate(market_data)

    # Should only generate signals for allowed market
    for signal in signals:
        assert signal.market_slug == "allowed-market"
        assert signal.token_id in ["yes-token-2", "no-token-2"]
