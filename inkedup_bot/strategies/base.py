from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Strategy(ABC):
    @abstractmethod
    def evaluate(self, rows: list[dict[str, Any]]):
        """
        Given current order book rows (from scanner), optionally yield actions.
        """
        ...


class NoOpStrategy(Strategy):
    def evaluate(self, rows):
        return []
