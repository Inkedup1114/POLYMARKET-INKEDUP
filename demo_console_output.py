#!/usr/bin/env python3
"""
Demo Console Output Display
Shows what the real-time trading dashboard console looks like
"""

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from datetime import datetime, timedelta
import asyncio
import random

console = Console()

def create_demo_dashboard():
    """Create a demo dashboard showing what the console output looks like."""
    
    # Create header with stats
    header_table = Table.grid(padding=1)
    header_table.add_column(justify="left")
    header_table.add_column(justify="center") 
    header_table.add_column(justify="right")

    # Status indicators
    uptime_str = "0:02:34"
    last_scan_str = datetime.now().strftime("%H:%M:%S")

    status_text = Text()
    status_text.append("🔄 Active", style="green")
    status_text.append(f" | ⏱️ Uptime: {uptime_str}")
    status_text.append(f" | 🔍 Last Scan: {last_scan_str}")

    # Key metrics
    metrics_text = Text()
    metrics_text.append("📊 Total Opportunities: ", style="white")
    metrics_text.append("12", style="cyan bold")
    metrics_text.append(" | ⭐ High Confidence: ", style="white")
    metrics_text.append("5", style="green bold")

    # Profit potential
    profit_text = Text()
    profit_text.append("💰 Total Profit Potential: ", style="white")
    profit_text.append("$247.85", style="green bold")
    profit_text.append(" | 📈 Avg Spread: ", style="white")
    profit_text.append("285 bps", style="yellow")

    header_table.add_row(status_text, metrics_text, profit_text)

    # Create opportunities table
    opp_table = Table(
        title="🎯 Live Trading Opportunities",
        show_header=True,
        header_style="bold magenta",
        title_style="bold blue"
    )

    # Table columns
    opp_table.add_column("Market", style="cyan", width=25)
    opp_table.add_column("Type", justify="center", width=12)
    opp_table.add_column("Spread", justify="right", style="yellow")
    opp_table.add_column("Profit", justify="right", style="green")
    opp_table.add_column("Size", justify="right", style="blue")
    opp_table.add_column("Confidence", justify="center")
    opp_table.add_column("Liquidity", justify="right", style="magenta")
    opp_table.add_column("Slippage", justify="right", style="red")
    opp_table.add_column("Age", justify="center", style="dim")

    # Sample opportunities
    opportunities = [
        ("2024 Presidential Election", "Complement Arb", "145 bps", "$45.20", "$2000", "[green]92%[/green]", "$45000", "0.8%", "12s"),
        ("Fed Rate Hike Dec 2024", "Wide Spread", "320 bps", "$32.50", "$1500", "[yellow]76%[/yellow]", "$28000", "1.2%", "34s"),
        ("Bitcoin to $100k 2024", "Market Making", "180 bps", "$18.75", "$800", "[yellow]68%[/yellow]", "$67000", "0.5%", "1.2m"),
        ("NFL Super Bowl Winner", "Wide Spread", "425 bps", "$51.30", "$1200", "[green]84%[/green]", "$12000", "2.1%", "45s"),
        ("S&P 500 Crash 2024", "Complement Arb", "210 bps", "$38.90", "$1800", "[green]89%[/green]", "$23000", "1.0%", "8s"),
        ("Nvidia Stock Price", "Market Making", "155 bps", "$15.60", "$750", "[red]58%[/red]", "$89000", "0.3%", "2.1m"),
        ("Apple Earnings Beat", "Wide Spread", "380 bps", "$42.10", "$1100", "[yellow]72%[/yellow]", "$34000", "1.8%", "1.5m"),
        ("Tesla Model Y Sales", "Complement Arb", "195 bps", "$29.45", "$1500", "[green]85%[/green]", "$41000", "0.9%", "23s"),
    ]

    for opp in opportunities:
        opp_table.add_row(*opp)

    # Market overview
    market_table = Table(
        title="📈 Market Overview",
        show_header=True,
        header_style="bold cyan"
    )

    market_table.add_column("Metric", style="white")
    market_table.add_column("Value", justify="right", style="cyan")
    market_table.add_column("Metric", style="white") 
    market_table.add_column("Value", justify="right", style="cyan")

    market_table.add_row("Active Markets", "8", "Scan Rate", "2.1/s")
    market_table.add_row("Opportunities/Hour", "34.2", "Avg Opportunity Age", "52s")

    # Footer
    footer = Text()
    footer.append("\n💡 Tips: ", style="bold white")
    footer.append("Look for high confidence + low slippage opportunities | ")
    footer.append("Monitor liquidity before placing large orders | ")
    footer.append("Consider market impact for position sizing\n")

    footer.append("🎛️ Controls: ", style="bold white")
    footer.append("[S]ort by different metrics | ")
    footer.append("[F]ilter opportunities | ")
    footer.append("[A]lert settings | ")
    footer.append("[Ctrl+C] to exit")

    # Combine all sections
    dashboard_content = f"{header_table}\n\n{opp_table}\n\n{market_table}\n{footer}"

    return Panel(
        dashboard_content,
        title="🎯 Polymarket Trading Opportunities Dashboard",
        border_style="bright_blue",
        padding=(1, 2)
    )

async def demo_live_updates():
    """Show the dashboard with live updates."""
    console.print("\n🚀 Starting Real-Time Polymarket Trading Dashboard...")
    console.print("📊 Update interval: 1.5s")
    console.print("💡 This is a demo showing mock data")
    console.print("🔄 Press Ctrl+C to stop\n")
    
    await asyncio.sleep(2)
    
    update_count = 0
    
    try:
        with Live(create_demo_dashboard(), console=console, refresh_per_second=1) as live:
            while update_count < 8:  # Show 8 updates then stop
                await asyncio.sleep(1.5)
                
                # Update the dashboard with slightly different data
                updated_dashboard = create_demo_dashboard()
                live.update(updated_dashboard)
                update_count += 1
                
                # Simulate new opportunities being found
                if update_count == 3:
                    console.print("🔔 [bold yellow]New high-value opportunity detected![/bold yellow]")
                elif update_count == 6:
                    console.print("🚨 [bold red]Alert: Complement arbitrage opportunity above threshold![/bold red]")
                    
    except KeyboardInterrupt:
        pass
    
    console.print("\n✅ [bold green]Demo completed![/bold green]")
    console.print("💡 This shows what the real-time dashboard looks like with live market data")
    console.print("🔄 In production, this would continuously update with actual Polymarket opportunities")

if __name__ == "__main__":
    asyncio.run(demo_live_updates())