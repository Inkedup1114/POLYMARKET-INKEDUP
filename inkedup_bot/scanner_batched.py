"""
Enhanced Scanner with Order Book Batch Processing Integration.

This module extends the base Scanner with efficient batch database operations
for storing order book snapshots, providing significant performance improvements
during high market volatility periods.

Key Features:
- Batch processing of order book snapshots
- Configurable storage of market data for analysis
- Performance monitoring and metrics
- Seamless integration with existing scanner functionality
- Background storage with minimal scanning impact
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .order_book_batch_processor import (
    BatchConfig,
    OrderBookBatchProcessor,
    OrderBookSnapshot,
    create_batch_processor,
    create_snapshot_from_book_entry,
)

# Try to import existing scanner components
try:
    from .config import BotConfig
    from .scanner import BookEntry, MarketComposite, Scanner

    SCANNER_AVAILABLE = True
except ImportError:
    SCANNER_AVAILABLE = False
    log.error("Scanner components not available")

log = logging.getLogger(__name__)


class EnhancedScanner:
    """
    Enhanced scanner with order book batch processing capabilities.

    Extends the base Scanner functionality with efficient batch database
    operations for storing order book data during market scanning.
    """

    def __init__(
        self,
        cfg: Optional["BotConfig"] = None,
        database_manager: Optional[Any] = None,
        enable_batch_storage: bool = True,
        batch_config: Optional[BatchConfig] = None,
    ):
        """
        Initialize enhanced scanner.

        Args:
            cfg: Bot configuration (same as base Scanner)
            database_manager: Database manager for batch operations
            enable_batch_storage: Whether to enable batch storage of snapshots
            batch_config: Configuration for batch processing
        """
        self.cfg = cfg
        self.database_manager = database_manager
        self.enable_batch_storage = enable_batch_storage

        # Initialize base scanner if available
        if SCANNER_AVAILABLE and cfg:
            self.base_scanner = Scanner(cfg)
        else:
            self.base_scanner = None
            log.warning("Base scanner not available, running in standalone mode")

        # Initialize batch processor
        self.batch_processor: Optional[OrderBookBatchProcessor] = None
        self.batch_config = batch_config or BatchConfig(
            max_batch_size=1000,
            max_queue_size=10000,
            max_batch_age_seconds=30,
            enable_metrics=True,
        )

        # Enhanced metrics
        self.enhanced_metrics = {
            "snapshots_stored": 0,
            "batches_processed": 0,
            "storage_errors": 0,
            "avg_storage_latency_ms": 0.0,
            "last_snapshot_time": 0.0,
        }

        log.info(
            f"EnhancedScanner initialized: "
            f"batch_storage={'enabled' if enable_batch_storage else 'disabled'}, "
            f"batch_size={self.batch_config.max_batch_size}"
        )

    async def start(self) -> None:
        """Start enhanced scanner services."""
        if self.enable_batch_storage and self.database_manager:
            self.batch_processor = await create_batch_processor(
                database_manager=self.database_manager,
                max_batch_size=self.batch_config.max_batch_size,
                max_queue_size=self.batch_config.max_queue_size,
                max_batch_age_seconds=self.batch_config.max_batch_age_seconds,
            )
            log.info("Order book batch processor started")

        log.info("EnhancedScanner started")

    async def stop(self) -> None:
        """Stop enhanced scanner services."""
        if self.batch_processor:
            await self.batch_processor.stop()
            log.info("Order book batch processor stopped")

        log.info("EnhancedScanner stopped")

    async def scan_once_with_storage(self, top: int = 15) -> List["MarketComposite"]:
        """
        Perform market scan with order book batch storage.

        Args:
            top: Number of top markets to scan

        Returns:
            List of MarketComposite objects (same as base scanner)
        """
        if not self.base_scanner:
            log.error("Base scanner not available")
            return []

        try:
            # Perform base scanner operation
            composites = await self.base_scanner.scan_once(top)

            # Store order book snapshots if batch processing enabled
            if self.enable_batch_storage and self.batch_processor:
                await self._store_order_book_snapshots(composites)

            return composites

        except Exception as e:
            log.error(f"Error in enhanced scan: {e}")
            self.enhanced_metrics["storage_errors"] += 1
            return []

    async def _store_order_book_snapshots(
        self, composites: List["MarketComposite"]
    ) -> None:
        """
        Store order book snapshots for all composites in batch.

        Args:
            composites: List of market composites with order book data
        """
        if not self.batch_processor:
            return

        start_time = time.perf_counter()
        snapshots_created = 0

        try:
            current_timestamp = time.time()
            snapshots = []

            # Convert all book entries to snapshots
            for composite in composites:
                for entry in composite.tokens:
                    # Skip entries with no price data
                    if entry.bid is None and entry.ask is None:
                        continue

                    snapshot = self._create_enhanced_snapshot(
                        entry=entry,
                        market_slug=composite.slug,
                        timestamp=current_timestamp,
                        volatility_score=composite.volatility_score,
                    )
                    snapshots.append(snapshot)
                    snapshots_created += 1

            # Add snapshots to batch processor
            if snapshots:
                added_count = await self.batch_processor.add_snapshots_batch(snapshots)

                # Update metrics
                self.enhanced_metrics["snapshots_stored"] += added_count
                self.enhanced_metrics["last_snapshot_time"] = current_timestamp

                if added_count < len(snapshots):
                    log.warning(
                        f"Only {added_count}/{len(snapshots)} snapshots queued (queue full)"
                    )

            # Update latency metrics
            processing_time_ms = (time.perf_counter() - start_time) * 1000
            self._update_storage_latency(processing_time_ms)

            log.debug(
                f"Created {snapshots_created} snapshots from {len(composites)} composites "
                f"in {processing_time_ms:.1f}ms"
            )

        except Exception as e:
            log.error(f"Error storing order book snapshots: {e}")
            self.enhanced_metrics["storage_errors"] += 1

    def _create_enhanced_snapshot(
        self,
        entry: "BookEntry",
        market_slug: str,
        timestamp: float,
        volatility_score: Optional[float] = None,
    ) -> OrderBookSnapshot:
        """
        Create enhanced order book snapshot with additional metadata.

        Args:
            entry: BookEntry from scanner
            market_slug: Market identifier
            timestamp: Snapshot timestamp
            volatility_score: Optional market volatility score

        Returns:
            Enhanced OrderBookSnapshot
        """
        # Calculate additional metrics
        mid_price = None
        liquidity_score = None

        if entry.bid is not None and entry.ask is not None:
            mid_price = (entry.bid + entry.ask) / 2

            # Simple liquidity score based on spread
            if entry.spread_bps is not None and entry.spread_bps > 0:
                # Lower spread = higher liquidity score (inverted and normalized)
                liquidity_score = max(
                    0.0, 1.0 - (entry.spread_bps / 1000)
                )  # Normalize by 10% spread

        return OrderBookSnapshot(
            token_id=entry.token_id,
            market_slug=market_slug,
            timestamp=timestamp,
            bid_price=entry.bid,
            ask_price=entry.ask,
            spread_bps=entry.spread_bps,
            mid_price=mid_price,
            liquidity_score=liquidity_score,
            volatility_score=volatility_score,
        )

    def _update_storage_latency(self, processing_time_ms: float) -> None:
        """Update storage latency metrics."""
        current_avg = self.enhanced_metrics["avg_storage_latency_ms"]
        snapshots_count = self.enhanced_metrics["snapshots_stored"]

        if snapshots_count > 0:
            self.enhanced_metrics["avg_storage_latency_ms"] = (
                current_avg * (snapshots_count - 1) + processing_time_ms
            ) / snapshots_count

    async def adaptive_loop_with_storage(self, top: int = 15) -> None:
        """
        Adaptive scanning loop with order book storage.

        Extends the base scanner's adaptive loop to include batch storage
        of order book data during scanning.

        Args:
            top: Number of markets to scan
        """
        if not self.base_scanner:
            log.error("Base scanner not available for adaptive loop")
            return

        log.info("Starting enhanced adaptive scanning loop with order book storage")

        try:
            while True:
                # Determine scan interval (delegate to base scanner if available)
                if hasattr(self.base_scanner, "_determine_adaptive_interval"):
                    interval = self.base_scanner._determine_adaptive_interval()
                else:
                    interval = 10.0  # Default 10 second interval

                # Perform scan with storage
                scan_start = time.perf_counter()
                composites = await self.scan_once_with_storage(top)
                scan_duration = time.perf_counter() - scan_start

                # Log performance
                if composites:
                    log.debug(
                        f"Enhanced scan completed: {len(composites)} markets, "
                        f"{scan_duration:.2f}s scan time, "
                        f"next scan in {interval:.1f}s"
                    )

                # Wait for next scan
                await asyncio.sleep(interval)

        except KeyboardInterrupt:
            log.info("Enhanced adaptive loop stopped by user")
        except Exception as e:
            log.error(f"Error in enhanced adaptive loop: {e}")
            raise

    def get_enhanced_metrics(self) -> Dict[str, Any]:
        """Get enhanced scanner performance metrics."""
        base_metrics = {}

        # Get base scanner metrics if available
        if self.base_scanner and hasattr(self.base_scanner, "get_adaptive_stats"):
            base_metrics = self.base_scanner.get_adaptive_stats()

        # Get batch processor metrics if available
        batch_metrics = {}
        if self.batch_processor:
            batch_metrics = self.batch_processor.get_performance_metrics()

        # Combine all metrics
        return {
            "enhanced_scanner": self.enhanced_metrics.copy(),
            "base_scanner": base_metrics,
            "batch_processor": batch_metrics,
            "configuration": {
                "batch_storage_enabled": self.enable_batch_storage,
                "batch_config": {
                    "max_batch_size": self.batch_config.max_batch_size,
                    "max_queue_size": self.batch_config.max_queue_size,
                    "max_batch_age_seconds": self.batch_config.max_batch_age_seconds,
                },
            },
        }

    def get_storage_summary(self) -> Dict[str, Any]:
        """Get summary of order book storage performance."""
        metrics = self.enhanced_metrics

        summary = {
            "storage_enabled": self.enable_batch_storage,
            "snapshots_stored": metrics["snapshots_stored"],
            "storage_errors": metrics["storage_errors"],
            "avg_storage_latency_ms": metrics["avg_storage_latency_ms"],
            "last_snapshot_time": metrics["last_snapshot_time"],
        }

        # Add batch processor summary if available
        if self.batch_processor:
            batch_metrics = self.batch_processor.get_performance_metrics()
            summary.update(
                {
                    "batch_throughput_rec_per_sec": batch_metrics["processing_stats"][
                        "records_per_second"
                    ],
                    "batch_queue_utilization": batch_metrics["resources"][
                        "queue_utilization"
                    ],
                    "batch_error_rate": batch_metrics["errors"]["error_rate"],
                }
            )

        return summary

    async def get_stored_snapshots(
        self,
        market_slug: Optional[str] = None,
        token_id: Optional[str] = None,
        hours: int = 24,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve stored order book snapshots.

        Args:
            market_slug: Filter by market slug
            token_id: Filter by token ID
            hours: Hours of data to retrieve
            limit: Maximum number of records

        Returns:
            List of stored snapshots
        """
        if not self.batch_processor:
            return []

        return await self.batch_processor.get_recent_snapshots(
            token_id=token_id, market_slug=market_slug, hours=hours, limit=limit
        )

    # Delegate other methods to base scanner
    def __getattr__(self, name):
        """Delegate unknown attributes to base scanner."""
        if self.base_scanner and hasattr(self.base_scanner, name):
            return getattr(self.base_scanner, name)
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'"
        )


# Integration utilities
class ScannerBatchingUpgrade:
    """
    Utility class to upgrade existing Scanner instances with batch processing.

    This allows adding batch processing to existing scanners without
    requiring major refactoring.
    """

    def __init__(
        self,
        existing_scanner: Any,
        database_manager: Any,
        batch_config: Optional[BatchConfig] = None,
    ):
        """
        Initialize scanner batching upgrade.

        Args:
            existing_scanner: Existing Scanner instance
            database_manager: Database manager for batch operations
            batch_config: Optional batch configuration
        """
        self.scanner = existing_scanner
        self.database_manager = database_manager
        self.batch_config = batch_config or BatchConfig()

        # Initialize batch processor
        self.batch_processor: Optional[OrderBookBatchProcessor] = None

        # Performance tracking
        self.upgrade_metrics = {
            "enhanced_scans": 0,
            "snapshots_stored": 0,
            "storage_time_ms": 0.0,
        }

    async def start(self) -> None:
        """Start batch processing upgrade."""
        self.batch_processor = await create_batch_processor(
            database_manager=self.database_manager,
            max_batch_size=self.batch_config.max_batch_size,
            max_queue_size=self.batch_config.max_queue_size,
            max_batch_age_seconds=self.batch_config.max_batch_age_seconds,
        )

        log.info("Scanner batch processing upgrade started")

    async def stop(self) -> None:
        """Stop batch processing upgrade."""
        if self.batch_processor:
            await self.batch_processor.stop()

        log.info("Scanner batch processing upgrade stopped")

    async def enhanced_scan_once(self, *args, **kwargs) -> List[Any]:
        """
        Enhanced scan_once with batch storage.

        Performs the original scan_once and adds batch storage.
        """
        if not self.batch_processor:
            log.warning("Batch processor not available, performing standard scan")
            return await self.scanner.scan_once(*args, **kwargs)

        start_time = time.perf_counter()

        # Perform original scan
        composites = await self.scanner.scan_once(*args, **kwargs)

        # Add batch storage
        snapshots = []
        current_timestamp = time.time()

        for composite in composites:
            for entry in composite.tokens:
                if entry.bid is not None or entry.ask is not None:
                    snapshot = create_snapshot_from_book_entry(
                        entry=entry,
                        market_slug=composite.slug,
                        timestamp=current_timestamp,
                    )
                    # Add volatility score if available
                    if (
                        hasattr(composite, "volatility_score")
                        and composite.volatility_score is not None
                    ):
                        snapshot.volatility_score = composite.volatility_score

                    snapshots.append(snapshot)

        # Queue snapshots for batch processing
        if snapshots:
            added_count = await self.batch_processor.add_snapshots_batch(snapshots)
            self.upgrade_metrics["snapshots_stored"] += added_count

        # Update metrics
        processing_time = (time.perf_counter() - start_time) * 1000
        self.upgrade_metrics["enhanced_scans"] += 1
        self.upgrade_metrics["storage_time_ms"] += processing_time

        return composites

    def get_upgrade_metrics(self) -> Dict[str, Any]:
        """Get upgrade performance metrics."""
        metrics = {
            "upgrade_stats": self.upgrade_metrics.copy(),
            "batch_processor": None,
        }

        if self.batch_processor:
            metrics["batch_processor"] = self.batch_processor.get_performance_metrics()

        return metrics


# Factory functions
async def create_enhanced_scanner(
    cfg: Optional["BotConfig"] = None,
    database_manager: Optional[Any] = None,
    enable_batch_storage: bool = True,
    max_batch_size: int = 1000,
    max_queue_size: int = 10000,
) -> EnhancedScanner:
    """
    Factory function to create and start enhanced scanner.

    Args:
        cfg: Bot configuration
        database_manager: Database manager instance
        enable_batch_storage: Whether to enable batch storage
        max_batch_size: Maximum records per batch
        max_queue_size: Maximum queued records

    Returns:
        Started EnhancedScanner instance
    """
    batch_config = BatchConfig(
        max_batch_size=max_batch_size,
        max_queue_size=max_queue_size,
        enable_metrics=True,
    )

    scanner = EnhancedScanner(
        cfg=cfg,
        database_manager=database_manager,
        enable_batch_storage=enable_batch_storage,
        batch_config=batch_config,
    )

    await scanner.start()
    return scanner


async def upgrade_existing_scanner(
    existing_scanner: Any, database_manager: Any, max_batch_size: int = 1000
) -> ScannerBatchingUpgrade:
    """
    Upgrade existing scanner with batch processing capabilities.

    Args:
        existing_scanner: Existing Scanner instance
        database_manager: Database manager instance
        max_batch_size: Maximum records per batch

    Returns:
        Started ScannerBatchingUpgrade instance
    """
    batch_config = BatchConfig(max_batch_size=max_batch_size)

    upgrade = ScannerBatchingUpgrade(
        existing_scanner=existing_scanner,
        database_manager=database_manager,
        batch_config=batch_config,
    )

    await upgrade.start()
    return upgrade
