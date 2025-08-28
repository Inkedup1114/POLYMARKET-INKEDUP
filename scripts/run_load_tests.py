#!/usr/bin/env python3
"""
Load Testing Runner for InkedUp Polymarket Trading Bot.

This script runs comprehensive load tests to validate system performance
under high-frequency trading conditions and extreme load scenarios.

Usage:
    python scripts/run_load_tests.py [options]

Options:
    --quick     Run quick load tests (reduced scale for CI)
    --full      Run full-scale load tests (production scale)
    --stress    Run stress tests only
    --performance Run performance benchmarks only
    --report    Generate detailed performance report
    --verbose   Enable verbose output
"""

import argparse
import asyncio
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class LoadTestRunner:
    """Comprehensive load testing runner."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: List[Dict] = []
        self.setup_logging()
    
    def setup_logging(self):
        """Setup logging configuration."""
        level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger("load_test_runner")
    
    async def run_quick_tests(self) -> Dict:
        """Run quick load tests suitable for CI/CD."""
        self.logger.info("🚀 Running Quick Load Tests")
        
        quick_tests = [
            "tests/test_comprehensive_load_testing.py::TestHighFrequencyLoadScenarios::test_market_data_burst_load",
            "tests/test_comprehensive_load_testing.py::TestHighFrequencyLoadScenarios::test_high_frequency_signal_processing"
        ]
        
        results = {}
        for test in quick_tests:
            test_name = test.split("::")[-1]
            self.logger.info(f"Running {test_name}...")
            
            start_time = time.time()
            result = await self.run_pytest_test(test)
            duration = time.time() - start_time
            
            results[test_name] = {
                "passed": result["returncode"] == 0,
                "duration": duration,
                "output": result["output"]
            }
            
            status = "✅ PASSED" if result["returncode"] == 0 else "❌ FAILED"
            self.logger.info(f"{test_name}: {status} ({duration:.1f}s)")
        
        return results
    
    async def run_full_tests(self) -> Dict:
        """Run full-scale load tests."""
        self.logger.info("🔥 Running Full-Scale Load Tests")
        
        full_tests = [
            "tests/test_comprehensive_load_testing.py::TestHighFrequencyLoadScenarios::test_market_data_burst_load",
            "tests/test_comprehensive_load_testing.py::TestHighFrequencyLoadScenarios::test_high_frequency_signal_processing",
            "tests/test_comprehensive_load_testing.py::TestHighFrequencyLoadScenarios::test_concurrent_strategy_execution",
            "tests/test_comprehensive_load_testing.py::TestHighFrequencyLoadScenarios::test_database_extreme_load",
            "tests/test_comprehensive_load_testing.py::TestHighFrequencyLoadScenarios::test_memory_stress_endurance"
        ]
        
        results = {}
        for test in full_tests:
            test_name = test.split("::")[-1]
            self.logger.info(f"Running {test_name}...")
            
            start_time = time.time()
            result = await self.run_pytest_test(test)
            duration = time.time() - start_time
            
            results[test_name] = {
                "passed": result["returncode"] == 0,
                "duration": duration,
                "output": result["output"]
            }
            
            status = "✅ PASSED" if result["returncode"] == 0 else "❌ FAILED"
            self.logger.info(f"{test_name}: {status} ({duration:.1f}s)")
        
        return results
    
    async def run_stress_tests(self) -> Dict:
        """Run stress tests only."""
        self.logger.info("⚡ Running Stress Tests")
        
        stress_tests = [
            "tests/test_comprehensive_load_testing.py::TestHighFrequencyLoadScenarios::test_database_extreme_load",
            "tests/test_comprehensive_load_testing.py::TestHighFrequencyLoadScenarios::test_memory_stress_endurance"
        ]
        
        results = {}
        for test in stress_tests:
            test_name = test.split("::")[-1]
            self.logger.info(f"Running {test_name}...")
            
            start_time = time.time()
            result = await self.run_pytest_test(test)
            duration = time.time() - start_time
            
            results[test_name] = {
                "passed": result["returncode"] == 0,
                "duration": duration,
                "output": result["output"]
            }
            
            status = "✅ PASSED" if result["returncode"] == 0 else "❌ FAILED"
            self.logger.info(f"{test_name}: {status} ({duration:.1f}s)")
        
        return results
    
    async def run_performance_benchmarks(self) -> Dict:
        """Run performance benchmarks."""
        self.logger.info("📊 Running Performance Benchmarks")
        
        # Run the existing performance benchmarks that were validated in previous task
        benchmark_script = project_root / "scripts" / "run_performance_benchmarks.py"
        
        if benchmark_script.exists():
            self.logger.info("Running integrated performance benchmarks...")
            try:
                result = subprocess.run(
                    [sys.executable, str(benchmark_script), "--quick"],
                    capture_output=True,
                    text=True,
                    cwd=str(project_root),
                    timeout=300  # 5 minute timeout
                )
                
                return {
                    "integrated_benchmarks": {
                        "passed": result.returncode == 0,
                        "duration": 0,  # Duration included in script output
                        "output": result.stdout if result.returncode == 0 else result.stderr
                    }
                }
            except subprocess.TimeoutExpired:
                self.logger.error("Performance benchmarks timed out")
                return {"integrated_benchmarks": {"passed": False, "duration": 300, "output": "Timeout"}}
        else:
            self.logger.warning("Integrated performance benchmarks not found")
            return {}
    
    async def run_pytest_test(self, test_path: str) -> Dict:
        """Run a single pytest test."""
        cmd = [
            sys.executable, "-m", "pytest",
            test_path,
            "-v",
            "--tb=short",
            "--disable-warnings",
            "-m", "load_test"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(project_root),
                timeout=300  # 5 minute timeout per test
            )
            
            return {
                "returncode": result.returncode,
                "output": result.stdout if result.returncode == 0 else result.stderr
            }
        except subprocess.TimeoutExpired:
            return {
                "returncode": 1,
                "output": f"Test {test_path} timed out after 300 seconds"
            }
    
    def generate_report(self, all_results: Dict) -> str:
        """Generate comprehensive load testing report."""
        report = []
        report.append("# InkedUp Bot Load Testing Report")
        report.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
        report.append("")
        
        # Summary statistics
        total_tests = 0
        passed_tests = 0
        total_duration = 0
        
        for test_type, results in all_results.items():
            if isinstance(results, dict):
                for test_name, result in results.items():
                    total_tests += 1
                    if result.get("passed", False):
                        passed_tests += 1
                    total_duration += result.get("duration", 0)
        
        report.append(f"## Summary")
        report.append(f"- **Total Tests**: {total_tests}")
        report.append(f"- **Passed**: {passed_tests}")
        report.append(f"- **Failed**: {total_tests - passed_tests}")
        report.append(f"- **Success Rate**: {passed_tests/total_tests*100:.1f}%" if total_tests > 0 else "0%")
        report.append(f"- **Total Duration**: {total_duration:.1f} seconds")
        report.append("")
        
        # Detailed results
        for test_type, results in all_results.items():
            report.append(f"## {test_type.replace('_', ' ').title()}")
            
            if isinstance(results, dict):
                for test_name, result in results.items():
                    status = "✅ PASSED" if result.get("passed", False) else "❌ FAILED"
                    duration = result.get("duration", 0)
                    
                    report.append(f"### {test_name}")
                    report.append(f"- **Status**: {status}")
                    report.append(f"- **Duration**: {duration:.2f} seconds")
                    
                    if not result.get("passed", False) and result.get("output"):
                        report.append("- **Error Output**:")
                        report.append("```")
                        report.append(result["output"][-1000:])  # Last 1000 chars
                        report.append("```")
                    report.append("")
        
        return "\n".join(report)
    
    def print_summary(self, all_results: Dict):
        """Print load testing summary to console."""
        print("\n" + "=" * 80)
        print("📊 LOAD TESTING SUMMARY")
        print("=" * 80)
        
        total_tests = 0
        passed_tests = 0
        
        for test_type, results in all_results.items():
            print(f"\n🔍 {test_type.replace('_', ' ').title()}:")
            if isinstance(results, dict):
                for test_name, result in results.items():
                    total_tests += 1
                    status = "✅ PASSED" if result.get("passed", False) else "❌ FAILED"
                    duration = result.get("duration", 0)
                    
                    if result.get("passed", False):
                        passed_tests += 1
                    
                    print(f"  {test_name:<40} {status} ({duration:.1f}s)")
        
        print("\n" + "=" * 80)
        success_rate = passed_tests / total_tests * 100 if total_tests > 0 else 0
        print(f"Overall Result: {passed_tests}/{total_tests} tests passed ({success_rate:.1f}%)")
        
        if passed_tests == total_tests:
            print("🎉 ALL LOAD TESTS PASSED!")
            print("✅ System is ready for high-frequency trading conditions")
        else:
            print("⚠️  Some tests failed - review performance bottlenecks")
        
        print("=" * 80)


async def main():
    """Main load testing runner."""
    parser = argparse.ArgumentParser(description="InkedUp Load Testing Runner")
    parser.add_argument("--quick", action="store_true", help="Run quick tests")
    parser.add_argument("--full", action="store_true", help="Run full-scale tests")
    parser.add_argument("--stress", action="store_true", help="Run stress tests only")
    parser.add_argument("--performance", action="store_true", help="Run performance benchmarks")
    parser.add_argument("--report", action="store_true", help="Generate detailed report")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    # Default to quick tests if no specific test type is requested
    if not any([args.quick, args.full, args.stress, args.performance]):
        args.quick = True
    
    runner = LoadTestRunner(verbose=args.verbose)
    all_results = {}
    
    print("🤖 InkedUp Trading Bot - Load Testing Suite")
    print(f"⏰ Started: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    
    start_time = time.time()
    
    try:
        if args.quick:
            all_results["quick_tests"] = await runner.run_quick_tests()
        
        if args.full:
            all_results["full_tests"] = await runner.run_full_tests()
        
        if args.stress:
            all_results["stress_tests"] = await runner.run_stress_tests()
        
        if args.performance:
            all_results["performance_benchmarks"] = await runner.run_performance_benchmarks()
        
        total_time = time.time() - start_time
        print(f"\n⏱️  Total execution time: {total_time:.2f} seconds")
        
        # Print summary
        runner.print_summary(all_results)
        
        # Generate report if requested
        if args.report:
            report = runner.generate_report(all_results)
            report_file = project_root / "LOAD_TESTING_REPORT.md"
            with open(report_file, 'w') as f:
                f.write(report)
            print(f"\n📄 Detailed report saved to: {report_file}")
        
        # Return exit code based on results
        total_tests = 0
        passed_tests = 0
        for test_type, results in all_results.items():
            if isinstance(results, dict):
                for test_name, result in results.items():
                    total_tests += 1
                    if result.get("passed", False):
                        passed_tests += 1
        
        return 0 if passed_tests == total_tests else 1
        
    except KeyboardInterrupt:
        print("\n⛔ Load testing interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Load testing error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)