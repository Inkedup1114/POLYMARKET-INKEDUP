#!/usr/bin/env python3
"""
Disaster Recovery Testing Runner for InkedUp Polymarket Trading Bot.

This script runs comprehensive disaster recovery tests to validate system
resilience and recovery capabilities under extreme failure conditions.

Usage:
    python scripts/run_disaster_recovery_tests.py [options]

Options:
    --quick         Run quick disaster recovery tests (reduced scenarios)
    --full          Run full disaster recovery test suite
    --scenarios     Run specific scenarios only (comma-separated list)
    --mttr          Focus on Mean Time To Recovery (MTTR) testing
    --availability  Focus on system availability testing
    --report        Generate detailed disaster recovery report
    --verbose       Enable verbose output
"""

import argparse
import asyncio
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class DisasterRecoveryTestRunner:
    """Comprehensive disaster recovery testing runner."""
    
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
        self.logger = logging.getLogger("disaster_recovery_runner")
    
    async def run_quick_tests(self) -> Dict:
        """Run quick disaster recovery tests suitable for CI/CD."""
        self.logger.info("🚀 Running Quick Disaster Recovery Tests")
        
        quick_tests = [
            "tests/test_disaster_recovery.py::TestDisasterRecoveryScenarios::test_database_corruption_recovery",
            "tests/test_disaster_recovery.py::TestDisasterRecoveryScenarios::test_network_partition_recovery"
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
        """Run full disaster recovery test suite."""
        self.logger.info("🔥 Running Full Disaster Recovery Test Suite")
        
        full_tests = [
            "tests/test_disaster_recovery.py::TestDisasterRecoveryScenarios::test_database_corruption_recovery",
            "tests/test_disaster_recovery.py::TestDisasterRecoveryScenarios::test_network_partition_recovery", 
            "tests/test_disaster_recovery.py::TestDisasterRecoveryScenarios::test_memory_exhaustion_recovery",
            "tests/test_disaster_recovery.py::TestDisasterRecoveryScenarios::test_cascading_failure_recovery",
            "tests/test_disaster_recovery.py::TestDisasterRecoveryScenarios::test_comprehensive_disaster_recovery_suite"
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
    
    async def run_specific_scenarios(self, scenarios: List[str]) -> Dict:
        """Run specific disaster recovery scenarios."""
        self.logger.info(f"🎯 Running Specific Scenarios: {', '.join(scenarios)}")
        
        scenario_map = {
            "database": "test_database_corruption_recovery",
            "network": "test_network_partition_recovery",
            "memory": "test_memory_exhaustion_recovery", 
            "cascading": "test_cascading_failure_recovery"
        }
        
        results = {}
        for scenario in scenarios:
            if scenario not in scenario_map:
                self.logger.warning(f"Unknown scenario: {scenario}")
                continue
                
            test_name = scenario_map[scenario]
            test_path = f"tests/test_disaster_recovery.py::TestDisasterRecoveryScenarios::{test_name}"
            
            self.logger.info(f"Running {scenario} scenario...")
            
            start_time = time.time()
            result = await self.run_pytest_test(test_path)
            duration = time.time() - start_time
            
            results[scenario] = {
                "passed": result["returncode"] == 0,
                "duration": duration,
                "output": result["output"]
            }
            
            status = "✅ PASSED" if result["returncode"] == 0 else "❌ FAILED"
            self.logger.info(f"{scenario} scenario: {status} ({duration:.1f}s)")
        
        return results
    
    async def run_mttr_tests(self) -> Dict:
        """Run Mean Time To Recovery (MTTR) focused tests."""
        self.logger.info("⏱️ Running MTTR (Mean Time To Recovery) Tests")
        
        mttr_tests = [
            "tests/test_disaster_recovery.py::TestSystemResilienceMetrics::test_mean_time_to_recovery"
        ]
        
        results = {}
        for test in mttr_tests:
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
    
    async def run_availability_tests(self) -> Dict:
        """Run system availability focused tests."""
        self.logger.info("📈 Running System Availability Tests")
        
        availability_tests = [
            "tests/test_disaster_recovery.py::TestSystemResilienceMetrics::test_system_availability_during_disasters"
        ]
        
        results = {}
        for test in availability_tests:
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
    
    async def run_pytest_test(self, test_path: str) -> Dict:
        """Run a single pytest test."""
        cmd = [
            sys.executable, "-m", "pytest",
            test_path,
            "-v",
            "--tb=short", 
            "--disable-warnings",
            "-m", "disaster_recovery"
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
    
    def generate_disaster_recovery_report(self, all_results: Dict) -> str:
        """Generate comprehensive disaster recovery report."""
        report = []
        report.append("# InkedUp Bot Disaster Recovery Testing Report")
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
        
        report.append("## Executive Summary")
        report.append(f"- **Total Disaster Scenarios Tested**: {total_tests}")
        report.append(f"- **Successful Recoveries**: {passed_tests}")
        report.append(f"- **Recovery Success Rate**: {passed_tests/total_tests*100:.1f}%" if total_tests > 0 else "0%")
        report.append(f"- **Total Testing Duration**: {total_duration:.1f} seconds")
        report.append("")
        
        # Resilience Assessment
        success_rate = passed_tests / total_tests if total_tests > 0 else 0
        if success_rate >= 0.95:
            resilience_grade = "EXCELLENT (A)"
            resilience_status = "✅ System demonstrates exceptional disaster recovery capabilities"
        elif success_rate >= 0.85:
            resilience_grade = "GOOD (B)"
            resilience_status = "✅ System shows good disaster recovery capabilities"
        elif success_rate >= 0.70:
            resilience_grade = "ADEQUATE (C)" 
            resilience_status = "⚠️ System has adequate but improvable disaster recovery"
        else:
            resilience_grade = "INADEQUATE (F)"
            resilience_status = "❌ System requires significant disaster recovery improvements"
            
        report.append("## Resilience Assessment")
        report.append(f"- **Overall Grade**: {resilience_grade}")
        report.append(f"- **Assessment**: {resilience_status}")
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
        
        # Recommendations
        report.append("## Recommendations")
        if passed_tests == total_tests:
            report.append("✅ All disaster recovery scenarios passed successfully.")
            report.append("System is ready for production deployment with excellent disaster recovery capabilities.")
        else:
            failed_tests = total_tests - passed_tests
            report.append(f"⚠️ {failed_tests} disaster recovery scenario(s) failed.")
            report.append("Recommendations:")
            report.append("1. Review failed scenarios and improve recovery mechanisms")
            report.append("2. Implement additional monitoring for identified failure points") 
            report.append("3. Consider enhancing fallback systems for failed scenarios")
            report.append("4. Rerun tests after implementing improvements")
            
        return "\n".join(report)
    
    def print_summary(self, all_results: Dict):
        """Print disaster recovery testing summary to console."""
        print("\n" + "=" * 80)
        print("🔥 DISASTER RECOVERY TESTING SUMMARY")
        print("=" * 80)
        
        total_tests = 0
        passed_tests = 0
        
        for test_type, results in all_results.items():
            print(f"\n🎯 {test_type.replace('_', ' ').title()}:")
            if isinstance(results, dict):
                for test_name, result in results.items():
                    total_tests += 1
                    status = "✅ PASSED" if result.get("passed", False) else "❌ FAILED"
                    duration = result.get("duration", 0)
                    
                    if result.get("passed", False):
                        passed_tests += 1
                    
                    print(f"  {test_name:<50} {status} ({duration:.1f}s)")
        
        print("\n" + "=" * 80)
        success_rate = passed_tests / total_tests * 100 if total_tests > 0 else 0
        print(f"Overall Result: {passed_tests}/{total_tests} tests passed ({success_rate:.1f}%)")
        
        if success_rate >= 95:
            print("🏆 EXCELLENT DISASTER RECOVERY CAPABILITIES!")
            print("✅ System is exceptionally resilient to catastrophic failures")
        elif success_rate >= 85:
            print("🎉 GOOD DISASTER RECOVERY CAPABILITIES!")
            print("✅ System demonstrates solid resilience to failures")
        elif success_rate >= 70:
            print("⚠️ ADEQUATE DISASTER RECOVERY CAPABILITIES")
            print("🔧 Some improvements recommended for better resilience")
        else:
            print("💥 INADEQUATE DISASTER RECOVERY CAPABILITIES")
            print("❌ Significant improvements required before production deployment")
        
        print("=" * 80)


async def main():
    """Main disaster recovery testing runner."""
    parser = argparse.ArgumentParser(description="InkedUp Disaster Recovery Testing Runner")
    parser.add_argument("--quick", action="store_true", help="Run quick tests")
    parser.add_argument("--full", action="store_true", help="Run full test suite")
    parser.add_argument("--scenarios", help="Run specific scenarios (comma-separated)")
    parser.add_argument("--mttr", action="store_true", help="Focus on MTTR testing")
    parser.add_argument("--availability", action="store_true", help="Focus on availability testing")
    parser.add_argument("--report", action="store_true", help="Generate detailed report")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    # Default to quick tests if no specific test type is requested
    if not any([args.quick, args.full, args.scenarios, args.mttr, args.availability]):
        args.quick = True
    
    runner = DisasterRecoveryTestRunner(verbose=args.verbose)
    all_results = {}
    
    print("🔥 InkedUp Trading Bot - Disaster Recovery Testing Suite")
    print(f"⏰ Started: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    
    start_time = time.time()
    
    try:
        if args.quick:
            all_results["quick_tests"] = await runner.run_quick_tests()
        
        if args.full:
            all_results["full_tests"] = await runner.run_full_tests()
        
        if args.scenarios:
            scenario_list = [s.strip() for s in args.scenarios.split(',')]
            all_results["specific_scenarios"] = await runner.run_specific_scenarios(scenario_list)
        
        if args.mttr:
            all_results["mttr_tests"] = await runner.run_mttr_tests()
        
        if args.availability:
            all_results["availability_tests"] = await runner.run_availability_tests()
        
        total_time = time.time() - start_time
        print(f"\n⏱️ Total execution time: {total_time:.2f} seconds")
        
        # Print summary
        runner.print_summary(all_results)
        
        # Generate report if requested
        if args.report:
            report = runner.generate_disaster_recovery_report(all_results)
            report_file = project_root / "DISASTER_RECOVERY_TESTING_REPORT.md"
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
        print("\n⛔ Disaster recovery testing interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Disaster recovery testing error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)