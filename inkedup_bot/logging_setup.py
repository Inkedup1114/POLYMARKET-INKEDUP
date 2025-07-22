import logging
import os

from rich import box
from rich.console import Console
from rich.table import Table

_console = Console()


class RichHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            style = "white"
            if record.levelno >= logging.ERROR:
                style = "bold red"
            elif record.levelno >= logging.WARNING:
                style = "yellow"
            elif record.levelno >= logging.INFO:
                style = "green"
            _console.print(f"[{style}]{msg}[/]")
        except Exception:
            pass  # pragma: no cover


def setup_logging(level: str | None = None):
    level = level or os.getenv("LOG_LEVEL", "INFO")
    root = logging.getLogger()
    if any(isinstance(h, RichHandler) for h in root.handlers):
        return
    root.setLevel(level.upper())
    handler = RichHandler()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s", "%H:%M:%S"
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


def table(headers, rows, title=""):
    t = Table(title=title, box=box.MINIMAL, expand=True)
    for h in headers:
        t.add_column(h)
    for r in rows:
        t.add_row(*[str(c) for c in r])
    _console.print(t)
