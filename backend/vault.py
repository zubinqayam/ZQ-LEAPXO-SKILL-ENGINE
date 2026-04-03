"""
backend/vault.py — LeapXO v9 secure vault / key management.

Provides a `VaultManager` that reads sensitive credentials from:
  1. Tauri Stronghold (injected at runtime via environment variables set by the
     Tauri IPC bridge or a sidecar process)
  2. Kubernetes Secrets (mounted as environment variables or files)
  3. A local .env file (development fallback — never committed)

No secrets are stored in localStorage, module globals, or source code.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment variable names
# ---------------------------------------------------------------------------
_ENV_DB_KEY = "LEAPXO_DB_KEY"
_ENV_API_KEY = "LEAPXO_API_KEY"  # LLM provider key
_ENV_REDIS_URL = "LEAPXO_REDIS_URL"
_ENV_SECRET_KEY = "LEAPXO_SECRET_KEY"  # JWT / HMAC signing key
_ENV_VAULT_TOKEN = "LEAPXO_VAULT_TOKEN"  # HashiCorp / Tauri Stronghold token
_ENV_FEEDBACK_KEY = "LEAPXO_FEEDBACK_ENC_KEY"  # Feedback chatbot keyhole key

# Path for Kubernetes secret file mounts (optional; env vars take precedence)
_SECRET_FILE_DIR = Path(os.environ.get("LEAPXO_SECRET_DIR", "/run/secrets/leapxo"))


class VaultManager:
    """
    Centralised key/secret accessor.

    All secret reads go through this class.  The class deliberately does NOT
    cache secrets in instance attributes — every call re-reads from the
    environment so that secret rotation is picked up automatically.
    """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _read_env(name: str) -> str | None:
        value = os.environ.get(name, "").strip()
        return value if value else None

    @staticmethod
    def _read_file(filename: str) -> str | None:
        path = _SECRET_FILE_DIR / filename
        try:
            content = path.read_text().strip()
            return content if content else None
        except (FileNotFoundError, PermissionError):
            return None

    def _get(self, env_name: str, file_name: str) -> str | None:
        """
        Read a secret — environment variable takes precedence over file mount.
        Returns None when the secret is not configured (caller decides whether
        to raise or use a default).
        """
        value = self._read_env(env_name)
        if value:
            return value
        value = self._read_file(file_name)
        if value:
            return value
        return None

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------
    def db_key(self) -> str:
        """SQLCipher database encryption key.  Empty string = unencrypted."""
        return self._get(_ENV_DB_KEY, "db-key") or ""

    def api_key(self) -> str:
        """LLM provider API key. Raises if not configured in production."""
        key = self._get(_ENV_API_KEY, "api-key")
        if not key:
            env = os.environ.get("LEAPXO_ENV", "development")
            if env == "production":
                raise RuntimeError(
                    "LLM API key not configured. "
                    f"Set the {_ENV_API_KEY} environment variable or mount a secret "
                    "at /run/secrets/leapxo/api-key."
                )
            logger.warning(
                "LLM API key not configured (%s); continuing without an API key in %s.",
                _ENV_API_KEY,
                env,
            )
            return ""
        return key

    def redis_url(self) -> str:
        """Redis connection URL with optional auth token."""
        return self._get(_ENV_REDIS_URL, "redis-url") or "redis://localhost:6379/0"

    def secret_key(self) -> str:
        """HMAC/JWT signing key.  Raises if not configured in production."""
        key = self._get(_ENV_SECRET_KEY, "secret-key")
        if not key:
            env = os.environ.get("LEAPXO_ENV", "development")
            if env == "production":
                raise RuntimeError(
                    f"Secret key not configured in production. Set {_ENV_SECRET_KEY}."
                )
            # Development fallback — never use in production
            logger.warning(
                "Using insecure development secret key. "
                "Set the LEAPXO_SECRET_KEY environment variable for production deployments."
            )
            return "dev-insecure-secret-key-do-not-use-in-production"
        return key

    def feedback_enc_key(self) -> str:
        """Feedback chatbot keyhole encryption key."""
        key = self._get(_ENV_FEEDBACK_KEY, "feedback-enc-key")
        if not key:
            logger.warning(
                "Feedback encryption key not set (%s). Feedback at rest will not be encrypted.",
                _ENV_FEEDBACK_KEY,
            )
            return ""
        return key

    def vault_token(self) -> str | None:
        """Optional HashiCorp Vault / Tauri Stronghold token for dynamic secrets."""
        return self._get(_ENV_VAULT_TOKEN, "vault-token")

    def is_production(self) -> bool:
        return os.environ.get("LEAPXO_ENV", "development").lower() == "production"

    def summary(self) -> dict:
        """Return a safe summary (no secret values) for health/status endpoints."""
        return {
            "db_key_set": bool(self._get(_ENV_DB_KEY, "db-key")),
            "api_key_set": bool(self._get(_ENV_API_KEY, "api-key")),
            "redis_url_set": bool(self._get(_ENV_REDIS_URL, "redis-url")),
            "secret_key_set": bool(self._get(_ENV_SECRET_KEY, "secret-key")),
            "vault_token_set": bool(self._get(_ENV_VAULT_TOKEN, "vault-token")),
            "feedback_key_set": bool(self._get(_ENV_FEEDBACK_KEY, "feedback-enc-key")),
            "environment": os.environ.get("LEAPXO_ENV", "development"),
        }


@lru_cache(maxsize=1)
def get_vault() -> VaultManager:
    """Return the module-level VaultManager singleton."""
    return VaultManager()
