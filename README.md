# LeapXO Skill Engine — v9 Production

> **Deployment- and audit-ready** AI skill orchestration with QAQC-verified
> security enhancements, SQLCipher+WAL persistence, Tauri Stronghold secure
> vault key management, and comprehensive CI/CD.

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

---

## Table of Contents

1. [What's New in v9](#whats-new-in-v9)
2. [Architecture](#architecture)
3. [Repository Layout](#repository-layout)
4. [Quick Start](#quick-start)
5. [Security](#security)
6. [API Reference](#api-reference)
7. [Kubernetes Deployment](#kubernetes-deployment)
8. [Build Scripts](#build-scripts)
9. [Running Tests](#running-tests)
10. [QAQC Results](#qaqc-results)
11. [Skill Schema](#skill-schema)
12. [Design Principles](#design-principles)
13. [Roadmap](#roadmap)

---

## What's New in v9

| Enhancement | Detail |
|---|---|
| **SQLCipher + WAL** | Agent state, audit events, and telemetry persist in an encrypted SQLite database with WAL journal mode |
| **Secure Vault** | `backend/vault.py` centralises all secret access — env vars + K8s secret-file fallback; Tauri Stronghold compatible |
| **Dynamic Port** | `PORT` env var (default 8000); works with Tauri sidecar, containers, and PaaS |
| **Strict Pydantic v2** | `strict=True`, `extra="forbid"`, field validators on all request models |
| **Optimistic Locking** | Per-row `version` column — concurrent trust-score updates are safe |
| **Telemetry Rate Limiting** | Per-IP 60 req/min sliding window; configurable via `LEAPXO_TELEMETRY_RATE_LIMIT` |
| **Liveness / Readiness Probes** | `GET /healthz` + `GET /readyz` (verifies DB connection) |
| **Frontend Secure Storage** | `useSecureStorage` hook — Tauri Stronghold in desktop builds, in-memory only in browser |
| **Tauri 2.x Integration** | `@tauri-apps/api` + `@tauri-apps/plugin-stronghold` in frontend |
| **CI/CD Workflows** | GitHub Actions: pytest (3.11 + 3.12), ruff lint, React build, Docker push, Helm package |
| **Docker Compose** | `docker compose up` for backend + frontend (nginx) + Redis |
| **Build Scripts** | Linux, Windows (PowerShell), Android (Tauri Mobile) |
| **QAQC** | 110 tests across ALGA / Mr.Q / DRM; all CRITICAL + HIGH findings resolved |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        UI LAYER                              │
│  React + Vite / Tauri Desktop + Mobile                       │
│  useSecureStorage → Tauri Stronghold (hardware-encrypted)    │
└──────────────────────────────────────────────────────────────┘
                         ↓ REST / Tauri IPC
┌──────────────────────────────────────────────────────────────┐
│                   FASTAPI BACKEND (v9)                       │
│  Dynamic PORT · Strict Pydantic v2 · Telemetry Rate Limit    │
│  VaultManager · /healthz /readyz · Audit Logging             │
└──────────────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────────┐
│                ORCHESTRATION LAYER                           │
│  Execution Engine · Circuit Breakers · Meta-Agent            │
│  Token Budget · Priority Queue · Adversarial Simulation      │
└──────────────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────────┐
│              SKILL TOOLSET LAYER (src/)                      │
│  L1 Discovery → L2 Instruction → L3 Sandboxed Execution      │
└──────────────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────────┐
│           GOVERNANCE & SECURITY (src/)                       │
│  ECDSA P-256 · Prompt Firewall · Policy Engine               │
│  Hash-chained Audit Log · MFA Approval Workflow              │
└──────────────────────────────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────────┐
│          DATA & REGISTRY LAYER                               │
│  SQLCipher+WAL DB · Optimistic Locking · Semantic Cache      │
│  Skill Registry (HNSW) · Redis IPC                           │
└──────────────────────────────────────────────────────────────┘
```

---

## Repository Layout

```
.
├── backend/
│   ├── __init__.py
│   ├── main.py          FastAPI v9 — strict validation, dynamic port, rate limit
│   ├── db.py            SQLCipher+WAL database layer, optimistic locking
│   └── vault.py         Secure vault key management (env / file / Stronghold)
├── frontend/
│   ├── src/
│   │   ├── App.jsx      React UI using useSecureStorage (no localStorage secrets)
│   │   ├── main.jsx
│   │   └── hooks/
│   │       └── useSecureStorage.js  Tauri Stronghold-compatible hook
│   ├── package.json     Includes @tauri-apps/api + @tauri-apps/plugin-stronghold
│   ├── Dockerfile.frontend
│   └── nginx.conf
├── src/                 Core Python skill-engine library (v2.1)
│   ├── core/            Skill schema, token predictor, exceptions
│   ├── execution/       L1/L2/L3 executors, circuit breaker
│   ├── security/        ECDSA signer, prompt firewall, policy engine
│   ├── orchestration/   Orchestration engine
│   ├── governance/      Audit logger, approval workflow
│   ├── cache/           Semantic cache
│   ├── registry/        Skill registry (HNSW)
│   └── repair/          Auto-repair pipeline
├── tests/               pytest suite (144 tests, all passing)
│   └── test_backend_v9.py  New v9-specific tests (39 tests)
├── TestSuite_Results/   ALGA / Mr.Q / DRM QAQC artifacts
│   ├── ALGA_TestResults.md
│   ├── MrQ_TestResults.md
│   ├── DRM_QAQC_TestResults.md
│   ├── Fix_Report.md
│   └── QAQC_Summary.md
├── scripts/
│   ├── build-linux.sh
│   ├── build-windows.ps1
│   ├── build-android.sh
│   └── test-all.sh
├── k8s/
│   ├── namespace.yaml
│   └── secrets.yaml     Secret template (no values committed)
├── helm/leapxo-skill-engine/
│   ├── Chart.yaml       v9.0.0
│   ├── values.yaml      Vault secret env-var injection, probes, PORT
│   └── templates/
│       ├── deployment.yaml
│       └── _helpers.tpl
├── .github/workflows/
│   ├── ci.yml           Lint + pytest + React build on every push/PR
│   └── release.yml      Docker push + Helm package on version tags
├── Dockerfile.backend
├── docker-compose.yml
├── .env.example         Copy to .env.local (never committed)
├── pyproject.toml       v9.0.0
├── requirements.txt
└── skills/examples/     Sample skill definitions
```

---

## Quick Start

### Prerequisites

| Tool | Minimum Version |
|------|----------------|
| Python | 3.11 |
| Node.js | 20 |
| Docker | 24 (optional) |

### Backend (FastAPI)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure secrets
cp .env.example .env.local
# Edit .env.local — at minimum set LEAPXO_ENV=development

# 3. Start
export $(grep -v '^#' .env.local | xargs)
uvicorn backend.main:app --reload --host 0.0.0.0 --port ${PORT:-8000}
```

API: `http://localhost:8000`  
Interactive docs: `http://localhost:8000/docs`  
Vault status: `http://localhost:8000/vault/status`

### Frontend (React + Vite / Tauri)

```bash
cd frontend

# Vite dev server (browser)
npm install
npm run dev
# → http://localhost:5173

# Tauri desktop (requires Rust + Tauri CLI 2.x)
npm install
npx tauri dev
```

### Docker Compose (all-in-one)

```bash
cp .env.example .env.local   # edit with your secrets
docker compose up
# Backend  → http://localhost:8000
# Frontend → http://localhost:5173
```

---

## Security

### Secure Vault Key Management

`backend/vault.py` — all secrets read from:

1. **Environment variables** (highest priority)
2. **Kubernetes secret file mounts** (`/run/secrets/leapxo/<name>`)

| Secret | Env Var | Purpose |
|--------|---------|---------|
| DB encryption key | `LEAPXO_DB_KEY` | SQLCipher at-rest encryption |
| LLM API key | `LEAPXO_API_KEY` | LLM provider authentication |
| JWT/HMAC key | `LEAPXO_SECRET_KEY` | Token signing |
| Feedback key | `LEAPXO_FEEDBACK_ENC_KEY` | Feedback chatbot keyhole |
| Vault token | `LEAPXO_VAULT_TOKEN` | HashiCorp Vault / Stronghold token |

`GET /vault/status` returns a boolean summary — safe for monitoring.

### SQLCipher + WAL Database

- WAL journal mode enabled on every connection
- SQLCipher encryption when `pysqlcipher3` is installed and `LEAPXO_DB_KEY` is set
- Optimistic locking via per-row `version` counter
- Asyncio `Lock` serialises all write operations

```bash
# Enable encryption
pip install 'leapxo-skill-engine[sqlcipher]'
export LEAPXO_DB_KEY='32-char-random-key'
```

### Tauri Stronghold (Desktop / Mobile)

`frontend/src/hooks/useSecureStorage.js`:

- **Tauri builds**: secrets stored in hardware-encrypted Stronghold vault
- **Browser builds**: secrets in React in-memory state only — **never** `localStorage`

### Telemetry Rate Limiting

`POST /telemetry`: per-IP sliding-window, default 60 req/min.  
Returns HTTP 429 when exceeded. Override: `LEAPXO_TELEMETRY_RATE_LIMIT`.

### ECDSA P-256 Signing

```python
from src.security.ecdsa_signer import ECDSASigner, ECDSAVerifier

signer = ECDSASigner()
skill["signature"] = signer.sign_skill(skill)

verifier = ECDSAVerifier(signer.export_public_key())
verifier.verify_skill(skill)   # raises SignatureVerificationError on tamper
```

P0 skills **must** carry a valid ECDSA signature.

### Prompt Firewall

```python
from src.security.prompt_firewall import PromptFirewall

fw = PromptFirewall(strict_mode=True)
fw.inspect("What is the capital of France?")     # ALLOW
fw.inspect("Ignore all previous instructions")   # raises PromptFirewallError
```

### Policy Engine

```python
from src.security.policy_engine import PolicyEngine

policy = PolicyEngine()
decision = policy.evaluate(
    skill_region_code="OM",
    request_region_code="OM",
    skill_tags=["medical", "triage"],
    security_level="P1",
)
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Version ping |
| `GET` | `/healthz` | Kubernetes liveness probe |
| `GET` | `/readyz` | Kubernetes readiness probe (DB check) |
| `GET` | `/vault/status` | Vault configuration summary (no secret values) |
| `GET` | `/status` | Orchestrator status snapshot |
| `GET` | `/agents` | List active agents |
| `GET` | `/agents/archived` | List archived agents |
| `POST` | `/agents/register` | Register a Skill DNA agent |
| `POST` | `/agents/override` | Set human override (allow/block) |
| `POST` | `/tasks/schedule` | Queue a prompt task |
| `POST` | `/tasks/run` | Execute all queued tasks |
| `POST` | `/telemetry` | Record a telemetry metric (rate-limited) |

---

## Kubernetes Deployment

```bash
# 1. Create namespace and secrets
kubectl apply -f k8s/namespace.yaml
kubectl create secret generic leapxo-vault-secrets \
  --from-literal=db-key='<key>' \
  --from-literal=api-key='<key>' \
  --from-literal=secret-key='<key>' \
  --from-literal=feedback-enc-key='<key>' \
  --namespace leapxo

# 2. Deploy via Helm
helm install leapxo ./helm/leapxo-skill-engine \
  --set global.deploymentMode=cloud \
  --set security.enforceSignatures=true \
  --namespace leapxo

# 3. Verify
kubectl get pods -n leapxo
curl http://<cluster-ip>/readyz
```

**Modes**: `cloud` | `hybrid` | `air-gapped`

---

## Build Scripts

| Platform | Script |
|----------|--------|
| Linux | `./scripts/build-linux.sh [--tauri] [--skip-tests]` |
| Windows | `.\scripts\build-windows.ps1 [-Tauri] [-SkipTests]` |
| Android | `./scripts/build-android.sh [--release]` |
| All tests | `./scripts/test-all.sh [--coverage] [--fail-fast]` |

---

## Running Tests

```bash
pytest tests/ -v --tb=short
# Expected: 144 passed

pytest tests/ -v --tb=short --cov=src --cov=backend --cov-report=term-missing
```

---

## QAQC Results

All artifacts in [`TestSuite_Results/`](TestSuite_Results/):

| Suite | Tests | Pass | Coverage |
|-------|-------|------|----------|
| [ALGA](TestSuite_Results/ALGA_TestResults.md) | 42 | 42 | 97.6 % |
| [Mr.Q](TestSuite_Results/MrQ_TestResults.md) | 38 | 38 | 96.2 % |
| [DRM](TestSuite_Results/DRM_QAQC_TestResults.md) | 30 | 30 | 94.8 % |
| **Total** | **110** | **110** | **96.2 %** |

See [`Fix_Report.md`](TestSuite_Results/Fix_Report.md) — all CRITICAL/HIGH findings resolved.  
**Verdict: ✅ APPROVED FOR PRODUCTION MERGE**

---

## Skill Schema

```json
{
  "skill_id": "kebab-case-id",
  "version": "2.1",
  "intent": "...",
  "output_format": "text|json|markdown|structured",
  "region_code": "GL",
  "security_level": "P0|P1|P2",
  "signature": "<ECDSA-base64>",
  "dependencies": [],
  "instructions": [
    { "content": "...", "prunable": false, "weight": 1.0 }
  ],
  "metadata": { "author": "...", "tags": [], "description": "..." }
}
```

Rules: kebab-case `skill_id`, P0 requires ECDSA signature, extra fields forbidden.

---

## Design Principles

| Principle | Implementation |
|-----------|---------------|
| Secrets as Default | VaultManager, SQLCipher, Stronghold, no localStorage |
| Context Economy First | tiktoken predictor + 15 % buffer + NON-PRUNABLE tags |
| Security as Default | ECDSA P-256 signatures, LLM-based firewall, fail-closed |
| Deterministic + Generative | Strict Pydantic v2 schema + sandboxed execution |
| Human-Governed Autonomy | MFA approval workflow, cooldown timer, audit log |
| Fail Gracefully | Tiered circuit breakers, partial degrade |

---

## Roadmap

| Phase | Target | Focus |
|-------|--------|-------|
| v9 ✅ | Current | SQLCipher+WAL, vault, Stronghold, rate limit, QAQC |
| v10 | Q3 2026 | External Secrets Operator, secret rotation API |
| v11 | Q4 2026 | Feedback chatbot Prometheus/Grafana dashboard |
| v12 | Q1 2027 | Multi-region HA, Blue/Green Helm deployments |
