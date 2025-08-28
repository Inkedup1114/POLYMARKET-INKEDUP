#!/usr/bin/env python3
"""
Web-Based Real-Time Trading Dashboard

Interactive web interface for monitoring Polymarket trading opportunities with:
- Real-time WebSocket updates
- Interactive charts and graphs  
- Detailed opportunity analysis
- Trade execution interface
- Portfolio tracking
- Historical performance analytics
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from aiohttp import web
from aiohttp.web import Application, Request, Response, WebSocketResponse

from .config import BotConfig
from .visual_trading_dashboard import VisualTradingDashboard

logger = logging.getLogger("web_trading_dashboard")


class WebTradingDashboard:
    """Web-based trading dashboard with real-time updates."""

    def __init__(self, config: BotConfig, port: int = 8080):
        """Initialize web dashboard.

        Args:
            config: Bot configuration
            port: Web server port
        """
        self.config = config
        self.port = port
        self.dashboard = VisualTradingDashboard(config)

        # WebSocket connections for real-time updates
        self.websockets: set[WebSocketResponse] = set()

        # Web application setup
        self.app = Application()
        self.setup_routes()

        logger.info(f"Web dashboard initialized on port {port}")

    def setup_routes(self) -> None:
        """Set up web application routes."""
        # Static files
        self.app.router.add_get("/", self.serve_dashboard)
        self.app.router.add_get("/dashboard", self.serve_dashboard)
        self.app.router.add_static("/static/", path=self.get_static_dir())

        # API endpoints
        self.app.router.add_get("/api/opportunities", self.get_opportunities)
        self.app.router.add_get("/api/stats", self.get_stats)
        self.app.router.add_get("/api/market/{slug}", self.get_market_details)
        self.app.router.add_post("/api/trade", self.execute_trade)

        # WebSocket for real-time updates
        self.app.router.add_get("/ws", self.websocket_handler)

        # Configuration endpoints
        self.app.router.add_get("/api/config", self.get_config)
        self.app.router.add_post("/api/config", self.update_config)

    def get_static_dir(self) -> Path:
        """Get static files directory."""
        return Path(__file__).parent / "static"

    async def serve_dashboard(self, request: Request) -> Response:
        """Serve the main dashboard HTML page."""
        html_content = await self.generate_dashboard_html()
        return Response(text=html_content, content_type="text/html")

    async def generate_dashboard_html(self) -> str:
        """Generate the dashboard HTML with embedded JavaScript."""
        return r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Polymarket Trading Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .opportunity-row:hover { background-color: #f3f4f6; }
        .profit-positive { color: #10b981; }
        .profit-negative { color: #ef4444; }
        .confidence-high { background-color: #d1fae5; }
        .confidence-medium { background-color: #fef3c7; }
        .confidence-low { background-color: #fee2e2; }
        .pulse { animation: pulse 2s infinite; }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
    </style>
</head>
<body class="bg-gray-100">
    <!-- Header -->
    <header class="bg-blue-600 text-white p-4">
        <div class="container mx-auto flex justify-between items-center">
            <h1 class="text-2xl font-bold">🎯 Polymarket Trading Dashboard</h1>
            <div class="flex items-center space-x-4">
                <div id="connection-status" class="flex items-center">
                    <div class="w-3 h-3 bg-green-400 rounded-full pulse mr-2"></div>
                    <span>Connected</span>
                </div>
                <div id="last-update" class="text-sm opacity-75">
                    Last Update: <span id="last-update-time">Never</span>
                </div>
            </div>
        </div>
    </header>

    <!-- Main Dashboard -->
    <div class="container mx-auto p-4">
        <!-- Stats Cards -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <div class="bg-white p-6 rounded-lg shadow">
                <h3 class="text-lg font-semibold text-gray-700">Total Opportunities</h3>
                <p id="total-opportunities" class="text-3xl font-bold text-blue-600">0</p>
            </div>
            <div class="bg-white p-6 rounded-lg shadow">
                <h3 class="text-lg font-semibold text-gray-700">High Confidence</h3>
                <p id="high-confidence" class="text-3xl font-bold text-green-600">0</p>
            </div>
            <div class="bg-white p-6 rounded-lg shadow">
                <h3 class="text-lg font-semibold text-gray-700">Profit Potential</h3>
                <p id="profit-potential" class="text-3xl font-bold text-green-500">$0</p>
            </div>
            <div class="bg-white p-6 rounded-lg shadow">
                <h3 class="text-lg font-semibold text-gray-700">Avg Spread</h3>
                <p id="avg-spread" class="text-3xl font-bold text-yellow-500">0 bps</p>
            </div>
        </div>

        <!-- Filters and Controls -->
        <div class="bg-white p-4 rounded-lg shadow mb-6">
            <div class="flex flex-wrap items-center gap-4">
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Sort By</label>
                    <select id="sort-by" class="border border-gray-300 rounded px-3 py-2">
                        <option value="signal_strength">Signal Strength</option>
                        <option value="expected_profit">Expected Profit</option>
                        <option value="confidence">Confidence</option>
                        <option value="spread_bps">Spread (bps)</option>
                        <option value="discovered_at">Time Discovered</option>
                    </select>
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Min Confidence</label>
                    <input id="min-confidence" type="range" min="0" max="1" step="0.1" value="0" 
                           class="w-24">
                    <span id="confidence-value" class="text-sm text-gray-600">0%</span>
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Opportunity Type</label>
                    <div class="flex gap-2">
                        <label><input type="checkbox" checked id="filter-complement"> Arbitrage</label>
                        <label><input type="checkbox" checked id="filter-spread"> Wide Spread</label>
                        <label><input type="checkbox" checked id="filter-mm"> Market Making</label>
                    </div>
                </div>
                <div>
                    <button id="refresh-btn" 
                            class="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded">
                        🔄 Refresh
                    </button>
                </div>
            </div>
        </div>

        <!-- Opportunities Table -->
        <div class="bg-white rounded-lg shadow overflow-hidden">
            <div class="px-6 py-4 border-b border-gray-200">
                <h2 class="text-xl font-semibold text-gray-800">🎯 Live Trading Opportunities</h2>
            </div>
            <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-200">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Market
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Type
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Spread
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Expected Profit
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Confidence
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Liquidity
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Slippage
                            </th>
                            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Actions
                            </th>
                        </tr>
                    </thead>
                    <tbody id="opportunities-tbody" class="bg-white divide-y divide-gray-200">
                        <tr>
                            <td colspan="8" class="px-6 py-4 text-center text-gray-500">
                                Loading opportunities...
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Charts Section -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
            <!-- Opportunity Timeline Chart -->
            <div class="bg-white p-6 rounded-lg shadow">
                <h3 class="text-lg font-semibold text-gray-700 mb-4">Opportunities Timeline</h3>
                <canvas id="timeline-chart" width="400" height="200"></canvas>
            </div>
            
            <!-- Profit Distribution Chart -->
            <div class="bg-white p-6 rounded-lg shadow">
                <h3 class="text-lg font-semibold text-gray-700 mb-4">Profit Distribution</h3>
                <canvas id="profit-chart" width="400" height="200"></canvas>
            </div>
        </div>
    </div>

    <!-- Trade Modal -->
    <div id="trade-modal" class="fixed inset-0 bg-gray-600 bg-opacity-50 hidden">
        <div class="flex justify-center items-center h-full">
            <div class="bg-white p-8 rounded-lg shadow-lg w-96">
                <h3 class="text-xl font-semibold mb-4">Execute Trade</h3>
                <div id="trade-details" class="mb-4">
                    <!-- Trade details will be populated here -->
                </div>
                <div class="flex justify-end gap-4">
                    <button id="cancel-trade" 
                            class="bg-gray-500 hover:bg-gray-700 text-white font-bold py-2 px-4 rounded">
                        Cancel
                    </button>
                    <button id="execute-trade" 
                            class="bg-green-500 hover:bg-green-700 text-white font-bold py-2 px-4 rounded">
                        Execute
                    </button>
                </div>
            </div>
        </div>
    </div>

    <script>
        // WebSocket connection for real-time updates
        const ws = new WebSocket(`ws://${window.location.host}/ws`);
        let opportunitiesData = [];
        let chartsInitialized = false;
        let timelineChart, profitChart;

        // WebSocket event handlers
        ws.onopen = function(event) {
            console.log('WebSocket connected');
            updateConnectionStatus(true);
        };

        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            handleWebSocketMessage(data);
        };

        ws.onclose = function(event) {
            console.log('WebSocket disconnected');
            updateConnectionStatus(false);
            // Attempt to reconnect
            setTimeout(() => {
                location.reload();
            }, 5000);
        };

        ws.onerror = function(error) {
            console.error('WebSocket error:', error);
            updateConnectionStatus(false);
        };

        function handleWebSocketMessage(data) {
            if (data.type === 'opportunities_update') {
                opportunitiesData = data.opportunities;
                updateDashboard();
            } else if (data.type === 'stats_update') {
                updateStats(data.stats);
            }
            
            document.getElementById('last-update-time').textContent = new Date().toLocaleTimeString();
        }

        function updateConnectionStatus(connected) {
            const statusEl = document.getElementById('connection-status');
            const dot = statusEl.querySelector('div');
            const text = statusEl.querySelector('span');
            
            if (connected) {
                dot.className = 'w-3 h-3 bg-green-400 rounded-full pulse mr-2';
                text.textContent = 'Connected';
            } else {
                dot.className = 'w-3 h-3 bg-red-400 rounded-full mr-2';
                text.textContent = 'Disconnected';
            }
        }

        function updateStats(stats) {
            document.getElementById('total-opportunities').textContent = stats.total_opportunities || 0;
            document.getElementById('high-confidence').textContent = stats.high_confidence_opportunities || 0;
            document.getElementById('profit-potential').textContent = '$' + (stats.total_profit_potential || 0).toFixed(2);
            document.getElementById('avg-spread').textContent = Math.round(stats.avg_spread || 0) + ' bps';
        }

        function updateDashboard() {
            updateOpportunitiesTable();
            updateCharts();
        }

        function updateOpportunitiesTable() {
            const tbody = document.getElementById('opportunities-tbody');
            
            if (!opportunitiesData || opportunitiesData.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" class="px-6 py-4 text-center text-gray-500">
                            No opportunities found
                        </td>
                    </tr>
                `;
                return;
            }

            const filteredData = filterOpportunities(opportunitiesData);
            const sortedData = sortOpportunities(filteredData);

            tbody.innerHTML = sortedData.map(opp => `
                <tr class="opportunity-row cursor-pointer" data-id="${opp.market_slug}_${opp.token_id}">
                    <td class="px-6 py-4 whitespace-nowrap">
                        <div class="text-sm font-medium text-gray-900">
                            ${truncate(opp.market_title, 30)}
                        </div>
                        <div class="text-sm text-gray-500">
                            ${opp.outcome_name}
                        </div>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap">
                        <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full 
                                     ${getTypeColor(opp.opportunity_type)}">
                            ${formatType(opp.opportunity_type)}
                        </span>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        ${opp.spread_bps} bps
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm font-medium profit-positive">
                        $${opp.expected_profit.toFixed(2)}
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap">
                        <div class="text-sm text-gray-900">
                            <span class="px-2 py-1 rounded ${getConfidenceColor(opp.confidence)}">
                                ${(opp.confidence * 100).toFixed(0)}%
                            </span>
                        </div>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        $${opp.available_liquidity.toFixed(0)}
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        ${opp.slippage_1k.toFixed(2)}%
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm font-medium">
                        <button onclick="showTradeModal('${opp.market_slug}_${opp.token_id}')"
                                class="text-indigo-600 hover:text-indigo-900">
                            Trade
                        </button>
                        <button onclick="showDetails('${opp.market_slug}_${opp.token_id}')"
                                class="ml-2 text-blue-600 hover:text-blue-900">
                            Details
                        </button>
                    </td>
                </tr>
            `).join('');
        }

        function filterOpportunities(opportunities) {
            const minConfidence = parseFloat(document.getElementById('min-confidence').value);
            const showComplement = document.getElementById('filter-complement').checked;
            const showSpread = document.getElementById('filter-spread').checked;
            const showMM = document.getElementById('filter-mm').checked;

            return opportunities.filter(opp => {
                if (opp.confidence < minConfidence) return false;
                
                if (opp.opportunity_type === 'complement_arb' && !showComplement) return false;
                if (opp.opportunity_type === 'wide_spread' && !showSpread) return false;
                if (opp.opportunity_type === 'market_making' && !showMM) return false;
                
                return true;
            });
        }

        function sortOpportunities(opportunities) {
            const sortBy = document.getElementById('sort-by').value;
            return [...opportunities].sort((a, b) => {
                const aVal = a[sortBy] || 0;
                const bVal = b[sortBy] || 0;
                return bVal - aVal; // Descending order
            });
        }

        function updateCharts() {
            if (!chartsInitialized) {
                initializeCharts();
                chartsInitialized = true;
            }

            updateTimelineChart();
            updateProfitChart();
        }

        function initializeCharts() {
            // Timeline Chart
            const timelineCtx = document.getElementById('timeline-chart').getContext('2d');
            timelineChart = new Chart(timelineCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Opportunities Found',
                        data: [],
                        borderColor: 'rgb(59, 130, 246)',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        tension: 0.1
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                stepSize: 1
                            }
                        }
                    }
                }
            });

            // Profit Chart
            const profitCtx = document.getElementById('profit-chart').getContext('2d');
            profitChart = new Chart(profitCtx, {
                type: 'doughnut',
                data: {
                    labels: ['Arbitrage', 'Wide Spread', 'Market Making'],
                    datasets: [{
                        data: [0, 0, 0],
                        backgroundColor: [
                            'rgb(34, 197, 94)',
                            'rgb(249, 115, 22)',
                            'rgb(147, 51, 234)'
                        ]
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: {
                            position: 'bottom'
                        }
                    }
                }
            });
        }

        function updateTimelineChart() {
            // Simplified timeline update - in production you'd track historical data
            const now = new Date();
            const timeStr = now.toLocaleTimeString();
            
            timelineChart.data.labels.push(timeStr);
            timelineChart.data.datasets[0].data.push(opportunitiesData.length);
            
            // Keep only last 20 data points
            if (timelineChart.data.labels.length > 20) {
                timelineChart.data.labels.shift();
                timelineChart.data.datasets[0].data.shift();
            }
            
            timelineChart.update('none');
        }

        function updateProfitChart() {
            const profitByType = {
                'complement_arb': 0,
                'wide_spread': 0,
                'market_making': 0
            };

            opportunitiesData.forEach(opp => {
                if (profitByType.hasOwnProperty(opp.opportunity_type)) {
                    profitByType[opp.opportunity_type] += opp.expected_profit;
                }
            });

            profitChart.data.datasets[0].data = [
                profitByType.complement_arb,
                profitByType.wide_spread,
                profitByType.market_making
            ];
            
            profitChart.update('none');
        }

        // Utility functions
        function truncate(str, length) {
            return str.length > length ? str.substring(0, length) + '...' : str;
        }

        function getTypeColor(type) {
            const colors = {
                'complement_arb': 'bg-green-100 text-green-800',
                'wide_spread': 'bg-yellow-100 text-yellow-800',
                'market_making': 'bg-purple-100 text-purple-800'
            };
            return colors[type] || 'bg-gray-100 text-gray-800';
        }

        function formatType(type) {
            return type.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
        }

        function getConfidenceColor(confidence) {
            if (confidence >= 0.8) return 'confidence-high';
            if (confidence >= 0.6) return 'confidence-medium';
            return 'confidence-low';
        }

        function showTradeModal(opportunityId) {
            // Implementation for trade modal
            document.getElementById('trade-modal').classList.remove('hidden');
        }

        function showDetails(opportunityId) {
            // Implementation for opportunity details
            const opportunity = opportunitiesData.find(opp => 
                `${opp.market_slug}_${opp.token_id}` === opportunityId
            );
            if (opportunity) {
                alert(`Details for: ${opportunity.market_title}\\n\\nProfit: $${opportunity.expected_profit.toFixed(2)}\\nConfidence: ${(opportunity.confidence * 100).toFixed(1)}%\\nLiquidity: $${opportunity.available_liquidity.toFixed(0)}`);
            }
        }

        // Event listeners
        document.getElementById('min-confidence').addEventListener('input', (e) => {
            document.getElementById('confidence-value').textContent = 
                Math.round(e.target.value * 100) + '%';
            updateOpportunitiesTable();
        });

        document.getElementById('sort-by').addEventListener('change', updateOpportunitiesTable);
        document.getElementById('filter-complement').addEventListener('change', updateOpportunitiesTable);
        document.getElementById('filter-spread').addEventListener('change', updateOpportunitiesTable);
        document.getElementById('filter-mm').addEventListener('change', updateOpportunitiesTable);

        document.getElementById('refresh-btn').addEventListener('click', () => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({type: 'request_update'}));
            }
        });

        document.getElementById('cancel-trade').addEventListener('click', () => {
            document.getElementById('trade-modal').classList.add('hidden');
        });

        // Initialize dashboard
        updateDashboard();
    </script>
</body>
</html>
        """

    async def get_opportunities(self, request: Request) -> Response:
        """Get current trading opportunities as JSON."""
        opportunities = []
        for opp in self.dashboard.opportunities.values():
            opportunities.append(
                {
                    "market_slug": opp.market_slug,
                    "market_title": opp.market_title,
                    "token_id": opp.token_id,
                    "outcome_name": opp.outcome_name,
                    "opportunity_type": opp.opportunity_type,
                    "signal_strength": opp.signal_strength,
                    "bid_price": opp.bid_price,
                    "ask_price": opp.ask_price,
                    "mid_price": opp.mid_price,
                    "spread_bps": opp.spread_bps,
                    "expected_profit": opp.expected_profit,
                    "confidence": opp.confidence,
                    "available_liquidity": opp.available_liquidity,
                    "slippage_1k": opp.slippage_1k,
                    "slippage_5k": opp.slippage_5k,
                    "slippage_10k": opp.slippage_10k,
                    "recommended_size": opp.recommended_size,
                    "discovered_at": opp.discovered_at.isoformat(),
                    "last_updated": opp.last_updated.isoformat(),
                }
            )

        return web.json_response(opportunities)

    async def get_stats(self, request: Request) -> Response:
        """Get dashboard statistics as JSON."""
        stats = {
            "total_opportunities": self.dashboard.stats.total_opportunities,
            "high_confidence_opportunities": self.dashboard.stats.high_confidence_opportunities,
            "total_profit_potential": self.dashboard.stats.total_profit_potential,
            "avg_spread": self.dashboard.stats.avg_spread,
            "markets_scanned": self.dashboard.stats.markets_scanned,
            "uptime": self.dashboard.stats.uptime,
            "last_scan": (
                self.dashboard.stats.last_scan.isoformat()
                if self.dashboard.stats.last_scan
                else None
            ),
        }
        return web.json_response(stats)

    async def get_market_details(self, request: Request) -> Response:
        """Get detailed market information."""
        market_slug = request.match_info["slug"]

        # Find opportunities for this market
        market_opportunities = [
            opp
            for opp in self.dashboard.opportunities.values()
            if opp.market_slug == market_slug
        ]

        if not market_opportunities:
            return web.json_response({"error": "Market not found"}, status=404)

        # Aggregate market data
        market_data = {
            "slug": market_slug,
            "title": market_opportunities[0].market_title,
            "opportunities": len(market_opportunities),
            "total_profit_potential": sum(
                opp.expected_profit for opp in market_opportunities
            ),
            "avg_confidence": sum(opp.confidence for opp in market_opportunities)
            / len(market_opportunities),
            "avg_liquidity": sum(
                opp.available_liquidity for opp in market_opportunities
            )
            / len(market_opportunities),
            "opportunities_detail": [
                {
                    "outcome_name": opp.outcome_name,
                    "opportunity_type": opp.opportunity_type,
                    "expected_profit": opp.expected_profit,
                    "confidence": opp.confidence,
                    "spread_bps": opp.spread_bps,
                    "recommended_size": opp.recommended_size,
                }
                for opp in market_opportunities
            ],
        }

        return web.json_response(market_data)

    async def execute_trade(self, request: Request) -> Response:
        """Execute a trade (placeholder for actual trading integration)."""
        data = await request.json()

        # This would integrate with your actual trading engine
        # For now, return a mock response
        response = {
            "success": False,
            "message": "Trading integration not implemented yet",
            "trade_data": data,
        }

        return web.json_response(response)

    async def get_config(self, request: Request) -> Response:
        """Get current configuration."""
        config_data = {
            "spread_alert_bps": self.config.spread_alert_bps,
            "complement_arb_min_deviation": self.config.complement_arb_min_deviation,
            "mm_enabled": self.config.mm_enabled,
            "market_cache_ttl": self.config.market_cache_ttl,
        }
        return web.json_response(config_data)

    async def update_config(self, request: Request) -> Response:
        """Update configuration."""
        data = await request.json()

        # Update configuration (would need proper validation in production)
        if "spread_alert_bps" in data:
            self.config.spread_alert_bps = data["spread_alert_bps"]

        return web.json_response({"success": True, "message": "Configuration updated"})

    async def websocket_handler(self, request: Request) -> WebSocketResponse:
        """Handle WebSocket connections for real-time updates."""
        ws = WebSocketResponse()
        await ws.prepare(request)

        self.websockets.add(ws)
        logger.info("WebSocket client connected")

        # Send initial data
        await self.send_opportunities_update(ws)
        await self.send_stats_update(ws)

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if data.get("type") == "request_update":
                        await self.send_opportunities_update(ws)
                        await self.send_stats_update(ws)
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")
        except Exception as e:
            logger.error(f"WebSocket handler error: {e}")
        finally:
            self.websockets.discard(ws)
            logger.info("WebSocket client disconnected")

        return ws

    async def send_opportunities_update(
        self, ws: WebSocketResponse | None = None
    ) -> None:
        """Send opportunities update to WebSocket clients."""
        opportunities = []
        for opp in self.dashboard.opportunities.values():
            opportunities.append(
                {
                    "market_slug": opp.market_slug,
                    "market_title": opp.market_title,
                    "token_id": opp.token_id,
                    "outcome_name": opp.outcome_name,
                    "opportunity_type": opp.opportunity_type,
                    "signal_strength": opp.signal_strength,
                    "bid_price": opp.bid_price,
                    "ask_price": opp.ask_price,
                    "spread_bps": opp.spread_bps,
                    "expected_profit": opp.expected_profit,
                    "confidence": opp.confidence,
                    "available_liquidity": opp.available_liquidity,
                    "slippage_1k": opp.slippage_1k,
                    "recommended_size": opp.recommended_size,
                }
            )

        message = {
            "type": "opportunities_update",
            "opportunities": opportunities,
            "timestamp": datetime.now().isoformat(),
        }

        await self.broadcast_message(message, ws)

    async def send_stats_update(self, ws: WebSocketResponse | None = None) -> None:
        """Send stats update to WebSocket clients."""
        message = {
            "type": "stats_update",
            "stats": {
                "total_opportunities": self.dashboard.stats.total_opportunities,
                "high_confidence_opportunities": self.dashboard.stats.high_confidence_opportunities,
                "total_profit_potential": self.dashboard.stats.total_profit_potential,
                "avg_spread": self.dashboard.stats.avg_spread,
            },
            "timestamp": datetime.now().isoformat(),
        }

        await self.broadcast_message(message, ws)

    async def broadcast_message(
        self, message: dict, single_ws: WebSocketResponse | None = None
    ) -> None:
        """Broadcast message to WebSocket clients."""
        message_str = json.dumps(message)

        if single_ws:
            try:
                await single_ws.send_str(message_str)
            except Exception as e:
                logger.error(f"Failed to send message to single WebSocket: {e}")
        else:
            # Broadcast to all connected clients
            disconnected = set()
            for ws in self.websockets:
                try:
                    await ws.send_str(message_str)
                except Exception as e:
                    logger.error(f"Failed to send message to WebSocket: {e}")
                    disconnected.add(ws)

            # Clean up disconnected clients
            self.websockets -= disconnected

    async def start_server(self) -> None:
        """Start the web server and dashboard background tasks."""
        # Start the dashboard background scanner
        dashboard_task = asyncio.create_task(self._run_dashboard_background())

        # Start web server
        runner = web.AppRunner(self.app)
        await runner.setup()

        site = web.TCPSite(runner, "localhost", self.port)
        await site.start()

        logger.info(f"Web dashboard started at http://localhost:{self.port}")
        print(f"\n🌐 Web dashboard available at: http://localhost:{self.port}")
        print("💡 Open in your browser to view real-time trading opportunities")

        try:
            # Keep server running
            await asyncio.Future()  # Run forever
        except KeyboardInterrupt:
            logger.info("Shutting down web server...")
        finally:
            dashboard_task.cancel()
            await runner.cleanup()

    async def _run_dashboard_background(self) -> None:
        """Run dashboard background tasks and send updates to WebSocket clients."""
        # Start the scanner
        scanner_task = asyncio.create_task(self.dashboard._run_scanner())

        try:
            while True:
                # Send periodic updates to connected clients
                if self.websockets:
                    await self.send_opportunities_update()
                    await self.send_stats_update()

                await asyncio.sleep(2)  # Update every 2 seconds
        except asyncio.CancelledError:
            scanner_task.cancel()
            raise


async def run_web_dashboard(
    config: BotConfig | None = None, port: int = 8080
) -> None:
    """Run the web-based trading dashboard.

    Args:
        config: Bot configuration
        port: Web server port
    """
    if config is None:
        config = BotConfig()

    dashboard = WebTradingDashboard(config, port)
    await dashboard.start_server()


if __name__ == "__main__":
    # Allow running web dashboard directly
    asyncio.run(run_web_dashboard())
