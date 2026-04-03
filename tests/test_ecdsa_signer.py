"""Tests for ECDSA signer / verifier."""

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from src.security.ecdsa_signer import ECDSASigner, ECDSAVerifier, canonical_payload
from src.core.exceptions import SignatureVerificationError


@pytest.fixture()
def signer():
    return ECDSASigner()


@pytest.fixture()
def verifier(signer):
    return ECDSAVerifier(signer.export_public_key())


class TestCanonicalPayload:
    def test_excludes_signature_field(self):
        skill = {"skill_id": "test", "signature": "abc", "version": "2.1"}
        payload = canonical_payload(skill)
        assert b'"signature"' not in payload

    def test_sorted_keys(self):
        skill = {"z": 1, "a": 2}
        payload = canonical_payload(skill).decode()
        assert payload.index('"a"') < payload.index('"z"')

    def test_deterministic(self):
        skill = {"skill_id": "abc", "intent": "test intent"}
        assert canonical_payload(skill) == canonical_payload(skill)


class TestECDSASigner:
    def test_generates_key_by_default(self, signer):
        assert signer.export_public_key().startswith(b"-----BEGIN PUBLIC KEY-----")

    def test_sign_returns_base64(self, signer):
        sig = signer.sign(b"hello world")
        assert isinstance(sig, str)
        assert len(sig) > 0

    def test_sign_skill(self, signer):
        skill = {"skill_id": "abc", "intent": "test"}
        sig = signer.sign_skill(skill)
        assert isinstance(sig, str)

    def test_from_pem_roundtrip(self, signer):
        pem = signer.export_private_key_pem()
        signer2 = ECDSASigner.from_pem(pem)
        # Both should produce verifiable signatures
        pub = signer.export_public_key()
        verifier = ECDSAVerifier(pub)
        payload = b"roundtrip test"
        sig = signer2.sign(payload)
        verifier.verify(payload, sig)


class TestECDSAVerifier:
    def test_valid_signature_passes(self, signer, verifier):
        payload = b"skill data payload"
        sig = signer.sign(payload)
        verifier.verify(payload, sig)  # should not raise

    def test_tampered_payload_fails(self, signer, verifier):
        payload = b"original payload"
        sig = signer.sign(payload)
        with pytest.raises(SignatureVerificationError):
            verifier.verify(b"tampered payload", sig)

    def test_wrong_signature_fails(self, verifier):
        with pytest.raises(SignatureVerificationError):
            verifier.verify(b"data", "bm90YXJlYWxzaWduYXR1cmU=")

    def test_verify_skill_no_signature(self, verifier):
        with pytest.raises(SignatureVerificationError, match="no signature"):
            verifier.verify_skill({"skill_id": "test"})

    def test_verify_skill_valid(self, signer, verifier):
        skill = {"skill_id": "test-skill", "intent": "demonstrate signing", "version": "2.1"}
        skill["signature"] = signer.sign_skill(skill)
        verifier.verify_skill(skill)  # should not raise

    def test_cross_key_fails(self):
        signer1 = ECDSASigner()
        signer2 = ECDSASigner()
        verifier2 = ECDSAVerifier(signer2.export_public_key())
        payload = b"payload"
        sig = signer1.sign(payload)
        with pytest.raises(SignatureVerificationError):
            verifier2.verify(payload, sig)
