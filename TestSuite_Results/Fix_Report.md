# QAQC Fix Report — LeapXO v9-Production
## Prepared by: ALGA / Mr.Q / DRM Autonomous Agents + ZQ Engineering
## Date: 2026-04-03

---

## Executive Summary

This report documents all issues identified during the QAQC cycle for the
LeapXO v9-production release, the remediation actions taken, and the
verification status of each fix.  All **HIGH** severity issues have been
resolved and verified.  The system is **deployment-ready** upon merge.

---

## Issue Register

### CRIT-001 — API Keys Exposed in Frontend State / localStorage

| Field | Value |
|-------|-------|
| ID | CRIT-001 |
| Severity | CRITICAL |
| Discovered by | Mr.Q Code Audit |
| Affected version | v3.6 – v8.x |
| Component | `frontend/src/App.jsx` |

**Description:**  
API keys and other credentials were stored directly in React component state
(`useState`) and, in some configurations, persisted to `localStorage`.  This
made them accessible via browser developer tools and susceptible to XSS
exfiltration.

**Fix Applied (v9):**
- Introduced `frontend/src/hooks/useSecureStorage.js` — a Tauri
  Stronghold-backed storage hook.  In Tauri builds, secrets are written to
  hardware-encrypted Stronghold vault.  In browser builds, secrets exist only
  in React in-memory state and are never serialised to `localStorage` or
  `sessionStorage`.
- All component code refactored to use `useSecureStorage` for any
  potentially sensitive values.
- `localStorage.setItem` / `sessionStorage.setItem` calls with secret
  parameters are explicitly prohibited by this hook's design contract.

**Verification:** MRQ-034 ✅

---

### HIGH-001 — Hard-coded Server Port

| Field | Value |
|-------|-------|
| ID | HIGH-001 |
| Severity | HIGH |
| Discovered by | DRM Infrastructure Scan |
| Affected version | v3.6 – v8.x |
| Component | `backend/main.py` |

**Description:**  
The FastAPI server port was hard-coded to `8000`.  This prevented
containerised deployments from using a dynamic port assigned by the runtime
(Kubernetes, Tauri sidecar, Render, Railway, etc.).

**Fix Applied (v9):**
```python
PORT: int = int(os.environ.get("PORT", "8000"))
```
`uvicorn` is invoked with `--port $PORT` in all scripts and manifests.

**Verification:** DRM-001, DRM-002 ✅

---

### HIGH-002 — No Liveness / Readiness Probes

| Field | Value |
|-------|-------|
| ID | HIGH-002 |
| Severity | HIGH |
| Discovered by | DRM Infrastructure Scan |
| Affected version | v3.6 – v8.x |
| Component | `backend/main.py`, `helm/` |

**Description:**  
The backend had no Kubernetes probe endpoints (`/healthz`, `/readyz`).  The
Helm deployment.yaml referenced these paths but the application did not
implement them, causing pods to be permanently marked NotReady.

**Fix Applied (v9):**
- Added `GET /healthz` (liveness) and `GET /readyz` (readiness, verifies DB
  connection) endpoints.
- Helm `deployment.yaml` probes already pointed to these paths — now resolved.

**Verification:** MRQ-016, MRQ-017, MRQ-018 ✅

---

### HIGH-003 — No Input Validation on Pydantic Models

| Field | Value |
|-------|-------|
| ID | HIGH-003 |
| Severity | HIGH |
| Discovered by | Mr.Q Code Audit |
| Affected version | v3.6 – v8.x |
| Component | `backend/main.py` |

**Description:**  
Pydantic request models lacked field constraints.  An attacker could submit
payloads with empty labels, negative trust scores, prompts of unlimited
length, or arbitrary extra fields that could be exploited for injection or
denial-of-service.

**Fix Applied (v9):**
- All models updated to use `model_config = {"strict": True, "extra": "forbid"}`.
- Added `Field` constraints: `min_length`, `max_length`, `ge`, `le`.
- Added `@field_validator` for `label` (strips whitespace, rejects blank) and
  `metric_name` (alphanumeric + `_.-` only).

**Verification:** MRQ-001 through MRQ-014 ✅

---

### MED-001 — No Telemetry Rate Limiting

| Field | Value |
|-------|-------|
| ID | MED-001 |
| Severity | MEDIUM |
| Discovered by | DRM Load Test |
| Affected version | v3.6 – v8.x |
| Component | `backend/main.py` |

**Description:**  
The telemetry endpoint had no rate limiting.  A single client could flood the
database with millions of metric rows, causing storage exhaustion and
performance degradation.

**Fix Applied (v9):**
- Implemented per-IP sliding-window rate limiter (`_check_telemetry_rate`).
- Default: 60 requests per minute per client IP.
- Configurable via `LEAPXO_TELEMETRY_RATE_LIMIT` environment variable.
- Returns HTTP 429 with descriptive message when exceeded.

**Verification:** MRQ-035 through MRQ-038, DRM-005 ✅

---

### MED-002 — No Database Persistence (In-Memory State Only)

| Field | Value |
|-------|-------|
| ID | MED-002 |
| Severity | MEDIUM |
| Discovered by | ALGA Restart Test |
| Affected version | v3.6 – v8.x |
| Component | `backend/main.py` |

**Description:**  
All agent state (trust scores, overrides, history) was held in Python
in-memory objects and lost on every server restart.

**Fix Applied (v9):**
- Added `backend/db.py` with SQLite/SQLCipher+WAL database layer.
- Agent state written to DB on register and update.
- Audit events and telemetry persist to DB.
- FastAPI lifespan hook ensures DB opens on startup and closes on shutdown.

**Verification:** ALGA-033 through ALGA-042, DRM-007 through DRM-014 ✅

---

### MED-003 — Secrets Not Vault-Managed

| Field | Value |
|-------|-------|
| ID | MED-003 |
| Severity | MEDIUM |
| Discovered by | Mr.Q Security Audit |
| Affected version | v3.6 – v8.x |
| Component | `backend/` |

**Description:**  
No centralised secret management mechanism existed.  Credentials were either
hard-coded, scattered across environment variable reads, or absent entirely.

**Fix Applied (v9):**
- Added `backend/vault.py` with `VaultManager` class.
- All secret reads centralised: environment variable with file-mount fallback
  (Kubernetes secret volume pattern).
- Compatible with Tauri Stronghold (secrets injected as env vars by the Tauri
  IPC bridge at runtime).
- `GET /vault/status` exposes boolean summary (key set / not set) without
  revealing secret values.

**Verification:** MRQ-027 through MRQ-033, ALGA-012 ✅

---

### LOW-001 — Missing CI/CD Workflows

| Field | Value |
|-------|-------|
| ID | LOW-001 |
| Severity | LOW |
| Discovered by | ZQ Engineering Review |
| Affected version | v3.6 – v8.x |
| Component | `.github/workflows/` |

**Description:**  
No GitHub Actions workflows existed.  No automated testing, linting, or
release pipeline was in place.

**Fix Applied (v9):**
- Added `.github/workflows/ci.yml`: lint + pytest on every push/PR.
- Added `.github/workflows/release.yml`: Docker build + push + Helm package
  on version tag.

**Verification:** Workflow syntax validated with `actionlint` ✅

---

### LOW-002 — No Docker Compose for Local Development

| Field | Value |
|-------|-------|
| ID | LOW-002 |
| Severity | LOW |
| Discovered by | ZQ Engineering Review |
| Affected version | v3.6 – v8.x |

**Description:**  
Developers had no single-command way to spin up the complete stack locally.

**Fix Applied (v9):**
- Added `docker-compose.yml` with backend, frontend (nginx), and Redis.
- All secrets injected via `env_file: .env.local` — no secrets in
  docker-compose.yml itself.

**Verification:** DRM Docker Compose checks ✅

---

## Residual / Accepted Risks

| ID | Risk | Accepted By | Rationale |
|----|------|-------------|-----------|
| ACC-001 | `CORS allow_origins=["*"]` in development | ZQ Engineering | Restricted at ingress level in production via Kubernetes NetworkPolicy |
| ACC-002 | `PRAGMA synchronous=NORMAL` (WAL trade-off) | ZQ Engineering | Acceptable for this workload; full durability available via `PRAGMA synchronous=FULL` env override |
| ACC-003 | No rate limiting on `/agents/*` endpoints | ZQ Engineering | Internal service — protected by network policy; candidate for v10 |

---

## Overall Verdict

> **✅ APPROVED FOR PRODUCTION MERGE**
>
> All CRITICAL and HIGH findings resolved and verified.
> MEDIUM findings resolved and verified.
> Residual LOW/INFO risks documented and accepted.

---

_This report was generated by the ALGA/Mr.Q/DRM autonomous QAQC pipeline and
reviewed by ZQ Engineering on 2026-04-03._
