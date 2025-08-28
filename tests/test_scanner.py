from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from inkedup_bot.config import BotConfig
from inkedup_bot.scanner import Scanner
from tests.mocks import MOCK_BOOKS, MOCK_MARKETS


@pytest.fixture
def scanner() -> Generator[Scanner, None, None]:
    """Fixture to create a Scanner with a mocked TradingEngine."""
    with patch("inkedup_bot.scanner.TradingEngine") as mock_engine:
        cfg = BotConfig()
        sc = Scanner(cfg)
        sc.engine = mock_engine.return_value
        yield sc


@pytest.mark.asyncio
@patch("inkedup_bot.scanner.fetch_markets", new_callable=AsyncMock)
@patch("inkedup_bot.scanner.Scanner.fetch_books_batch", new_callable=AsyncMock)
async def test_scan_once_success(
    mock_fetch_books: AsyncMock,
    mock_fetch_markets: AsyncMock,
    scanner: Scanner,
) -> None:
    """Tests a successful scan_once execution."""
    mock_fetch_markets.return_value = MOCK_MARKETS
    mock_fetch_books.return_value = MOCK_BOOKS

    composites = await scanner.scan_once(top=5)

    assert len(composites) == 2
    assert composites[0].slug == "test-market-2"
    assert composites[0].tokens[0].bid == 0.70


@pytest.mark.asyncio
@patch("inkedup_bot.scanner.fetch_markets", new_callable=AsyncMock)
async def test_ensure_markets_cache(
    mock_fetch_markets: AsyncMock, scanner: Scanner
) -> None:
    """Tests that markets are fetched and cached."""
    mock_fetch_markets.return_value = MOCK_MARKETS

    await scanner.ensure_markets()

    assert scanner._markets_cache == MOCK_MARKETS
    assert mock_fetch_markets.call_count == 1

    # Should use cache
    await scanner.ensure_markets()
    assert mock_fetch_markets.call_count == 1
