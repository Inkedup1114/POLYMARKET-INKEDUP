"""
Encrypted Configuration Manager for InkedUp Trading Bot.

This module extends the standard BotConfig to provide automatic encryption
of sensitive configuration values like API keys and private keys at rest.

Key Features:
    - Automatic encryption of sensitive configuration fields
    - Transparent decryption during application runtime
    - Support for environment variables with encrypted values
    - Configuration file encryption/decryption
    - Key rotation and migration support
    - Backward compatibility with existing configurations
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Set

from .config import BotConfig
from .encryption import (
    ConfigurationEncryption,
    EncryptionManager,
    get_encryption_manager,
)

log = logging.getLogger("encrypted_config")


class EncryptedBotConfig(BotConfig):
    """
    Enhanced bot configuration with automatic encryption of sensitive values.

    Extends BotConfig to automatically encrypt sensitive configuration values
    at rest while providing transparent access during runtime.
    """

    def __init__(self, encryption_manager: EncryptionManager = None, **kwargs):
        """
        Initialize encrypted configuration.

        Args:
            encryption_manager: Encryption manager instance
            **kwargs: Configuration parameters
        """
        self.encryption_manager = encryption_manager or get_encryption_manager()
        self.config_encryption = ConfigurationEncryption(self.encryption_manager)

        # Define which configuration fields should be encrypted
        self.sensitive_fields = {
            "private_key",
            "public_key",
            "api_key",
            "secret_key",
            "password",
            "database_url",
            "webhook_secret",
            "jwt_secret",
            "encryption_key",
        }

        # Process encrypted values before parent initialization
        processed_kwargs = self._decrypt_config_values(kwargs)

        super().__init__(**processed_kwargs)

        log.info("Encrypted configuration initialized")

    def _decrypt_config_values(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decrypt sensitive configuration values.

        Args:
            config_data: Raw configuration data (may contain encrypted values)

        Returns:
            Configuration data with decrypted sensitive values
        """
        decrypted_data = config_data.copy()

        for field, value in config_data.items():
            if field.lower() in {f.lower() for f in self.sensitive_fields}:
                if isinstance(value, str) and self.config_encryption.is_encrypted_value(
                    value
                ):
                    try:
                        decrypted_value = self.config_encryption.decrypt_config_value(
                            field, value
                        )
                        decrypted_data[field] = decrypted_value
                        log.debug(f"Decrypted configuration field: {field}")
                    except Exception as e:
                        log.warning(
                            f"Failed to decrypt configuration field {field}: {e}"
                        )

        return decrypted_data

    def encrypt_sensitive_config(self) -> Dict[str, str]:
        """
        Encrypt sensitive configuration values for storage.

        Returns:
            Dictionary of encrypted configuration values
        """
        encrypted_config = {}

        for field_name in self.sensitive_fields:
            # Get the actual field value from the config
            value = getattr(self, field_name, None)
            if value is not None:
                encrypted_value = self.config_encryption.encrypt_config_value(
                    field_name, str(value)
                )
                encrypted_config[field_name] = encrypted_value

        return encrypted_config

    def save_encrypted_config(self, config_path: Path) -> None:
        """
        Save configuration to file with encrypted sensitive values.

        Args:
            config_path: Path to save encrypted configuration file
        """
        try:
            # Get all configuration as dictionary
            config_dict = {}

            # Add non-sensitive fields as plain text
            for field_name, field_value in self.__dict__.items():
                if not field_name.startswith("_") and field_name not in {
                    "encryption_manager",
                    "config_encryption",
                }:
                    if field_name.lower() not in {
                        f.lower() for f in self.sensitive_fields
                    }:
                        config_dict[field_name] = field_value

            # Add encrypted sensitive fields
            encrypted_values = self.encrypt_sensitive_config()
            for field, encrypted_value in encrypted_values.items():
                config_dict[field] = encrypted_value

            # Save to file
            with open(config_path, "w") as f:
                json.dump(config_dict, f, indent=2, default=str)

            log.info(f"Encrypted configuration saved to {config_path}")

        except Exception as e:
            log.error(f"Failed to save encrypted configuration: {e}")
            raise

    @classmethod
    def load_encrypted_config(
        cls, config_path: Path, encryption_manager: EncryptionManager = None
    ) -> "EncryptedBotConfig":
        """
        Load configuration from encrypted file.

        Args:
            config_path: Path to encrypted configuration file
            encryption_manager: Encryption manager instance

        Returns:
            Loaded encrypted configuration instance
        """
        try:
            with open(config_path, "r") as f:
                config_data = json.load(f)

            log.info(f"Loaded encrypted configuration from {config_path}")
            return cls(encryption_manager=encryption_manager, **config_data)

        except Exception as e:
            log.error(f"Failed to load encrypted configuration from {config_path}: {e}")
            raise

    def migrate_to_encryption(self, source_config_path: Optional[Path] = None) -> None:
        """
        Migrate existing plain-text configuration to encrypted format.

        Args:
            source_config_path: Path to existing plain-text configuration.
                               If None, uses current configuration values.
        """
        try:
            if source_config_path and source_config_path.exists():
                # Load plain-text configuration
                with open(source_config_path, "r") as f:
                    plain_config = json.load(f)

                # Create encrypted version
                encrypted_config = EncryptedBotConfig(
                    encryption_manager=self.encryption_manager, **plain_config
                )

                # Save encrypted version
                encrypted_path = source_config_path.with_suffix(".encrypted.json")
                encrypted_config.save_encrypted_config(encrypted_path)

                log.info(
                    f"Migrated configuration from {source_config_path} to {encrypted_path}"
                )
            else:
                log.info("Migration completed using current configuration values")

        except Exception as e:
            log.error(f"Configuration migration failed: {e}")
            raise

    def rotate_encryption_keys(
        self, new_encryption_manager: EncryptionManager
    ) -> "EncryptedBotConfig":
        """
        Rotate encryption keys by re-encrypting with new encryption manager.

        Args:
            new_encryption_manager: New encryption manager with different keys

        Returns:
            New configuration instance with re-encrypted values
        """
        try:
            # Get current plain-text values
            current_values = {}
            for field_name in self.sensitive_fields:
                value = getattr(self, field_name, None)
                if value is not None:
                    current_values[field_name] = value

            # Create new configuration with new encryption manager
            new_config = EncryptedBotConfig(
                encryption_manager=new_encryption_manager, **current_values
            )

            log.info("Encryption keys rotated successfully")
            return new_config

        except Exception as e:
            log.error(f"Key rotation failed: {e}")
            raise

    def verify_encryption_integrity(self) -> Dict[str, Any]:
        """
        Verify that sensitive configuration can be encrypted and decrypted properly.

        Returns:
            Verification results
        """
        verification_results = {
            "fields_verified": 0,
            "encryption_errors": 0,
            "decryption_errors": 0,
            "integrity_ok": True,
            "errors": [],
        }

        try:
            for field_name in self.sensitive_fields:
                value = getattr(self, field_name, None)
                if value is not None:
                    try:
                        # Test encryption/decryption cycle
                        encrypted = self.config_encryption.encrypt_config_value(
                            field_name, str(value)
                        )
                        decrypted = self.config_encryption.decrypt_config_value(
                            field_name, encrypted
                        )

                        if str(value) == decrypted:
                            verification_results["fields_verified"] += 1
                        else:
                            verification_results["integrity_ok"] = False
                            error_msg = f"Encryption/decryption mismatch for field: {field_name}"
                            verification_results["errors"].append(error_msg)

                    except Exception as e:
                        verification_results["encryption_errors"] += 1
                        verification_results["integrity_ok"] = False
                        error_msg = f"Encryption error for field {field_name}: {e}"
                        verification_results["errors"].append(error_msg)

            log.info(
                f"Configuration encryption integrity verification: {verification_results}"
            )
            return verification_results

        except Exception as e:
            error_msg = f"Configuration verification failed: {e}"
            verification_results["errors"].append(error_msg)
            verification_results["integrity_ok"] = False
            log.error(error_msg)
            return verification_results


class EncryptedEnvironmentManager:
    """
    Manager for encrypted environment variables.

    Provides utilities for storing and retrieving encrypted values from
    environment variables and .env files.
    """

    def __init__(self, encryption_manager: EncryptionManager = None):
        """Initialize with encryption manager."""
        self.encryption_manager = encryption_manager or get_encryption_manager()
        self.config_encryption = ConfigurationEncryption(self.encryption_manager)

    def set_encrypted_env(self, key: str, value: str, env_file: Path = None) -> None:
        """
        Set encrypted environment variable.

        Args:
            key: Environment variable name
            value: Plain-text value to encrypt
            env_file: Optional .env file to update
        """
        try:
            encrypted_value = self.config_encryption.encrypt_config_value(key, value)

            # Set in current environment
            os.environ[key] = encrypted_value

            # Update .env file if specified
            if env_file:
                self._update_env_file(env_file, key, encrypted_value)

            log.info(f"Set encrypted environment variable: {key}")

        except Exception as e:
            log.error(f"Failed to set encrypted environment variable {key}: {e}")
            raise

    def get_decrypted_env(self, key: str, default: str = None) -> Optional[str]:
        """
        Get and decrypt environment variable.

        Args:
            key: Environment variable name
            default: Default value if not found

        Returns:
            Decrypted environment variable value
        """
        try:
            encrypted_value = os.environ.get(key, default)
            if encrypted_value and self.config_encryption.is_encrypted_value(
                encrypted_value
            ):
                return self.config_encryption.decrypt_config_value(key, encrypted_value)
            return encrypted_value

        except Exception as e:
            log.warning(f"Failed to decrypt environment variable {key}: {e}")
            return default

    def _update_env_file(self, env_file: Path, key: str, value: str) -> None:
        """Update .env file with new encrypted value."""
        try:
            # Read existing content
            content = []
            if env_file.exists():
                with open(env_file, "r") as f:
                    content = f.readlines()

            # Update or add the key
            updated = False
            for i, line in enumerate(content):
                if line.strip().startswith(f"{key}="):
                    content[i] = f"{key}={value}\n"
                    updated = True
                    break

            if not updated:
                content.append(f"{key}={value}\n")

            # Write back to file
            with open(env_file, "w") as f:
                f.writelines(content)

        except Exception as e:
            log.error(f"Failed to update .env file {env_file}: {e}")
            raise

    def encrypt_env_file(self, env_file: Path, sensitive_keys: Set[str]) -> None:
        """
        Encrypt sensitive values in .env file.

        Args:
            env_file: Path to .env file
            sensitive_keys: Set of keys to encrypt
        """
        try:
            if not env_file.exists():
                log.warning(f"Environment file not found: {env_file}")
                return

            # Read and parse .env file
            updated_content = []

            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and "=" in line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")  # Remove quotes

                        if (
                            key in sensitive_keys
                            and not self.config_encryption.is_encrypted_value(value)
                        ):
                            # Encrypt the value
                            encrypted_value = (
                                self.config_encryption.encrypt_config_value(key, value)
                            )
                            updated_content.append(f"{key}={encrypted_value}\n")
                            log.info(f"Encrypted environment variable: {key}")
                        else:
                            updated_content.append(line + "\n")
                    else:
                        updated_content.append(line + "\n")

            # Write back encrypted content
            with open(env_file, "w") as f:
                f.writelines(updated_content)

            log.info(f"Environment file encryption completed: {env_file}")

        except Exception as e:
            log.error(f"Failed to encrypt environment file {env_file}: {e}")
            raise


# Example usage and utilities
def setup_encrypted_config(
    config_path: Path = None, env_file: Path = None
) -> EncryptedBotConfig:
    """
    Setup encrypted configuration with automatic migration from plain-text sources.

    Args:
        config_path: Path to configuration file (plain-text or encrypted)
        env_file: Path to .env file to encrypt

    Returns:
        Configured encrypted bot configuration
    """
    try:
        # Setup encryption manager
        encryption_manager = get_encryption_manager()

        # Encrypt .env file if provided
        if env_file and env_file.exists():
            env_manager = EncryptedEnvironmentManager(encryption_manager)
            sensitive_keys = {
                "PRIVATE_KEY",
                "PUBLIC_KEY",
                "API_KEY",
                "SECRET_KEY",
                "DATABASE_URL",
                "ENCRYPTION_KEY",
            }
            env_manager.encrypt_env_file(env_file, sensitive_keys)

        # Load or create encrypted configuration
        if config_path and config_path.exists():
            # Try to load as encrypted config first
            try:
                config = EncryptedBotConfig.load_encrypted_config(
                    config_path, encryption_manager
                )
                log.info("Loaded existing encrypted configuration")
            except:
                # If that fails, treat as plain-text and migrate
                config = EncryptedBotConfig(encryption_manager=encryption_manager)
                config.migrate_to_encryption(config_path)
                log.info("Migrated plain-text configuration to encrypted format")
        else:
            # Create new encrypted configuration
            config = EncryptedBotConfig(encryption_manager=encryption_manager)
            log.info("Created new encrypted configuration")

        # Verify encryption integrity
        verification = config.verify_encryption_integrity()
        if not verification["integrity_ok"]:
            log.warning(
                f"Configuration encryption integrity issues detected: {verification['errors']}"
            )

        return config

    except Exception as e:
        log.error(f"Failed to setup encrypted configuration: {e}")
        raise


if __name__ == "__main__":
    # Example usage
    print("🔐 Encrypted Configuration Demo")
    print("=" * 40)

    # Create encrypted configuration
    config = EncryptedBotConfig(
        private_key="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        public_key="0xabcdef1234567890abcdef1234567890abcdef12",
        database_url="sqlite:///encrypted_bot_data.db",
    )

    print(f"Private key: {config.private_key[:20]}...")
    print(f"Database URL: {config.database_url}")

    # Test encryption/decryption
    encrypted_config = config.encrypt_sensitive_config()
    print(f"Encrypted private key: {encrypted_config['private_key'][:50]}...")

    # Verify integrity
    verification = config.verify_encryption_integrity()
    print(f"Encryption integrity OK: {verification['integrity_ok']}")
    print(f"Fields verified: {verification['fields_verified']}")
