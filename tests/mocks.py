from __future__ import annotations

from dataclasses import dataclass

MOCK_MARKETS = [
    {
        "slug": "test-market-1",
        "token_ids": ["yes-token-1", "no-token-1"],
    },
    {
        "slug": "test-market-2",
        "token_ids": ["yes-token-2", "no-token-2"],
    },
]

MOCK_BOOKS = {
    "yes-token-1": {
        "bids": [{"price": "0.60", "size": "100"}],
        "asks": [{"price": "0.62", "size": "100"}],
    },
    "no-token-1": {
        "bids": [{"price": "0.38", "size": "100"}],
        "asks": [{"price": "0.40", "size": "100"}],
    },
    "yes-token-2": {
        "bids": [{"price": "0.70", "size": "100"}],
        "asks": [{"price": "0.72", "size": "100"}],
    },
    "no-token-2": {
        "bids": [{"price": "0.28", "size": "100"}],
        "asks": [{"price": "0.30", "size": "100"}],
    },
}


@dataclass
class MockSignedOrder:
    id: str
    status: str


@dataclass
class MockPosition:
    notional: float


VALID_ORDER = MockSignedOrder(id="12345", status="PENDING")
INVALID_ORDER = None
