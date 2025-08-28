#!/usr/bin/env python3
"""
Comprehensive Load Testing Runner for InkedUp Bot

This script orchestrates all load testing modules to provide complete
performance analysis including:
- 1000+ concurrent market updates
- High-frequency trading simulation
- WebSocket stress testing
- Database performance testing
- Memory and CPU benchmarking
- System integration testing
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any

# Add tests directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "tests"))

# Import all load testing modules
from integration_load_tests import run_integration_load_tests
from load_testing_suite import LoadTestSuite
from performance_benchmarks import run_performance_benchmarks
from websocket_load_tests import run_websocket_load_tests

# Configure comprehensive logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("comprehensive_load_tests.log"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("comprehensive_load_tests")


class ComprehensiveLoadTestRunner:
    """Main orchestrator for all load testing activities."""

    def __init__(self):
        self.results = {}
        self.start_time = None
        self.end_time = None

    async def run_all_tests(self) -> dict[str, Any]:
        """Run complete load testing suite."""
        logger.info("🚀 STARTING COMPREHENSIVE LOAD TESTING SUITE")
        logger.info("=" * 80)
        logger.info("This suite will test:")
        logger.info("  • 1000+ concurrent market updates")
        logger.info("  • High-frequency trading simulation")
        logger.info("  • WebSocket connection stress testing")
        logger.info("  • Database performance under load")
        logger.info("  • Memory usage and leak detection")
        logger.info("  • CPU performance benchmarking")
        logger.info("  • System integration testing")
        logger.info("=" * 80)

        self.start_time = time.time()

        try:
            # Phase 1: Core Load Testing Suite (includes 1000+ market updates)
            logger.info("\n🔥 PHASE 1: CORE LOAD TESTING SUITE")
            logger.info("Testing 1000+ concurrent market updates and HFT scenarios...")

            try:
                core_suite = LoadTestSuite()
                core_results = await core_suite.run_comprehensive_load_tests()
                self.results["core_load_tests"] = core_results
                logger.info("✅ Core load testing completed successfully")
            except Exception as e:
                logger.error(f"❌ Core load testing failed: {e}")
                self.results["core_load_tests"] = {
                    "error": str(e),
                    "phase": "core_load_tests",
                }

            # Small break between phases
            await asyncio.sleep(3)

            # Phase 2: System Integration Load Testing
            logger.info("\n🔧 PHASE 2: SYSTEM INTEGRATION LOAD TESTING")
            logger.info("Testing actual bot components under load...")

            try:
                integration_results = await run_integration_load_tests()
                self.results["integration_tests"] = integration_results
                logger.info("✅ Integration load testing completed successfully")
            except Exception as e:
                logger.error(f"❌ Integration load testing failed: {e}")
                self.results["integration_tests"] = {
                    "error": str(e),
                    "phase": "integration_tests",
                }

            await asyncio.sleep(3)

            # Phase 3: WebSocket Load Testing
            logger.info("\n📡 PHASE 3: WEBSOCKET LOAD TESTING")
            logger.info("Testing WebSocket connections and messaging under load...")

            try:
                websocket_results = await run_websocket_load_tests()
                self.results["websocket_tests"] = websocket_results
                logger.info("✅ WebSocket load testing completed successfully")
            except Exception as e:
                logger.error(f"❌ WebSocket load testing failed: {e}")
                self.results["websocket_tests"] = {
                    "error": str(e),
                    "phase": "websocket_tests",
                }

            await asyncio.sleep(3)

            # Phase 4: Performance Benchmarking
            logger.info("\n🔬 PHASE 4: PERFORMANCE BENCHMARKING")
            logger.info("Running comprehensive performance benchmarks...")

            try:
                benchmark_results = await run_performance_benchmarks()
                self.results["performance_benchmarks"] = benchmark_results
                logger.info("✅ Performance benchmarking completed successfully")
            except Exception as e:
                logger.error(f"❌ Performance benchmarking failed: {e}")
                self.results["performance_benchmarks"] = {
                    "error": str(e),
                    "phase": "performance_benchmarks",
                }

        except KeyboardInterrupt:
            logger.warning("🛑 Load testing interrupted by user")
            self.results["interruption"] = {
                "interrupted_at": time.time(),
                "message": "Testing suite interrupted by user",
            }
        except Exception as e:
            logger.error(f"💥 Critical error in load testing suite: {e}")
            self.results["critical_error"] = {"error": str(e), "timestamp": time.time()}

        self.end_time = time.time()

        # Compile final results
        final_results = await self._compile_final_results()

        return final_results

    async def _compile_final_results(self) -> dict[str, Any]:
        """Compile comprehensive results from all test phases."""
        total_duration = (
            self.end_time - self.start_time if self.start_time and self.end_time else 0
        )

        # Count successful and failed test phases
        successful_phases = len(
            [
                r
                for r in self.results.values()
                if not isinstance(r, dict) or "error" not in r
            ]
        )
        failed_phases = len(
            [r for r in self.results.values() if isinstance(r, dict) and "error" in r]
        )

        # Extract key performance metrics
        performance_summary = await self._extract_performance_summary()

        # Generate recommendations
        recommendations = await self._generate_comprehensive_recommendations()

        final_results = {
            "test_suite_info": {
                "name": "InkedUp Bot Comprehensive Load Testing Suite",
                "version": "1.0",
                "timestamp": datetime.now().isoformat(),
                "duration_seconds": total_duration,
                "start_time": (
                    datetime.fromtimestamp(self.start_time).isoformat()
                    if self.start_time
                    else None
                ),
                "end_time": (
                    datetime.fromtimestamp(self.end_time).isoformat()
                    if self.end_time
                    else None
                ),
            },
            "test_phases": {
                "total_phases": len(self.results),
                "successful_phases": successful_phases,
                "failed_phases": failed_phases,
                "success_rate_percent": (
                    (successful_phases / len(self.results) * 100) if self.results else 0
                ),
            },
            "performance_summary": performance_summary,
            "detailed_results": self.results,
            "recommendations": recommendations,
            "test_environment": {
                "python_version": sys.version,
                "platform": sys.platform,
                "test_timestamp": datetime.now().isoformat(),
            },
        }

        return final_results

    async def _extract_performance_summary(self) -> dict[str, Any]:
        """Extract key performance metrics across all test phases."""
        summary = {
            "market_data_performance": {},
            "trading_performance": {},
            "websocket_performance": {},
            "database_performance": {},
            "memory_performance": {},
            "cpu_performance": {},
            "overall_assessment": "unknown",
        }

        try:
            # Extract core load test metrics (includes 1000+ market updates)
            core_results = self.results.get("core_load_tests", {})
            if (
                "market_data_load" in core_results
                and "error" not in core_results["market_data_load"]
            ):
                market_data = core_results["market_data_load"]

                if "performance" in market_data:
                    summary["market_data_performance"] = {
                        "concurrent_updates_tested": 1000,  # As per test specification
                        "success_rate_percent": market_data["performance"].get(
                            "success_rate", 0
                        ),
                        "avg_response_time_ms": market_data["performance"].get(
                            "avg_response_time_ms", 0
                        ),
                        "p95_response_time_ms": market_data["performance"].get(
                            "p95_response_time_ms", 0
                        ),
                        "throughput_updates_per_second": market_data.get(
                            "throughput", {}
                        ).get("avg_throughput_rps", 0),
                        "peak_throughput_updates_per_second": market_data.get(
                            "throughput", {}
                        ).get("peak_throughput_rps", 0),
                        "markets_processed": market_data.get(
                            "application_metrics", {}
                        ).get("market_updates_processed", 0),
                        "assessment": self._assess_market_data_performance(market_data),
                    }

            # Extract HFT simulation metrics
            if (
                "hft_simulation" in core_results
                and "error" not in core_results["hft_simulation"]
            ):
                hft_data = core_results["hft_simulation"]

                if "performance" in hft_data:
                    summary["trading_performance"] = {
                        "concurrent_traders_tested": 100,  # As per test specification
                        "success_rate_percent": hft_data["performance"].get(
                            "success_rate", 0
                        ),
                        "avg_order_processing_ms": hft_data["performance"].get(
                            "avg_response_time_ms", 0
                        ),
                        "orders_executed": hft_data.get("application_metrics", {}).get(
                            "orders_executed", 0
                        ),
                        "assessment": self._assess_trading_performance(hft_data),
                    }

            # Extract WebSocket performance
            websocket_results = self.results.get("websocket_tests", {})
            if websocket_results and "error" not in websocket_results:
                # Aggregate WebSocket metrics from multiple tests
                ws_summary = self._aggregate_websocket_metrics(websocket_results)
                summary["websocket_performance"] = ws_summary

            # Extract database performance
            integration_results = self.results.get("integration_tests", {})
            if integration_results and "error" not in integration_results:
                db_perf = integration_results.get("database_concurrent_load", {})
                if db_perf and "error" not in db_perf:
                    summary["database_performance"] = {
                        "concurrent_clients_tested": 50,  # As per test specification
                        "operations_per_second": db_perf.get(
                            "operations_per_second", 0
                        ),
                        "avg_query_time_ms": db_perf.get("avg_query_time_ms", 0),
                        "p95_query_time_ms": db_perf.get("p95_query_time_ms", 0),
                        "error_rate_percent": db_perf.get("error_rate", 0),
                        "assessment": self._assess_database_performance(db_perf),
                    }

            # Extract memory and CPU performance from benchmarks
            benchmark_results = self.results.get("performance_benchmarks", {})
            if benchmark_results and "error" not in benchmark_results:
                overall_perf = benchmark_results.get("overall_performance", {})

                memory_summary = overall_perf.get("memory_summary", {})
                if memory_summary:
                    summary["memory_performance"] = {
                        "peak_usage_mb": memory_summary.get("peak_usage_mb", 0),
                        "avg_peak_mb": memory_summary.get("avg_peak_mb", 0),
                        "assessment": self._assess_memory_performance(memory_summary),
                    }

                cpu_summary = overall_perf.get("cpu_summary", {})
                if cpu_summary:
                    summary["cpu_performance"] = {
                        "avg_utilization_percent": cpu_summary.get(
                            "avg_utilization_percent", 0
                        ),
                        "peak_utilization_percent": cpu_summary.get(
                            "peak_utilization_percent", 0
                        ),
                        "assessment": self._assess_cpu_performance(cpu_summary),
                    }

            # Overall assessment
            summary["overall_assessment"] = self._calculate_overall_assessment(summary)

        except Exception as e:
            logger.error(f"Error extracting performance summary: {e}")
            summary["extraction_error"] = str(e)

        return summary

    def _assess_market_data_performance(self, data: dict[str, Any]) -> str:
        """Assess market data processing performance."""
        success_rate = data.get("performance", {}).get("success_rate", 0)
        avg_response = data.get("performance", {}).get("avg_response_time_ms", 0)

        if success_rate >= 99 and avg_response <= 5:
            return "excellent"
        elif success_rate >= 95 and avg_response <= 10:
            return "good"
        elif success_rate >= 90 and avg_response <= 20:
            return "fair"
        else:
            return "poor"

    def _assess_trading_performance(self, data: dict[str, Any]) -> str:
        """Assess trading system performance."""
        success_rate = data.get("performance", {}).get("success_rate", 0)
        avg_response = data.get("performance", {}).get("avg_response_time_ms", 0)

        if success_rate >= 98 and avg_response <= 10:
            return "excellent"
        elif success_rate >= 95 and avg_response <= 25:
            return "good"
        elif success_rate >= 90 and avg_response <= 50:
            return "fair"
        else:
            return "poor"

    def _assess_database_performance(self, data: dict[str, Any]) -> str:
        """Assess database performance."""
        error_rate = data.get("error_rate", 0)
        avg_query_time = data.get("avg_query_time_ms", 0)

        if error_rate <= 1 and avg_query_time <= 10:
            return "excellent"
        elif error_rate <= 3 and avg_query_time <= 25:
            return "good"
        elif error_rate <= 5 and avg_query_time <= 50:
            return "fair"
        else:
            return "poor"

    def _assess_memory_performance(self, data: dict[str, Any]) -> str:
        """Assess memory usage performance."""
        peak_usage = data.get("peak_usage_mb", 0)

        if peak_usage <= 500:
            return "excellent"
        elif peak_usage <= 1000:
            return "good"
        elif peak_usage <= 2000:
            return "fair"
        else:
            return "poor"

    def _assess_cpu_performance(self, data: dict[str, Any]) -> str:
        """Assess CPU utilization performance."""
        avg_cpu = data.get("avg_utilization_percent", 0)

        if avg_cpu <= 50:
            return "excellent"
        elif avg_cpu <= 70:
            return "good"
        elif avg_cpu <= 85:
            return "fair"
        else:
            return "poor"

    def _aggregate_websocket_metrics(
        self, websocket_results: dict[str, Any]
    ) -> dict[str, Any]:
        """Aggregate WebSocket test metrics."""
        summary = {
            "connection_scalability": "unknown",
            "message_throughput": "unknown",
            "connection_resilience": "unknown",
            "overall_assessment": "unknown",
        }

        try:
            # Connection scalability metrics
            if "connection_scalability" in websocket_results:
                conn_data = websocket_results["connection_scalability"]
                if "error" not in conn_data:
                    success_rate = conn_data.get("connections", {}).get(
                        "successful_connections", 0
                    )
                    total_attempted = conn_data.get("test_parameters", {}).get(
                        "max_connections", 1
                    )
                    conn_success_rate = (
                        (success_rate / total_attempted * 100)
                        if total_attempted > 0
                        else 0
                    )

                    summary["connection_scalability"] = {
                        "connections_tested": total_attempted,
                        "success_rate_percent": conn_success_rate,
                        "avg_connection_time_ms": conn_data.get("connections", {}).get(
                            "avg_connection_time_ms", 0
                        ),
                        "assessment": (
                            "excellent"
                            if conn_success_rate >= 95
                            else (
                                "good"
                                if conn_success_rate >= 85
                                else "fair" if conn_success_rate >= 70 else "poor"
                            )
                        ),
                    }

            # Message throughput metrics
            if "message_throughput" in websocket_results:
                msg_data = websocket_results["message_throughput"]
                if "error" not in msg_data:
                    avg_latency = msg_data.get("messaging", {}).get("avg_latency_ms", 0)
                    throughput = msg_data.get("throughput", {}).get(
                        "avg_messages_per_second", 0
                    )

                    summary["message_throughput"] = {
                        "avg_latency_ms": avg_latency,
                        "avg_throughput_msg_per_sec": throughput,
                        "assessment": (
                            "excellent"
                            if avg_latency <= 10 and throughput >= 100
                            else (
                                "good"
                                if avg_latency <= 25 and throughput >= 50
                                else "fair" if avg_latency <= 50 else "poor"
                            )
                        ),
                    }

            # Overall WebSocket assessment
            assessments = [
                summary[key].get("assessment", "unknown")
                for key in ["connection_scalability", "message_throughput"]
                if isinstance(summary[key], dict)
            ]
            if assessments:
                assessment_scores = {
                    "excellent": 4,
                    "good": 3,
                    "fair": 2,
                    "poor": 1,
                    "unknown": 0,
                }
                avg_score = sum(assessment_scores.get(a, 0) for a in assessments) / len(
                    assessments
                )

                if avg_score >= 3.5:
                    summary["overall_assessment"] = "excellent"
                elif avg_score >= 2.5:
                    summary["overall_assessment"] = "good"
                elif avg_score >= 1.5:
                    summary["overall_assessment"] = "fair"
                else:
                    summary["overall_assessment"] = "poor"

        except Exception as e:
            logger.error(f"Error aggregating WebSocket metrics: {e}")
            summary["aggregation_error"] = str(e)

        return summary

    def _calculate_overall_assessment(self, summary: dict[str, Any]) -> str:
        """Calculate overall system performance assessment."""
        assessments = []

        # Collect all individual assessments
        for category, data in summary.items():
            if isinstance(data, dict) and "assessment" in data:
                assessments.append(data["assessment"])

        if not assessments:
            return "unknown"

        # Calculate weighted average (market data and trading are most important)
        assessment_weights = {
            "market_data_performance": 3,
            "trading_performance": 3,
            "websocket_performance": 2,
            "database_performance": 2,
            "memory_performance": 1,
            "cpu_performance": 1,
        }

        assessment_scores = {"excellent": 4, "good": 3, "fair": 2, "poor": 1}

        total_score = 0
        total_weight = 0

        for category, data in summary.items():
            if isinstance(data, dict) and "assessment" in data:
                weight = assessment_weights.get(category, 1)
                score = assessment_scores.get(data["assessment"], 0)
                total_score += score * weight
                total_weight += weight

        if total_weight == 0:
            return "unknown"

        avg_score = total_score / total_weight

        if avg_score >= 3.5:
            return "excellent"
        elif avg_score >= 2.5:
            return "good"
        elif avg_score >= 1.5:
            return "fair"
        else:
            return "poor"

    async def _generate_comprehensive_recommendations(self) -> list[str]:
        """Generate comprehensive recommendations based on all test results."""
        recommendations = []

        try:
            # Market data recommendations
            core_results = self.results.get("core_load_tests", {})
            if (
                "market_data_load" in core_results
                and "error" not in core_results["market_data_load"]
            ):
                market_perf = core_results["market_data_load"].get("performance", {})
                if market_perf.get("success_rate", 0) < 95:
                    recommendations.append(
                        "⚠️  Market data processing success rate below 95% - investigate error handling and retry mechanisms"
                    )

                if market_perf.get("avg_response_time_ms", 0) > 10:
                    recommendations.append(
                        "🔧 Market data processing response times could be optimized - consider implementing data streaming or caching"
                    )

            # Trading system recommendations
            if (
                "hft_simulation" in core_results
                and "error" not in core_results["hft_simulation"]
            ):
                trading_perf = core_results["hft_simulation"].get("performance", {})
                if trading_perf.get("success_rate", 0) < 98:
                    recommendations.append(
                        "💰 Trading system reliability needs improvement - implement circuit breakers and fallback mechanisms"
                    )

            # WebSocket recommendations
            websocket_results = self.results.get("websocket_tests", {})
            if websocket_results and "error" not in websocket_results:
                if "connection_scalability" in websocket_results:
                    conn_data = websocket_results["connection_scalability"]
                    success_rate = conn_data.get("connections", {}).get(
                        "successful_connections", 0
                    )
                    attempted = conn_data.get("test_parameters", {}).get(
                        "max_connections", 1
                    )
                    if (success_rate / attempted * 100) < 90:
                        recommendations.append(
                            "📡 WebSocket connection scalability needs improvement - consider connection pooling and load balancing"
                        )

            # Database recommendations
            integration_results = self.results.get("integration_tests", {})
            if (
                integration_results
                and "database_concurrent_load" in integration_results
            ):
                db_perf = integration_results["database_concurrent_load"]
                if "error" not in db_perf:
                    if db_perf.get("error_rate", 0) > 3:
                        recommendations.append(
                            "💾 Database error rate is high - consider implementing connection pooling and query optimization"
                        )

                    if db_perf.get("avg_query_time_ms", 0) > 25:
                        recommendations.append(
                            "🗄️  Database query performance needs optimization - add indexes and consider read replicas"
                        )

            # Memory recommendations
            benchmark_results = self.results.get("performance_benchmarks", {})
            if benchmark_results and "error" not in benchmark_results:
                overall_perf = benchmark_results.get("overall_performance", {})
                memory_summary = overall_perf.get("memory_summary", {})

                if memory_summary.get("peak_usage_mb", 0) > 1000:
                    recommendations.append(
                        "🧠 High memory usage detected - implement memory management strategies and object pooling"
                    )

                # Check for memory leak recommendations from benchmark results
                if benchmark_results.get("recommendations"):
                    for rec in benchmark_results["recommendations"]:
                        if "memory" in rec.lower() or "leak" in rec.lower():
                            recommendations.append(f"💧 {rec}")

            # General recommendations based on test failures
            failed_phases = [
                k
                for k, v in self.results.items()
                if isinstance(v, dict) and "error" in v
            ]
            if failed_phases:
                recommendations.append(
                    f"🔧 {len(failed_phases)} test phase(s) failed: {', '.join(failed_phases)} - investigate and resolve critical issues"
                )

            # Performance-based scaling recommendations
            performance_summary = await self._extract_performance_summary()
            overall_assessment = performance_summary.get(
                "overall_assessment", "unknown"
            )

            if overall_assessment == "excellent":
                recommendations.append(
                    "🎉 System performance is excellent - ready for production high-frequency trading"
                )
            elif overall_assessment == "good":
                recommendations.append(
                    "✅ System performance is good - minor optimizations recommended before production"
                )
            elif overall_assessment == "fair":
                recommendations.append(
                    "⚠️  System performance is fair - significant optimizations needed before high-load production use"
                )
            elif overall_assessment == "poor":
                recommendations.append(
                    "❌ System performance is poor - major architectural changes required before production deployment"
                )

            if not recommendations:
                recommendations.append(
                    "🎯 No critical issues detected - system appears ready for load testing validation"
                )

        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            recommendations.append(f"⚠️  Error generating recommendations: {e}")

        return recommendations

    def save_results(self, results: dict[str, Any], filename: str = None) -> str:
        """Save comprehensive results to file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"comprehensive_load_test_results_{timestamp}.json"

        try:
            with open(filename, "w") as f:
                json.dump(results, f, indent=2, default=str)

            logger.info(f"📁 Comprehensive results saved to: {filename}")
            return filename

        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            return None

    def generate_summary_report(self, results: dict[str, Any]) -> str:
        """Generate human-readable comprehensive test report."""
        if not results:
            return "No test results available."

        report = []
        report.append("🔬 INKEDUP BOT COMPREHENSIVE LOAD TESTING REPORT")
        report.append("=" * 80)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        # Suite information
        suite_info = results.get("test_suite_info", {})
        if suite_info:
            report.append("📋 TEST SUITE OVERVIEW")
            report.append("-" * 40)
            report.append(
                f"Duration: {suite_info.get('duration_seconds', 0):.2f} seconds"
            )
            report.append(f"Start Time: {suite_info.get('start_time', 'Unknown')}")
            report.append(f"End Time: {suite_info.get('end_time', 'Unknown')}")
            report.append("")

        # Test phases summary
        phases = results.get("test_phases", {})
        if phases:
            report.append("🎯 TEST PHASES SUMMARY")
            report.append("-" * 40)
            report.append(f"Total Phases: {phases.get('total_phases', 0)}")
            report.append(f"Successful: {phases.get('successful_phases', 0)}")
            report.append(f"Failed: {phases.get('failed_phases', 0)}")
            report.append(f"Success Rate: {phases.get('success_rate_percent', 0):.1f}%")
            report.append("")

        # Performance summary
        perf_summary = results.get("performance_summary", {})
        if perf_summary:
            report.append("⚡ PERFORMANCE SUMMARY")
            report.append("-" * 40)

            # Market data performance (1000+ concurrent updates)
            market_perf = perf_summary.get("market_data_performance", {})
            if market_perf:
                report.append(
                    f"🔥 MARKET DATA (1000+ Concurrent Updates): {market_perf.get('assessment', 'Unknown').upper()}"
                )
                report.append(
                    f"   Success Rate: {market_perf.get('success_rate_percent', 0):.1f}%"
                )
                report.append(
                    f"   Avg Response: {market_perf.get('avg_response_time_ms', 0):.2f}ms"
                )
                report.append(
                    f"   Peak Throughput: {market_perf.get('peak_throughput_updates_per_second', 0):.1f} updates/s"
                )
                report.append(
                    f"   Markets Processed: {market_perf.get('markets_processed', 0):,}"
                )
                report.append("")

            # Trading performance
            trading_perf = perf_summary.get("trading_performance", {})
            if trading_perf:
                report.append(
                    f"💰 HIGH-FREQUENCY TRADING: {trading_perf.get('assessment', 'Unknown').upper()}"
                )
                report.append(
                    f"   Success Rate: {trading_perf.get('success_rate_percent', 0):.1f}%"
                )
                report.append(
                    f"   Avg Processing: {trading_perf.get('avg_order_processing_ms', 0):.2f}ms"
                )
                report.append(
                    f"   Orders Executed: {trading_perf.get('orders_executed', 0):,}"
                )
                report.append("")

            # WebSocket performance
            ws_perf = perf_summary.get("websocket_performance", {})
            if ws_perf and isinstance(ws_perf, dict):
                report.append(
                    f"📡 WEBSOCKET PERFORMANCE: {ws_perf.get('overall_assessment', 'Unknown').upper()}"
                )

                conn_scale = ws_perf.get("connection_scalability", {})
                if isinstance(conn_scale, dict):
                    report.append(
                        f"   Connection Success: {conn_scale.get('success_rate_percent', 0):.1f}%"
                    )
                    report.append(
                        f"   Avg Connection Time: {conn_scale.get('avg_connection_time_ms', 0):.2f}ms"
                    )

                msg_throughput = ws_perf.get("message_throughput", {})
                if isinstance(msg_throughput, dict):
                    report.append(
                        f"   Message Latency: {msg_throughput.get('avg_latency_ms', 0):.2f}ms"
                    )
                    report.append(
                        f"   Message Throughput: {msg_throughput.get('avg_throughput_msg_per_sec', 0):.1f} msg/s"
                    )
                report.append("")

            # Database performance
            db_perf = perf_summary.get("database_performance", {})
            if db_perf:
                report.append(
                    f"💾 DATABASE PERFORMANCE: {db_perf.get('assessment', 'Unknown').upper()}"
                )
                report.append(
                    f"   Operations/Second: {db_perf.get('operations_per_second', 0):.1f}"
                )
                report.append(
                    f"   Avg Query Time: {db_perf.get('avg_query_time_ms', 0):.2f}ms"
                )
                report.append(
                    f"   Error Rate: {db_perf.get('error_rate_percent', 0):.1f}%"
                )
                report.append("")

            # Memory and CPU performance
            memory_perf = perf_summary.get("memory_performance", {})
            cpu_perf = perf_summary.get("cpu_performance", {})

            if memory_perf or cpu_perf:
                report.append("🖥️  SYSTEM RESOURCES:")
                if memory_perf:
                    report.append(
                        f"   Memory Usage: {memory_perf.get('assessment', 'Unknown').upper()}"
                    )
                    report.append(
                        f"   Peak Memory: {memory_perf.get('peak_usage_mb', 0):.1f}MB"
                    )
                if cpu_perf:
                    report.append(
                        f"   CPU Usage: {cpu_perf.get('assessment', 'Unknown').upper()}"
                    )
                    report.append(
                        f"   Avg CPU: {cpu_perf.get('avg_utilization_percent', 0):.1f}%"
                    )
                report.append("")

            # Overall assessment
            overall = perf_summary.get("overall_assessment", "unknown")
            report.append(f"🎯 OVERALL ASSESSMENT: {overall.upper()}")
            report.append("")

        # Recommendations
        recommendations = results.get("recommendations", [])
        if recommendations:
            report.append("💡 RECOMMENDATIONS")
            report.append("-" * 40)
            for i, rec in enumerate(recommendations, 1):
                report.append(f"{i:2}. {rec}")
            report.append("")

        # Test environment
        env = results.get("test_environment", {})
        if env:
            report.append("🔧 TEST ENVIRONMENT")
            report.append("-" * 40)
            report.append(f"Python: {env.get('python_version', 'Unknown')}")
            report.append(f"Platform: {env.get('platform', 'Unknown')}")
            report.append("")

        report.append("=" * 80)

        return "\n".join(report)


async def main():
    """Main execution function."""
    print("🚀 InkedUp Bot Comprehensive Load Testing Suite")
    print("This will test the system's ability to handle:")
    print("  • 1000+ concurrent market updates")
    print("  • High-frequency trading conditions")
    print("  • WebSocket connection stress")
    print("  • Database performance under load")
    print("  • Memory usage and leak detection")
    print("  • CPU performance benchmarks")
    print("")

    runner = ComprehensiveLoadTestRunner()

    try:
        # Run comprehensive testing suite
        results = await runner.run_all_tests()

        # Generate and display summary report
        report = runner.generate_summary_report(results)
        print("\n" + report)

        # Save detailed results
        results_file = runner.save_results(results)
        if results_file:
            print(f"\n📁 Detailed results saved to: {results_file}")

        # Determine exit code based on overall assessment
        overall_assessment = results.get("performance_summary", {}).get(
            "overall_assessment", "unknown"
        )
        if overall_assessment in ["excellent", "good"]:
            print(
                "\n✅ Load testing completed successfully - system performance is acceptable!"
            )
            return 0
        elif overall_assessment == "fair":
            print("\n⚠️  Load testing completed - system performance needs improvement")
            return 1
        else:
            print(
                "\n❌ Load testing completed - system performance requires significant improvement"
            )
            return 2

    except KeyboardInterrupt:
        print("\n🛑 Load testing interrupted by user")
        return 130
    except Exception as e:
        print(f"\n💥 Load testing failed with error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    # Run comprehensive load testing
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
