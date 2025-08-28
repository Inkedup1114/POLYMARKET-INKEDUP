from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

from inkedup_bot.config import BotConfig
from inkedup_bot.order_client import OrderClient
from inkedup_bot.state import StateManager
from tests.mocks import VALID_ORDER


@pytest.fixture
def mock_clob_client() -> Generator[MagicMock, None, None]:
    """Fixture to mock the ClobClient."""
    with patch("inkedup_bot.order_client.ClobClient") as mock:
        yield mock


@pytest.fixture
def order_client(mock_clob_client: MagicMock) -> tuple[OrderClient, MagicMock]:
    """Fixture to create an OrderClient and the mocked ClobClient instance."""
    cfg = BotConfig(private_key="test_key")
    state = StateManager(db_path=":memory:")
    client = OrderClient(cfg, state)
    mock_instance = mock_clob_client.return_value
    client.client = mock_instance
    return client, mock_instance


def test_order_client_initialization(order_client: tuple[OrderClient, MagicMock]):
    """Tests that the ClobClient is initialized correctly."""
    client, _ = order_client
    assert client.ready()


@patch(
    "inkedup_bot.order_client.asdict", return_value={"id": "12345", "status": "PENDING"}
)
def test_place_limit_order_success(
    mock_asdict: MagicMock, order_client: tuple[OrderClient, MagicMock]
):
    """Tests successful limit order placement."""
    client, mock_clob = order_client
    mock_clob.create_order.return_value = VALID_ORDER

    order = client.place_limit(token_id="token1", side="buy", price=0.5, size=100)

    mock_clob.create_order.assert_called_once()
    assert order is not None
    assert order["id"] == "12345"
    assert "12345" in client.state.open_orders


def test_place_limit_order_failure(order_client: tuple[OrderClient, MagicMock]):
    """Tests failure scenarios for limit order placement."""
    client, mock_clob = order_client
    mock_clob.create_order.return_value = None

    order = client.place_limit(token_id="token1", side="buy", price=0.5, size=100)

    assert order is None


def test_cancel_all_orders(order_client: tuple[OrderClient, MagicMock]):
    """Tests cancelling all orders."""
    client, mock_clob = order_client
    mock_clob.cancel_all.return_value = ["123", "456"]

    cancelled_orders = client.cancel_all()

    mock_clob.cancel_all.assert_called_once()
    assert len(cancelled_orders) == 2


def test_get_positions(order_client: tuple[OrderClient, MagicMock]):
    """Tests fetching positions."""
    client, mock_clob = order_client
    mock_position = MagicMock()
    mock_position.notional = 100.0
    mock_clob.get_positions.return_value = [mock_position]

    positions = client.get_positions()

    mock_clob.get_positions.assert_called_once()
    assert len(positions) == 1
    assert positions[0].notional == 100.0
