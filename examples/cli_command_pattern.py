"""
Example: CLI Command Pattern with Typer

This example demonstrates the preferred pattern for adding new CLI commands
to the InkedUp bot using Typer framework.
"""

import asyncio

import typer
from rich import print

from inkedup_bot.config import BotConfig

app = typer.Typer()


@app.command()
def example_command(
    param1: str = typer.Option(..., help="Required parameter"),
    param2: int = typer.Option(10, help="Optional parameter with default"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose output"
    ),
) -> None:
    """
    Example CLI command demonstrating the preferred pattern.

    This shows how to:
    - Use type hints
    - Add helpful descriptions
    - Handle both required and optional parameters
    - Structure async operations
    """
    if verbose:
        print(
            f"[green]Running example command with param1={param1}, param2={param2}[/green]"
        )

    # For async operations, use this pattern:
    async def run() -> None:
        # Load configuration if needed
        config = BotConfig()
        # Your async logic here
        print(f"Processing {param1} with value {param2}")
        print(f"API Base: {config.api_base}")
        # Example: await some_async_operation()

    # Run the async function
    asyncio.run(run())


if __name__ == "__main__":
    app()
