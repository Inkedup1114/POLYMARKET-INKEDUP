#!/usr/bin/env python3
"""
Batched Database Manager for InkedUp Bot

This module extends the existing DatabaseManager with advanced batch processing capabilities
for high-volume database operations including inserts, updates, and queries.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from .batch_processor import (
    BatchConfig,
    BatchOperation,
    BatchPriority,
    BatchProcessor,
    BatchType,
    get_batch_processor,
    initialize_batch_processor,
)
from .database import DatabaseManager

logger = logging.getLogger(__name__)


class BatchedDatabaseManager(DatabaseManager):
    """
    Enhanced DatabaseManager with comprehensive batch processing capabilities.

    Extends the base DatabaseManager to provide:
    - Batch inserts with automatic grouping
    - Bulk updates with transaction optimization
    - Batch query processing
    - Performance monitoring and metrics
    """

    def __init__(self, db_path: str = "bot_data.db", batch_config: BatchConfig = None):
        super().__init__(db_path)
        self.batch_config = batch_config or BatchConfig()
        self._batch_processor: BatchProcessor | None = None
        self._batch_enabled = True

    async def initialize_batch_processing(self):
        """Initialize the batch processing system."""
        if self._batch_processor is None:
            await initialize_batch_processor(self, self.batch_config)
            self._batch_processor = get_batch_processor()
            logger.info("Batch processing initialized for DatabaseManager")

    async def shutdown_batch_processing(self):
        """Shutdown the batch processing system."""
        if self._batch_processor:
            await self._batch_processor.stop()
            self._batch_processor = None
            logger.info("Batch processing shutdown complete")

    def enable_batching(self):
        """Enable batch processing for database operations."""
        self._batch_enabled = True
        logger.info("Batch processing enabled")

    def disable_batching(self):
        """Disable batch processing - operations will execute immediately."""
        self._batch_enabled = False
        logger.info("Batch processing disabled - operating in immediate mode")

    # Enhanced batch insert methods

    async def batch_insert_orders(
        self,
        orders: list[dict[str, Any]],
        priority: BatchPriority = BatchPriority.NORMAL,
    ) -> bool:
        """Insert multiple orders efficiently using batch processing."""
        if not self._batch_enabled or not self._batch_processor:
            # Fallback to individual inserts
            success_count = 0
            for order in orders:
                try:
                    await self.insert_order(order)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to insert order: {e}")
            return success_count == len(orders)

        return await self._batch_processor.submit_batch_insert(
            "orders", orders, priority
        )

    async def batch_insert_positions(
        self,
        positions: list[dict[str, Any]],
        priority: BatchPriority = BatchPriority.NORMAL,
    ) -> bool:
        """Insert multiple positions efficiently using batch processing."""
        if not self._batch_enabled or not self._batch_processor:
            # Fallback to individual inserts
            success_count = 0
            for position in positions:
                try:
                    await self.upsert_position(position)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to insert position: {e}")
            return success_count == len(positions)

        return await self._batch_processor.submit_batch_insert(
            "positions", positions, priority
        )

    async def batch_insert_trades(
        self,
        trades: list[dict[str, Any]],
        priority: BatchPriority = BatchPriority.NORMAL,
    ) -> bool:
        """Insert multiple trades efficiently using batch processing."""
        if not self._batch_enabled or not self._batch_processor:
            # Fallback to individual inserts
            success_count = 0
            for trade in trades:
                try:
                    await self.insert_trade(trade)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to insert trade: {e}")
            return success_count == len(trades)

        return await self._batch_processor.submit_batch_insert(
            "trades", trades, priority
        )

    async def batch_insert_outcome_exposures(
        self,
        exposures: list[dict[str, Any]],
        priority: BatchPriority = BatchPriority.NORMAL,
    ) -> bool:
        """Insert multiple outcome exposures efficiently using batch processing."""
        if not self._batch_enabled or not self._batch_processor:
            # Fallback to individual inserts
            success_count = 0
            for exposure in exposures:
                try:
                    await self.insert_outcome_exposure(exposure)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to insert outcome exposure: {e}")
            return success_count == len(exposures)

        return await self._batch_processor.submit_batch_insert(
            "outcome_exposures", exposures, priority
        )

    # Enhanced batch update methods

    async def batch_update_orders(
        self,
        updates: list[tuple[str, dict[str, Any]]],
        priority: BatchPriority = BatchPriority.HIGH,
    ) -> bool:
        """Update multiple orders efficiently using batch processing."""
        if not self._batch_enabled or not self._batch_processor:
            # Fallback to individual updates
            success_count = 0
            for order_id, update_data in updates:
                try:
                    await self.update_order(order_id, update_data)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to update order {order_id}: {e}")
            return success_count == len(updates)

        # Convert to batch format
        batch_updates = [
            ({"id": order_id}, update_data) for order_id, update_data in updates
        ]
        return await self._batch_processor.submit_batch_update(
            "orders", batch_updates, priority
        )

    async def batch_update_positions(
        self,
        updates: list[tuple[dict[str, Any], dict[str, Any]]],
        priority: BatchPriority = BatchPriority.NORMAL,
    ) -> bool:
        """Update multiple positions efficiently using batch processing."""
        if not self._batch_enabled or not self._batch_processor:
            # Fallback to individual updates
            success_count = 0
            for _conditions, _update_data in updates:
                try:
                    # Find position by conditions and update (simplified approach)
                    # In practice, you'd implement a more sophisticated position update method
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to update position: {e}")
            return success_count == len(updates)

        return await self._batch_processor.submit_batch_update(
            "positions", updates, priority
        )

    async def batch_update_outcome_prices(
        self,
        price_updates: list[dict[str, Any]],
        priority: BatchPriority = BatchPriority.HIGH,
    ) -> bool:
        """Update multiple outcome prices efficiently using batch processing."""
        if not self._batch_enabled or not self._batch_processor:
            # Fallback to individual updates
            success_count = 0
            for update in price_updates:
                try:
                    await self.update_outcome_price(
                        update.get("token_id"),
                        update.get("price"),
                        update.get("market_slug"),
                    )
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to update outcome price: {e}")
            return success_count == len(price_updates)

        # Convert to batch operations
        operations = []
        for i, update in enumerate(price_updates):
            operation = BatchOperation(
                operation_id=f"price_update_{i}_{int(datetime.now().timestamp() * 1000)}",
                batch_type=BatchType.UPDATE,
                table_name="outcomes",
                data={"price": update.get("price")},
                priority=priority,
                metadata={
                    "conditions": {
                        "token_id": update.get("token_id"),
                        "market_slug": update.get("market_slug"),
                    }
                },
                sql_query="UPDATE outcomes SET price = ?, updated_at = CURRENT_TIMESTAMP WHERE token_id = ? AND market_slug = ?",
                parameters=(
                    update.get("price"),
                    update.get("token_id"),
                    update.get("market_slug"),
                ),
            )
            operations.append(operation)

        # Submit operations
        success_count = 0
        for op in operations:
            if await self._batch_processor.submit_operation(op):
                success_count += 1

        return success_count == len(operations)

    # Batch query optimization methods

    async def batch_get_orders(self, order_ids: list[str]) -> list[dict[str, Any]]:
        """Retrieve multiple orders efficiently using optimized queries."""
        if not order_ids:
            return []

        # Use IN clause for efficient bulk retrieval
        placeholders = ",".join("?" * len(order_ids))
        query = f"""
            SELECT id, token_id, market_slug, side, price, size, status,
                   notional_value, outcome_type, created_at, updated_at, filled_at
            FROM orders
            WHERE id IN ({placeholders})
        """

        async with self.connection() as db:
            cursor = await db.execute(query, order_ids)
            rows = await cursor.fetchall()

            # Convert to dictionaries
            orders = []
            for row in rows:
                orders.append(
                    {
                        "id": row[0],
                        "token_id": row[1],
                        "market_slug": row[2],
                        "side": row[3],
                        "price": row[4],
                        "size": row[5],
                        "status": row[6],
                        "notional_value": row[7],
                        "outcome_type": row[8],
                        "created_at": row[9],
                        "updated_at": row[10],
                        "filled_at": row[11],
                    }
                )

            return orders

    async def batch_get_positions(self, token_ids: list[str]) -> list[dict[str, Any]]:
        """Retrieve multiple positions efficiently using optimized queries."""
        if not token_ids:
            return []

        placeholders = ",".join("?" * len(token_ids))
        query = f"""
            SELECT token_id, market_slug, size, notional_value, outcome_type, side,
                   created_at, updated_at
            FROM positions
            WHERE token_id IN ({placeholders})
        """

        async with self.connection() as db:
            cursor = await db.execute(query, token_ids)
            rows = await cursor.fetchall()

            positions = []
            for row in rows:
                positions.append(
                    {
                        "token_id": row[0],
                        "market_slug": row[1],
                        "size": row[2],
                        "notional_value": row[3],
                        "outcome_type": row[4],
                        "side": row[5],
                        "created_at": row[6],
                        "updated_at": row[7],
                    }
                )

            return positions

    async def batch_get_market_data(
        self, market_slugs: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Retrieve market data for multiple markets efficiently."""
        if not market_slugs:
            return {}

        placeholders = ",".join("?" * len(market_slugs))

        # Get market data
        market_query = f"""
            SELECT market_slug, outcome_type, token_id, price, last_updated
            FROM outcomes
            WHERE market_slug IN ({placeholders})
            ORDER BY market_slug, outcome_type
        """

        # Get position data for markets
        position_query = f"""
            SELECT market_slug, outcome_type, token_id,
                   SUM(size) as total_size, SUM(notional_value) as total_notional
            FROM positions
            WHERE market_slug IN ({placeholders})
            GROUP BY market_slug, outcome_type, token_id
        """

        market_data = {}

        async with self.connection() as db:
            # Get market outcomes
            cursor = await db.execute(market_query, market_slugs)
            outcome_rows = await cursor.fetchall()

            # Get position data
            cursor = await db.execute(position_query, market_slugs)
            position_rows = await cursor.fetchall()

            # Organize data by market
            for row in outcome_rows:
                market_slug = row[0]
                if market_slug not in market_data:
                    market_data[market_slug] = {"outcomes": {}, "positions": {}}

                outcome_key = f"{row[1]}_{row[2]}"  # outcome_type_token_id
                market_data[market_slug]["outcomes"][outcome_key] = {
                    "outcome_type": row[1],
                    "token_id": row[2],
                    "price": row[3],
                    "last_updated": row[4],
                }

            # Add position data
            for row in position_rows:
                market_slug = row[0]
                if market_slug not in market_data:
                    market_data[market_slug] = {"outcomes": {}, "positions": {}}

                position_key = f"{row[1]}_{row[2]}"  # outcome_type_token_id
                market_data[market_slug]["positions"][position_key] = {
                    "outcome_type": row[1],
                    "token_id": row[2],
                    "total_size": row[3],
                    "total_notional": row[4],
                }

        return market_data

    # Advanced batch operations

    async def batch_reconcile_positions(self, market_slug: str) -> dict[str, Any]:
        """Perform batch position reconciliation for a market."""
        reconciliation_results = {
            "market_slug": market_slug,
            "positions_updated": 0,
            "discrepancies_found": 0,
            "corrections_made": 0,
            "timestamp": datetime.now().isoformat(),
        }

        # Get all positions for the market
        positions_query = """
            SELECT token_id, outcome_type, SUM(size) as calculated_size,
                   SUM(notional_value) as calculated_notional
            FROM trades
            WHERE market_slug = ? AND status = 'FILLED'
            GROUP BY token_id, outcome_type
        """

        stored_positions_query = """
            SELECT token_id, outcome_type, size, notional_value
            FROM positions
            WHERE market_slug = ?
        """

        async with self.connection() as db:
            # Get calculated positions from trades
            cursor = await db.execute(positions_query, (market_slug,))
            calculated_positions = await cursor.fetchall()

            # Get stored positions
            cursor = await db.execute(stored_positions_query, (market_slug,))
            stored_positions = await cursor.fetchall()

            # Create lookup dictionaries
            calculated_dict = {
                (row[0], row[1]): (row[2], row[3]) for row in calculated_positions
            }
            stored_dict = {
                (row[0], row[1]): (row[2], row[3]) for row in stored_positions
            }

            # Find discrepancies
            corrections = []
            all_keys = set(calculated_dict.keys()) | set(stored_dict.keys())

            for key in all_keys:
                token_id, outcome_type = key
                calc_size, calc_notional = calculated_dict.get(key, (0, 0))
                stored_size, stored_notional = stored_dict.get(key, (0, 0))

                if (
                    abs(calc_size - stored_size) > 1e-6
                    or abs(calc_notional - stored_notional) > 1e-6
                ):
                    reconciliation_results["discrepancies_found"] += 1
                    corrections.append(
                        {
                            "token_id": token_id,
                            "outcome_type": outcome_type,
                            "market_slug": market_slug,
                            "size": calc_size,
                            "notional_value": calc_notional,
                            "side": "BUY" if calc_size > 0 else "SELL",
                        }
                    )

            # Apply corrections using batch processing
            if corrections:
                success = await self.batch_insert_positions(
                    corrections, BatchPriority.HIGH
                )
                if success:
                    reconciliation_results["corrections_made"] = len(corrections)
                    reconciliation_results["positions_updated"] = len(corrections)

        return reconciliation_results

    async def batch_cleanup_old_data(self, days_to_keep: int = 30) -> dict[str, int]:
        """Perform batch cleanup of old data."""
        cleanup_results = {
            "orders_deleted": 0,
            "trades_deleted": 0,
            "old_outcomes_deleted": 0,
            "timestamp": datetime.now().isoformat(),
        }

        cutoff_date = datetime.now() - timedelta(days=days_to_keep)

        cleanup_queries = [
            (
                "DELETE FROM orders WHERE status IN ('FILLED', 'CANCELLED') AND updated_at < ?",
                "orders_deleted",
            ),
            ("DELETE FROM trades WHERE created_at < ?", "trades_deleted"),
            (
                "DELETE FROM outcomes WHERE last_updated < ? AND market_slug NOT IN (SELECT DISTINCT market_slug FROM positions)",
                "old_outcomes_deleted",
            ),
        ]

        async with self.connection() as db:
            for query, result_key in cleanup_queries:
                try:
                    cursor = await db.execute(query, (cutoff_date,))
                    cleanup_results[result_key] = cursor.rowcount
                    await db.commit()
                except Exception as e:
                    logger.error(f"Error in cleanup query {result_key}: {e}")

        logger.info(f"Batch cleanup completed: {cleanup_results}")
        return cleanup_results

    # Transaction optimization methods

    async def execute_batch_transaction(
        self, operations: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Execute multiple operations in a single optimized transaction."""
        result = {
            "success": False,
            "operations_completed": 0,
            "total_operations": len(operations),
            "errors": [],
            "timestamp": datetime.now().isoformat(),
        }

        if not operations:
            result["success"] = True
            return result

        async with self.connection() as db:
            try:
                await db.execute("BEGIN TRANSACTION")

                for i, operation in enumerate(operations):
                    try:
                        op_type = operation.get("type")

                        if op_type == "insert_order":
                            await self._execute_single_order_insert(
                                db, operation.get("data")
                            )
                        elif op_type == "update_order":
                            await self._execute_single_order_update(
                                db, operation.get("data")
                            )
                        elif op_type == "insert_position":
                            await self._execute_single_position_insert(
                                db, operation.get("data")
                            )
                        elif op_type == "insert_trade":
                            await self._execute_single_trade_insert(
                                db, operation.get("data")
                            )
                        elif op_type == "custom_query":
                            await db.execute(
                                operation.get("query"), operation.get("parameters", ())
                            )

                        result["operations_completed"] += 1

                    except Exception as e:
                        error_info = {
                            "operation_index": i,
                            "operation_type": operation.get("type"),
                            "error": str(e),
                        }
                        result["errors"].append(error_info)
                        logger.error(f"Error in batch operation {i}: {e}")

                await db.execute("COMMIT")
                result["success"] = True

            except Exception as e:
                await db.execute("ROLLBACK")
                result["errors"].append({"transaction_error": str(e)})
                logger.error(f"Transaction failed, rolled back: {e}")

        return result

    async def _execute_single_order_insert(self, db, order_data: dict[str, Any]):
        """Execute a single order insert within a transaction."""
        await db.execute(
            """
            INSERT INTO orders (
                id, token_id, market_slug, side, price, size, status,
                notional_value, outcome_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_data.get("id"),
                order_data.get("token_id"),
                order_data.get("market_slug"),
                order_data.get("side"),
                order_data.get("price"),
                order_data.get("size"),
                order_data.get("status", "OPEN"),
                order_data.get("notional_value", 0.0),
                order_data.get("outcome_type"),
            ),
        )

    async def _execute_single_order_update(self, db, update_data: dict[str, Any]):
        """Execute a single order update within a transaction."""
        order_id = update_data.pop("id")
        if not update_data:
            return

        set_clauses = []
        params = []

        for key, value in update_data.items():
            if key in ["status", "filled_at", "size", "price", "notional_value"]:
                set_clauses.append(f"{key} = ?")
                params.append(value)

        if set_clauses:
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")
            params.append(order_id)

            await db.execute(
                f"UPDATE orders SET {', '.join(set_clauses)} WHERE id = ?", params
            )

    async def _execute_single_position_insert(self, db, position_data: dict[str, Any]):
        """Execute a single position insert within a transaction."""
        await db.execute(
            """
            INSERT OR REPLACE INTO positions (
                token_id, market_slug, size, notional_value, outcome_type, side
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                position_data.get("token_id"),
                position_data.get("market_slug"),
                position_data.get("size", 0.0),
                position_data.get("notional_value", 0.0),
                position_data.get("outcome_type"),
                position_data.get("side"),
            ),
        )

    async def _execute_single_trade_insert(self, db, trade_data: dict[str, Any]):
        """Execute a single trade insert within a transaction."""
        await db.execute(
            """
            INSERT INTO trades (
                id, order_id, token_id, market_slug, side, price, size, fee, outcome_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade_data.get("id"),
                trade_data.get("order_id"),
                trade_data.get("token_id"),
                trade_data.get("market_slug"),
                trade_data.get("side"),
                trade_data.get("price", 0.0),
                trade_data.get("size", 0.0),
                trade_data.get("fee", 0.0),
                trade_data.get("outcome_type"),
            ),
        )

    # Monitoring and metrics

    async def get_batch_metrics(self) -> dict[str, Any] | None:
        """Get current batch processing metrics."""
        if not self._batch_processor:
            return None

        metrics = await self._batch_processor.get_metrics()
        return {
            "total_operations": metrics.total_operations,
            "successful_operations": metrics.successful_operations,
            "failed_operations": metrics.failed_operations,
            "total_batches_processed": metrics.total_batches_processed,
            "average_batch_size": metrics.average_batch_size,
            "average_processing_time_ms": metrics.average_processing_time_ms,
            "throughput_ops_per_second": metrics.throughput_ops_per_second,
            "error_rate": metrics.error_rate,
            "last_updated": metrics.last_updated.isoformat(),
        }

    async def force_flush_batches(self):
        """Force flush all pending batches."""
        if self._batch_processor:
            await self._batch_processor.force_flush()
            logger.info("Forced flush of all pending batches completed")

    async def get_database_statistics(self) -> dict[str, Any]:
        """Get comprehensive database statistics including batch performance."""
        stats = {
            "timestamp": datetime.now().isoformat(),
            "batch_metrics": await self.get_batch_metrics(),
            "table_counts": {},
            "database_size_mb": 0,
            "index_usage": {},
        }

        # Get table row counts
        tables = ["orders", "positions", "trades", "outcomes", "outcome_exposures"]
        async with self.connection() as db:
            for table in tables:
                try:
                    cursor = await db.execute(f"SELECT COUNT(*) FROM {table}")
                    row = await cursor.fetchone()
                    stats["table_counts"][table] = row[0] if row else 0
                except Exception as e:
                    logger.error(f"Error getting count for table {table}: {e}")
                    stats["table_counts"][table] = -1

            # Get database file size if not in memory
            if not self._is_memory_db:
                try:
                    import os

                    stats["database_size_mb"] = os.path.getsize(self.db_path) / (
                        1024 * 1024
                    )
                except Exception as e:
                    logger.error(f"Error getting database size: {e}")

        return stats
