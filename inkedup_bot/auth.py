"""
Authentication manager for Polymarket WebSocket connections.

This module handles API key derivation, signature generation, and secure credential management
for both EOA and smart wallet authentication types.
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from py_clob_client.constants import POLYGON

logger = logging.getLogger(__name__)


class SignatureType(str, Enum):
    """Supported signature types for authentication."""

    EOA = "EOA"
    POLY_GNOSIS_SAFE = "POLY_GNOSIS_SAFE"
    POLY_PROXY = "POLY_PROXY"


@dataclass
class AuthCredentials:
    """Container for authentication credentials."""

    api_key: str
    api_secret: str
    passphrase: str
    signature_type: SignatureType
    wallet_address: str
    expires_at: datetime | None = None

    @property
    def is_expired(self) -> bool:
        """Check if credentials have expired."""
        if not self.expires_at:
            return False
        return datetime.utcnow() >= self.expires_at


class AuthManager:
    """
    Manages authentication for Polymarket WebSocket connections.

    Handles API key derivation, credential rotation, and secure storage.
    """

    def __init__(
        self,
        private_key: str,
        chain_id: int = POLYGON,
        host: str = "https://clob.polymarket.com",
        creds_file: str | None = None,
        auto_refresh: bool = True,
    ):
        """
        Initialize the authentication manager.

        Args:
            private_key: Private key for signing
            chain_id: Chain ID (default: POLYGON)
            host: CLOB API host
            creds_file: Optional file to store/load credentials
            auto_refresh: Whether to auto-refresh expired credentials
        """
        self.private_key = private_key
        self.chain_id = chain_id
        self.host = host
        self.creds_file = creds_file
        self.auto_refresh = auto_refresh

        self._credentials: dict[SignatureType, AuthCredentials] = {}
        self._client: ClobClient | None = None

    async def initialize(self) -> None:
        """Initialize the authentication manager."""
        await self._load_stored_credentials()
        await self._setup_client()

    async def _setup_client(self) -> None:
        """Set up the CLOB client."""
        try:
            self._client = ClobClient(
                host=self.host, chain_id=self.chain_id, key=self.private_key
            )
            logger.info("CLOB client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize CLOB client: {e}")
            raise

    async def _load_stored_credentials(self) -> None:
        """Load credentials from file if available."""
        if not self.creds_file or not os.path.exists(self.creds_file):
            return

        try:
            with open(self.creds_file) as f:
                data = json.load(f)

            for sig_type_str, creds_data in data.items():
                sig_type = SignatureType(sig_type_str)
                creds = AuthCredentials(
                    api_key=creds_data["api_key"],
                    api_secret=creds_data["api_secret"],
                    passphrase=creds_data["passphrase"],
                    signature_type=sig_type,
                    wallet_address=creds_data["wallet_address"],
                    expires_at=(
                        datetime.fromisoformat(creds_data["expires_at"])
                        if creds_data.get("expires_at")
                        else None
                    ),
                )
                self._credentials[sig_type] = creds

            logger.info(
                f"Loaded {len(self._credentials)} credential sets from {self.creds_file}"
            )
        except Exception as e:
            logger.warning(f"Failed to load stored credentials: {e}")

    async def _save_credentials(self) -> None:
        """Save credentials to file."""
        if not self.creds_file:
            return

        try:
            os.makedirs(os.path.dirname(self.creds_file), exist_ok=True)

            data = {}
            for sig_type, creds in self._credentials.items():
                data[sig_type.value] = {
                    "api_key": creds.api_key,
                    "api_secret": creds.api_secret,
                    "passphrase": creds.passphrase,
                    "wallet_address": creds.wallet_address,
                    "expires_at": (
                        creds.expires_at.isoformat() if creds.expires_at else None
                    ),
                }

            with open(self.creds_file, "w") as f:
                json.dump(data, f, indent=2)

            # Set restrictive permissions
            os.chmod(self.creds_file, 0o600)
            logger.info(f"Credentials saved to {self.creds_file}")
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")

    async def derive_credentials(
        self,
        signature_type: SignatureType = SignatureType.EOA,
        force_refresh: bool = False,
    ) -> AuthCredentials:
        """
        Derive API credentials for the specified signature type.

        Args:
            signature_type: Type of signature to use
            force_refresh: Force refresh even if credentials exist

        Returns:
            Authentication credentials
        """
        if self._client is None:
            await self.initialize()

        # Return existing credentials if valid
        if not force_refresh and signature_type in self._credentials:
            creds = self._credentials[signature_type]
            if not creds.is_expired:
                return creds

        try:
            assert self._client is not None, "Client not initialized"

            # Derive new credentials
            api_creds = self._client.derive_api_key()

            creds = AuthCredentials(
                api_key=api_creds.api_key,
                api_secret=api_creds.api_secret,
                passphrase=api_creds.api_passphrase,
                signature_type=signature_type,
                wallet_address=self._client.get_address(),
                expires_at=datetime.utcnow() + timedelta(days=7),  # 7-day expiry
            )

            self._credentials[signature_type] = creds
            await self._save_credentials()

            logger.info(f"Derived new credentials for {signature_type}")
            return creds

        except Exception as e:
            logger.error(f"Failed to derive credentials for {signature_type}: {e}")
            raise

    async def get_credentials(
        self, signature_type: SignatureType = SignatureType.EOA
    ) -> AuthCredentials:
        """
        Get credentials for the specified signature type.

        Args:
            signature_type: Type of signature to use

        Returns:
            Authentication credentials

        Raises:
            ValueError: If credentials cannot be obtained
        """
        if (
            signature_type not in self._credentials
            or self._credentials[signature_type].is_expired
        ):
            if self.auto_refresh:
                return await self.derive_credentials(signature_type)
            else:
                raise ValueError(
                    f"Credentials for {signature_type} are expired and auto-refresh is disabled"
                )

        return self._credentials[signature_type]

    async def refresh_credentials(
        self, signature_type: SignatureType
    ) -> AuthCredentials:
        """Force refresh credentials for the specified signature type."""
        return await self.derive_credentials(signature_type, force_refresh=True)

    async def validate_credentials(self, credentials: AuthCredentials) -> bool:
        """
        Validate credentials by making a test API call.

        Args:
            credentials: Credentials to validate

        Returns:
            True if credentials are valid
        """
        try:
            # Create a temporary client with these credentials
            temp_client = ClobClient(
                host=self.host, chain_id=self.chain_id, key=self.private_key
            )

            # Set credentials
            temp_client.set_api_creds(
                ApiCreds(
                    api_key=credentials.api_key,
                    api_secret=credentials.api_secret,
                    api_passphrase=credentials.passphrase,
                )
            )

            # Make a test call
            temp_client.get_sampling_markets()
            return True

        except Exception as e:
            logger.error(f"Credential validation failed: {e}")
            return False

    async def rotate_credentials(self) -> dict[SignatureType, AuthCredentials]:
        """Rotate all credentials."""
        results = {}
        for sig_type in SignatureType:
            try:
                results[sig_type] = await self.refresh_credentials(sig_type)
            except Exception as e:
                logger.error(f"Failed to rotate credentials for {sig_type}: {e}")

        return results

    async def cleanup(self) -> None:
        """Clean up resources."""
        if self._client:
            # Close any open connections
            pass  # ClobClient doesn't have explicit close method

    def get_wallet_address(self) -> str:
        """Get the wallet address from the client."""
        if self._client is None:
            raise ValueError("Client not initialized")
        address = self._client.get_address()
        if address is None:
            raise ValueError("Failed to get wallet address")
        return address
