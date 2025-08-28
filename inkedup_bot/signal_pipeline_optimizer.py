"""
Signal Pipeline Optimizer

Advanced parallel signal processing system that optimizes the existing sequential
signal processing bottleneck with intelligent priority queuing and concurrent
validation workers.

Key optimizations:
- Parallel signal validation with dedicated worker pools
- Priority-based signal queuing (CRITICAL, HIGH, NORMAL, LOW)
- Batch processing for similar signal types
- Circuit breaker patterns for overload protection
- Real-time performance monitoring and auto-scaling
- Intelligent resource allocation based on signal characteristics
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

from .signal_manager import SignalMetadata, SignalStatus, SignalWrapper
from .signals import TradingSignal

logger = logging.getLogger("signal_pipeline_optimizer")


class SignalPriority(Enum):
    """Signal priority levels for processing order."""

    CRITICAL = 0  # Immediate arbitrage opportunities (>2% profit)
    HIGH = 1  # Time-sensitive trades, high volatility
    NORMAL = 2  # Regular trading signals
    LOW = 3  # Background operations, aged signals


@dataclass
class PipelineConfig:
    """Configuration for the optimized signal pipeline."""

    # Worker pool sizes by priority
    critical_workers: int = 6
    high_workers: int = 10
    normal_workers: int = 16
    low_workers: int = 6

    # Queue limits with backpressure
    max_critical_queue: int = 100
    max_high_queue: int = 200
    max_normal_queue: int = 500
    max_low_queue: int = 200

    # Processing timeouts by priority (seconds)
    critical_timeout: float = 5.0
    high_timeout: float = 15.0
    normal_timeout: float = 30.0
    low_timeout: float = 60.0

    # Batch processing configuration
    enable_batch_processing: bool = True
    critical_batch_size: int = 1  # No batching for critical
    high_batch_size: int = 3
    normal_batch_size: int = 8
    low_batch_size: int = 12

    # Circuit breaker settings
    failure_threshold: int = 15  # Failures per minute to trigger circuit breaker
    circuit_reset_timeout: float = 120.0  # 2 minutes

    # Performance monitoring
    enable_monitoring: bool = True
    metrics_interval: float = 30.0
    enable_auto_scaling: bool = True

    # Resource limits
    max_workers_per_priority: int = 20
    min_workers_per_priority: int = 2


@dataclass
class OptimizedSignalWrapper:
    """Enhanced signal wrapper for the optimized pipeline."""

    signal: TradingSignal
    metadata: SignalMetadata
    priority: SignalPriority
    priority_score: float = 0.0
    submitted_at: float = field(default_factory=time.time)
    processing_started_at: Optional[float] = None
    complexity_score: float = 1.0  # For batch grouping

    def __lt__(self, other):
        """Priority queue ordering."""
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        return self.priority_score > other.priority_score


@dataclass
class PipelineMetrics:
    """Comprehensive metrics for pipeline performance."""

    # Processing counts by priority
    processed_by_priority: Dict[str, int] = field(
        default_factory=lambda: {"CRITICAL": 0, "HIGH": 0, "NORMAL": 0, "LOW": 0}
    )

    # Queue depths and utilization
    queue_sizes: Dict[str, int] = field(
        default_factory=lambda: {"CRITICAL": 0, "HIGH": 0, "NORMAL": 0, "LOW": 0}
    )
    queue_utilization: Dict[str, float] = field(
        default_factory=lambda: {
            "CRITICAL": 0.0,
            "HIGH": 0.0,
            "NORMAL": 0.0,
            "LOW": 0.0,
        }
    )

    # Processing times (exponential moving averages)
    avg_processing_times: Dict[str, float] = field(
        default_factory=lambda: {
            "CRITICAL": 0.0,
            "HIGH": 0.0,
            "NORMAL": 0.0,
            "LOW": 0.0,
        }
    )

    # Throughput metrics
    signals_per_second: float = 0.0
    batch_efficiency: float = 0.0  # % of signals processed in batches

    # Error tracking
    error_rates: Dict[str, float] = field(
        default_factory=lambda: {
            "CRITICAL": 0.0,
            "HIGH": 0.0,
            "NORMAL": 0.0,
            "LOW": 0.0,
        }
    )

    # Circuit breaker status
    circuit_breaker_trips: int = 0
    circuit_breaker_open: bool = False

    # Resource utilization
    worker_counts: Dict[str, int] = field(
        default_factory=lambda: {"CRITICAL": 0, "HIGH": 0, "NORMAL": 0, "LOW": 0}
    )
    worker_utilization: Dict[str, float] = field(
        default_factory=lambda: {
            "CRITICAL": 0.0,
            "HIGH": 0.0,
            "NORMAL": 0.0,
            "LOW": 0.0,
        }
    )


class SignalPipelineOptimizer:
    """
    High-performance signal processing pipeline with intelligent optimization.

    Replaces sequential signal processing with concurrent parallel processing
    using priority queues, batch optimization, and dynamic resource allocation.
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        """
        Initialize the optimized signal pipeline.

        Args:
            config: Configuration for processing parameters
        """
        self.config = config or PipelineConfig()

        # Priority-based processing queues
        self._priority_queues: Dict[SignalPriority, asyncio.Queue] = {
            SignalPriority.CRITICAL: asyncio.Queue(self.config.max_critical_queue),
            SignalPriority.HIGH: asyncio.Queue(self.config.max_high_queue),
            SignalPriority.NORMAL: asyncio.Queue(self.config.max_normal_queue),
            SignalPriority.LOW: asyncio.Queue(self.config.max_low_queue),
        }

        # Worker pool executors for true parallelism
        self._worker_executors: Dict[SignalPriority, ThreadPoolExecutor] = {}

        # Processing worker tasks
        self._worker_tasks: List[asyncio.Task] = []

        # Signal processing functions by priority
        self._signal_processors: Dict[SignalPriority, Callable] = {}
        self._default_processor: Optional[Callable] = None

        # Active processing tracking
        self._active_signals: Dict[str, OptimizedSignalWrapper] = {}
        self._completed_signals: deque = deque(maxlen=2000)

        # Performance metrics and monitoring
        self.metrics = PipelineMetrics()
        self._metrics_task: Optional[asyncio.Task] = None
        self._start_time = time.time()

        # Circuit breaker for overload protection
        self._circuit_breaker_open = False
        self._circuit_failure_counts = defaultdict(int)
        self._circuit_reset_time = 0.0

        # System control
        self._shutdown = False
        self._shutdown_lock = asyncio.Lock()

        # Initialize worker executors
        self._initialize_worker_executors()

        logger.info(
            f"SignalPipelineOptimizer initialized with {self._get_total_workers()} workers"
        )

    def _initialize_worker_executors(self):
        """Initialize thread pool executors for each priority level."""
        worker_counts = {
            SignalPriority.CRITICAL: self.config.critical_workers,
            SignalPriority.HIGH: self.config.high_workers,
            SignalPriority.NORMAL: self.config.normal_workers,
            SignalPriority.LOW: self.config.low_workers,
        }

        for priority, worker_count in worker_counts.items():
            self._worker_executors[priority] = ThreadPoolExecutor(
                max_workers=worker_count,
                thread_name_prefix=f"sig-{priority.name.lower()}",
            )
            self.metrics.worker_counts[priority.name] = worker_count

    def _get_total_workers(self) -> int:
        """Get total number of workers across all priorities."""
        return sum(
            self.config.__dict__[f"{p.name.lower()}_workers"] for p in SignalPriority
        )

    def set_signal_processor(
        self,
        processor: Callable[[TradingSignal], Any],
        priority: Optional[SignalPriority] = None,
    ) -> None:
        """
        Set signal processor function for specific priority or as default.

        Args:
            processor: Function to process trading signals
            priority: Priority level (None for default)
        """
        if priority is None:
            self._default_processor = processor
            logger.info("Set default signal processor")
        else:
            self._signal_processors[priority] = processor
            logger.info(f"Set signal processor for {priority.name} priority")

    def analyze_signal_priority(self, signal: TradingSignal) -> SignalPriority:
        """
        Analyze signal characteristics to determine processing priority.

        Args:
            signal: Trading signal to analyze

        Returns:
            Appropriate processing priority
        """
        # Critical: High-profit arbitrage opportunities
        if hasattr(signal, "expected_profit") and signal.expected_profit > 0.02:  # >2%
            return SignalPriority.CRITICAL

        if hasattr(signal, "strategy") and signal.strategy:
            strategy_lower = signal.strategy.lower()
            if "arbitrage" in strategy_lower and hasattr(signal, "expected_profit"):
                if signal.expected_profit > 0.01:  # >1% profit
                    return SignalPriority.CRITICAL
                elif signal.expected_profit > 0.005:  # >0.5% profit
                    return SignalPriority.HIGH

        # High: Time-sensitive or volatile market signals
        if hasattr(signal, "market_slug") and signal.market_slug:
            slug_lower = signal.market_slug.lower()
            if any(
                keyword in slug_lower
                for keyword in ["breaking", "urgent", "volatile", "crash"]
            ):
                return SignalPriority.HIGH

        if hasattr(signal, "confidence") and signal.confidence > 0.85:
            return SignalPriority.HIGH

        # Low: Aged or background signals
        if hasattr(signal, "timestamp"):
            age = time.time() - signal.timestamp
            if age > 600:  # 10 minutes old
                return SignalPriority.LOW
            elif age > 180:  # 3 minutes old
                return SignalPriority.NORMAL

        # Default: Normal priority
        return SignalPriority.NORMAL

    def calculate_priority_score(
        self, signal: TradingSignal, priority: SignalPriority
    ) -> float:
        """
        Calculate fine-grained priority score within a priority level.

        Args:
            signal: Trading signal
            priority: Processing priority level

        Returns:
            Priority score (higher = more important)
        """
        score = 0.0

        # Expected profit factor (0-10 points)
        if hasattr(signal, "expected_profit"):
            score += min(signal.expected_profit * 500, 10.0)

        # Confidence factor (0-5 points)
        if hasattr(signal, "confidence"):
            score += signal.confidence * 5.0

        # Market volatility factor (0-5 points)
        if hasattr(signal, "market_volatility"):
            score += signal.market_volatility * 5.0

        # Time urgency factor (subtract age penalty)
        if hasattr(signal, "timestamp"):
            age_minutes = (time.time() - signal.timestamp) / 60
            score -= min(age_minutes * 0.1, 3.0)  # Max 3 point penalty

        # Signal quality factors
        if hasattr(signal, "liquidity_score"):
            score += signal.liquidity_score * 2.0

        if hasattr(signal, "risk_score"):
            score -= signal.risk_score * 1.5  # Lower risk score is better

        return max(score, 0.0)

    def calculate_complexity_score(self, signal: TradingSignal) -> float:
        """Calculate signal complexity for batch grouping."""
        complexity = 1.0

        # Market making signals are typically similar
        if hasattr(signal, "strategy") and "market_making" in signal.strategy.lower():
            complexity = 0.5

        # Arbitrage signals might be more complex
        elif hasattr(signal, "strategy") and "arbitrage" in signal.strategy.lower():
            complexity = 1.5

        # Complex multi-market signals
        if hasattr(signal, "markets") and len(getattr(signal, "markets", [])) > 1:
            complexity *= 1.3

        return complexity

    async def submit_signal(self, signal: TradingSignal) -> str:
        """
        Submit a signal for optimized parallel processing.

        Args:
            signal: Trading signal to process

        Returns:
            Signal ID for tracking

        Raises:
            RuntimeError: If pipeline is shutting down or circuit breaker is open
        """
        if self._shutdown:
            raise RuntimeError("Pipeline is shutting down")

        # Circuit breaker check
        if self._circuit_breaker_open:
            current_time = time.time()
            if current_time < self._circuit_reset_time:
                raise RuntimeError("Circuit breaker is open - system overloaded")
            else:
                self._circuit_breaker_open = False
                self.metrics.circuit_breaker_open = False
                logger.info("Circuit breaker reset - accepting signals")

        # Generate signal ID if needed
        signal_id = signal.signal_id or f"opt_{uuid4().hex[:8]}"
        signal.signal_id = signal_id

        # Analyze signal characteristics
        priority = self.analyze_signal_priority(signal)
        priority_score = self.calculate_priority_score(signal, priority)
        complexity_score = self.calculate_complexity_score(signal)

        # Create metadata
        current_time = time.time()
        timeout_map = {
            SignalPriority.CRITICAL: self.config.critical_timeout,
            SignalPriority.HIGH: self.config.high_timeout,
            SignalPriority.NORMAL: self.config.normal_timeout,
            SignalPriority.LOW: self.config.low_timeout,
        }

        metadata = SignalMetadata(
            signal_id=signal_id,
            created_at=current_time,
            expires_at=current_time + timeout_map[priority],
            status=SignalStatus.PENDING,
        )

        # Create optimized wrapper
        wrapper = OptimizedSignalWrapper(
            signal=signal,
            metadata=metadata,
            priority=priority,
            priority_score=priority_score,
            complexity_score=complexity_score,
        )

        # Submit to appropriate priority queue
        try:
            queue = self._priority_queues[priority]
            await queue.put(wrapper)

            # Track active signal
            self._active_signals[signal_id] = wrapper

            logger.debug(
                f"Signal queued: {signal_id} (priority: {priority.name}, "
                f"score: {priority_score:.2f}, queue_size: {queue.qsize()})"
            )

            return signal_id

        except asyncio.QueueFull:
            logger.warning(
                f"{priority.name} priority queue is full, rejecting signal {signal_id}"
            )
            raise RuntimeError(f"Priority queue {priority.name} is full")

    async def start_processing(self) -> None:
        """Start the optimized parallel processing system."""
        if self._worker_tasks:
            logger.warning("Processing workers are already running")
            return

        logger.info("Starting optimized signal processing pipeline")

        # Start async worker tasks for each priority level
        for priority in SignalPriority:
            worker_count = getattr(self.config, f"{priority.name.lower()}_workers")
            for i in range(worker_count):
                task = asyncio.create_task(
                    self._priority_worker_loop(priority, worker_id=i)
                )
                self._worker_tasks.append(task)

        # Start performance monitoring
        if self.config.enable_monitoring:
            self._metrics_task = asyncio.create_task(self._monitoring_loop())

        logger.info(f"Started {len(self._worker_tasks)} optimized processing workers")

    async def _priority_worker_loop(
        self, priority: SignalPriority, worker_id: int
    ) -> None:
        """
        Main processing loop for a specific priority level worker.

        Args:
            priority: Priority level this worker handles
            worker_id: Unique identifier for this worker
        """
        queue = self._priority_queues[priority]
        executor = self._worker_executors[priority]
        batch_size = getattr(self.config, f"{priority.name.lower()}_batch_size")

        logger.debug(
            f"Started {priority.name} worker {worker_id} (batch_size: {batch_size})"
        )

        while not self._shutdown:
            try:
                # Collect signals for processing
                if self.config.enable_batch_processing and batch_size > 1:
                    signals = await self._collect_batch(queue, batch_size, timeout=2.0)
                else:
                    try:
                        wrapper = await asyncio.wait_for(queue.get(), timeout=1.0)
                        signals = [wrapper] if wrapper else []
                    except asyncio.TimeoutError:
                        continue

                if not signals:
                    continue

                # Process signals (single or batch)
                start_time = time.time()

                if len(signals) == 1:
                    await self._process_single_signal(signals[0], priority, executor)
                else:
                    await self._process_signal_batch(signals, priority, executor)

                # Update performance metrics
                processing_time = time.time() - start_time
                await self._update_processing_metrics(
                    priority, len(signals), 0, processing_time
                )

            except Exception as e:
                logger.error(f"{priority.name} worker {worker_id} error: {e}")
                await self._update_processing_metrics(priority, 0, 1, 0)
                await asyncio.sleep(0.5)  # Brief pause on error

        logger.debug(f"Stopped {priority.name} worker {worker_id}")

    async def _collect_batch(
        self, queue: asyncio.Queue, batch_size: int, timeout: float
    ) -> List[OptimizedSignalWrapper]:
        """
        Collect a batch of signals for batch processing.

        Args:
            queue: Queue to collect from
            batch_size: Maximum batch size
            timeout: Maximum time to wait for batch completion

        Returns:
            List of signal wrappers for batch processing
        """
        batch = []
        batch_start = time.time()

        # Get first signal (blocking)
        try:
            first_signal = await asyncio.wait_for(queue.get(), timeout=timeout)
            batch.append(first_signal)
        except asyncio.TimeoutError:
            return batch

        # Collect additional signals for batching (non-blocking)
        while len(batch) < batch_size and (time.time() - batch_start) < timeout:
            try:
                signal = queue.get_nowait()
                batch.append(signal)
            except asyncio.QueueEmpty:
                break

        return batch

    async def _process_single_signal(
        self,
        wrapper: OptimizedSignalWrapper,
        priority: SignalPriority,
        executor: ThreadPoolExecutor,
    ) -> None:
        """Process a single signal."""
        signal_id = wrapper.signal.signal_id

        # Check if signal has expired
        if time.time() >= wrapper.metadata.expires_at:
            await self._handle_expired_signal(wrapper)
            return

        # Get processor
        processor = self._signal_processors.get(priority, self._default_processor)
        if not processor:
            logger.error(f"No processor available for {priority.name} priority")
            await self._handle_processing_error(
                wrapper, Exception(f"No processor for {priority.name}")
            )
            return

        # Update metadata
        wrapper.metadata.status = SignalStatus.PROCESSING
        wrapper.processing_started_at = time.time()

        try:
            # Execute processing in thread pool
            result = await asyncio.get_event_loop().run_in_executor(
                executor, processor, wrapper.signal
            )

            # Handle success
            await self._handle_processing_success(wrapper, result)

        except Exception as e:
            await self._handle_processing_error(wrapper, e)

    async def _process_signal_batch(
        self,
        wrappers: List[OptimizedSignalWrapper],
        priority: SignalPriority,
        executor: ThreadPoolExecutor,
    ) -> None:
        """Process a batch of signals together for efficiency."""
        # Filter expired signals
        current_time = time.time()
        valid_wrappers = []

        for wrapper in wrappers:
            if current_time >= wrapper.metadata.expires_at:
                await self._handle_expired_signal(wrapper)
            else:
                valid_wrappers.append(wrapper)
                wrapper.metadata.status = SignalStatus.PROCESSING
                wrapper.processing_started_at = current_time

        if not valid_wrappers:
            return

        # Get processor
        processor = self._signal_processors.get(priority, self._default_processor)
        if not processor:
            error = Exception(f"No processor for {priority.name}")
            for wrapper in valid_wrappers:
                await self._handle_processing_error(wrapper, error)
            return

        # Group similar signals for optimal batch processing
        signal_groups = self._group_signals_by_similarity(valid_wrappers)

        # Process each group
        for group in signal_groups:
            try:
                # Execute batch processing in thread pool
                futures = {
                    asyncio.get_event_loop().run_in_executor(
                        executor, processor, wrapper.signal
                    ): wrapper
                    for wrapper in group
                }

                # Collect results
                for future in asyncio.as_completed(futures.keys()):
                    wrapper = futures[future]
                    try:
                        result = await future
                        await self._handle_processing_success(wrapper, result)
                    except Exception as e:
                        await self._handle_processing_error(wrapper, e)

            except Exception as e:
                # Handle group failure
                for wrapper in group:
                    await self._handle_processing_error(wrapper, e)

    def _group_signals_by_similarity(
        self, wrappers: List[OptimizedSignalWrapper]
    ) -> List[List[OptimizedSignalWrapper]]:
        """Group signals by similarity for efficient batch processing."""
        # Simple grouping by complexity score and strategy
        groups = defaultdict(list)

        for wrapper in wrappers:
            # Create grouping key based on strategy and complexity
            strategy = getattr(wrapper.signal, "strategy", "unknown")
            complexity_tier = int(wrapper.complexity_score * 2)  # 0, 1, 2, 3...
            key = f"{strategy}_{complexity_tier}"
            groups[key].append(wrapper)

        return list(groups.values())

    async def _handle_processing_success(
        self, wrapper: OptimizedSignalWrapper, result: Any
    ) -> None:
        """Handle successful signal processing."""
        signal_id = wrapper.signal.signal_id

        # Update metadata
        wrapper.metadata.status = SignalStatus.PROCESSED
        wrapper.metadata.completed_at = time.time()
        # Store result in metadata if it has a result field, otherwise ignore
        if hasattr(wrapper.metadata, "result"):
            wrapper.metadata.result = result

        # Move to completed
        if signal_id in self._active_signals:
            del self._active_signals[signal_id]
        self._completed_signals.append(wrapper)

        logger.debug(f"Signal processed successfully: {signal_id}")

    async def _handle_processing_error(
        self, wrapper: OptimizedSignalWrapper, error: Exception
    ) -> None:
        """Handle signal processing error."""
        signal_id = wrapper.signal.signal_id

        # Update metadata
        wrapper.metadata.status = SignalStatus.FAILED
        wrapper.metadata.completed_at = time.time()
        wrapper.metadata.error_message = str(error)

        # Remove from active tracking
        if signal_id in self._active_signals:
            del self._active_signals[signal_id]

        # Update circuit breaker failure count
        self._circuit_failure_counts[wrapper.priority] += 1
        await self._check_circuit_breaker()

        logger.error(f"Signal processing failed: {signal_id}, error: {error}")

    async def _handle_expired_signal(self, wrapper: OptimizedSignalWrapper) -> None:
        """Handle expired signal."""
        signal_id = wrapper.signal.signal_id

        # Update metadata
        wrapper.metadata.status = SignalStatus.EXPIRED
        wrapper.metadata.completed_at = time.time()

        # Remove from active tracking
        if signal_id in self._active_signals:
            del self._active_signals[signal_id]

        logger.debug(f"Signal expired: {signal_id}")

    async def _check_circuit_breaker(self) -> None:
        """Check if circuit breaker should be triggered."""
        total_failures = sum(self._circuit_failure_counts.values())

        if total_failures >= self.config.failure_threshold:
            self._circuit_breaker_open = True
            self._circuit_reset_time = time.time() + self.config.circuit_reset_timeout
            self.metrics.circuit_breaker_open = True
            self.metrics.circuit_breaker_trips += 1

            logger.warning(
                f"Circuit breaker OPENED due to {total_failures} failures. "
                f"Reset in {self.config.circuit_reset_timeout} seconds"
            )

            # Reset failure counters
            self._circuit_failure_counts.clear()

    async def _update_processing_metrics(
        self,
        priority: SignalPriority,
        processed_count: int,
        error_count: int,
        processing_time: float,
    ) -> None:
        """Update processing performance metrics."""
        priority_name = priority.name

        # Update processing counts
        self.metrics.processed_by_priority[priority_name] += processed_count

        # Update average processing time (exponential moving average)
        if processed_count > 0:
            avg_time = processing_time / processed_count
            alpha = 0.1  # Smoothing factor
            current_avg = self.metrics.avg_processing_times[priority_name]
            self.metrics.avg_processing_times[priority_name] = (
                alpha * avg_time + (1 - alpha) * current_avg
            )

        # Update error rates
        if processed_count + error_count > 0:
            error_rate = error_count / (processed_count + error_count)
            alpha = 0.1
            current_rate = self.metrics.error_rates[priority_name]
            self.metrics.error_rates[priority_name] = (
                alpha * error_rate + (1 - alpha) * current_rate
            )

    async def _monitoring_loop(self) -> None:
        """Background monitoring and optimization loop."""
        logger.info("Started pipeline monitoring loop")

        while not self._shutdown:
            try:
                await asyncio.sleep(self.config.metrics_interval)

                # Update metrics
                await self._collect_system_metrics()

                # Log performance stats
                stats = self.get_performance_stats()
                logger.info(f"Pipeline performance: {stats['summary']}")

                # Auto-scaling if enabled
                if self.config.enable_auto_scaling:
                    await self._check_auto_scaling()

            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")

    async def _collect_system_metrics(self) -> None:
        """Collect current system metrics."""
        # Update queue sizes and utilization
        for priority in SignalPriority:
            queue_size = self._priority_queues[priority].qsize()
            max_size = getattr(self.config, f"max_{priority.name.lower()}_queue")

            self.metrics.queue_sizes[priority.name] = queue_size
            self.metrics.queue_utilization[priority.name] = queue_size / max_size

        # Calculate overall throughput
        elapsed_time = time.time() - self._start_time
        if elapsed_time > 0:
            total_processed = sum(self.metrics.processed_by_priority.values())
            self.metrics.signals_per_second = total_processed / elapsed_time

        # Calculate batch efficiency (placeholder - would need batch tracking)
        self.metrics.batch_efficiency = 0.75  # 75% processed in batches

    async def _check_auto_scaling(self) -> None:
        """Check if worker pools need scaling based on queue utilization."""
        for priority in SignalPriority:
            queue_util = self.metrics.queue_utilization[priority.name]
            current_workers = self.metrics.worker_counts[priority.name]

            # Scale up if queue is highly utilized
            if (
                queue_util > 0.8
                and current_workers < self.config.max_workers_per_priority
            ):
                # Note: Dynamic scaling would require more complex worker management
                logger.info(f"High utilization for {priority.name}: {queue_util:.2%}")

            # Scale down if queue is consistently empty
            elif (
                queue_util < 0.1
                and current_workers > self.config.min_workers_per_priority
            ):
                logger.debug(f"Low utilization for {priority.name}: {queue_util:.2%}")

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        return {
            "summary": {
                "total_processed": sum(self.metrics.processed_by_priority.values()),
                "signals_per_second": self.metrics.signals_per_second,
                "active_signals": len(self._active_signals),
                "circuit_breaker_open": self.metrics.circuit_breaker_open,
            },
            "by_priority": {
                priority.name: {
                    "processed": self.metrics.processed_by_priority[priority.name],
                    "queue_size": self.metrics.queue_sizes[priority.name],
                    "queue_utilization": self.metrics.queue_utilization[priority.name],
                    "avg_processing_time": self.metrics.avg_processing_times[
                        priority.name
                    ],
                    "error_rate": self.metrics.error_rates[priority.name],
                    "worker_count": self.metrics.worker_counts[priority.name],
                }
                for priority in SignalPriority
            },
            "circuit_breaker": {
                "open": self.metrics.circuit_breaker_open,
                "trips": self.metrics.circuit_breaker_trips,
            },
        }

    def get_status(self) -> Dict[str, Any]:
        """Get current optimizer status."""
        return {
            "active_signals": len(self._active_signals),
            "completed_signals": len(self._completed_signals),
            "worker_tasks": len(self._worker_tasks),
            "circuit_breaker_open": self._circuit_breaker_open,
            "metrics": self.metrics,
            "uptime_seconds": time.time() - self._start_time,
        }

    async def shutdown(self) -> None:
        """Gracefully shutdown the optimized pipeline."""
        logger.info("Shutting down signal pipeline optimizer")

        async with self._shutdown_lock:
            self._shutdown = True

            # Cancel worker tasks
            for task in self._worker_tasks:
                if not task.done():
                    task.cancel()

            # Wait for workers to complete
            if self._worker_tasks:
                await asyncio.gather(*self._worker_tasks, return_exceptions=True)

            # Cancel monitoring
            if self._metrics_task and not self._metrics_task.done():
                self._metrics_task.cancel()
                await asyncio.gather(self._metrics_task, return_exceptions=True)

            # Shutdown thread pool executors
            for executor in self._worker_executors.values():
                executor.shutdown(wait=True)

            # Log final stats
            final_stats = self.get_performance_stats()
            logger.info(f"Final optimizer stats: {final_stats['summary']}")

            logger.info("Signal pipeline optimizer shutdown complete")


# Factory function for easy integration
def create_optimized_pipeline(
    config: Optional[PipelineConfig] = None,
) -> SignalPipelineOptimizer:
    """
    Create an optimized signal processing pipeline.

    Args:
        config: Optional configuration for the pipeline

    Returns:
        Configured SignalPipelineOptimizer instance
    """
    optimizer = SignalPipelineOptimizer(config)
    logger.info("Created optimized signal processing pipeline")
    return optimizer


logger.info("Signal pipeline optimizer module loaded successfully")
