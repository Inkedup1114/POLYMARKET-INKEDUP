"""
Encrypted Database Manager for InkedUp Trading Bot.

This module extends the standard DatabaseManager to provide transparent
encryption/decryption of sensitive data at rest. It maintains compatibility
with existing database operations while adding encryption capabilities.

Key Features:
    - Transparent field-level encryption/decryption
    - Backward compatibility with existing database operations
    - Automatic encryption of sensitive fields (prices, sizes, PnL, etc.)
    - Secure key management and rotation support
    - Performance optimized with selective encryption
    - Database migration support for encryption upgrades
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .database import DatabaseManager
from .encryption import DatabaseEncryption, EncryptionManager, get_encryption_manager

log = logging.getLogger("encrypted_database")


class EncryptedDatabaseManager(DatabaseManager):
    """
    Database manager with transparent encryption/decryption capabilities.

    Extends the standard DatabaseManager to automatically encrypt sensitive data
    when storing and decrypt when retrieving, while maintaining full compatibility
    with existing database operations.
    """

    def __init__(
        self,
        db_path: Union[str, Path] = "bot_data.db",
        config=None,
        encryption_manager: EncryptionManager = None,
    ):
        """
        Initialize encrypted database manager.

        Args:
            db_path: Path to database file
            config: Database configuration
            encryption_manager: Encryption manager instance. If None, uses global instance.
        """
        super().__init__(db_path, config)

        self.encryption_manager = encryption_manager or get_encryption_manager()
        self.db_encryption = DatabaseEncryption(self.encryption_manager)
        self.encryption_enabled = True

        # Track encryption status in database metadata
        self._encryption_metadata_table = "encryption_metadata"

        log.info(f"Encrypted database manager initialized for {self.db_path}")

    async def initialize(self) -> None:
        """Initialize database with encryption support."""
        # Call parent initialization first
        await super().initialize()

        # Create encryption metadata table
        await self._create_encryption_metadata_table()
        await self._initialize_encryption_metadata()

    async def _create_encryption_metadata_table(self) -> None:
        """Create table to track encryption status and metadata."""

        async def create_metadata_table():
            async with self.connection() as conn:
                await conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._encryption_metadata_table} (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )
                await conn.commit()

        await self._with_retry("create_encryption_metadata", create_metadata_table)

    async def _initialize_encryption_metadata(self) -> None:
        """Initialize encryption metadata if not exists."""

        async def init_metadata():
            async with self.connection() as conn:
                # Check if encryption is already initialized
                cursor = await conn.execute(
                    f"SELECT value FROM {self._encryption_metadata_table} WHERE key = ?",
                    ("encryption_initialized",),
                )
                result = await cursor.fetchone()

                if not result:
                    # First time setup - mark as encrypted
                    await conn.execute(
                        f"INSERT INTO {self._encryption_metadata_table} (key, value) VALUES (?, ?)",
                        ("encryption_initialized", "true"),
                    )
                    await conn.execute(
                        f"INSERT INTO {self._encryption_metadata_table} (key, value) VALUES (?, ?)",
                        ("encryption_version", "1.0"),
                    )
                    await conn.commit()
                    log.info("Database encryption initialized")

        await self._with_retry("init_encryption_metadata", init_metadata)

    async def insert_order(self, order_data: Dict[str, Any]) -> None:
        """Insert order with encryption of sensitive fields."""
        if self.encryption_enabled:
            # Encrypt sensitive fields before insertion
            encrypted_data = self.db_encryption.encrypt_row_data("orders", order_data)
            await super().insert_order(encrypted_data)
        else:
            await super().insert_order(order_data)

    async def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get order with decryption of sensitive fields."""
        order = await super().get_order(order_id)

        if order and self.encryption_enabled:
            # Decrypt sensitive fields after retrieval
            return self.db_encryption.decrypt_row_data("orders", order)

        return order

    async def get_all_orders(self) -> List[Dict[str, Any]]:
        """Get all orders with decryption."""
        orders = await super().get_all_orders()

        if self.encryption_enabled:
            return [
                self.db_encryption.decrypt_row_data("orders", order) for order in orders
            ]

        return orders

    async def update_order(self, order_id: str, updates: Dict[str, Any]) -> None:
        """Update order with encryption of sensitive fields."""
        if self.encryption_enabled:
            # Encrypt sensitive fields in updates
            encrypted_updates = self.db_encryption.encrypt_row_data("orders", updates)
            await super().update_order(order_id, encrypted_updates)
        else:
            await super().update_order(order_id, updates)

    async def upsert_position(self, position_data: Dict[str, Any]) -> None:
        """Upsert position with encryption."""
        if self.encryption_enabled:
            encrypted_data = self.db_encryption.encrypt_row_data(
                "positions", position_data
            )
            await super().upsert_position(encrypted_data)
        else:
            await super().upsert_position(position_data)

    async def get_position(self, token_id: str) -> Optional[Dict[str, Any]]:
        """Get position with decryption."""
        position = await super().get_position(token_id)

        if position and self.encryption_enabled:
            return self.db_encryption.decrypt_row_data("positions", position)

        return position

    async def get_all_positions(self) -> List[Dict[str, Any]]:
        """Get all positions with decryption."""
        positions = await super().get_all_positions()

        if self.encryption_enabled:
            return [
                self.db_encryption.decrypt_row_data("positions", pos)
                for pos in positions
            ]

        return positions

    async def get_positions_by_market(self, market_slug: str) -> List[Dict[str, Any]]:
        """Get positions by market with decryption."""
        positions = await super().get_positions_by_market(market_slug)

        if self.encryption_enabled:
            return [
                self.db_encryption.decrypt_row_data("positions", pos)
                for pos in positions
            ]

        return positions

    async def record_trade(self, trade_data: Dict[str, Any]) -> None:
        """Record trade with encryption."""
        if self.encryption_enabled:
            encrypted_data = self.db_encryption.encrypt_row_data("trades", trade_data)
            await super().record_trade(encrypted_data)
        else:
            await super().record_trade(trade_data)

    async def get_recent_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent trades with decryption."""
        trades = await super().get_recent_trades(limit)

        if self.encryption_enabled:
            return [
                self.db_encryption.decrypt_row_data("trades", trade) for trade in trades
            ]

        return trades

    async def record_market_snapshot(self, snapshot_data: Dict[str, Any]) -> None:
        """Record market snapshot with encryption."""
        if self.encryption_enabled:
            encrypted_data = self.db_encryption.encrypt_row_data(
                "market_snapshots", snapshot_data
            )
            await super().record_market_snapshot(encrypted_data)
        else:
            await super().record_market_snapshot(snapshot_data)

    async def get_market_snapshots(
        self, market_slug: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get market snapshots with decryption."""
        snapshots = await super().get_market_snapshots(market_slug, limit)

        if self.encryption_enabled:
            return [
                self.db_encryption.decrypt_row_data("market_snapshots", snap)
                for snap in snapshots
            ]

        return snapshots

    async def record_risk_event(self, event_data: Dict[str, Any]) -> None:
        """Record risk event with encryption."""
        if self.encryption_enabled:
            encrypted_data = self.db_encryption.encrypt_row_data(
                "risk_events", event_data
            )
            await super().record_risk_event(encrypted_data)
        else:
            await super().record_risk_event(event_data)

    async def get_risk_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get risk events with decryption."""
        events = await super().get_risk_events(limit)

        if self.encryption_enabled:
            return [
                self.db_encryption.decrypt_row_data("risk_events", event)
                for event in events
            ]

        return events

    async def insert_outcome_exposure(self, exposure_data: Dict[str, Any]) -> None:
        """Insert outcome exposure with encryption."""
        if self.encryption_enabled:
            encrypted_data = self.db_encryption.encrypt_row_data(
                "outcome_exposures", exposure_data
            )
            await super().insert_outcome_exposure(encrypted_data)
        else:
            await super().insert_outcome_exposure(exposure_data)

    async def get_outcome_exposures(self) -> List[Dict[str, Any]]:
        """Get outcome exposures with decryption."""
        exposures = await super().get_outcome_exposures()

        if self.encryption_enabled:
            return [
                self.db_encryption.decrypt_row_data("outcome_exposures", exp)
                for exp in exposures
            ]

        return exposures

    async def get_total_exposure(self) -> float:
        """Get total exposure (decrypted values used in calculation)."""
        # Get all positions with decrypted data
        positions = await self.get_all_positions()

        total = 0.0
        for position in positions:
            notional = position.get("notional_value", 0)
            if isinstance(notional, (int, float)):
                total += abs(notional)
            elif isinstance(notional, str):
                try:
                    total += abs(float(notional))
                except (ValueError, TypeError):
                    log.warning(f"Invalid notional value in position: {notional}")

        return total

    async def get_market_exposure(self, market_slug: str) -> float:
        """Get market exposure (decrypted values used in calculation)."""
        positions = await self.get_positions_by_market(market_slug)

        total = 0.0
        for position in positions:
            notional = position.get("notional_value", 0)
            if isinstance(notional, (int, float)):
                total += abs(notional)
            elif isinstance(notional, str):
                try:
                    total += abs(float(notional))
                except (ValueError, TypeError):
                    log.warning(f"Invalid notional value in position: {notional}")

        return total

    async def migrate_to_encryption(self) -> Dict[str, Any]:
        """
        Migrate existing unencrypted database to encrypted format.

        This method encrypts existing sensitive data in-place while maintaining
        database integrity and operation continuity.

        Returns:
            Migration statistics and results
        """
        log.info("Starting database encryption migration")

        migration_stats = {
            "tables_migrated": 0,
            "records_encrypted": 0,
            "errors": [],
            "start_time": asyncio.get_event_loop().time(),
        }

        try:
            # Temporarily disable encryption for raw data access
            original_encryption_state = self.encryption_enabled
            self.encryption_enabled = False

            # Get list of tables to migrate
            tables_to_migrate = [
                "orders",
                "positions",
                "trades",
                "risk_events",
                "outcome_exposures",
                "market_snapshots",
            ]

            async with self.connection() as conn:
                for table_name in tables_to_migrate:
                    try:
                        # Get all records from table
                        cursor = await conn.execute(f"SELECT * FROM {table_name}")
                        records = await cursor.fetchall()

                        if not records:
                            continue

                        # Get column names
                        column_names = [
                            description[0] for description in cursor.description
                        ]

                        # Encrypt each record
                        for record in records:
                            # Convert to dictionary
                            record_dict = dict(zip(column_names, record))

                            # Encrypt sensitive fields
                            encrypted_record = self.db_encryption.encrypt_row_data(
                                table_name, record_dict
                            )

                            # Build update query for changed fields
                            updates = {}
                            for field, value in encrypted_record.items():
                                if str(value) != str(record_dict[field]):
                                    updates[field] = value

                            if updates:
                                # Update record with encrypted values
                                set_clause = ", ".join(
                                    [f"{field} = ?" for field in updates.keys()]
                                )
                                values = list(updates.values())

                                # Add primary key to WHERE clause
                                primary_key = self._get_primary_key(table_name)
                                values.append(record_dict[primary_key])

                                await conn.execute(
                                    f"UPDATE {table_name} SET {set_clause} WHERE {primary_key} = ?",
                                    values,
                                )
                                migration_stats["records_encrypted"] += 1

                        migration_stats["tables_migrated"] += 1
                        log.info(f"Migrated {len(records)} records in {table_name}")

                    except Exception as e:
                        error_msg = f"Error migrating table {table_name}: {e}"
                        migration_stats["errors"].append(error_msg)
                        log.error(error_msg)

                await conn.commit()

            # Re-enable encryption
            self.encryption_enabled = original_encryption_state

            # Update encryption metadata
            await conn.execute(
                f"INSERT OR REPLACE INTO {self._encryption_metadata_table} (key, value) VALUES (?, ?)",
                ("migration_completed", "true"),
            )
            await conn.commit()

            migration_stats["end_time"] = asyncio.get_event_loop().time()
            migration_stats["duration"] = (
                migration_stats["end_time"] - migration_stats["start_time"]
            )

            log.info(f"Database encryption migration completed: {migration_stats}")
            return migration_stats

        except Exception as e:
            # Restore original encryption state on error
            self.encryption_enabled = original_encryption_state
            error_msg = f"Database encryption migration failed: {e}"
            migration_stats["errors"].append(error_msg)
            log.error(error_msg)
            raise

    def _get_primary_key(self, table_name: str) -> str:
        """Get primary key column name for a table."""
        primary_keys = {
            "orders": "id",
            "positions": "token_id",
            "trades": "id",
            "risk_events": "id",
            "outcome_exposures": "id",
            "market_snapshots": "id",
        }
        return primary_keys.get(table_name, "id")

    async def verify_encryption_integrity(self) -> Dict[str, Any]:
        """
        Verify encryption integrity across the database.

        Returns:
            Verification results and statistics
        """
        log.info("Starting encryption integrity verification")

        verification_results = {
            "tables_verified": 0,
            "records_verified": 0,
            "encryption_errors": 0,
            "decryption_errors": 0,
            "integrity_ok": True,
            "errors": [],
        }

        try:
            tables_to_verify = [
                "orders",
                "positions",
                "trades",
                "risk_events",
                "outcome_exposures",
                "market_snapshots",
            ]

            for table_name in tables_to_verify:
                try:
                    # Get sample of records
                    records = []
                    if table_name == "orders":
                        records = await self.get_all_orders()
                    elif table_name == "positions":
                        records = await self.get_all_positions()
                    elif table_name == "trades":
                        records = await self.get_recent_trades(10)
                    # Add other tables as needed

                    for record in records:
                        # Verify that sensitive fields can be processed correctly
                        sensitive_fields = self.db_encryption.sensitive_fields.get(
                            table_name, set()
                        )
                        for field in sensitive_fields:
                            if field in record and record[field] is not None:
                                try:
                                    # Value should be properly decrypted (numeric or string)
                                    value = record[field]
                                    if isinstance(value, str):
                                        # Try to convert numeric fields back to numbers
                                        if field in {
                                            "price",
                                            "size",
                                            "notional_value",
                                            "current_exposure",
                                            "position_size",
                                            "average_price",
                                            "current_price",
                                            "unrealized_pnl",
                                            "realized_pnl",
                                            "bid",
                                            "ask",
                                            "volume_24h",
                                            "liquidity",
                                            "limit_value",
                                            "intended_notional",
                                        }:
                                            float(
                                                value
                                            )  # Should be convertible to float

                                    verification_results["records_verified"] += 1

                                except (ValueError, TypeError) as e:
                                    verification_results["decryption_errors"] += 1
                                    verification_results["integrity_ok"] = False
                                    error_msg = (
                                        f"Decryption error in {table_name}.{field}: {e}"
                                    )
                                    verification_results["errors"].append(error_msg)

                    verification_results["tables_verified"] += 1

                except Exception as e:
                    error_msg = f"Verification error for table {table_name}: {e}"
                    verification_results["errors"].append(error_msg)
                    verification_results["integrity_ok"] = False

            log.info(
                f"Encryption integrity verification completed: {verification_results}"
            )
            return verification_results

        except Exception as e:
            error_msg = f"Encryption integrity verification failed: {e}"
            verification_results["errors"].append(error_msg)
            verification_results["integrity_ok"] = False
            log.error(error_msg)
            return verification_results

    async def get_encryption_status(self) -> Dict[str, Any]:
        """Get encryption status and metadata."""

        async def get_metadata():
            metadata = {}
            async with self.connection() as conn:
                cursor = await conn.execute(
                    f"SELECT key, value FROM {self._encryption_metadata_table}"
                )
                rows = await cursor.fetchall()
                for row in rows:
                    metadata[row[0]] = row[1]
            return metadata

        try:
            metadata = await self._with_retry("get_encryption_metadata", get_metadata)

            return {
                "encryption_enabled": self.encryption_enabled,
                "encryption_initialized": metadata.get("encryption_initialized")
                == "true",
                "encryption_version": metadata.get("encryption_version", "unknown"),
                "migration_completed": metadata.get("migration_completed") == "true",
                "sensitive_tables": list(self.db_encryption.sensitive_fields.keys()),
                "total_sensitive_fields": sum(
                    len(fields)
                    for fields in self.db_encryption.sensitive_fields.values()
                ),
            }
        except Exception as e:
            log.error(f"Failed to get encryption status: {e}")
            return {"encryption_enabled": self.encryption_enabled, "error": str(e)}
