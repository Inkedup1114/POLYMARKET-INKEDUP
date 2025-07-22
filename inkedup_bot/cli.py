from __future__ import annotations

import asyncio
import logging
from typing import Optional

import typer
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import BotConfig
from .database import DatabaseManager
from .logging_setup import setup_logging
from .order_client import OrderClient
from .risk import RiskManager
from .scanner import Scanner
from .snapshot_service import SnapshotService
from .state import StateManager
from .utils import calculate_shares
from .ws_stream import WSStream

app = typer.Typer(
    add_completion=False,
    help="InkedUp Polymarket Bot CLI",
    rich_markup_mode=None,
)
log = logging.getLogger("cli")


# Helper functions for status command health checks


async def _check_database_health() -> tuple[bool, str]:
    """
    Check database connectivity and basic health.

    Returns:
        tuple[bool, str]: (is_healthy, status_message)
    """
    try:
        db = DatabaseManager()
        await db.initialize()

        # Test basic database operation
        async with db.connection() as conn:
            await conn.execute("SELECT 1")

        return True, "Connected and operational"
    except Exception as e:
        error_msg = str(e)[:100] + "..." if len(str(e)) > 100 else str(e)
        return False, f"Connection failed: {error_msg}"


async def _check_scanner_status(cfg: BotConfig) -> tuple[bool, str]:
    """
    Check if scanner service can be initialized and is functional.

    Args:
        cfg: Bot configuration object

    Returns:
        tuple[bool, str]: (is_healthy, status_message)
    """
    try:
        scanner = Scanner(cfg)
        # Test basic scanner functionality without network calls
        if hasattr(scanner, "cfg") and scanner.cfg:
            return True, "Scanner service available"
        else:
            return False, "Scanner initialization incomplete"
    except Exception as e:
        error_msg = str(e)[:100] + "..." if len(str(e)) > 100 else str(e)
        return False, f"Scanner unavailable: {error_msg}"


async def _check_portfolio_health(cfg: BotConfig) -> tuple[bool, str]:
    """
    Check portfolio API endpoint and credential validity.

    Args:
        cfg: Bot configuration object

    Returns:
        tuple[bool, str]: (is_healthy, status_message)
    """
    if not cfg.private_key or not cfg.public_key:
        return False, "Credentials not configured"
    try:
        state = StateManager()
        oc = OrderClient(cfg, state)
        if not oc.ready():
            return False, "Order client not initialized"

        # Test API connection by fetching positions
        await asyncio.to_thread(oc.get_positions)
        return True, "API connection successful"
    except Exception as e:
        error_msg = str(e)[:100] + "..." if len(str(e)) > 100 else str(e)
        return False, f"API connection failed: {error_msg}"


def _check_config_validity(cfg: BotConfig) -> tuple[bool, list[str]]:
    """
    Validate configuration settings and identify warnings.

    Args:
        cfg: Bot configuration object

    Returns:
        tuple[bool, list[str]]: (is_valid, list_of_warnings)
    """
    warnings = []
    is_valid = True

    # Check critical configuration
    if not cfg.api_base:
        is_valid = False
        warnings.append("API base URL not configured")

    if not cfg.ws_url:
        is_valid = False
        warnings.append("WebSocket URL not configured")

    # Check non-critical but important settings
    if not cfg.private_key or not cfg.public_key:
        warnings.append(
            "Trading credentials not configured - bot will run in read-only mode"
        )

    if cfg.mm_enabled and (cfg.mm_max_position_size <= 0 or cfg.mm_quote_size <= 0):
        warnings.append(
            "Market making enabled but position/quote sizes not properly configured"
        )

    if cfg.global_risk_cap <= 0 and (cfg.private_key and cfg.public_key):
        warnings.append("Trading credentials available but no risk caps configured")

    # Validate risk management configuration
    if cfg.mm_enabled and cfg.mm_min_spread_bps >= cfg.mm_max_spread_bps:
        warnings.append(
            "Market making min spread >= max spread - this will cause issues"
        )

    return is_valid, warnings


async def _get_recent_activity() -> dict[str, str | int]:
    """
    Retrieve recent bot activity information.

    Returns:
        dict: Activity information including orders, positions, etc.
    """
    try:
        state = StateManager()
        activity: dict[str, str | int] = {}

        # Get basic activity info - handle both sync and async contexts
        try:
            if hasattr(state, "open_orders"):
                activity["open_orders"] = len(state.open_orders)
            if hasattr(state, "positions"):
                activity["positions"] = len(state.positions)
        except Exception:
            # Fallback to basic info if detailed access fails
            activity["open_orders"] = 0
            activity["positions"] = 0

        # Try to get timestamp of last activity if available
        try:
            # This would require database query - implement if needed
            activity["last_activity"] = "Not available"
        except Exception:
            activity["last_activity"] = "Not available"

        return activity
    except Exception:
        return {}


@app.command()
def status(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed status information"
    ),
) -> None:
    """
    Display bot operational status, configuration summary, and recent activity.

    Provides comprehensive health checks for monitoring systems and operators.
    Returns exit codes:
    - 0: Healthy status - all systems operational
    - 1: Warning conditions - non-critical issues (no recent activity, missing optional config)
    - 2: Error conditions - critical issues (database unavailable, missing required config)
    """

    async def run() -> None:
        console = Console()
        cfg = BotConfig()
        exit_code = 0

        # Display header
        console.print(Panel.fit("InkedUp Bot Status", style="bold blue"))

        # Perform comprehensive health checks
        db_healthy, db_status = await _check_database_health()
        scanner_healthy, scanner_status = await _check_scanner_status(cfg)
        portfolio_healthy, portfolio_status = await _check_portfolio_health(cfg)
        config_healthy, config_warnings = _check_config_validity(cfg)
        recent_activity = await _get_recent_activity()

        # System Health Status Table
        health_table = Table(title="System Health")
        health_table.add_column("Component", style="cyan", no_wrap=True)
        health_table.add_column("Status", style="magenta")
        health_table.add_column("Details", style="white")

        # Database status
        db_style = "green" if db_healthy else "red"
        health_table.add_row(
            "Database",
            f"[{db_style}]{'✓ Connected' if db_healthy else '✗ Error'}[/{db_style}]",
            db_status,
        )

        # Scanner status
        scanner_style = "green" if scanner_healthy else "yellow"
        health_table.add_row(
            "Scanner Service",
            f"[{scanner_style}]{'✓ Available' if scanner_healthy else '⚠ Warning'}[/{scanner_style}]",
            scanner_status,
        )

        # Portfolio/Trading API status
        portfolio_style = "green" if portfolio_healthy else "red"
        health_table.add_row(
            "Portfolio API",
            f"[{portfolio_style}]{'✓ Connected' if portfolio_healthy else '✗ Error'}[/{portfolio_style}]",
            portfolio_status,
        )

        # Configuration status
        config_style = (
            "green"
            if config_healthy and not config_warnings
            else "yellow" if config_warnings else "red"
        )
        config_status_text = (
            "✓ Valid"
            if config_healthy and not config_warnings
            else "⚠ Warnings" if config_warnings else "✗ Invalid"
        )
        health_table.add_row(
            "Configuration",
            f"[{config_style}]{config_status_text}[/{config_style}]",
            (
                f"{len(config_warnings)} warnings"
                if config_warnings
                else "All settings valid"
            ),
        )

        console.print(health_table)

        # Configuration Details
        config_table = Table(title="Configuration Summary")
        config_table.add_column("Setting", style="cyan", no_wrap=True)
        config_table.add_column("Value", style="magenta")
        config_table.add_column("Status", style="green")

        # API Configuration
        config_table.add_row("API Base", cfg.api_base, "✓ Configured")
        config_table.add_row("WebSocket URL", cfg.ws_url, "✓ Configured")

        # Credentials status
        if cfg.private_key and cfg.public_key:
            config_table.add_row("Trading Credentials", "***configured***", "✓ Ready")
        else:
            config_table.add_row("Trading Credentials", "Not configured", "⚠ Warning")
            if "credentials" not in [w.lower() for w in config_warnings]:
                config_warnings.append("Trading credentials not configured")

        # Feature flags
        config_table.add_row(
            "WebSocket Enabled",
            str(cfg.ws_enabled),
            "✓ Enabled" if cfg.ws_enabled else "○ Disabled",
        )
        config_table.add_row(
            "Market Making",
            str(cfg.mm_enabled),
            "✓ Enabled" if cfg.mm_enabled else "○ Disabled",
        )

        console.print(config_table)

        # Recent Activity Panel
        if recent_activity:
            activity_content = []
            if recent_activity.get("open_orders") is not None:
                activity_content.append(
                    f"Open Orders: {recent_activity['open_orders']}"
                )
            if recent_activity.get("positions") is not None:
                activity_content.append(
                    f"Active Positions: {recent_activity['positions']}"
                )
            if recent_activity.get("last_activity"):
                activity_content.append(
                    f"Last Activity: {recent_activity['last_activity']}"
                )

            if activity_content:
                console.print(
                    Panel("\n".join(activity_content), title="Recent Activity")
                )
            else:
                console.print(
                    Panel(
                        "No recent activity data available",
                        title="Recent Activity",
                        style="yellow",
                    )
                )
        else:
            console.print(
                Panel(
                    "Unable to retrieve activity data",
                    title="Recent Activity",
                    style="red",
                )
            )

        # Verbose output
        if verbose:
            # Risk Management Settings
            risk_table = Table(title="Risk Management Configuration")
            risk_table.add_column("Parameter", style="cyan")
            risk_table.add_column("Value", style="magenta")

            risk_table.add_row("Global Risk Cap", f"${cfg.global_risk_cap:.2f}")
            risk_table.add_row("Position Risk Cap", f"${cfg.position_risk_cap:.2f}")
            risk_table.add_row("Market Risk Cap", f"${cfg.market_risk_cap:.2f}")
            risk_table.add_row("Per-Market Risk Cap", f"${cfg.per_market_risk_cap:.2f}")
            risk_table.add_row(
                "Per-Outcome Risk Cap", f"${cfg.per_outcome_risk_cap:.2f}"
            )

            console.print(risk_table)

            # Market Making Configuration (if enabled)
            if cfg.mm_enabled:
                mm_table = Table(title="Market Making Configuration")
                mm_table.add_column("Parameter", style="cyan")
                mm_table.add_column("Value", style="magenta")

                mm_table.add_row("Target Spread (bps)", f"{cfg.mm_target_spread_bps}")
                mm_table.add_row(
                    "Max Position Size", f"${cfg.mm_max_position_size:.2f}"
                )
                mm_table.add_row("Quote Size", f"${cfg.mm_quote_size:.2f}")
                mm_table.add_row("Min Spread (bps)", f"{cfg.mm_min_spread_bps}")
                mm_table.add_row("Max Spread (bps)", f"{cfg.mm_max_spread_bps}")

                console.print(mm_table)

            # Configuration warnings detail
            if config_warnings:
                warnings_text = "\n".join(
                    [f"• {warning}" for warning in config_warnings]
                )
                console.print(
                    Panel(warnings_text, title="Configuration Warnings", style="yellow")
                )

        # Determine exit code based on health checks
        if not db_healthy or not portfolio_healthy:
            exit_code = 2  # Critical error
        elif not config_healthy:
            exit_code = 2  # Critical configuration error
        elif config_warnings or not scanner_healthy:
            exit_code = max(exit_code, 1)  # Warning conditions

        # Overall status summary
        if exit_code == 0:
            console.print("[green]Overall Status: ✓ All systems healthy[/green]")
        elif exit_code == 1:
            console.print(
                "[yellow]Overall Status: ⚠ Warning conditions detected[/yellow]"
            )
        else:
            console.print(
                "[red]Overall Status: ✗ Critical issues require attention[/red]"
            )

        raise typer.Exit(exit_code)

    # Run the async function
    asyncio.run(run())


@app.command()
def scan(interval: int = typer.Option(30), top: int = typer.Option(15)) -> None:
    """REST batch scanner loop."""
    cfg = BotConfig()
    scanner = Scanner(cfg)

    async def run() -> None:
        await scanner.loop(interval=interval, top=top)

    asyncio.run(run())


@app.command("once")
def once(top: int = 15) -> None:
    cfg = BotConfig()
    scanner = Scanner(cfg)

    async def run() -> None:
        comps = await scanner.scan_once(top)
        scanner.display(comps)

    asyncio.run(run())


@app.command("ws-scan")
def ws_scan(
    duration: int = typer.Option(120, help="Seconds to stream"), top: int = 15
) -> None:
    """WebSocket-driven snapshot stream (initial + deltas)."""
    cfg = BotConfig()
    if not cfg.ws_enabled:
        print("[yellow]WS_ENABLED not true; enable in .env to use ws-scan[/yellow]")
        raise typer.Exit(1)

    scanner = Scanner(cfg)

    async def run() -> None:
        await scanner.ensure_markets(force=True)
        token_ids: list[str] = []
        for m in scanner._markets_cache:
            token_ids.extend(m.get("token_ids") or m.get("tokens") or [])
        books = {}

        def on_book(msg: dict) -> None:
            token = msg.get("token_id")
            book = msg.get("book") or {}
            if token:
                books[token] = book

        stream = WSStream(cfg, token_ids, on_book)
        task = asyncio.create_task(stream.run())

        try:
            end = asyncio.get_event_loop().time() + duration
            while asyncio.get_event_loop().time() < end:
                # Build composites from current books
                comps = await scanner.scan_once(top)  # Reuses batch logic + strategies
                scanner.display(comps)
                await asyncio.sleep(10)
        finally:
            await stream.stop()
            task.cancel()

    asyncio.run(run())


@app.command()
def buy(token_id: str, usd: float, price: float) -> None:
    cfg = BotConfig()
    state = StateManager()
    oc = OrderClient(cfg, state)
    risk = RiskManager(cfg, oc, state)
    if not oc.ready():
        print("[red]Trading client not ready[/red]")
        raise typer.Exit(1)
    size = calculate_shares(usd, price)
    notional = usd  # simplistic
    try:
        risk.preflight(token_id, notional)
    except Exception as e:
        print(f"[red]Risk rejected: {e}[/red]")
        raise typer.Exit(1) from e
    oc.place_limit(token_id, "buy", price, size)


@app.command()
def sell(token_id: str, size: float, price: float) -> None:
    cfg = BotConfig()
    state = StateManager()
    oc = OrderClient(cfg, state)
    risk = RiskManager(cfg, oc, state)
    if not oc.ready():
        print("[red]Trading client not ready[/red]")
        raise typer.Exit(1)
    notional = size * price
    try:
        risk.preflight(token_id, notional)
    except Exception as e:
        print(f"[red]Risk rejected: {e}[/red]")
        raise typer.Exit(1) from e
    oc.place_limit(token_id, "sell", price, size)


@app.command("cancel-all")
def cancel_all() -> None:
    cfg = BotConfig()
    state = StateManager()
    oc = OrderClient(cfg, state)
    if not oc.ready():
        print("[red]Trading client not ready[/red]")
        raise typer.Exit(1)
    oc.cancel_all()


@app.command("snapshots")
def snapshots(
    duration: int = typer.Option(
        3600, help="Duration to run snapshot service (seconds)"
    ),
    stats_token: Optional[str] = typer.Option(
        None, help="Show stats for specific token ID"
    ),
) -> None:
    """Run market data snapshot service or show snapshot statistics."""
    cfg = BotConfig()

    async def run() -> None:
        service = SnapshotService(cfg)

        if stats_token:
            # Show statistics for specific token
            stats = await service.get_snapshot_stats(stats_token, hours=24)
            if stats:
                print(f"[green]Snapshot statistics for {stats_token}:[/green]")
                print(f"Snapshots in last 24h: {stats['snapshot_count']}")
                if stats["avg_spread_bps"]:
                    print(f"Average spread: {stats['avg_spread_bps']:.1f} bps")
                    print(f"Min spread: {stats['min_spread_bps']:.1f} bps")
                    print(f"Max spread: {stats['max_spread_bps']:.1f} bps")
                if stats["avg_volume_24h"]:
                    print(f"Average 24h volume: ${stats['avg_volume_24h']:.2f}")
            else:
                print(f"[yellow]No snapshot data found for {stats_token}[/yellow]")
            return

        # Run snapshot service
        print(f"[green]Starting snapshot service for {duration} seconds...[/green]")
        await service.start()

        try:
            await asyncio.sleep(duration)
        except KeyboardInterrupt:
            print("\n[yellow]Stopping snapshot service...[/yellow]")
        finally:
            await service.stop()
            print("[green]Snapshot service stopped[/green]")

    asyncio.run(run())


@app.command()
def portfolio() -> None:
    """Display portfolio, including positions and total value."""

    async def run() -> None:
        console = Console()
        cfg = BotConfig()
        state = StateManager()
        oc = OrderClient(cfg, state)

        if not oc.ready():
            console.print(
                Panel(
                    "[bold red]Trading client not ready.[/bold red]\n\n"
                    "Please ensure `PRIVATE_KEY` and `PUBLIC_KEY` are set in your `.env` file.",
                    title="Error",
                    border_style="red",
                )
            )
            raise typer.Exit(1)

        try:
            positions = await asyncio.to_thread(oc.get_positions)
            total_value = sum(p.get("usd_value", 0) for p in positions)

            # Portfolio Summary Panel
            summary_panel = Panel(
                f"[bold green]Total Portfolio Value: ${total_value:,.2f}[/bold green]\n"
                f"Total Positions: {len(positions)}",
                title="Portfolio Summary",
                expand=False,
            )
            console.print(summary_panel)

            if not positions:
                console.print("[yellow]No open positions.[/yellow]")
                return

            # Positions Table
            table = Table(
                title="Active Positions", show_header=True, header_style="bold magenta"
            )
            table.add_column("Symbol", style="cyan", no_wrap=True)
            table.add_column("Size", justify="right")
            table.add_column("Notional Value", justify="right")

            for p in positions:
                value = p.get("usd_value", 0)
                table.add_row(
                    p.get("symbol", "N/A"),
                    f"{p.get('size', 0):.4f}",
                    f"${value:,.2f}",
                )

            console.print(table)

        except Exception as e:
            console.print(
                Panel(
                    f"[bold red]Failed to fetch portfolio.[/bold red]\n\n"
                    f"Error: {e}",
                    title="API Error",
                    border_style="red",
                )
            )
            raise typer.Exit(1)

    asyncio.run(run())


@app.command()
def config() -> None:
    cfg = BotConfig()
    print(cfg)


if __name__ == "__main__":
    app()
