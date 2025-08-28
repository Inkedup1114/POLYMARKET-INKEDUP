#!/usr/bin/env python3
"""
Standalone Health Check HTTP Server for InkedUp Trading Bot.

This script provides a simple HTTP server with health check endpoints
that can be used by monitoring systems, load balancers, and Kubernetes
health probes without requiring the full trading bot to be running.

Usage:
    python scripts/health_server.py [options]

Options:
    --host HOST         Server host (default: 0.0.0.0)
    --port PORT         Server port (default: 8080)
    --config PATH       Path to bot configuration file
    --verbose           Enable verbose logging

Endpoints:
    GET /health         Basic health check
    GET /health/live    Liveness probe (always returns 200)
    GET /health/ready   Readiness probe (checks critical components)
    GET /status         Detailed system status
    GET /metrics        Prometheus metrics
    GET /info           System information
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from aiohttp import web
from aiohttp.web import Request, Response

from inkedup_bot.config import BotConfig
from inkedup_bot.database import DatabaseManager
from inkedup_bot.health_service import setup_health_service
from inkedup_bot.order_client import OrderClient

log = logging.getLogger("health_server")


class StandaloneHealthServer:
    """Standalone HTTP server for health checks."""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8080, config: BotConfig = None):
        self.host = host
        self.port = port
        self.config = config or BotConfig()
        self.app = None
        self.runner = None
        self.site = None
        self.start_time = time.time()
        self.health_service = None
        
    async def setup_health_service(self):
        """Setup health service with available components."""
        components = {}
        
        # Try to initialize database
        try:
            db_path = self.config.database_url.replace("sqlite:///", "") if self.config.database_url else "bot_data.db"
            db = DatabaseManager(db_path)
            await db.initialize()
            components['database_manager'] = db
            log.info("Database component initialized for health checks")
        except Exception as e:
            log.warning(f"Could not initialize database for health checks: {e}")
        
        # Try to initialize order client (without making actual API calls)
        try:
            order_client = OrderClient(self.config)
            components['order_client'] = order_client  
            log.info("Order client component initialized for health checks")
        except Exception as e:
            log.warning(f"Could not initialize order client for health checks: {e}")
        
        # Setup health service
        self.health_service = setup_health_service(self.config, **components)
        log.info(f"Health service setup with {len(components)} components")
        
    async def start(self):
        """Start the health check server."""
        log.info(f"Starting health check server on http://{self.host}:{self.port}")
        
        # Setup health service
        await self.setup_health_service()
        
        # Create web application
        self.app = web.Application()
        
        # Setup routes
        self._setup_routes()
        self._setup_cors()
        
        # Start server
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        
        log.info(f"Health check server running on http://{self.host}:{self.port}")
        
    async def stop(self):
        """Stop the health check server."""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        log.info("Health check server stopped")
        
    def _setup_routes(self):
        """Setup HTTP routes."""
        self.app.router.add_get("/", self._root_handler)
        self.app.router.add_get("/health", self._health_handler)
        self.app.router.add_get("/health/live", self._liveness_handler)
        self.app.router.add_get("/health/ready", self._readiness_handler)
        self.app.router.add_get("/status", self._status_handler)
        self.app.router.add_get("/metrics", self._metrics_handler)
        self.app.router.add_get("/info", self._info_handler)
        
    def _setup_cors(self):
        """Setup CORS for API access."""
        async def cors_middleware(request: Request, handler):
            response = await handler(request)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return response
        
        self.app.middlewares.append(cors_middleware)
        
    async def _health_handler(self, request: Request) -> Response:
        """Basic health check endpoint."""
        try:
            if not self.health_service:
                return web.json_response(
                    {"status": "unhealthy", "message": "Health service not initialized"},
                    status=503
                )
            
            is_healthy = await self.health_service.is_healthy()
            
            if is_healthy:
                return web.json_response(
                    {
                        "status": "healthy",
                        "timestamp": datetime.utcnow().isoformat(),
                        "uptime_seconds": time.time() - self.start_time,
                    },
                    status=200
                )
            else:
                health_status = await self.health_service.get_system_health_status(include_details=False)
                return web.json_response(
                    {
                        "status": health_status.get("overall_status", "unknown"),
                        "timestamp": datetime.utcnow().isoformat(),
                        "component_status": health_status.get("component_status", {}),
                    },
                    status=503
                )
                
        except Exception as e:
            log.error(f"Health check error: {e}")
            return web.json_response(
                {
                    "status": "error",
                    "message": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                },
                status=500
            )
            
    async def _liveness_handler(self, request: Request) -> Response:
        """Kubernetes liveness probe."""
        return web.json_response(
            {
                "alive": True,
                "timestamp": datetime.utcnow().isoformat(),
                "uptime_seconds": time.time() - self.start_time,
            },
            status=200
        )
        
    async def _readiness_handler(self, request: Request) -> Response:
        """Kubernetes readiness probe."""
        try:
            if not self.health_service:
                return web.json_response(
                    {"ready": False, "message": "Health service not initialized"},
                    status=503
                )
            
            ready_status = await self.health_service.get_readiness_status()
            
            if ready_status.get("ready", False):
                return web.json_response(ready_status, status=200)
            else:
                return web.json_response(ready_status, status=503)
                
        except Exception as e:
            log.error(f"Readiness check error: {e}")
            return web.json_response(
                {
                    "ready": False,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                },
                status=503
            )
            
    async def _status_handler(self, request: Request) -> Response:
        """Detailed system status."""
        try:
            if not self.health_service:
                return web.json_response(
                    {"error": "Health service not initialized"},
                    status=503
                )
            
            status = await self.health_service.get_system_health_status(include_details=True)
            return web.json_response(status, status=200)
            
        except Exception as e:
            log.error(f"Status check error: {e}")
            return web.json_response(
                {"error": str(e), "timestamp": datetime.utcnow().isoformat()},
                status=500
            )
            
    async def _metrics_handler(self, request: Request) -> Response:
        """Prometheus metrics endpoint."""
        try:
            if not self.health_service:
                return web.Response(
                    text="# Health service not initialized\n",
                    content_type="text/plain",
                    status=503
                )
            
            status = await self.health_service.get_system_health_status(include_details=False)
            
            # Generate basic Prometheus metrics
            timestamp_ms = int(time.time() * 1000)
            
            metrics_lines = [
                "# HELP inkedup_health_status Overall health status (1=healthy, 0=unhealthy)",
                "# TYPE inkedup_health_status gauge",
                f"inkedup_health_status {1 if status.get('overall_status') == 'healthy' else 0} {timestamp_ms}",
                "",
                "# HELP inkedup_uptime_seconds Server uptime in seconds",
                "# TYPE inkedup_uptime_seconds counter", 
                f"inkedup_uptime_seconds {status.get('uptime_seconds', 0)} {timestamp_ms}",
                "",
                "# HELP inkedup_components_total Total number of monitored components",
                "# TYPE inkedup_components_total gauge",
                f"inkedup_components_total {status.get('summary', {}).get('total_components', 0)} {timestamp_ms}",
                "",
                "# HELP inkedup_components_healthy Number of healthy components",
                "# TYPE inkedup_components_healthy gauge", 
                f"inkedup_components_healthy {status.get('summary', {}).get('healthy_components', 0)} {timestamp_ms}",
                "",
                "# HELP inkedup_components_unhealthy Number of unhealthy components",
                "# TYPE inkedup_components_unhealthy gauge",
                f"inkedup_components_unhealthy {status.get('summary', {}).get('unhealthy_components', 0)} {timestamp_ms}",
            ]
            
            return web.Response(
                text="\n".join(metrics_lines),
                content_type="text/plain; version=0.0.4; charset=utf-8",
                status=200
            )
            
        except Exception as e:
            log.error(f"Metrics error: {e}")
            return web.Response(
                text=f"# Error generating metrics: {e}\n",
                content_type="text/plain",
                status=500
            )
            
    async def _info_handler(self, request: Request) -> Response:
        """System information endpoint."""
        try:
            import platform

            import psutil
            
            info = {
                "application": {
                    "name": "InkedUp Polymarket Trading Bot",
                    "version": "1.0.0",
                    "uptime_seconds": time.time() - self.start_time,
                    "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
                },
                "system": {
                    "platform": platform.platform(),
                    "python_version": platform.python_version(),
                    "cpu_count": psutil.cpu_count(),
                    "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                },
                "health_service": {
                    "initialized": self.health_service is not None,
                    "components_monitored": len(self.health_service.system_health.components) if self.health_service else 0,
                },
                "timestamp": datetime.utcnow().isoformat(),
            }
            
            return web.json_response(info, status=200)
            
        except Exception as e:
            log.error(f"Info endpoint error: {e}")
            return web.json_response({"error": str(e)}, status=500)
            
    async def _root_handler(self, request: Request) -> Response:
        """Root endpoint with API documentation."""
        api_docs = {
            "service": "InkedUp Trading Bot - Health Check Server",
            "version": "1.0.0",
            "uptime_seconds": time.time() - self.start_time,
            "endpoints": {
                "/health": "Basic health check (200=healthy, 503=unhealthy)",
                "/health/live": "Liveness probe (always 200)",
                "/health/ready": "Readiness probe (200=ready, 503=not ready)",
                "/status": "Detailed system status with component information",
                "/metrics": "Prometheus-compatible metrics",
                "/info": "System and application information",
            },
            "usage": {
                "kubernetes_liveness": "livenessProbe: httpGet: path: /health/live, port: 8080",
                "kubernetes_readiness": "readinessProbe: httpGet: path: /health/ready, port: 8080",
                "monitoring": "Monitor /health endpoint for overall system status",
                "prometheus": "Scrape /metrics endpoint for monitoring metrics",
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        return web.json_response(api_docs, status=200)


async def main():
    """Main health server function."""
    parser = argparse.ArgumentParser(description="InkedUp Trading Bot Health Check Server")
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument("--config", help="Path to configuration file")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Load configuration
    config = None
    if args.config:
        config_path = Path(args.config)
        if config_path.exists():
            # Load configuration from file (simplified)
            config = BotConfig()
            log.info(f"Using configuration from {config_path}")
        else:
            log.warning(f"Configuration file not found: {config_path}")
    
    if not config:
        config = BotConfig()
        log.info("Using default configuration")
    
    # Create and start server
    server = StandaloneHealthServer(args.host, args.port, config)
    
    try:
        await server.start()
        
        print(f"🏥 Health Check Server Started")
        print(f"   Host: {args.host}")
        print(f"   Port: {args.port}")
        print(f"   Health: http://{args.host}:{args.port}/health")
        print(f"   Status: http://{args.host}:{args.port}/status")
        print(f"   Metrics: http://{args.host}:{args.port}/metrics")
        print(f"   API Docs: http://{args.host}:{args.port}/")
        print(f"")
        print("Press Ctrl+C to stop")
        
        # Keep server running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            log.info("Shutdown signal received")
            
    except Exception as e:
        log.error(f"Failed to start health server: {e}")
        return 1
    finally:
        await server.stop()
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)