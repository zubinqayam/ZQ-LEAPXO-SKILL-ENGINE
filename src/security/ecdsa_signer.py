"""ECDSA P-256 signature system for skill integrity verification.

Design:
* Private key lives ONLY inside the Skill Factory (never in the registry).
* Public key is published to the Skill Registry for verification.
* Every skill signed at rest; signature MUST be verified before load.
* Algorithm: ECDSA with P-256 curve + SHA-256 (deterministic, FIPS-140 compatible).

Usage:
    signer = ECDSASigner()
    public_pem = signer.export_public_key()

    payload = canonical_payload(skill_dict)
    sig_b64 = signer.sign(payload)

    verifier = ECDSAVerifier(public_pem)
    verifier.verify(payload, sig_b64)  # raises SignatureVerificationError on failure
"""

from __future__ import annotations

import base64
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from src.core.exceptions import SignatureVerificationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def canonical_payload(skill: dict) -> bytes:
    """Return a stable canonical byte representation of a skill dict.

    The 'signature' field is excluded so that the payload can be signed
    without a chicken-and-egg problem.
    Serialised as UTF-8 JSON with sorted keys, no extra whitespace.
    """
    clean = {k: v for k, v in skill.items() if k != "signature"}
    return json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


# ---------------------------------------------------------------------------
# Signer (private-key side — Skill Factory only)
# ---------------------------------------------------------------------------


class ECDSASigner:
    """Signs skill payloads with ECDSA P-256.

    In production the private key is generated once, stored in an HSM or
    sealed secret, and NEVER leaves the Skill Factory environment.
    """

    def __init__(self, private_key: ec.EllipticCurvePrivateKey | None = None) -> None:
        self._private_key: ec.EllipticCurvePrivateKey = (
            private_key if private_key is not None else ec.generate_private_key(ec.SECP256R1())
        )

    # ------------------------------------------------------------------
    # Key export
    # ------------------------------------------------------------------

    def export_private_key_pem(self, password: bytes | None = None) -> bytes:
        """Export the private key as PEM (handle with care)."""
        encryption = (
            serialization.BestAvailableEncryption(password)
            if password
            else serialization.NoEncryption()
        )
        return self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption,
        )

    def export_public_key(self) -> bytes:
        """Export the corresponding public key as PEM."""
        return self._private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    # ------------------------------------------------------------------
    # Sign
    # ------------------------------------------------------------------

    def sign(self, payload: bytes) -> str:
        """Sign *payload* and return a base64-encoded DER signature string."""
        sig_der = self._private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
        return base64.b64encode(sig_der).decode("ascii")

    def sign_skill(self, skill: dict) -> str:
        """Compute canonical payload for *skill* and return its signature."""
        return self.sign(canonical_payload(skill))

    # ------------------------------------------------------------------
    # Class-level factory
    # ------------------------------------------------------------------

    @classmethod
    def from_pem(cls, pem: bytes, password: bytes | None = None) -> ECDSASigner:
        key = serialization.load_pem_private_key(pem, password=password)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise ValueError("PEM does not contain an EC private key.")
        return cls(private_key=key)


# ---------------------------------------------------------------------------
# Verifier (public-key side — Skill Registry)
# ---------------------------------------------------------------------------


class ECDSAVerifier:
    """Verifies skill signatures using the published public key."""

    def __init__(self, public_key_pem: bytes) -> None:
        key = serialization.load_pem_public_key(public_key_pem)
        if not isinstance(key, ec.EllipticCurvePublicKey):
            raise ValueError("PEM does not contain an EC public key.")
        self._public_key: ec.EllipticCurvePublicKey = key

    def verify(self, payload: bytes, signature_b64: str) -> None:
        """Verify *signature_b64* against *payload*.

        Raises:
            SignatureVerificationError: If the signature is invalid or the
                payload has been tampered with.
        """
        try:
            sig_der = base64.b64decode(signature_b64)
            self._public_key.verify(sig_der, payload, ec.ECDSA(hashes.SHA256()))
        except (InvalidSignature, Exception) as exc:
            raise SignatureVerificationError(
                "ECDSA signature verification failed — skill may have been tampered with."
            ) from exc

    def verify_skill(self, skill: dict) -> None:
        """Convenience wrapper: extract signature from *skill* and verify."""
        sig = skill.get("signature")
        if not sig:
            raise SignatureVerificationError("Skill carries no signature.")
        self.verify(canonical_payload(skill), sig)
