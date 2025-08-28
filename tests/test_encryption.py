"""
Comprehensive tests for the encryption at rest system.

Tests all aspects of the encryption functionality including basic encryption/decryption,
database integration, configuration encryption, key management, and migration procedures.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from inkedup_bot.config import BotConfig
from inkedup_bot.config_encrypted import EncryptedBotConfig, EncryptedEnvironmentManager
from inkedup_bot.database_encrypted import EncryptedDatabaseManager
from inkedup_bot.encryption import (
    ConfigurationEncryption,
    DatabaseEncryption,
    EncryptionManager,
    setup_encryption,
)


class TestEncryptionManager:
    """Test the core encryption functionality."""

    def test_encryption_manager_initialization(self):
        """Test encryption manager initializes correctly."""
        encryption = EncryptionManager("test_master_key_123456789012345678901234")

        assert encryption.master_key == "test_master_key_123456789012345678901234"
        assert encryption.salt_length == 32
        assert encryption.nonce_length == 16
        assert encryption.key_length == 32
        assert encryption.iterations == 100000

    def test_basic_encryption_decryption(self):
        """Test basic encryption and decryption of values."""
        encryption = EncryptionManager("test_master_key_123456789012345678901234")

        original_value = "sensitive_data_12345"
        encrypted_value = encryption.encrypt_value(original_value)
        decrypted_value = encryption.decrypt_value(encrypted_value)

        assert original_value == decrypted_value
        assert encrypted_value != original_value
        assert len(encrypted_value) > len(
            original_value
        )  # Should be longer due to encoding

    def test_encryption_with_context(self):
        """Test encryption with different contexts produces different results."""
        encryption = EncryptionManager("test_master_key_123456789012345678901234")

        value = "same_value"
        encrypted_1 = encryption.encrypt_value(value, "context1")
        encrypted_2 = encryption.encrypt_value(value, "context2")

        # Different contexts should produce different encrypted values
        assert encrypted_1 != encrypted_2

        # But both should decrypt correctly with their respective contexts
        assert encryption.decrypt_value(encrypted_1, "context1") == value
        assert encryption.decrypt_value(encrypted_2, "context2") == value

    def test_encryption_with_bytes(self):
        """Test encryption of byte data."""
        encryption = EncryptionManager("test_master_key_123456789012345678901234")

        original_bytes = b"binary_sensitive_data"
        encrypted_value = encryption.encrypt_value(original_bytes)
        decrypted_value = encryption.decrypt_value(encrypted_value)

        assert decrypted_value == original_bytes.decode("utf-8")

    def test_none_value_handling(self):
        """Test handling of None values."""
        encryption = EncryptionManager("test_master_key_123456789012345678901234")

        encrypted_none = encryption.encrypt_value(None)
        decrypted_none = encryption.decrypt_value(None)

        assert encrypted_none is None
        assert decrypted_none is None

    def test_dictionary_encryption(self):
        """Test encryption of dictionary with sensitive fields."""
        encryption = EncryptionManager("test_master_key_123456789012345678901234")

        test_data = {
            "id": "order_123",
            "price": 0.55,
            "size": 100.0,
            "notional_value": 55.0,
            "side": "BUY",  # Not sensitive
            "market": "test_market",  # Not sensitive
        }

        sensitive_fields = {"price", "size", "notional_value"}
        encrypted_dict = encryption.encrypt_dict(test_data, sensitive_fields)
        decrypted_dict = encryption.decrypt_dict(encrypted_dict, sensitive_fields)

        # Non-sensitive fields should be unchanged
        assert encrypted_dict["id"] == test_data["id"]
        assert encrypted_dict["side"] == test_data["side"]

        # Sensitive fields should be encrypted (and thus different)
        assert encrypted_dict["price"] != str(test_data["price"])
        assert encrypted_dict["size"] != str(test_data["size"])

        # Decrypted data should match original
        assert float(decrypted_dict["price"]) == test_data["price"]
        assert float(decrypted_dict["size"]) == test_data["size"]
        assert float(decrypted_dict["notional_value"]) == test_data["notional_value"]

    def test_invalid_decryption(self):
        """Test handling of invalid encrypted data."""
        encryption = EncryptionManager("test_master_key_123456789012345678901234")

        with pytest.raises(Exception):  # Should raise EncryptionError or similar
            encryption.decrypt_value("invalid_encrypted_data")

        with pytest.raises(Exception):
            encryption.decrypt_value("validbase64butnotencrypted==")


class TestDatabaseEncryption:
    """Test database encryption functionality."""

    def test_database_encryption_initialization(self):
        """Test database encryption initializes correctly."""
        encryption_manager = EncryptionManager("test_key_123456789012345678901234")
        db_encryption = DatabaseEncryption(encryption_manager)

        assert db_encryption.encryption == encryption_manager
        assert "orders" in db_encryption.sensitive_fields
        assert "positions" in db_encryption.sensitive_fields
        assert "price" in db_encryption.sensitive_fields["orders"]

    def test_row_data_encryption(self):
        """Test encryption of database row data."""
        encryption_manager = EncryptionManager("test_key_123456789012345678901234")
        db_encryption = DatabaseEncryption(encryption_manager)

        order_data = {
            "id": "order_123",
            "token_id": "token_456",
            "price": 0.55,
            "size": 100.0,
            "side": "BUY",
            "status": "OPEN",
        }

        encrypted_data = db_encryption.encrypt_row_data("orders", order_data)
        decrypted_data = db_encryption.decrypt_row_data("orders", encrypted_data)

        # Non-sensitive fields unchanged
        assert encrypted_data["id"] == order_data["id"]
        assert encrypted_data["side"] == order_data["side"]

        # Sensitive fields encrypted
        assert encrypted_data["price"] != str(order_data["price"])
        assert encrypted_data["size"] != str(order_data["size"])

        # Decryption restores original values
        assert float(decrypted_data["price"]) == order_data["price"]
        assert float(decrypted_data["size"]) == order_data["size"]

    def test_position_data_encryption(self):
        """Test encryption of position data."""
        encryption_manager = EncryptionManager("test_key_123456789012345678901234")
        db_encryption = DatabaseEncryption(encryption_manager)

        position_data = {
            "token_id": "token_123",
            "market_slug": "test_market",
            "size": 50.0,
            "notional_value": 27.5,
            "outcome_type": "YES",
        }

        encrypted_data = db_encryption.encrypt_row_data("positions", position_data)
        decrypted_data = db_encryption.decrypt_row_data("positions", encrypted_data)

        # Verify encryption/decryption cycle
        assert float(decrypted_data["size"]) == position_data["size"]
        assert (
            float(decrypted_data["notional_value"]) == position_data["notional_value"]
        )
        assert decrypted_data["outcome_type"] == position_data["outcome_type"]


@pytest.mark.asyncio
class TestEncryptedDatabaseManager:
    """Test the encrypted database manager."""

    async def create_test_encrypted_db(self):
        """Create test encrypted database manager."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        encryption_manager = EncryptionManager("test_key_123456789012345678901234")
        db_manager = EncryptedDatabaseManager(
            db_path, encryption_manager=encryption_manager
        )
        await db_manager.initialize()

        return db_manager, db_path

    async def cleanup_test_db(self, db_manager, db_path):
        """Clean up test database."""
        await db_manager.close()
        if os.path.exists(db_path):
            os.unlink(db_path)

    async def test_encrypted_database_initialization(self):
        """Test encrypted database manager initialization."""
        db_manager, db_path = await self.create_test_encrypted_db()

        try:
            assert db_manager.encryption_enabled
            assert db_manager.encryption_manager is not None
            assert db_manager._initialized

            # Check encryption status
            status = await db_manager.get_encryption_status()
            assert status["encryption_enabled"]
            assert status["encryption_initialized"]

        finally:
            await self.cleanup_test_db(db_manager, db_path)

    async def test_encrypted_order_operations(self):
        """Test encrypted order insert/retrieve operations."""
        db_manager, db_path = await self.create_test_encrypted_db()

        try:
            order_data = {
                "id": "test_order_123",
                "token_id": "token_456",
                "price": 0.65,
                "size": 200.0,
                "side": "SELL",
                "status": "OPEN",
            }

            # Insert order (should encrypt sensitive fields)
            await db_manager.insert_order(order_data)

            # Retrieve order (should decrypt sensitive fields)
            retrieved_order = await db_manager.get_order("test_order_123")

            assert retrieved_order is not None
            assert retrieved_order["id"] == order_data["id"]
            assert float(retrieved_order["price"]) == order_data["price"]
            assert float(retrieved_order["size"]) == order_data["size"]
            assert retrieved_order["side"] == order_data["side"]

        finally:
            await self.cleanup_test_db(db_manager, db_path)

    async def test_encrypted_position_operations(self):
        """Test encrypted position operations."""
        db_manager, db_path = await self.create_test_encrypted_db()

        try:
            position_data = {
                "token_id": "token_789",
                "market_slug": "test_market",
                "size": 150.0,
                "notional_value": 82.5,
                "outcome_type": "NO",
            }

            # Insert position
            await db_manager.upsert_position(position_data)

            # Retrieve position
            retrieved_position = await db_manager.get_position("token_789")

            assert retrieved_position is not None
            assert retrieved_position["token_id"] == position_data["token_id"]
            assert float(retrieved_position["size"]) == position_data["size"]
            assert (
                float(retrieved_position["notional_value"])
                == position_data["notional_value"]
            )

        finally:
            await self.cleanup_test_db(db_manager, db_path)

    async def test_encrypted_exposure_calculations(self):
        """Test exposure calculations with encrypted data."""
        db_manager, db_path = await self.create_test_encrypted_db()

        try:
            # Insert test positions
            positions = [
                {
                    "token_id": "token_1",
                    "market_slug": "market_1",
                    "size": 100.0,
                    "notional_value": 55.0,
                    "outcome_type": "YES",
                },
                {
                    "token_id": "token_2",
                    "market_slug": "market_1",
                    "size": 200.0,
                    "notional_value": 90.0,
                    "outcome_type": "NO",
                },
            ]

            for position in positions:
                await db_manager.upsert_position(position)

            # Test exposure calculations
            total_exposure = await db_manager.get_total_exposure()
            market_exposure = await db_manager.get_market_exposure("market_1")

            assert total_exposure == 145.0  # 55.0 + 90.0
            assert market_exposure == 145.0

        finally:
            await self.cleanup_test_db(db_manager, db_path)

    async def test_encryption_integrity_verification(self):
        """Test encryption integrity verification."""
        db_manager, db_path = await self.create_test_encrypted_db()

        try:
            # Add some test data
            await db_manager.insert_order(
                {
                    "id": "test_order",
                    "token_id": "token_1",
                    "price": 0.75,
                    "size": 50.0,
                    "side": "BUY",
                    "status": "OPEN",
                }
            )

            # Verify encryption integrity
            results = await db_manager.verify_encryption_integrity()

            assert results["integrity_ok"]
            assert results["records_verified"] >= 1
            assert results["encryption_errors"] == 0
            assert results["decryption_errors"] == 0

        finally:
            await self.cleanup_test_db(db_manager, db_path)


class TestConfigurationEncryption:
    """Test configuration encryption functionality."""

    def test_configuration_encryption_initialization(self):
        """Test configuration encryption initializes correctly."""
        encryption_manager = EncryptionManager("test_key_123456789012345678901234")
        config_encryption = ConfigurationEncryption(encryption_manager)

        assert config_encryption.encryption == encryption_manager

    def test_config_value_encryption(self):
        """Test encryption of configuration values."""
        encryption_manager = EncryptionManager("test_key_123456789012345678901234")
        config_encryption = ConfigurationEncryption(encryption_manager)

        key = "private_key"
        value = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"

        encrypted_value = config_encryption.encrypt_config_value(key, value)
        decrypted_value = config_encryption.decrypt_config_value(key, encrypted_value)

        assert decrypted_value == value
        assert encrypted_value != value

    def test_encrypted_value_detection(self):
        """Test detection of encrypted values."""
        encryption_manager = EncryptionManager("test_key_123456789012345678901234")
        config_encryption = ConfigurationEncryption(encryption_manager)

        plain_value = "plain_text_value"
        encrypted_value = config_encryption.encrypt_config_value("test", plain_value)

        assert not config_encryption.is_encrypted_value(plain_value)
        assert config_encryption.is_encrypted_value(encrypted_value)
        assert not config_encryption.is_encrypted_value("")
        assert not config_encryption.is_encrypted_value("short")


class TestEncryptedBotConfig:
    """Test encrypted bot configuration."""

    def test_encrypted_config_initialization(self):
        """Test encrypted configuration initialization."""
        encryption_manager = EncryptionManager("test_key_123456789012345678901234")

        config = EncryptedBotConfig(
            encryption_manager=encryption_manager,
            private_key="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
            public_key="0xabcdef1234567890abcdef1234567890abcdef12",
        )

        assert (
            config.private_key
            == "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        )
        assert config.public_key == "0xabcdef1234567890abcdef1234567890abcdef12"

    def test_sensitive_config_encryption(self):
        """Test encryption of sensitive configuration fields."""
        encryption_manager = EncryptionManager("test_key_123456789012345678901234")

        config = EncryptedBotConfig(
            encryption_manager=encryption_manager,
            private_key="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        )

        encrypted_config = config.encrypt_sensitive_config()

        assert "private_key" in encrypted_config
        assert encrypted_config["private_key"] != config.private_key

    def test_config_file_operations(self):
        """Test saving and loading encrypted configuration files."""
        encryption_manager = EncryptionManager("test_key_123456789012345678901234")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            config_path = Path(tmp.name)

        try:
            # Create and save encrypted config
            original_config = EncryptedBotConfig(
                encryption_manager=encryption_manager,
                private_key="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
                database_url="sqlite:///test.db",
            )

            original_config.save_encrypted_config(config_path)

            # Load encrypted config
            loaded_config = EncryptedBotConfig.load_encrypted_config(
                config_path, encryption_manager
            )

            # Verify loaded config matches original
            assert loaded_config.private_key == original_config.private_key
            assert loaded_config.database_url == original_config.database_url

        finally:
            if config_path.exists():
                config_path.unlink()

    def test_config_integrity_verification(self):
        """Test configuration integrity verification."""
        encryption_manager = EncryptionManager("test_key_123456789012345678901234")

        config = EncryptedBotConfig(
            encryption_manager=encryption_manager,
            private_key="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        )

        verification = config.verify_encryption_integrity()

        assert verification["integrity_ok"]
        assert verification["fields_verified"] >= 1
        assert verification["encryption_errors"] == 0


class TestEncryptedEnvironmentManager:
    """Test encrypted environment variable management."""

    def test_environment_manager_initialization(self):
        """Test environment manager initialization."""
        encryption_manager = EncryptionManager("test_key_123456789012345678901234")
        env_manager = EncryptedEnvironmentManager(encryption_manager)

        assert env_manager.encryption_manager == encryption_manager

    def test_encrypted_env_operations(self):
        """Test setting and getting encrypted environment variables."""
        encryption_manager = EncryptionManager("test_key_123456789012345678901234")
        env_manager = EncryptedEnvironmentManager(encryption_manager)

        test_key = "TEST_ENCRYPTED_VAR"
        test_value = "sensitive_test_value_123"

        # Clean up any existing value
        if test_key in os.environ:
            del os.environ[test_key]

        try:
            # Set encrypted environment variable
            env_manager.set_encrypted_env(test_key, test_value)

            # Verify it's set and encrypted
            raw_value = os.environ.get(test_key)
            assert raw_value != test_value
            assert env_manager.config_encryption.is_encrypted_value(raw_value)

            # Get decrypted value
            decrypted_value = env_manager.get_decrypted_env(test_key)
            assert decrypted_value == test_value

        finally:
            # Clean up
            if test_key in os.environ:
                del os.environ[test_key]

    def test_env_file_encryption(self):
        """Test encryption of .env files."""
        encryption_manager = EncryptionManager("test_key_123456789012345678901234")
        env_manager = EncryptedEnvironmentManager(encryption_manager)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as tmp:
            env_path = Path(tmp.name)
            tmp.write("PRIVATE_KEY=0x1234567890abcdef\n")
            tmp.write("PUBLIC_KEY=0xabcdef123456\n")
            tmp.write("REGULAR_VAR=not_sensitive\n")

        try:
            # Encrypt sensitive variables
            sensitive_keys = {"PRIVATE_KEY", "PUBLIC_KEY"}
            env_manager.encrypt_env_file(env_path, sensitive_keys)

            # Read back and verify
            with open(env_path, "r") as f:
                content = f.read()

            assert "PRIVATE_KEY=" in content
            assert "0x1234567890abcdef" not in content  # Should be encrypted
            assert "REGULAR_VAR=not_sensitive" in content  # Should be unchanged

        finally:
            if env_path.exists():
                env_path.unlink()


class TestEncryptionIntegration:
    """Test integration scenarios and edge cases."""

    def test_global_encryption_manager(self):
        """Test global encryption manager functionality."""
        # Test setup_encryption
        manager = setup_encryption("global_test_key_123456789012345678901234")
        assert manager is not None

        # Test convenience functions
        from inkedup_bot.encryption import (
            decrypt_sensitive_value,
            encrypt_sensitive_value,
        )

        test_value = "sensitive_global_data"
        encrypted = encrypt_sensitive_value(test_value)
        decrypted = decrypt_sensitive_value(encrypted)

        assert decrypted == test_value

    def test_encryption_with_missing_cryptography(self):
        """Test handling when cryptography package is not available."""
        with patch("inkedup_bot.encryption.CRYPTOGRAPHY_AVAILABLE", False):
            with pytest.raises(Exception):  # Should raise EncryptionError
                EncryptionManager("test_key")

    def test_empty_and_edge_case_values(self):
        """Test encryption with edge case values."""
        encryption = EncryptionManager("test_key_123456789012345678901234")

        # Empty string
        encrypted_empty = encryption.encrypt_value("")
        decrypted_empty = encryption.decrypt_value(encrypted_empty)
        assert decrypted_empty == ""

        # Unicode values
        unicode_value = "🔐 encrypted data with emojis 中文"
        encrypted_unicode = encryption.encrypt_value(unicode_value)
        decrypted_unicode = encryption.decrypt_value(encrypted_unicode)
        assert decrypted_unicode == unicode_value

    @pytest.mark.asyncio
    async def test_database_migration_to_encryption(self):
        """Test migration of existing database to encrypted format."""
        # This would test the migration functionality
        # For now, we'll test that the migration method exists and runs
        db_manager, db_path = await self.create_test_encrypted_db()

        try:
            # Add some unencrypted data first (by disabling encryption temporarily)
            db_manager.encryption_enabled = False
            await db_manager.insert_order(
                {
                    "id": "migration_test",
                    "token_id": "token_1",
                    "price": 0.5,
                    "size": 100.0,
                    "side": "BUY",
                    "status": "OPEN",
                }
            )

            # Enable encryption and test migration
            db_manager.encryption_enabled = True
            migration_stats = await db_manager.migrate_to_encryption()

            assert migration_stats["tables_migrated"] >= 1
            assert migration_stats["records_encrypted"] >= 1
            assert len(migration_stats["errors"]) == 0

        finally:
            await self.cleanup_test_db(db_manager, db_path)

    async def create_test_encrypted_db(self):
        """Helper to create test encrypted database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        encryption_manager = EncryptionManager("test_key_123456789012345678901234")
        db_manager = EncryptedDatabaseManager(
            db_path, encryption_manager=encryption_manager
        )
        await db_manager.initialize()

        return db_manager, db_path

    async def cleanup_test_db(self, db_manager, db_path):
        """Helper to clean up test database."""
        await db_manager.close()
        if os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
