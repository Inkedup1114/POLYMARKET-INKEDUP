from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import typer
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .backup_manager import BackupType, get_backup_manager
from .config import BotConfig
from .config_hot_reload import get_config_reload_stats, reload_config_now
from .config_manager import get_config_manager
from .data_retention import DataRetentionManager, RetentionPeriod, RetentionPolicy
from .visual_trading_dashboard import run_visual_dashboard
from .web_trading_dashboard import run_web_dashboard
from .scanner_dashboard_integration import run_integrated_dashboard, run_integrated_web_dashboard
from .database import DatabaseManager
from .health_service import setup_health_service
from .order_client import OrderClient
from .risk import RiskManager
from .scanner import Scanner
from .shutdown_manager import (
    ShutdownPriority,
    get_shutdown_manager,
    register_shutdown_component,
    wait_for_shutdown,
)
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
        config_table.add_row("API Base", str(cfg.api_base), "✓ Configured")
        config_table.add_row("WebSocket URL", str(cfg.ws_url), "✓ Configured")

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
def scan(
    interval: int = typer.Option(30),
    top: int = typer.Option(15),
    enable_hot_reload: bool = typer.Option(
        False, help="Enable configuration hot reload"
    ),
) -> None:
    """REST batch scanner loop with graceful shutdown and optional hot reload."""

    async def run() -> None:
        print(
            "[green]Starting InkedUp scanner with graceful shutdown support...[/green]"
        )

        # Setup configuration management
        if enable_hot_reload:
            config_manager = get_config_manager()
            config_manager.start()
            print("[blue]Configuration hot reload enabled[/blue]")
            cfg = config_manager.get_config()
        else:
            cfg = BotConfig()

        scanner = Scanner(cfg)

        # Setup shutdown manager
        shutdown_manager = get_shutdown_manager()

        # Register scanner for shutdown (if it has a stop method)
        if hasattr(scanner, "stop"):
            register_shutdown_component(
                name="scanner",
                shutdown_func=scanner.stop,
                priority=ShutdownPriority.HIGH,
                timeout=15.0,
                description="Market scanner component",
            )

        # Register database cleanup
        if hasattr(scanner, "_db") and hasattr(scanner._db, "close"):
            register_shutdown_component(
                name="scanner_database",
                shutdown_func=scanner._db.close,
                priority=ShutdownPriority.CRITICAL,
                timeout=10.0,
                description="Scanner database connection",
            )

        try:
            # Create scanner task
            scanner_task = asyncio.create_task(scanner.loop(interval=interval, top=top))

            # Create shutdown monitoring task
            shutdown_task = asyncio.create_task(wait_for_shutdown())

            print(
                f"[blue]Scanner running with {interval}s interval. Press Ctrl+C for graceful shutdown.[/blue]"
            )

            # Wait for either scanner completion or shutdown signal
            done, pending = await asyncio.wait(
                [scanner_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            if shutdown_task in done:
                print("\n[yellow]Graceful shutdown initiated...[/yellow]")
                scanner_task.cancel()
                try:
                    await scanner_task
                except asyncio.CancelledError:
                    pass

                # Wait for shutdown to complete
                while not shutdown_manager.is_shutdown_complete():
                    await asyncio.sleep(0.1)

                print("[green]Scanner shutdown completed gracefully.[/green]")
            else:
                print("\n[blue]Scanner completed normally.[/blue]")

        except KeyboardInterrupt:
            print(
                "\n[yellow]KeyboardInterrupt received, triggering graceful shutdown...[/yellow]"
            )
            await shutdown_manager.trigger_shutdown("KeyboardInterrupt")

            # Wait for shutdown to complete
            while not shutdown_manager.is_shutdown_complete():
                await asyncio.sleep(0.1)

            print("[green]Scanner shutdown completed gracefully.[/green]")

        except Exception as e:
            print(f"[red]Scanner error: {e}[/red]")
            await shutdown_manager.trigger_shutdown(f"Scanner error: {e}")
            raise

        finally:
            # Stop configuration monitoring if it was started
            if enable_hot_reload:
                config_manager.stop()
                print("[blue]Configuration hot reload stopped[/blue]")

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
        print(
            "[green]Starting WebSocket scanner with graceful shutdown support...[/green]"
        )

        # Setup shutdown manager
        shutdown_manager = get_shutdown_manager()

        await scanner.ensure_markets(force=True)
        token_ids: list[str] = []
        for m in scanner._markets_cache:
            token_ids.extend(m.get("token_ids") or m.get("tokens") or [])
        books = {}

        def on_book(msg: dict[str, Any]) -> None:
            token = msg.get("token_id")
            book = msg.get("book") or {}
            if token:
                books[token] = book

        stream = WSStream(cfg, token_ids, on_book)

        # Register WebSocket stream for shutdown
        register_shutdown_component(
            name="websocket_stream",
            shutdown_func=stream.stop,
            priority=ShutdownPriority.HIGH,
            timeout=10.0,
            description="WebSocket market data stream",
        )

        # Register scanner for shutdown (if it has a stop method)
        if hasattr(scanner, "stop"):
            register_shutdown_component(
                name="ws_scanner",
                shutdown_func=scanner.stop,
                priority=ShutdownPriority.HIGH,
                timeout=15.0,
                description="WebSocket market scanner",
            )

        try:
            # Create WebSocket task
            ws_task = asyncio.create_task(stream.run())

            # Create shutdown monitoring task
            shutdown_task = asyncio.create_task(wait_for_shutdown())

            print(
                f"[blue]WebSocket scanner running for {duration}s. Press Ctrl+C for graceful shutdown.[/blue]"
            )

            end_time = asyncio.get_event_loop().time() + duration

            try:
                while (
                    asyncio.get_event_loop().time() < end_time
                    and not shutdown_manager.is_shutting_down()
                ):
                    # Build composites from current books
                    comps = await scanner.scan_once(
                        top
                    )  # Reuses batch logic + strategies
                    scanner.display(comps)

                    # Wait with shutdown check
                    try:
                        await asyncio.wait_for(asyncio.sleep(10), timeout=1.0)
                    except TimeoutError:
                        pass  # Continue checking shutdown status

            except KeyboardInterrupt:
                print(
                    "\n[yellow]KeyboardInterrupt received, triggering graceful shutdown...[/yellow]"
                )
                await shutdown_manager.trigger_shutdown("KeyboardInterrupt")

            # Wait for shutdown completion or normal end
            if shutdown_manager.is_shutting_down():
                while not shutdown_manager.is_shutdown_complete():
                    await asyncio.sleep(0.1)
                print("[green]WebSocket scanner shutdown completed gracefully.[/green]")
            else:
                print("\n[blue]WebSocket scanning completed normally.[/blue]")

        finally:
            # Ensure cleanup happens
            try:
                if not shutdown_manager.is_shutting_down():
                    await stream.stop()
                ws_task.cancel()
                await ws_task
            except asyncio.CancelledError:
                pass

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

        # Run snapshot service with graceful shutdown
        print(
            f"[green]Starting snapshot service for {duration} seconds with graceful shutdown...[/green]"
        )

        # Setup shutdown manager
        shutdown_manager = get_shutdown_manager()

        # Register snapshot service for shutdown
        register_shutdown_component(
            name="snapshot_service",
            shutdown_func=service.stop,
            priority=ShutdownPriority.HIGH,
            timeout=15.0,
            description="Market snapshot service",
        )

        await service.start()

        try:
            # Create shutdown monitoring task
            shutdown_task = asyncio.create_task(wait_for_shutdown())
            sleep_task = asyncio.create_task(asyncio.sleep(duration))

            print(
                f"[blue]Snapshot service running for {duration}s. Press Ctrl+C for graceful shutdown.[/blue]"
            )

            # Wait for either duration completion or shutdown signal
            done, pending = await asyncio.wait(
                [sleep_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            if shutdown_task in done:
                print("\n[yellow]Graceful shutdown initiated...[/yellow]")
                # Wait for shutdown to complete
                while not shutdown_manager.is_shutdown_complete():
                    await asyncio.sleep(0.1)
                print("[green]Snapshot service shutdown completed gracefully.[/green]")
            else:
                print("\n[blue]Snapshot service completed normally.[/blue]")
                # Trigger graceful shutdown for cleanup
                await shutdown_manager.trigger_shutdown("Normal completion")

        except KeyboardInterrupt:
            print(
                "\n[yellow]KeyboardInterrupt received, triggering graceful shutdown...[/yellow]"
            )
            await shutdown_manager.trigger_shutdown("KeyboardInterrupt")

            # Wait for shutdown to complete
            while not shutdown_manager.is_shutdown_complete():
                await asyncio.sleep(0.1)

            print("[green]Snapshot service shutdown completed gracefully.[/green]")

        except Exception as e:
            print(f"[red]Snapshot service error: {e}[/red]")
            await shutdown_manager.trigger_shutdown(f"Service error: {e}")
            raise

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
            raise typer.Exit(1) from None

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
            raise typer.Exit(1) from None

    asyncio.run(run())


@app.command()
def health(
    format: str = typer.Option("table", help="Output format: table, json, text"),
    detailed: bool = typer.Option(False, help="Show detailed component information"),
    export: str = typer.Option(None, help="Export health status to file"),
    diagnostics: bool = typer.Option(False, help="Run full health diagnostics"),
) -> None:
    """Check system health status and component status."""
    console = Console()

    async def run() -> None:
        try:
            # Setup health service with system components
            cfg = BotConfig()

            # Initialize components for health monitoring
            components = {}
            try:
                db = DatabaseManager(cfg.database_url.replace("sqlite:///", ""))
                await db.initialize()
                components["database_manager"] = db
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Could not initialize database for health checks: {e}[/yellow]"
                )

            try:
                order_client = OrderClient(cfg)
                components["order_client"] = order_client
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Could not initialize order client for health checks: {e}[/yellow]"
                )

            # Setup health service
            health_service = setup_health_service(cfg, **components)

            if diagnostics:
                # Run comprehensive health diagnostics
                console.print(
                    "[cyan]Running comprehensive health diagnostics...[/cyan]"
                )
                diagnostic_results = await health_service.run_health_diagnostics()

                if format == "json":
                    import json

                    print(json.dumps(diagnostic_results, indent=2))
                else:
                    # Display diagnostics in readable format
                    health_status = diagnostic_results.get("health_status", {})
                    trends = diagnostic_results.get("health_trends", {})
                    recommendations = diagnostic_results.get("recommendations", [])

                    # Overall status
                    overall_status = health_status.get("overall_status", "unknown")
                    status_style = (
                        "green"
                        if overall_status == "healthy"
                        else "red" if overall_status == "unhealthy" else "yellow"
                    )

                    console.print(
                        Panel(
                            f"[bold {status_style}]Overall Status: {overall_status.upper()}[/bold {status_style}]\n"
                            f"Uptime: {health_status.get('uptime_seconds', 0):.0f} seconds\n"
                            f"Components: {health_status.get('summary', {}).get('total_components', 0)}",
                            title="System Health Diagnostics",
                            expand=False,
                        )
                    )

                    # Component status table
                    health_table = Table(title="Component Health Details")
                    health_table.add_column("Component", style="cyan", no_wrap=True)
                    health_table.add_column("Status", style="magenta")
                    health_table.add_column("Details", style="white")

                    for comp_name, comp_data in health_status.get(
                        "components", {}
                    ).items():
                        comp_status = comp_data.get("overall_status", "unknown")
                        comp_style = (
                            "green"
                            if comp_status == "healthy"
                            else "red" if comp_status == "unhealthy" else "yellow"
                        )

                        # Get first check details as summary
                        checks = comp_data.get("checks", {})
                        first_check = next(iter(checks.values())) if checks else {}
                        details = first_check.get("message", "No details available")

                        health_table.add_row(
                            comp_name.replace("_", " ").title(),
                            f"[{comp_style}]{comp_status.upper()}[/{comp_style}]",
                            details[:50] + "..." if len(details) > 50 else details,
                        )

                    console.print(health_table)

                    # Health trends
                    if trends.get("data_points", 0) > 0:
                        console.print(
                            "\n[bold cyan]Health Trends (Last Hour)[/bold cyan]"
                        )
                        trend_direction = trends.get("trend", "stable")
                        trend_style = (
                            "green"
                            if trend_direction == "improving"
                            else (
                                "red"
                                if trend_direction == "deteriorating"
                                else "yellow"
                            )
                        )
                        console.print(
                            f"Trend: [{trend_style}]{trend_direction.upper()}[/{trend_style}]"
                        )

                        status_dist = trends.get("status_distribution", {})
                        for status, data in status_dist.items():
                            if data["count"] > 0:
                                console.print(
                                    f"  {status.title()}: {data['count']} checks ({data['percentage']}%)"
                                )

                    # Recommendations
                    if recommendations:
                        console.print("\n[bold cyan]Recommendations[/bold cyan]")
                        for i, rec in enumerate(recommendations, 1):
                            console.print(f"  {i}. {rec}")

            else:
                # Standard health check
                health_status = await health_service.get_system_health_status(
                    include_details=detailed
                )

                if format == "json":
                    import json

                    print(json.dumps(health_status, indent=2))
                elif format == "text":
                    # Simple text output
                    overall_status = health_status.get("overall_status", "unknown")
                    print(
                        f"InkedUp Trading Bot Health Status: {overall_status.upper()}"
                    )
                    print(f"Timestamp: {health_status.get('timestamp', 'unknown')}")
                    print(
                        f"Uptime: {health_status.get('uptime_seconds', 0):.0f} seconds"
                    )

                    if detailed:
                        print("\nComponent Details:")
                        for comp_name, comp_data in health_status.get(
                            "components", {}
                        ).items():
                            comp_status = comp_data.get("overall_status", "unknown")
                            print(f"  {comp_name}: {comp_status}")
                else:
                    # Table format (default)
                    overall_status = health_status.get("overall_status", "unknown")
                    status_style = (
                        "green"
                        if overall_status == "healthy"
                        else "red" if overall_status == "unhealthy" else "yellow"
                    )

                    console.print(
                        Panel(
                            f"[bold {status_style}]Overall Status: {overall_status.upper()}[/bold {status_style}]\n"
                            f"Timestamp: {health_status.get('timestamp', 'unknown')}\n"
                            f"Uptime: {health_status.get('uptime_seconds', 0):.0f} seconds",
                            title="InkedUp Trading Bot Health",
                            expand=False,
                        )
                    )

                    # Component summary table
                    health_table = Table(title="Component Status")
                    health_table.add_column("Component", style="cyan", no_wrap=True)
                    health_table.add_column("Status", style="magenta")

                    if detailed:
                        health_table.add_column("Details", style="white")

                    component_status = (
                        health_status.get("component_status", {})
                        if not detailed
                        else None
                    )
                    components_detailed = (
                        health_status.get("components", {}) if detailed else {}
                    )

                    if component_status:
                        # Simple component status
                        for comp_name, comp_status in component_status.items():
                            comp_style = (
                                "green"
                                if comp_status == "healthy"
                                else "red" if comp_status == "unhealthy" else "yellow"
                            )
                            health_table.add_row(
                                comp_name.replace("_", " ").title(),
                                f"[{comp_style}]{comp_status.upper()}[/{comp_style}]",
                            )
                    elif components_detailed:
                        # Detailed component status
                        for comp_name, comp_data in components_detailed.items():
                            comp_status = comp_data.get("overall_status", "unknown")
                            comp_style = (
                                "green"
                                if comp_status == "healthy"
                                else "red" if comp_status == "unhealthy" else "yellow"
                            )

                            # Get summary from first check
                            checks = comp_data.get("checks", {})
                            first_check = next(iter(checks.values())) if checks else {}
                            details = first_check.get("message", "No details available")

                            health_table.add_row(
                                comp_name.replace("_", " ").title(),
                                f"[{comp_style}]{comp_status.upper()}[/{comp_style}]",
                                details[:40] + "..." if len(details) > 40 else details,
                            )

                    console.print(health_table)

                    # Summary statistics
                    summary = health_status.get("summary", {})
                    if summary:
                        console.print(
                            f"\n[cyan]Summary:[/cyan] "
                            f"{summary.get('healthy_components', 0)} healthy, "
                            f"{summary.get('warning_components', 0)} warnings, "
                            f"{summary.get('unhealthy_components', 0)} unhealthy"
                        )

            # Export if requested
            if export:
                export_format = "json" if export.endswith(".json") else "text"
                content = health_service.export_health_status(
                    export_format, Path(export)
                )
                console.print(f"[green]Health status exported to {export}[/green]")

            # Clean up
            for component in components.values():
                if hasattr(component, "close"):
                    try:
                        await component.close()
                    except Exception:
                        pass

        except Exception as e:
            console.print(
                Panel(
                    f"[bold red]Health check failed[/bold red]\n\n" f"Error: {e}",
                    title="Health Check Error",
                    border_style="red",
                )
            )
            import traceback

            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            raise typer.Exit(1)

    asyncio.run(run())


@app.command("shutdown-status")
def shutdown_status() -> None:
    """Show current shutdown manager status and registered components."""
    from .shutdown_manager import _shutdown_manager

    console = Console()

    if _shutdown_manager is None:
        console.print(
            Panel(
                "[yellow]No shutdown manager instance found.[/yellow]\n"
                "The shutdown manager is only active when running long-running commands like 'scan', 'ws-scan', or 'snapshots'.",
                title="Shutdown Manager Status",
                border_style="yellow",
            )
        )
        return

    # Get shutdown status
    status = _shutdown_manager.get_shutdown_status()

    # Create main status table
    status_table = Table(show_header=True, header_style="bold blue")
    status_table.add_column("Property", style="cyan")
    status_table.add_column("Value", style="white")

    # Overall status
    state_style = (
        "red"
        if status["state"] == "stopped"
        else "yellow" if status["state"] == "shutting_down" else "green"
    )
    status_table.add_row(
        "State",
        f"[{state_style}]{status['state'].upper().replace('_', ' ')}[/{state_style}]",
    )

    if status.get("triggered_by"):
        status_table.add_row("Triggered By", str(status["triggered_by"]))

    status_table.add_row(
        "Force Shutdown",
        "[red]Yes[/red]" if status.get("force_shutdown") else "[green]No[/green]",
    )

    # Component counts
    components = status.get("components", {})
    status_table.add_row("Total Components", str(components.get("total", 0)))
    status_table.add_row(
        "Completed", f"[green]{components.get('completed', 0)}[/green]"
    )
    status_table.add_row("Failed", f"[red]{components.get('failed', 0)}[/red]")
    status_table.add_row(
        "In Progress", f"[yellow]{components.get('in_progress', 0)}[/yellow]"
    )

    # Timing information
    timing = status.get("timing", {})
    if timing.get("started_at"):
        status_table.add_row("Started At", timing["started_at"])
        status_table.add_row("Duration", f"{timing.get('duration', 0):.1f} seconds")

    if timing.get("completed_at"):
        status_table.add_row("Completed At", timing["completed_at"])

    console.print(
        Panel(status_table, title="Shutdown Manager Status", border_style="blue")
    )

    # Component details
    component_details = status.get("component_details", [])
    if component_details:
        console.print("\n[bold cyan]Registered Components[/bold cyan]")

        comp_table = Table(show_header=True, header_style="bold blue")
        comp_table.add_column("Component", style="cyan")
        comp_table.add_column("Priority", style="magenta")
        comp_table.add_column("Timeout", style="yellow")
        comp_table.add_column("Status", style="white")
        comp_table.add_column("Duration", style="dim")

        for comp in component_details:
            status_text = (
                "[green]Completed[/green]"
                if comp.get("completed")
                else (
                    "[red]Failed[/red]"
                    if comp.get("error")
                    else "[yellow]Pending[/yellow]"
                )
            )

            if comp.get("error"):
                status_text += (
                    f" ([red]{comp['error'][:30]}...[/red])"
                    if len(comp["error"]) > 30
                    else f" ([red]{comp['error']}[/red])"
                )

            duration_text = (
                f"{comp.get('duration', 0):.1f}s" if comp.get("duration") else "-"
            )

            comp_table.add_row(
                comp["name"].replace("_", " ").title(),
                comp["priority"],
                f"{comp['timeout']}s",
                status_text,
                duration_text,
            )

        console.print(comp_table)


@app.command("config-reload")
def config_reload() -> None:
    """Reload configuration from .env file without restarting."""
    console = Console()

    try:
        success = reload_config_now()

        if success:
            console.print(
                Panel(
                    "[green]Configuration reloaded successfully![/green]\n"
                    "Changes have been applied and components notified.",
                    title="Configuration Reload",
                    border_style="green",
                )
            )
        else:
            console.print(
                Panel(
                    "[red]Configuration reload failed![/red]\n"
                    "Check the logs for error details. The previous configuration remains active.",
                    title="Configuration Reload Failed",
                    border_style="red",
                )
            )
            raise typer.Exit(1)

    except Exception as e:
        console.print(
            Panel(
                f"[red]Error during configuration reload:[/red]\n{e}",
                title="Configuration Reload Error",
                border_style="red",
            )
        )
        raise typer.Exit(1)


@app.command("config-status")
def config_status() -> None:
    """Show configuration hot reload status and statistics."""
    console = Console()

    try:
        # Get hot reload stats
        stats = get_config_reload_stats()

        # Create main status table
        status_table = Table(show_header=True, header_style="bold blue")
        status_table.add_column("Property", style="cyan")
        status_table.add_column("Value", style="white")

        # Monitoring status
        monitoring_status = (
            "[green]Active[/green]"
            if stats.get("monitoring", False)
            else "[red]Inactive[/red]"
        )
        status_table.add_row("Hot Reload Monitoring", monitoring_status)

        # File information
        status_table.add_row(
            "Configuration File", str(stats.get("env_file_path", "Unknown"))
        )
        file_exists = (
            "[green]Yes[/green]"
            if stats.get("env_file_exists", False)
            else "[red]No[/red]"
        )
        status_table.add_row("File Exists", file_exists)

        # Reload statistics
        status_table.add_row("Total Reloads", str(stats.get("total_reloads", 0)))
        status_table.add_row(
            "Successful", f"[green]{stats.get('successful_reloads', 0)}[/green]"
        )
        status_table.add_row("Failed", f"[red]{stats.get('failed_reloads', 0)}[/red]")

        # Timing information
        last_reload = stats.get("last_reload_time")
        if last_reload:
            status_table.add_row("Last Reload", last_reload)
        else:
            status_table.add_row("Last Reload", "[dim]Never[/dim]")

        status_table.add_row(
            "Registered Callbacks", str(stats.get("registered_callbacks", 0))
        )

        console.print(
            Panel(
                status_table,
                title="Configuration Hot Reload Status",
                border_style="blue",
            )
        )

        # Show config manager stats if available
        try:
            config_manager = get_config_manager()
            manager_stats = config_manager.get_reload_stats()

            if manager_stats.get("registered_components"):
                console.print("\n[bold cyan]Registered Components[/bold cyan]")
                components_table = Table(show_header=False)
                components_table.add_column("Component", style="green")

                for component in manager_stats["registered_components"]:
                    components_table.add_row(component)

                console.print(components_table)
        except Exception:
            # Config manager might not be initialized
            pass

    except Exception as e:
        console.print(
            Panel(
                f"[red]Error getting configuration status:[/red]\n{e}",
                title="Configuration Status Error",
                border_style="red",
            )
        )
        raise typer.Exit(1)


@app.command("config-watch")
def config_watch(
    duration: int = typer.Option(60, help="Duration to watch in seconds")
) -> None:
    """Watch for configuration file changes and show reload events."""
    console = Console()

    console.print(
        f"[blue]Watching configuration changes for {duration} seconds...[/blue]"
    )
    console.print("[dim]Modify your .env file to see hot reload in action[/dim]")
    console.print("[dim]Press Ctrl+C to stop watching[/dim]\n")

    # Start configuration manager
    config_manager = get_config_manager()
    config_manager.start()

    # Track reload count
    initial_stats = get_config_reload_stats()
    initial_reloads = initial_stats.get("total_reloads", 0)

    import time

    start_time = time.time()

    try:
        while time.time() - start_time < duration:
            time.sleep(1)

            # Check for new reloads
            current_stats = get_config_reload_stats()
            current_reloads = current_stats.get("total_reloads", 0)

            if current_reloads > initial_reloads:
                console.print(
                    f"[green]✅ Configuration reloaded![/green] (Total: {current_reloads})"
                )
                console.print(
                    f"   Last reload: {current_stats.get('last_reload_time', 'Unknown')}"
                )

                if current_stats.get("failed_reloads", 0) > initial_stats.get(
                    "failed_reloads", 0
                ):
                    console.print("[red]❌ Some reloads failed![/red]")

                initial_reloads = current_reloads
                console.print()

        console.print(f"[blue]Finished watching after {duration} seconds[/blue]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped watching configuration changes[/yellow]")

    finally:
        config_manager.stop()


@app.command()
def backup_create(
    backup_type: Optional[str] = typer.Option(
        "full", help="Type of backup to create (full, incremental, configuration)"
    )
) -> None:
    """Create a manual backup."""
    console = Console()

    async def run():
        try:
            backup_manager = get_backup_manager()

            # Convert string to BackupType enum
            try:
                backup_type_enum = BackupType(backup_type.lower())
            except ValueError:
                console.print(
                    f"[red]Invalid backup type: {backup_type}. Must be one of: full, incremental, configuration[/red]"
                )
                raise typer.Exit(1)

            console.print(f"[blue]Creating {backup_type_enum.value} backup...[/blue]")
            backup_record = await backup_manager.create_manual_backup(
                backup_type=backup_type_enum
            )

            if backup_record is None:
                console.print("[red]Failed to create backup[/red]")
                raise typer.Exit(1)

            # Create table for backup details
            table = Table(title="Backup Created Successfully", show_header=True)
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Backup ID", backup_record.backup_id)
            table.add_row("Type", backup_record.backup_type.value.title())
            table.add_row("Status", backup_record.status.value.title())
            table.add_row(
                "Created", backup_record.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            )
            table.add_row(
                "Size",
                (
                    f"{backup_record.size_bytes:,} bytes"
                    if backup_record.size_bytes
                    else "N/A"
                ),
            )
            table.add_row("Path", str(backup_record.file_path))

            console.print(table)

        except Exception as e:
            console.print(f"[red]Failed to create backup: {e}[/red]")
            raise typer.Exit(1)

    asyncio.run(run())


@app.command()
def backup_list(
    limit: int = typer.Option(10, help="Maximum number of backups to display")
) -> None:
    """List available backups."""
    console = Console()

    try:
        backup_manager = get_backup_manager()
        backups = backup_manager.list_backups(limit=limit)

        if not backups:
            console.print("[yellow]No backups found[/yellow]")
            return

        # Create table for backup list
        table = Table(
            title=f"Available Backups (showing {len(backups)})", show_header=True
        )
        table.add_column("ID", style="cyan")
        table.add_column("Type", style="blue")
        table.add_column("Status", style="green")
        table.add_column("Created", style="yellow")
        table.add_column("Size", style="magenta")
        table.add_column("Description", style="white")

        for backup in backups:
            size_str = f"{backup.size_bytes:,} bytes" if backup.size_bytes else "N/A"
            created_str = backup.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            description = (
                backup.metadata.get("description", "No description")
                if backup.metadata
                else "No description"
            )

            table.add_row(
                backup.backup_id,
                backup.backup_type.value.title(),
                backup.status.value.title(),
                created_str,
                size_str,
                description,
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Failed to list backups: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def backup_restore(
    backup_id: str = typer.Argument(..., help="ID of the backup to restore"),
    confirm: bool = typer.Option(
        False, "--confirm", help="Confirm the restoration without prompting"
    ),
) -> None:
    """Restore from a backup."""
    console = Console()

    try:
        backup_manager = get_backup_manager()

        # Get backup details
        backups = backup_manager.list_backups()
        backup_record = next((b for b in backups if b.backup_id == backup_id), None)

        if not backup_record:
            console.print(f"[red]Backup {backup_id} not found[/red]")
            raise typer.Exit(1)

        # Show backup details
        console.print("[blue]Backup Details:[/blue]")
        console.print(f"  ID: {backup_record.backup_id}")
        console.print(f"  Type: {backup_record.backup_type.value.title()}")
        console.print(
            f"  Created: {backup_record.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        console.print(
            f"  Size: {backup_record.size_bytes:,} bytes"
            if backup_record.size_bytes
            else "  Size: N/A"
        )
        console.print(f"  Path: {backup_record.file_path}")

        # Confirm restoration
        if not confirm:
            confirm_restore = typer.confirm(
                "\n[yellow]WARNING: This will restore the database from the backup. Continue?[/yellow]"
            )
            if not confirm_restore:
                console.print("[blue]Restoration cancelled[/blue]")
                return

        console.print(f"[blue]Restoring from backup {backup_id}...[/blue]")
        success = backup_manager.restore_from_backup(backup_id)

        if success:
            console.print(
                f"[green]Successfully restored from backup {backup_id}[/green]"
            )
        else:
            console.print(f"[red]Failed to restore from backup {backup_id}[/red]")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Failed to restore backup: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def backup_status() -> None:
    """Display backup system status and statistics."""
    console = Console()

    try:
        backup_manager = get_backup_manager()
        stats = backup_manager.get_backup_stats()

        # Main status table
        status_table = Table(title="Backup System Status", show_header=True)
        status_table.add_column("Metric", style="cyan")
        status_table.add_column("Value", style="green")

        status_table.add_row(
            "Scheduled Backups",
            "Enabled" if backup_manager.is_scheduled_enabled() else "Disabled",
        )
        status_table.add_row("Total Backups", str(stats["total_backups"]))
        status_table.add_row("Successful Backups", str(stats["successful_backups"]))
        status_table.add_row("Failed Backups", str(stats["failed_backups"]))
        status_table.add_row(
            "Total Storage Used", f"{stats['total_storage_bytes']:,} bytes"
        )

        if stats["last_backup_time"]:
            status_table.add_row("Last Backup", stats["last_backup_time"])
        else:
            status_table.add_row("Last Backup", "Never")

        if stats["next_scheduled_backup"]:
            status_table.add_row("Next Scheduled", stats["next_scheduled_backup"])

        console.print(status_table)

        # Backup type breakdown
        if stats["backup_types"]:
            type_table = Table(title="Backup Types", show_header=True)
            type_table.add_column("Type", style="blue")
            type_table.add_column("Count", style="yellow")

            for backup_type, count in stats["backup_types"].items():
                type_table.add_row(backup_type.title(), str(count))

            console.print(type_table)

    except Exception as e:
        console.print(f"[red]Failed to get backup status: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def backup_cleanup(
    older_than_days: int = typer.Option(
        7, help="Remove backups older than this many days"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be deleted without actually deleting"
    ),
) -> None:
    """Clean up old backups based on retention policy."""
    console = Console()

    try:
        backup_manager = get_backup_manager()

        if dry_run:
            console.print(
                f"[blue]Dry run: Would clean up backups older than {older_than_days} days[/blue]"
            )
        else:
            console.print(
                f"[blue]Cleaning up backups older than {older_than_days} days...[/blue]"
            )

        deleted_count = backup_manager.cleanup_old_backups(
            older_than_days, dry_run=dry_run
        )

        if dry_run:
            console.print(
                f"[yellow]Would delete {deleted_count} old backup(s)[/yellow]"
            )
        else:
            console.print(
                f"[green]Successfully deleted {deleted_count} old backup(s)[/green]"
            )

    except Exception as e:
        console.print(f"[red]Failed to cleanup backups: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def config() -> None:
    """Display current configuration values."""
    cfg = BotConfig()
    print(cfg)


@app.command("retention-apply")
def retention_apply(
    dry_run: bool = typer.Option(
        False, help="Simulate operation without actual deletion"
    ),
    enable_archiving: bool = typer.Option(True, help="Archive data before deletion"),
) -> None:
    """Apply data retention policies to clean up old data."""
    console = Console()

    try:
        console.print("\n[bold cyan]Applying Data Retention Policies[/bold cyan]")

        async def run_retention():
            cfg = BotConfig()
            db = DatabaseManager(cfg.database_url.replace("sqlite:///", ""))

            # Get backup manager if archiving is enabled
            backup_manager = None
            if enable_archiving:
                try:
                    backup_manager = get_backup_manager(cfg, db)
                except:
                    console.print(
                        "[yellow]Warning: Backup manager unavailable, archiving disabled[/yellow]"
                    )

            # Create retention manager
            retention_manager = DataRetentionManager(
                database_manager=db,
                backup_manager=backup_manager,
                dry_run=dry_run,
                enable_archiving=enable_archiving,
            )

            # Apply policies
            stats = await retention_manager.apply_retention_policies()

            # Display results
            table = Table(title="Retention Policy Results")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", justify="right")

            table.add_row("Tables Processed", str(stats.total_tables_processed))
            table.add_row("Rows Deleted", f"{stats.total_rows_deleted:,}")
            table.add_row("Rows Archived", f"{stats.total_rows_archived:,}")
            table.add_row("Storage Freed", f"{stats.total_storage_freed_mb:.2f} MB")
            table.add_row("Errors", str(stats.errors_encountered))
            table.add_row(
                "Processing Time", f"{stats.processing_time_seconds:.2f} seconds"
            )

            if dry_run:
                table.add_row("Mode", "[yellow]DRY RUN[/yellow]")

            console.print(table)

            # Show per-table statistics
            if stats.table_statistics:
                detail_table = Table(title="Per-Table Statistics")
                detail_table.add_column("Table", style="cyan")
                detail_table.add_column("Rows Deleted", justify="right")
                detail_table.add_column("Rows Archived", justify="right")
                detail_table.add_column("Storage Freed", justify="right")

                for table_name, table_stats in stats.table_statistics.items():
                    detail_table.add_row(
                        table_name,
                        f"{table_stats.get('rows_deleted', 0):,}",
                        f"{table_stats.get('rows_archived', 0):,}",
                        f"{table_stats.get('storage_freed_mb', 0):.2f} MB",
                    )

                console.print(detail_table)

        asyncio.run(run_retention())

    except Exception as e:
        console.print(f"[red]Failed to apply retention policies: {e}[/red]")
        raise typer.Exit(1)


@app.command("retention-status")
def retention_status() -> None:
    """Display current retention policy status and statistics."""
    console = Console()

    try:

        async def show_status():
            cfg = BotConfig()
            db = DatabaseManager(cfg.database_url.replace("sqlite:///", ""))

            retention_manager = DataRetentionManager(
                database_manager=db, dry_run=True  # Use dry run for status check
            )

            # Get statistics
            stats = retention_manager.get_statistics()

            # Display overall status
            status_table = Table(title="Retention Manager Status")
            status_table.add_column("Property", style="cyan")
            status_table.add_column("Value", justify="right")

            status_table.add_row("Last Run", stats.get("last_run", "Never"))
            status_table.add_row("Next Run", stats.get("next_run", "Not scheduled"))
            status_table.add_row("Total Policies", str(stats.get("policies_count", 0)))
            status_table.add_row(
                "Enabled Policies", str(stats.get("enabled_policies", 0))
            )

            if stats.get("last_run"):
                status_table.add_row("Last Run Results", "")
                status_table.add_row(
                    "  Tables Processed", str(stats.get("total_tables_processed", 0))
                )
                status_table.add_row(
                    "  Rows Deleted", f"{stats.get('total_rows_deleted', 0):,}"
                )
                status_table.add_row(
                    "  Rows Archived", f"{stats.get('total_rows_archived', 0):,}"
                )
                status_table.add_row(
                    "  Storage Freed",
                    f"{stats.get('total_storage_freed_mb', 0):.2f} MB",
                )

            console.print(status_table)

            # Show policy summary
            policies = retention_manager.get_policy_summary()
            if policies:
                policy_table = Table(title="Configured Retention Policies")
                policy_table.add_column("Table", style="cyan")
                policy_table.add_column("Retention Days", justify="right")
                policy_table.add_column("Archive", justify="center")
                policy_table.add_column("Status", justify="center")
                policy_table.add_column("Cutoff Date")

                for policy in policies:
                    status_emoji = "✅" if policy["enabled"] else "❌"
                    archive_emoji = "✅" if policy["archive_enabled"] else "❌"
                    policy_table.add_row(
                        policy["table"],
                        str(policy["retention_days"]),
                        archive_emoji,
                        status_emoji,
                        policy["cutoff_date"][:10],  # Just the date part
                    )

                console.print(policy_table)

        asyncio.run(show_status())

    except Exception as e:
        console.print(f"[red]Failed to get retention status: {e}[/red]")
        raise typer.Exit(1)


@app.command("retention-analyze")
def retention_analyze() -> None:
    """Analyze current database storage usage and retention opportunities."""
    console = Console()

    try:

        async def analyze_storage():
            cfg = BotConfig()
            db = DatabaseManager(cfg.database_url.replace("sqlite:///", ""))

            retention_manager = DataRetentionManager(database_manager=db, dry_run=True)

            # Analyze storage usage
            storage_info = await retention_manager.analyze_storage_usage()

            if not storage_info:
                console.print("[yellow]No storage information available[/yellow]")
                return

            # Display overall statistics
            total_table = Table(title="Database Storage Overview")
            total_table.add_column("Metric", style="cyan")
            total_table.add_column("Value", justify="right")

            total_table.add_row("Total Rows", f"{storage_info.get('total_rows', 0):,}")
            total_table.add_row(
                "Estimated Size",
                f"{storage_info.get('total_estimated_size_mb', 0):.2f} MB",
            )
            total_table.add_row(
                "Tables with Policies", str(storage_info.get("tables_with_policies", 0))
            )
            total_table.add_row(
                "Tables without Policies",
                str(storage_info.get("tables_without_policies", 0)),
            )

            console.print(total_table)

            # Display per-table information
            tables_info = storage_info.get("tables", {})
            if tables_info:
                table_detail = Table(title="Table Storage Details")
                table_detail.add_column("Table", style="cyan")
                table_detail.add_column("Row Count", justify="right")
                table_detail.add_column("Est. Size (MB)", justify="right")
                table_detail.add_column("Has Policy", justify="center")
                table_detail.add_column("Retention Days", justify="right")

                # Sort tables by size (descending)
                sorted_tables = sorted(
                    tables_info.items(),
                    key=lambda x: x[1]["estimated_size_mb"],
                    reverse=True,
                )

                for table_name, info in sorted_tables:
                    has_policy = "✅" if info["has_retention_policy"] else "❌"
                    retention_days = (
                        str(info["retention_days"]) if info["retention_days"] else "N/A"
                    )

                    table_detail.add_row(
                        table_name,
                        f"{info['row_count']:,}",
                        f"{info['estimated_size_mb']:.2f}",
                        has_policy,
                        retention_days,
                    )

                console.print(table_detail)

                # Show recommendations
                tables_without_policies = [
                    name
                    for name, info in tables_info.items()
                    if not info["has_retention_policy"] and info["row_count"] > 1000
                ]

                if tables_without_policies:
                    console.print("\n[yellow]⚠️ Recommendations:[/yellow]")
                    console.print(
                        f"Consider adding retention policies for these high-volume tables:"
                    )
                    for table in tables_without_policies:
                        console.print(
                            f"  • {table} ({tables_info[table]['row_count']:,} rows)"
                        )

        asyncio.run(analyze_storage())

    except Exception as e:
        console.print(f"[red]Failed to analyze storage: {e}[/red]")
        raise typer.Exit(1)


@app.command("retention-vacuum")
def retention_vacuum(
    confirm: bool = typer.Option(False, "--confirm", help="Confirm vacuum operation")
) -> None:
    """Vacuum the database to reclaim space after deletions."""
    console = Console()

    if not confirm:
        console.print(
            "[yellow]⚠️ Warning: Database vacuum can be slow for large databases.[/yellow]"
        )
        console.print("Run with --confirm to proceed.")
        return

    try:

        async def run_vacuum():
            cfg = BotConfig()
            db = DatabaseManager(cfg.database_url.replace("sqlite:///", ""))

            retention_manager = DataRetentionManager(database_manager=db, dry_run=False)

            console.print("[cyan]Starting database vacuum operation...[/cyan]")
            await retention_manager.vacuum_database()
            console.print("[green]✅ Database vacuum completed successfully[/green]")

        asyncio.run(run_vacuum())

    except Exception as e:
        console.print(f"[red]Failed to vacuum database: {e}[/red]")
        raise typer.Exit(1)


@app.command("retention-schedule")
def retention_schedule(
    interval_hours: int = typer.Option(24, help="Hours between cleanup runs"),
    duration_hours: int = typer.Option(
        168, help="Total duration to run scheduler (168 = 1 week)"
    ),
) -> None:
    """Start scheduled data retention cleanup."""
    console = Console()

    try:

        async def run_scheduled():
            cfg = BotConfig()
            db = DatabaseManager(cfg.database_url.replace("sqlite:///", ""))

            # Get backup manager for archiving
            backup_manager = None
            try:
                backup_manager = get_backup_manager(cfg, db)
            except:
                console.print(
                    "[yellow]Warning: Backup manager unavailable, archiving disabled[/yellow]"
                )

            retention_manager = DataRetentionManager(
                database_manager=db,
                backup_manager=backup_manager,
                dry_run=False,
                enable_archiving=True,
            )

            console.print(f"[cyan]Starting scheduled retention cleanup[/cyan]")
            console.print(f"  • Interval: {interval_hours} hours")
            console.print(f"  • Duration: {duration_hours} hours")
            console.print(f"  • Press Ctrl+C to stop")

            # Start scheduled cleanup
            await retention_manager.start_scheduled_cleanup(interval_hours)

            # Wait for specified duration
            await asyncio.sleep(duration_hours * 3600)

            # Stop scheduled cleanup
            await retention_manager.stop_scheduled_cleanup()
            console.print("[green]✅ Scheduled cleanup completed[/green]")

        asyncio.run(run_scheduled())

    except KeyboardInterrupt:
        console.print("\n[yellow]Scheduled cleanup stopped by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Failed to run scheduled cleanup: {e}[/red]")
        raise typer.Exit(1)


@app.command("dashboard")
def dashboard(
    mode: str = typer.Option(
        "console", 
        help="Dashboard mode: console, web, or integrated"
    ),
    port: int = typer.Option(8080, help="Port for web dashboard"),
    mock: bool = typer.Option(False, help="Use mock data for demo"),
) -> None:
    """Start the real-time trading opportunities dashboard."""
    console = Console()
    
    console.print("🎯 Starting Polymarket Trading Dashboard...")
    console.print(f"Mode: {mode.upper()}")
    
    if mode not in ["console", "web", "integrated"]:
        console.print("[red]Error: mode must be 'console', 'web', or 'integrated'[/red]")
        raise typer.Exit(1)
    
    try:
        cfg = BotConfig()
        
        async def run_dashboard():
            if mode == "console":
                if mock:
                    # Use mock data for demo
                    from examples.realtime_trading_dashboard_demo import MockVisualDashboard
                    dashboard = MockVisualDashboard(cfg)
                    await dashboard.start_dashboard()
                else:
                    await run_integrated_dashboard(cfg)
            
            elif mode == "web":
                console.print(f"🌐 Web dashboard starting on port {port}")
                console.print(f"💡 Open http://localhost:{port} in your browser")
                
                if mock:
                    await run_web_dashboard(cfg, port)
                else:
                    await run_integrated_web_dashboard(cfg, port)
            
            elif mode == "integrated":
                console.print("🔄 Starting integrated dashboard with live scanner data...")
                await run_integrated_dashboard(cfg)
        
        asyncio.run(run_dashboard())
        
    except KeyboardInterrupt:
        console.print("\n👋 Dashboard stopped")
    except Exception as e:
        console.print(f"[red]Dashboard error: {e}[/red]")
        raise typer.Exit(1)


@app.command("dashboard-demo")  
def dashboard_demo() -> None:
    """Run the interactive trading dashboard demo."""
    console = Console()
    
    try:
        from examples.realtime_trading_dashboard_demo import main as demo_main
        asyncio.run(demo_main())
        
    except KeyboardInterrupt:
        console.print("\n👋 Demo stopped")
    except Exception as e:
        console.print(f"[red]Demo error: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
