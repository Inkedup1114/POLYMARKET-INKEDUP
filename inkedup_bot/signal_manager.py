"""
Signal lifecycle management with timeout handling and automatic cleanup.

This module provides comprehensive signal processing pipeline management including:
- Timestamp tracking for all signals
- Configurable timeout periods
- Automatic cleanup of stale signals
- Signal deduplication and validation
- M        # Check if this is a market making signal (simplified check)
        # Note: TradingSignal doesn't have strategy_type, so we infer from market_slug
        if 'market_making' in market_slug or 'mm' in market_slug:
            return self.config.market_making_signal_timeoutics and monitoring for signal processing
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import uuid4

from .signals import TradingSignal

logger = logging.getLogger("signal_manager")


class SignalStatus(str, Enum):
    """Signal processing status."""

    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    EXPIRED = "expired"
    FAILED = "failed"


@dataclass(slots=True)
class SignalMetadata:
    """Metadata for signal tracking and timeout handling."""

    signal_id: str
    created_at: float
    expires_at: float
    status: SignalStatus = SignalStatus.PENDING
    processing_started_at: float | None = None
    completed_at: float | None = None
    error_message: str | None = None
    retry_count: int = 0
    deduplication_key: str | None = None


@dataclass(slots=True)
class SignalWrapper:
    """Wrapper for trading signals with metadata."""

    signal: TradingSignal
    metadata: SignalMetadata


@dataclass
class SignalManagerConfig:
    """Configuration for signal manager timeout and cleanup behavior."""

    # Timeout settings (in seconds)
    default_signal_timeout: float = 30.0
    spread_signal_timeout: float = 15.0
    complement_signal_timeout: float = 45.0
    market_making_signal_timeout: float = 60.0

    # Cleanup settings
    cleanup_interval: float = 10.0  # How often to run cleanup
    max_expired_signals: int = 1000  # Max expired signals to keep in memory
    max_failed_signals: int = 500  # Max failed signals to keep in memory

    # Processing settings
    max_concurrent_signals: int = 10
    enable_deduplication: bool = True
    deduplication_window: float = 5.0  # Seconds to check for duplicates

    # Monitoring settings
    enable_metrics: bool = True
    metrics_log_interval: float = 60.0  # How often to log metrics


class SignalTimeoutError(Exception):
    """Raised when a signal expires before processing."""

    pass


class SignalDeduplicationError(Exception):
    """Raised when a duplicate signal is detected."""

    pass


class SignalManager:
    """
    Manages signal lifecycle with timeout handling and automatic cleanup.

    Features:
    - Timestamp tracking for all signals
    - Configurable timeout periods based on signal type
    - Automatic cleanup of stale/expired signals
    - Signal deduplication
    - Processing queue management
    - Metrics and monitoring
    """

    def __init__(self, config: SignalManagerConfig | None = None):
        self.config = config or SignalManagerConfig()

        # Signal storage
        self._pending_signals: dict[str, SignalWrapper] = {}
        self._processing_signals: dict[str, SignalWrapper] = {}
        self._processed_signals: deque[SignalWrapper] = deque(
            maxlen=self.config.max_expired_signals
        )
        self._expired_signals: deque[SignalWrapper] = deque(
            maxlen=self.config.max_expired_signals
        )
        self._failed_signals: deque[SignalWrapper] = deque(
            maxlen=self.config.max_failed_signals
        )

        # Deduplication tracking
        self._dedup_cache: dict[str, float] = {}  # key -> timestamp

        # Processing management
        self._processing_semaphore = asyncio.Semaphore(
            self.config.max_concurrent_signals
        )
        self._signal_processor: Callable[[TradingSignal], None] | None = None

        # Background tasks
        self._cleanup_task: asyncio.Task | None = None
        self._metrics_task: asyncio.Task | None = None
        self._running = False

        # Thread safety
        self._lock = threading.RLock()

        # Metrics
        self._metrics = {
            "signals_received": 0,
            "signals_processed": 0,
            "signals_expired": 0,
            "signals_failed": 0,
            "signals_deduplicated": 0,
            "avg_processing_time": 0.0,
            "last_cleanup_at": 0.0,
        }

        logger.info(f"SignalManager initialized with config: {self.config}")

    def set_signal_processor(self, processor: Callable[[TradingSignal], None]) -> None:
        """Set the signal processor function."""
        self._signal_processor = processor
        logger.info("Signal processor set")

    async def start(self) -> None:
        """Start the signal manager background tasks."""
        if self._running:
            logger.warning("SignalManager already running")
            return

        self._running = True
        logger.info("Starting SignalManager")

        # Start background tasks
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        if self.config.enable_metrics:
            self._metrics_task = asyncio.create_task(self._metrics_loop())

    async def stop(self) -> None:
        """Stop the signal manager and cleanup resources."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping SignalManager")

        # Cancel background tasks
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        if self._metrics_task:
            self._metrics_task.cancel()
            try:
                await self._metrics_task
            except asyncio.CancelledError:
                pass

        # Process any remaining signals quickly
        await self._final_cleanup()

        logger.info("SignalManager stopped")

    def submit_signal(self, signal: TradingSignal) -> str:
        """
        Submit a signal for processing with timeout handling.

        Args:
            signal: The trading signal to process

        Returns:
            signal_id: Unique identifier for tracking the signal

        Raises:
            SignalDeduplicationError: If duplicate signal detected
        """
        with self._lock:
            # Generate signal ID if not present
            if not signal.signal_id:
                signal.signal_id = f"sig_{uuid4().hex[:8]}"

            # Determine timeout based on signal characteristics
            timeout = self._get_signal_timeout(signal)
            current_time = time.time()

            # Create metadata
            metadata = SignalMetadata(
                signal_id=signal.signal_id,
                created_at=current_time,
                expires_at=current_time + timeout,
                deduplication_key=self._generate_dedup_key(signal),
            )

            # Check for deduplication
            if self.config.enable_deduplication and metadata.deduplication_key:
                if self._is_duplicate_signal(metadata.deduplication_key, current_time):
                    self._metrics["signals_deduplicated"] += 1
                    logger.debug(f"Duplicate signal detected: {signal.signal_id}")
                    raise SignalDeduplicationError(
                        f"Duplicate signal: {signal.signal_id}"
                    )

                # Update deduplication cache
                self._dedup_cache[metadata.deduplication_key] = current_time

            # Create wrapper and store
            wrapper = SignalWrapper(signal=signal, metadata=metadata)
            self._pending_signals[signal.signal_id] = wrapper

            self._metrics["signals_received"] += 1

            logger.debug(
                f"Signal submitted: {signal.signal_id} "
                f"(timeout: {timeout}s, expires_at: {metadata.expires_at})"
            )

            # Schedule processing
            try:
                asyncio.get_running_loop()
                asyncio.create_task(self._process_signal_async(wrapper))
            except RuntimeError:
                # If no event loop is running, log warning but continue
                logger.warning(
                    f"No event loop running, signal {signal.signal_id} will not be processed automatically"
                )

            return str(signal.signal_id)

    def get_signal_status(self, signal_id: str) -> SignalStatus | None:
        """Get the current status of a signal."""
        with self._lock:
            # Check pending signals
            if signal_id in self._pending_signals:
                return SignalStatus.PENDING

            # Check processing signals
            if signal_id in self._processing_signals:
                return SignalStatus.PROCESSING

            # Check recent processed/expired/failed signals
            for signals_list in [
                self._processed_signals,
                self._expired_signals,
                self._failed_signals,
            ]:
                for wrapper in signals_list:
                    if wrapper.metadata.signal_id == signal_id:
                        return wrapper.metadata.status

            return None

    def get_metrics(self) -> dict[str, Any]:
        """Get current signal processing metrics."""
        with self._lock:
            return {
                **self._metrics,
                "pending_signals": len(self._pending_signals),
                "processing_signals": len(self._processing_signals),
                "processed_signals": len(self._processed_signals),
                "expired_signals": len(self._expired_signals),
                "failed_signals": len(self._failed_signals),
                "dedup_cache_size": len(self._dedup_cache),
            }

    def _get_signal_timeout(self, signal: TradingSignal) -> float:
        """Determine appropriate timeout for a signal based on its characteristics."""
        # Check if this is a market making signal
        if hasattr(signal, "strategy_type") and signal.strategy_type == "market_making":
            return self.config.market_making_signal_timeout

        # Check signal characteristics to determine type
        market_slug = getattr(signal, "market_slug", "").lower()

        # For high-frequency or spread-based signals, use shorter timeout
        if any(keyword in market_slug for keyword in ["spread", "arb", "mm"]):
            return self.config.spread_signal_timeout

        # For complement arbitrage signals, use longer timeout
        if "complement" in market_slug or hasattr(signal, "complement_deviation"):
            return self.config.complement_signal_timeout

        return self.config.default_signal_timeout

    def _generate_dedup_key(self, signal: TradingSignal) -> str:
        """Generate a deduplication key for a signal."""
        key_parts = [
            signal.market_slug,
            signal.token_id,
            signal.side,
            f"{signal.price:.6f}",
            f"{signal.size:.6f}",
        ]

        # Include outcome type if available
        if signal.outcome_type:
            key_parts.append(signal.outcome_type)

        return "|".join(key_parts)

    def _is_duplicate_signal(self, dedup_key: str, current_time: float) -> bool:
        """Check if a signal is a duplicate within the deduplication window."""
        if dedup_key not in self._dedup_cache:
            return False

        last_seen = self._dedup_cache[dedup_key]
        return (current_time - last_seen) < self.config.deduplication_window

    async def _process_signal_async(self, wrapper: SignalWrapper) -> None:
        """Process a signal asynchronously with timeout handling."""
        signal_id = wrapper.metadata.signal_id

        # Wait for processing slot
        async with self._processing_semaphore:
            # Check if signal has expired before we got to process it
            current_time = time.time()
            if current_time >= wrapper.metadata.expires_at:
                await self._handle_expired_signal(wrapper)
                return

            # Move to processing
            with self._lock:
                if signal_id in self._pending_signals:
                    del self._pending_signals[signal_id]
                    self._processing_signals[signal_id] = wrapper
                    wrapper.metadata.status = SignalStatus.PROCESSING
                    wrapper.metadata.processing_started_at = current_time
                else:
                    # Signal was already processed or expired
                    return

            try:
                # Process the signal
                if self._signal_processor:
                    # Run processor in a thread to avoid blocking
                    await asyncio.get_event_loop().run_in_executor(
                        None, self._signal_processor, wrapper.signal
                    )

                # Mark as completed
                completion_time = time.time()
                with self._lock:
                    if signal_id in self._processing_signals:
                        del self._processing_signals[signal_id]
                        wrapper.metadata.status = SignalStatus.PROCESSED
                        wrapper.metadata.completed_at = completion_time
                        self._processed_signals.append(wrapper)

                        # Update metrics
                        self._metrics["signals_processed"] += 1
                        processing_time = (
                            completion_time - wrapper.metadata.processing_started_at
                        )
                        self._update_avg_processing_time(processing_time)

                logger.debug(f"Signal processed successfully: {signal_id}")

            except Exception as e:
                logger.error(f"Error processing signal {signal_id}: {e}")
                await self._handle_failed_signal(wrapper, str(e))

    async def _handle_expired_signal(self, wrapper: SignalWrapper) -> None:
        """Handle a signal that has expired."""
        signal_id = wrapper.metadata.signal_id

        with self._lock:
            # Remove from pending/processing
            self._pending_signals.pop(signal_id, None)
            self._processing_signals.pop(signal_id, None)

            # Mark as expired
            wrapper.metadata.status = SignalStatus.EXPIRED
            wrapper.metadata.completed_at = time.time()
            self._expired_signals.append(wrapper)

            self._metrics["signals_expired"] += 1

        logger.warning(f"Signal expired: {signal_id}")

    async def _handle_failed_signal(
        self, wrapper: SignalWrapper, error_message: str
    ) -> None:
        """Handle a signal that failed processing."""
        signal_id = wrapper.metadata.signal_id

        with self._lock:
            # Remove from processing
            self._processing_signals.pop(signal_id, None)

            # Mark as failed
            wrapper.metadata.status = SignalStatus.FAILED
            wrapper.metadata.completed_at = time.time()
            wrapper.metadata.error_message = error_message
            self._failed_signals.append(wrapper)

            self._metrics["signals_failed"] += 1

    def _update_avg_processing_time(self, processing_time: float) -> None:
        """Update the average processing time metric."""
        current_avg = self._metrics["avg_processing_time"]
        processed_count = self._metrics["signals_processed"]

        if processed_count == 1:
            self._metrics["avg_processing_time"] = processing_time
        else:
            # Exponential moving average
            self._metrics["avg_processing_time"] = (current_avg * 0.9) + (
                processing_time * 0.1
            )

    async def _cleanup_loop(self) -> None:
        """Background task for cleaning up expired and stale signals."""
        while self._running:
            try:
                await asyncio.sleep(self.config.cleanup_interval)
                await self._cleanup_signals()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")

    async def _cleanup_signals(self) -> None:
        """Clean up expired signals and stale deduplication cache."""
        current_time = time.time()
        expired_signal_ids = []

        with self._lock:
            # Find expired pending signals
            for signal_id, wrapper in list(self._pending_signals.items()):
                if current_time >= wrapper.metadata.expires_at:
                    expired_signal_ids.append(signal_id)

            # Clean up deduplication cache
            stale_dedup_keys = [
                key
                for key, timestamp in self._dedup_cache.items()
                if (current_time - timestamp) > self.config.deduplication_window * 2
            ]

            for key in stale_dedup_keys:
                del self._dedup_cache[key]

            self._metrics["last_cleanup_at"] = current_time

        # Handle expired signals
        for signal_id in expired_signal_ids:
            wrapper = self._pending_signals.get(signal_id)
            if wrapper is not None:
                await self._handle_expired_signal(wrapper)

        if expired_signal_ids or stale_dedup_keys:
            logger.debug(
                f"Cleanup completed: expired {len(expired_signal_ids)} signals, "
                f"removed {len(stale_dedup_keys)} stale dedup entries"
            )

    async def _metrics_loop(self) -> None:
        """Background task for logging metrics."""
        while self._running:
            try:
                await asyncio.sleep(self.config.metrics_log_interval)
                metrics = self.get_metrics()
                logger.info(f"Signal processing metrics: {metrics}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics loop: {e}")

    async def _final_cleanup(self) -> None:
        """Final cleanup when stopping the signal manager."""
        # Process any remaining pending signals quickly or mark them as expired
        current_time = time.time()

        with self._lock:
            for wrapper in list(self._pending_signals.values()):
                if current_time >= wrapper.metadata.expires_at:
                    await self._handle_expired_signal(wrapper)
                else:
                    # Try to process quickly if processor is available
                    if self._signal_processor:
                        try:
                            self._signal_processor(wrapper.signal)
                            wrapper.metadata.status = SignalStatus.PROCESSED
                            wrapper.metadata.completed_at = current_time
                            self._processed_signals.append(wrapper)
                            self._metrics["signals_processed"] += 1
                        except Exception as e:
                            await self._handle_failed_signal(wrapper, str(e))

            self._pending_signals.clear()
            self._processing_signals.clear()
