#!/usr/bin/env python3
"""
Quick validation of load testing framework functionality.
"""

import asyncio
import sys
import tempfile
from pathlib import Path

# Add project to path
sys.path.insert(0, '.')

from inkedup_bot.config import BotConfig
from tests.test_comprehensive_load_testing import (
    HighFrequencyLoadTester,
    LoadTestResults,
)


async def validate_load_testing():
    """Validate load testing framework works correctly."""
    
    print("🧪 Validating Load Testing Framework")
    print("=" * 50)
    
    try:
        # Test 1: Basic load tester functionality
        print("📊 Test 1: Load Tester Initialization")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            config = BotConfig(database_url=f"sqlite:///{db_path}")
            
            load_tester = HighFrequencyLoadTester(config)
            load_tester.start_system_monitoring()
            
            print("   ✅ Load tester created and monitoring started")
            
            # Test 2: Operation recording
            print("📊 Test 2: Operation Recording")
            
            import time
            for i in range(10):
                start_time = time.time()
                await asyncio.sleep(0.01)  # Simulate work
                load_tester.record_operation(start_time, success=True)
            
            print("   ✅ Operations recorded successfully")
            
            # Test 3: Results calculation
            print("📊 Test 3: Results Calculation")
            
            results = load_tester.calculate_results("Validation Test", 0.2, 10)
            
            print(f"   Test Name: {results.test_name}")
            print(f"   Success Rate: {results.success_rate:.1%}")
            print(f"   Operations/sec: {results.operations_per_second:.0f}")
            print(f"   Average Latency: {results.average_latency_ms:.2f}ms")
            print(f"   Passed: {results.passed}")
            
            assert results.success_rate == 1.0, "All operations should succeed"
            assert results.operations_per_second > 0, "Should have positive throughput"
            
            print("   ✅ Results calculated correctly")
            
            # Test 4: Simple load scenario
            print("📊 Test 4: Simple Load Scenario")
            
            load_tester2 = HighFrequencyLoadTester(config)
            load_tester2.start_system_monitoring()
            
            start_time = time.time()
            
            # Simulate 50 rapid operations
            async def simple_operation(op_id: int):
                op_start = time.time()
                try:
                    await asyncio.sleep(0.001)  # 1ms simulated work
                    load_tester2.record_operation(op_start, success=True)
                    return True
                except Exception as e:
                    load_tester2.record_operation(op_start, success=False, error=str(e))
                    return False
            
            tasks = [simple_operation(i) for i in range(50)]
            results_list = await asyncio.gather(*tasks)
            
            duration = time.time() - start_time
            final_results = load_tester2.calculate_results("Simple Load", duration, 50)
            
            print(f"   Total Operations: {final_results.total_operations}")
            print(f"   Successful: {final_results.successful_operations}")
            print(f"   Duration: {final_results.duration_seconds:.2f}s")
            print(f"   Throughput: {final_results.operations_per_second:.0f} ops/sec")
            print(f"   Success Rate: {final_results.success_rate:.1%}")
            
            assert final_results.success_rate >= 0.9, "Should have high success rate"
            assert final_results.operations_per_second > 10, "Should have reasonable throughput"
            
            print("   ✅ Simple load scenario completed successfully")
        
        print("\n" + "=" * 50)
        print("🎉 Load Testing Framework Validation SUCCESSFUL!")
        print("✅ All components working correctly")
        print("✅ Ready for comprehensive load testing")
        print("=" * 50)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(validate_load_testing())
    sys.exit(0 if success else 1)