from inkedup_bot.utils import (
    best_bid_ask,
    calc_spread_bps,
    calculate_shares,
    complement_deviation,
)


def test_calculate_shares():
    assert calculate_shares(10, 0.5) == 20.0


def test_calc_spread_bps():
    bps = calc_spread_bps(0.45, 0.55)
    assert bps > 0


def test_best_bid_ask():
    book = {"bids": [{"price": "0.40"}], "asks": [{"price": "0.60"}]}
    bid, ask = best_bid_ask(book)
    assert bid == 0.40 and ask == 0.60


def test_complement_dev():
    assert complement_deviation(0.55, 0.45) < 0.01
