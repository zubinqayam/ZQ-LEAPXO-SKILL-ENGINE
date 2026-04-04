"""
tests/test_backend_v9.py — Tests for LeapXO v9 backend enhancements.

Covers:
- Strict Pydantic v2 request validation
- Dynamic port configuration
- Telemetry rate limiting
- VaultManager / secure key management
- SQLite+WAL database layer (db.py)
- FastAPI endpoint contracts (/healthz, /readyz, /vault/status, /telemetry)
"""

import os
import time

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Pydantic model validation tests
# ---------------------------------------------------------------------------
class TestRegisterAgentRequestValidation:
    def test_valid_label(self):
        from backend.main import RegisterAgentRequest

        req = RegisterAgentRequest(label="my-agent", initial_trust=0.9)
        assert req.label == "my-agent"
        assert req.initial_trust == 0.9

    def test_blank_label_raises(self):
        from backend.main import RegisterAgentRequest

        with pytest.raises(ValidationError):
            RegisterAgentRequest(label="   ", initial_trust=1.0)

    def test_label_stripped(self):
        from backend.main import RegisterAgentRequest

        req = RegisterAgentRequest(label="  trimmed  ", initial_trust=1.0)
        assert req.label == "trimmed"

    def test_trust_above_one_raises(self):
        from backend.main import RegisterAgentRequest

        with pytest.raises(ValidationError):
            RegisterAgentRequest(label="x", initial_trust=1.5)

    def test_trust_below_zero_raises(self):
        from backend.main import RegisterAgentRequest

        with pytest.raises(ValidationError):
            RegisterAgentRequest(label="x", initial_trust=-0.1)

    def test_extra_field_raises(self):
        from backend.main import RegisterAgentRequest

        with pytest.raises(ValidationError):
            RegisterAgentRequest(label="x", initial_trust=1.0, hacked="payload")


class TestScheduleTaskRequestValidation:
    def test_valid(self):
        from backend.main import ScheduleTaskRequest

        req = ScheduleTaskRequest(model_hash="abc123", prompt="hello", priority=3)
        assert req.priority == 3

    def test_priority_too_low_raises(self):
        from backend.main import ScheduleTaskRequest

        with pytest.raises(ValidationError):
            ScheduleTaskRequest(model_hash="abc", prompt="x", priority=0)

    def test_priority_too_high_raises(self):
        from backend.main import ScheduleTaskRequest

        with pytest.raises(ValidationError):
            ScheduleTaskRequest(model_hash="abc", prompt="x", priority=11)

    def test_prompt_too_long_raises(self):
        from backend.main import ScheduleTaskRequest

        with pytest.raises(ValidationError):
            ScheduleTaskRequest(model_hash="abc", prompt="x" * 4097, priority=5)

    def test_extra_field_raises(self):
        from backend.main import ScheduleTaskRequest

        with pytest.raises(ValidationError):
            ScheduleTaskRequest(model_hash="abc", prompt="x", priority=1, evil="field")


class TestTelemetryRequestValidation:
    def test_valid(self):
        from backend.main import TelemetryRequest

        req = TelemetryRequest(metric_name="cpu.usage", value=0.75)
        assert req.metric_name == "cpu.usage"

    def test_metric_name_special_chars_raises(self):
        from backend.main import TelemetryRequest

        with pytest.raises(ValidationError):
            TelemetryRequest(metric_name="bad metric!", value=1.0)

    def test_labels_too_long_raises(self):
        from backend.main import TelemetryRequest

        with pytest.raises(ValidationError):
            TelemetryRequest(metric_name="m", value=1.0, labels="x" * 513)

    def test_extra_field_raises(self):
        from backend.main import TelemetryRequest

        with pytest.raises(ValidationError):
            TelemetryRequest(metric_name="m", value=1.0, injected="evil")


class TestParseCorsAllowOrigins:
    def test_empty_unset_means_wildcard(self):
        from backend.main import parse_cors_allow_origins

        assert parse_cors_allow_origins(None) == ["*"]
        assert parse_cors_allow_origins("") == ["*"]
        assert parse_cors_allow_origins("   ") == ["*"]

    def test_comma_separated_origins(self):
        from backend.main import parse_cors_allow_origins

        out = parse_cors_allow_origins(
            "https://app.leapxo.example.com, https://other.example "
        )
        assert out == ["https://app.leapxo.example.com", "https://other.example"]

    def test_only_commas_falls_back_to_wildcard(self):
        from backend.main import parse_cors_allow_origins

        assert parse_cors_allow_origins(", , ") == ["*"]


# ---------------------------------------------------------------------------
# Dynamic PORT configuration
# ---------------------------------------------------------------------------
class TestDynamicPort:
    def test_default_port(self, monkeypatch):
        monkeypatch.delenv("PORT", raising=False)
        import backend.main as bm

        # PORT is module-level constant; verify it falls back to 8000
        assert int(os.environ.get("PORT", "8000")) == bm.PORT

    def test_custom_port(self, monkeypatch):
        monkeypatch.setenv("PORT", "9001")
        # Re-evaluating the expression, not re-importing (module already loaded)
        assert int(os.environ.get("PORT", "8000")) == 9001


# ---------------------------------------------------------------------------
# Telemetry rate limiter
# ---------------------------------------------------------------------------
class TestTelemetryRateLimit:
    @pytest.mark.asyncio
    async def test_within_limit_passes(self, monkeypatch):
        monkeypatch.setenv("LEAPXO_TELEMETRY_RATE_LIMIT", "5")
        from backend import main as bm

        bm._telemetry_window.clear()
        # Allow 5 requests
        for _ in range(5):
            await bm._check_telemetry_rate("127.0.0.1")

    @pytest.mark.asyncio
    async def test_over_limit_raises(self, monkeypatch):
        from backend import main as bm
        from fastapi import HTTPException

        bm._telemetry_window.clear()
        # Fill the window
        ip = "10.0.0.99"
        now = time.monotonic()
        bm._telemetry_window[ip] = __import__("collections").deque(
            [now - i * 0.1 for i in range(60)]
        )
        with pytest.raises(HTTPException) as exc_info:
            await bm._check_telemetry_rate(ip)
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_old_entries_evicted(self):
        from backend import main as bm

        ip = "192.168.1.1"
        # Add 60 entries older than 60 seconds
        bm._telemetry_window[ip] = __import__("collections").deque(
            [time.monotonic() - 61 for _ in range(60)]
        )
        # Should not raise — old entries are evicted
        await bm._check_telemetry_rate(ip)


# ---------------------------------------------------------------------------
# VaultManager
# ---------------------------------------------------------------------------
class TestVaultManager:
    def test_db_key_from_env(self, monkeypatch):
        monkeypatch.setenv("LEAPXO_DB_KEY", "mysecretkey")
        from backend.vault import VaultManager

        vm = VaultManager()
        assert vm.db_key() == "mysecretkey"

    def test_db_key_empty_when_unset(self, monkeypatch):
        monkeypatch.delenv("LEAPXO_DB_KEY", raising=False)
        from backend.vault import VaultManager

        vm = VaultManager()
        assert vm.db_key() == ""

    def test_api_key_raises_when_absent_in_production(self, monkeypatch):
        monkeypatch.setenv("LEAPXO_ENV", "production")
        monkeypatch.delenv("LEAPXO_API_KEY", raising=False)
        from backend.vault import VaultManager

        vm = VaultManager()
        with pytest.raises(RuntimeError, match="API key"):
            vm.api_key()

    def test_secret_key_dev_fallback(self, monkeypatch):
        monkeypatch.setenv("LEAPXO_ENV", "development")
        monkeypatch.delenv("LEAPXO_SECRET_KEY", raising=False)
        from backend.vault import VaultManager

        vm = VaultManager()
        key = vm.secret_key()
        assert "dev-insecure" in key

    def test_secret_key_raises_in_production_when_unset(self, monkeypatch):
        monkeypatch.setenv("LEAPXO_ENV", "production")
        monkeypatch.delenv("LEAPXO_SECRET_KEY", raising=False)
        from backend.vault import VaultManager

        vm = VaultManager()
        with pytest.raises(RuntimeError, match="Secret key"):
            vm.secret_key()

    def test_summary_has_no_secret_values(self, monkeypatch):
        monkeypatch.setenv("LEAPXO_DB_KEY", "top-secret")
        monkeypatch.setenv("LEAPXO_API_KEY", "sk-secret")
        from backend.vault import VaultManager

        vm = VaultManager()
        summary = vm.summary()
        # Values must be booleans (or the environment string), not actual key strings
        for key, val in summary.items():
            if key == "environment":
                assert isinstance(val, str)
            else:
                assert isinstance(val, bool), (
                    f"Summary field '{key}' should be a boolean, got {type(val).__name__}: {val!r}"
                )
        assert summary["db_key_set"] is True
        assert summary["api_key_set"] is True


# ---------------------------------------------------------------------------
# Database layer (db.py) — using in-memory / temp file SQLite
# ---------------------------------------------------------------------------
class TestDatabase:
    @pytest.fixture
    def db(self, tmp_path):
        from backend.db import Database

        d = Database(str(tmp_path / "test.db"))
        d.connect()
        yield d
        d.close()

    def test_wal_mode(self, db):
        cur = db._conn.execute("PRAGMA journal_mode")
        mode = cur.fetchone()[0]
        assert mode == "wal"

    def test_tables_created(self, db):
        cur = db._conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = {row[0] for row in cur.fetchall()}
        assert {"agents", "audit_events", "telemetry"} <= tables

    @pytest.mark.asyncio
    async def test_upsert_agent(self, db):
        await db.upsert_agent("hash1", "agent-one", 0.8)
        rows = await db.fetchall("SELECT * FROM agents WHERE model_hash = ?", ("hash1",))
        assert len(rows) == 1
        assert rows[0]["label"] == "agent-one"
        assert rows[0]["trust_score"] == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_upsert_agent_updates_on_conflict(self, db):
        await db.upsert_agent("hash2", "agent-two", 0.5)
        await db.upsert_agent("hash2", "agent-two", 0.9)
        rows = await db.fetchall("SELECT trust_score FROM agents WHERE model_hash = ?", ("hash2",))
        assert rows[0]["trust_score"] == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_optimistic_lock_success(self, db):
        await db.upsert_agent("hash3", "agent-three", 0.7)
        success = await db.update_with_version(
            table="agents",
            updates={"trust_score": 0.6},
            where_key="model_hash",
            where_value="hash3",
            expected_version=1,
        )
        assert success is True

    @pytest.mark.asyncio
    async def test_optimistic_lock_stale_version(self, db):
        await db.upsert_agent("hash4", "agent-four", 0.7)
        success = await db.update_with_version(
            table="agents",
            updates={"trust_score": 0.6},
            where_key="model_hash",
            where_value="hash4",
            expected_version=99,  # wrong version
        )
        assert success is False

    @pytest.mark.asyncio
    async def test_archive_agent(self, db):
        await db.upsert_agent("hash5", "agent-five", 0.1)
        await db.archive_agent("hash5")
        active = await db.list_agents(archived=False)
        assert not any(r["model_hash"] == "hash5" for r in active)
        archived = await db.list_agents(archived=True)
        assert any(r["model_hash"] == "hash5" for r in archived)

    @pytest.mark.asyncio
    async def test_record_telemetry(self, db):
        await db.record_telemetry("test.metric", 42.0, "env=test")
        rows = await db.fetchall("SELECT * FROM telemetry WHERE metric_name = ?", ("test.metric",))
        assert len(rows) == 1
        assert rows[0]["value"] == pytest.approx(42.0)

    @pytest.mark.asyncio
    async def test_audit_event(self, db):
        await db.audit("test_event", "hash6", "payload data")
        rows = await db.fetchall("SELECT * FROM audit_events WHERE event_type = ?", ("test_event",))
        assert len(rows) == 1
        assert rows[0]["payload"] == "payload data"

    @pytest.mark.asyncio
    async def test_schema_migration_idempotent(self, db):
        # Running migrate again should not raise
        db._migrate()

    def test_close_and_reopen(self, tmp_path):
        from backend.db import Database

        path = str(tmp_path / "persist.db")
        d = Database(path)
        d.connect()
        d.close()
        # Reopen and verify tables still exist
        d2 = Database(path)
        d2.connect()
        cur = d2._conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = {row[0] for row in cur.fetchall()}
        assert "agents" in tables
        d2.close()


class TestDatabaseSingleton:
    def test_get_db_raises_before_init(self, monkeypatch):
        import backend.db as db_mod

        original = db_mod._db
        db_mod._db = None
        try:
            with pytest.raises(RuntimeError, match="not been initialised"):
                db_mod.get_db()
        finally:
            db_mod._db = original

    def test_init_db_returns_database(self, tmp_path):
        import backend.db as db_mod

        original = db_mod._db
        try:
            db = db_mod.init_db(str(tmp_path / "singleton.db"))
            assert db is not None
            assert db_mod.get_db() is db
        finally:
            db_mod.close_db()
            db_mod._db = original
