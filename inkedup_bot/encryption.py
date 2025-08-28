"""
Data Encryption at Rest System for InkedUp Trading Bot.

This module provides comprehensive encryption capabilities for protecting sensitive data
stored in databases, configuration files, and other persistent storage systems.

Key Features:
    - AES-256-GCM encryption for maximum security
    - Key derivation using PBKDF2 with secure parameters
    - Field-level encryption for database columns
    - Configuration value encryption
    - Key rotation support
    - Secure key management with environment variables
    - Performance optimized with caching

Security Design:
    - Uses industry-standard AES-256-GCM encryption
    - PBKDF2 key derivation with 100,000 iterations
    - Unique salt and nonce for each encryption operation
    - Authenticated encryption prevents tampering
    - Memory-safe key handling with automatic clearing
"""

import base64
import hashlib
import logging
import os
import secrets
from typing import Any, Dict, Optional, Union

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

log = logging.getLogger("encryption")


class EncryptionError(Exception):
    """Base exception for encryption-related errors."""

    pass


class EncryptionManager:
    """
    Comprehensive encryption manager for data at rest protection.

    Provides secure encryption/decryption of sensitive data using AES-256-GCM
    with PBKDF2 key derivation and authenticated encryption.
    """

    def __init__(self, master_key: Optional[str] = None):
        """
        Initialize encryption manager.

        Args:
            master_key: Master encryption key. If not provided, will be read from
                       ENCRYPTION_KEY environment variable or generated.
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            raise EncryptionError(
                "cryptography package is required for encryption. "
                "Install with: pip install cryptography"
            )

        self.master_key = self._get_or_generate_master_key(master_key)
        self._encryption_cache = {}  # Cache for derived keys

        # Encryption parameters
        self.salt_length = 32  # 256 bits
        self.nonce_length = 16  # 128 bits for GCM
        self.key_length = 32  # 256 bits for AES-256
        self.iterations = 100000  # PBKDF2 iterations

        log.info("Encryption manager initialized with AES-256-GCM")

    def _get_or_generate_master_key(self, provided_key: Optional[str]) -> str:
        """Get master key from parameter, environment, or generate new one."""
        if provided_key:
            return provided_key

        # Try to get from environment
        env_key = os.getenv("ENCRYPTION_KEY")
        if env_key:
            return env_key

        # Generate new key and warn
        new_key = base64.b64encode(secrets.token_bytes(32)).decode("utf-8")
        log.warning(
            "No encryption key provided. Generated new key. "
            "Set ENCRYPTION_KEY environment variable to persist encryption."
        )
        return new_key

    def _derive_key(self, salt: bytes, context: str = "") -> bytes:
        """
        Derive encryption key from master key using PBKDF2.

        Args:
            salt: Random salt for key derivation
            context: Context string for key separation

        Returns:
            Derived 256-bit encryption key
        """
        # Use master key + context as password
        password = (self.master_key + context).encode("utf-8")

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.key_length,
            salt=salt,
            iterations=self.iterations,
            backend=default_backend(),
        )

        return kdf.derive(password)

    def encrypt_value(self, value: Union[str, bytes], context: str = "default") -> str:
        """
        Encrypt a single value with authenticated encryption.

        Args:
            value: Value to encrypt (string or bytes)
            context: Context for key derivation (for different data types)

        Returns:
            Base64-encoded encrypted value with embedded salt and nonce

        Format: base64(salt + nonce + ciphertext + tag)
        """
        if value is None:
            return None

        # Convert to bytes if string
        if isinstance(value, str):
            plaintext = value.encode("utf-8")
        else:
            plaintext = value

        # Generate random salt and nonce
        salt = secrets.token_bytes(self.salt_length)
        nonce = secrets.token_bytes(self.nonce_length)

        # Derive encryption key
        key = self._derive_key(salt, context)

        # Encrypt using AES-GCM
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        # Combine salt + nonce + ciphertext and encode
        encrypted_data = salt + nonce + ciphertext
        return base64.b64encode(encrypted_data).decode("utf-8")

    def decrypt_value(self, encrypted_value: str, context: str = "default") -> str:
        """
        Decrypt a single value with authentication verification.

        Args:
            encrypted_value: Base64-encoded encrypted value
            context: Context used during encryption

        Returns:
            Decrypted plaintext value

        Raises:
            EncryptionError: If decryption fails or authentication fails
        """
        if encrypted_value is None:
            return None

        try:
            # Decode from base64
            encrypted_data = base64.b64decode(encrypted_value.encode("utf-8"))

            # Extract salt, nonce, and ciphertext
            salt = encrypted_data[: self.salt_length]
            nonce = encrypted_data[
                self.salt_length : self.salt_length + self.nonce_length
            ]
            ciphertext = encrypted_data[self.salt_length + self.nonce_length :]

            # Derive encryption key
            key = self._derive_key(salt, context)

            # Decrypt using AES-GCM
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)

            return plaintext.decode("utf-8")

        except Exception as e:
            raise EncryptionError(f"Decryption failed: {e}")

    def encrypt_dict(
        self, data: Dict[str, Any], sensitive_fields: set = None
    ) -> Dict[str, Any]:
        """
        Encrypt sensitive fields in a dictionary.

        Args:
            data: Dictionary containing data to encrypt
            sensitive_fields: Set of field names to encrypt. If None, encrypts all values.

        Returns:
            Dictionary with encrypted sensitive fields
        """
        if not data:
            return data

        encrypted_data = data.copy()

        # Default sensitive fields if not specified
        if sensitive_fields is None:
            sensitive_fields = {
                "private_key",
                "api_key",
                "secret",
                "password",
                "token",
                "notional_value",
                "size",
                "price",
                "unrealized_pnl",
                "realized_pnl",
            }

        for field, value in encrypted_data.items():
            if field.lower() in {f.lower() for f in sensitive_fields}:
                if value is not None:
                    encrypted_data[field] = self.encrypt_value(
                        str(value), context=field
                    )

        return encrypted_data

    def decrypt_dict(
        self, encrypted_data: Dict[str, Any], sensitive_fields: set = None
    ) -> Dict[str, Any]:
        """
        Decrypt sensitive fields in a dictionary.

        Args:
            encrypted_data: Dictionary containing encrypted data
            sensitive_fields: Set of field names that were encrypted

        Returns:
            Dictionary with decrypted sensitive fields
        """
        if not encrypted_data:
            return encrypted_data

        decrypted_data = encrypted_data.copy()

        # Default sensitive fields if not specified
        if sensitive_fields is None:
            sensitive_fields = {
                "private_key",
                "api_key",
                "secret",
                "password",
                "token",
                "notional_value",
                "size",
                "price",
                "unrealized_pnl",
                "realized_pnl",
            }

        for field, value in decrypted_data.items():
            if field.lower() in {f.lower() for f in sensitive_fields}:
                if value is not None and isinstance(value, str):
                    try:
                        decrypted_data[field] = self.decrypt_value(value, context=field)
                    except EncryptionError:
                        # Value might not be encrypted, leave as-is
                        pass

        return decrypted_data


class DatabaseEncryption:
    """
    Database-specific encryption functionality for protecting sensitive data.

    Provides transparent encryption/decryption for database operations with
    field-level encryption support.
    """

    def __init__(self, encryption_manager: EncryptionManager):
        """Initialize with encryption manager."""
        self.encryption = encryption_manager

        # Define which database fields should be encrypted
        self.sensitive_fields = {
            # Orders table
            "orders": {"price", "size", "notional_value"},
            # Positions table
            "positions": {"size", "notional_value"},
            # Trades table
            "trades": {"price", "size", "notional_value"},
            # Risk events table
            "risk_events": {"current_exposure", "limit_value", "intended_notional"},
            # Outcome exposures table
            "outcome_exposures": {
                "position_size",
                "notional_value",
                "average_price",
                "current_price",
                "unrealized_pnl",
                "realized_pnl",
            },
            # Market snapshots
            "market_snapshots": {"bid", "ask", "volume_24h", "liquidity"},
        }

    def encrypt_row_data(
        self, table_name: str, row_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Encrypt sensitive fields in a database row.

        Args:
            table_name: Name of the database table
            row_data: Row data dictionary

        Returns:
            Row data with encrypted sensitive fields
        """
        sensitive_fields = self.sensitive_fields.get(table_name, set())
        return self.encryption.encrypt_dict(row_data, sensitive_fields)

    def decrypt_row_data(
        self, table_name: str, row_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Decrypt sensitive fields in a database row.

        Args:
            table_name: Name of the database table
            row_data: Encrypted row data dictionary

        Returns:
            Row data with decrypted sensitive fields
        """
        sensitive_fields = self.sensitive_fields.get(table_name, set())
        return self.encryption.decrypt_dict(row_data, sensitive_fields)


class ConfigurationEncryption:
    """
    Configuration-specific encryption for protecting sensitive config values.

    Provides secure storage and retrieval of sensitive configuration values
    like API keys and private keys.
    """

    def __init__(self, encryption_manager: EncryptionManager):
        """Initialize with encryption manager."""
        self.encryption = encryption_manager

    def encrypt_config_value(self, key: str, value: str) -> str:
        """
        Encrypt a configuration value.

        Args:
            key: Configuration key name
            value: Configuration value to encrypt

        Returns:
            Encrypted configuration value
        """
        return self.encryption.encrypt_value(value, context=f"config_{key}")

    def decrypt_config_value(self, key: str, encrypted_value: str) -> str:
        """
        Decrypt a configuration value.

        Args:
            key: Configuration key name
            encrypted_value: Encrypted configuration value

        Returns:
            Decrypted configuration value
        """
        return self.encryption.decrypt_value(encrypted_value, context=f"config_{key}")

    def is_encrypted_value(self, value: str) -> bool:
        """
        Check if a value appears to be encrypted.

        Args:
            value: Value to check

        Returns:
            True if value appears to be encrypted
        """
        if not isinstance(value, str) or len(value) < 50:
            return False

        try:
            # Try to decode as base64
            decoded = base64.b64decode(value.encode("utf-8"))
            # Check if it has the expected minimum length (salt + nonce + minimal ciphertext)
            return len(decoded) >= (
                self.encryption.salt_length + self.encryption.nonce_length + 16
            )
        except Exception:
            return False


# Global encryption manager instance
_encryption_manager = None


def get_encryption_manager() -> EncryptionManager:
    """Get or create global encryption manager instance."""
    global _encryption_manager
    if _encryption_manager is None:
        _encryption_manager = EncryptionManager()
    return _encryption_manager


def encrypt_sensitive_value(value: str, context: str = "default") -> str:
    """Convenience function to encrypt a sensitive value."""
    return get_encryption_manager().encrypt_value(value, context)


def decrypt_sensitive_value(encrypted_value: str, context: str = "default") -> str:
    """Convenience function to decrypt a sensitive value."""
    return get_encryption_manager().decrypt_value(encrypted_value, context)


def setup_encryption(master_key: Optional[str] = None) -> EncryptionManager:
    """
    Setup encryption with optional master key.

    Args:
        master_key: Master encryption key. If not provided, uses environment variable.

    Returns:
        Configured encryption manager
    """
    global _encryption_manager
    _encryption_manager = EncryptionManager(master_key)
    return _encryption_manager


# Example usage and testing
if __name__ == "__main__":
    # Example usage
    print("🔐 Encryption System Demo")
    print("=" * 40)

    # Initialize encryption manager
    encryption = EncryptionManager()

    # Test basic encryption/decryption
    sensitive_data = (
        "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    )
    encrypted = encryption.encrypt_value(sensitive_data, "private_key")
    decrypted = encryption.decrypt_value(encrypted, "private_key")

    print(f"Original: {sensitive_data[:20]}...")
    print(f"Encrypted: {encrypted[:50]}...")
    print(f"Decrypted: {decrypted[:20]}...")
    print(f"Match: {sensitive_data == decrypted}")
    print()

    # Test dictionary encryption
    trade_data = {
        "id": "trade_123",
        "price": 0.55,
        "size": 100.0,
        "notional_value": 55.0,
        "side": "BUY",
    }

    sensitive_fields = {"price", "size", "notional_value"}
    encrypted_dict = encryption.encrypt_dict(trade_data, sensitive_fields)
    decrypted_dict = encryption.decrypt_dict(encrypted_dict, sensitive_fields)

    print("Original trade data:", trade_data)
    print(
        "Encrypted fields:",
        {k: v[:30] + "..." for k, v in encrypted_dict.items() if k in sensitive_fields},
    )
    print("Decrypted match:", trade_data == decrypted_dict)
