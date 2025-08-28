#!/usr/bin/env python3
"""
Simple test of the signal pipeline optimization
"""

import asyncio
import logging
import time
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO)

# Mock signal class for testing
@dataclass 
class MockSignal:
    signal_id: str
    strategy: str = "test"
    expected_profit: float = 0.01
    confidence: float = 0.7
    market_slug: str = "test-market"
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


async def test_basic_optimization():
    """Test basic optimization functionality."""
    from inkedup_bot.signal_pipeline_optimizer import (
        PipelineConfig,
        SignalPipelineOptimizer,
    )
    
    print("Testing Signal Pipeline Optimization...")
    
    # Create config
    config = PipelineConfig(
        critical_workers=2,
        high_workers=2, 
        normal_workers=3,
        low_workers=1,
        enable_monitoring=False
    )
    
    # Create optimizer
    optimizer = SignalPipelineOptimizer(config)
    
    # Track processed signals
    processed = []
    
    def mock_processor(signal):
        processed.append(signal.signal_id)
        time.sleep(0.1)  # Simulate processing
        return f"processed_{signal.signal_id}"
    
    optimizer.set_signal_processor(mock_processor)
    
    try:
        # Start processing
        await optimizer.start_processing()
        print(f"Started {len(optimizer._worker_tasks)} workers")
        
        # Create test signals
        signals = []
        for i in range(10):
            if i < 2:  # First 2 are critical
                signal = MockSignal(
                    signal_id=f"critical_{i}",
                    strategy="arbitrage_spread",
                    expected_profit=0.025  # 2.5% = critical
                )
            elif i < 5:  # Next 3 are high priority  
                signal = MockSignal(
                    signal_id=f"high_{i}",
                    strategy="momentum_trade",
                    market_slug="volatile-market"
                )
            else:  # Rest are normal
                signal = MockSignal(
                    signal_id=f"normal_{i}"
                )
            signals.append(signal)
        
        # Submit signals
        print(f"Submitting {len(signals)} signals...")
        start_time = time.time()
        
        for signal in signals:
            await optimizer.submit_signal(signal)
        
        # Wait for processing
        while optimizer.get_status()['active_signals'] > 0:
            await asyncio.sleep(0.1)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        print(f"Processed {len(processed)} signals in {total_time:.2f} seconds")
        print(f"Throughput: {len(processed) / total_time:.1f} signals/sec")
        
        # Show final stats
        stats = optimizer.get_performance_stats()
        print(f"Final stats: {stats['summary']}")
        
        return True
        
    except Exception as e:
        print(f"Test failed: {e}")
        return False
    finally:
        await optimizer.shutdown()


if __name__ == "__main__":
    success = asyncio.run(test_basic_optimization())
    if success:
        print("✅ Signal pipeline optimization test passed!")
    else:
        print("❌ Signal pipeline optimization test failed!")