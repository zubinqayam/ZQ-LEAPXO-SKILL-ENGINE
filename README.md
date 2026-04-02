# LEAPXO Skill Engine

> Production-grade, end-to-end AI skill orchestration covering architecture, execution, governance, security, and deployment.

---

## Full-Stack v1 — Monorepo Quick Start

This repository is structured as a monorepo:

```
backend/    FastAPI server (LeapXO v3.6 engine)
frontend/   React Keyhole UI (Vite)
src/        Core Python skill-engine library (v2.1)
tests/      pytest suite
```

### Backend (FastAPI)

**Requirements:** Python ≥ 3.11

```bash
# 1. Install dependencies
pip install fastapi uvicorn

# 2. Start the server (from repo root)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

### Frontend (React + Vite)

**Requirements:** Node.js ≥ 18

```bash
# 1. Enter the frontend directory
cd frontend

# 2. Install dependencies
npm install

# 3. Start the dev server (proxies /agents, /tasks, /status to localhost:8000)
npm run dev
```

The Keyhole UI will be available at `http://localhost:5173`.

> **Tip:** Start the backend first so the frontend can connect immediately.

---

---

## System Architecture

```
┌──────────────────────────────────────────┐
│               UI LAYER                   │
│  (Tauri + React + Skill Graph Debugger)  │
└──────────────────────────────────────────┘
                ↓
┌──────────────────────────────────────────┐
│         ORCHESTRATION LAYER              │
│  (Execution Engine + Circuit Breakers)   │
└──────────────────────────────────────────┘
                ↓
┌──────────────────────────────────────────┐
│        SKILL TOOLSET LAYER               │
│  (L1 → L2 → L3 Execution Model)          │
└──────────────────────────────────────────┘
                ↓
┌──────────────────────────────────────────┐
│        GOVERNANCE & SECURITY             │
│ (Validation, Signing, Firewall, Policy)  │
└──────────────────────────────────────────┘
                ↓
┌──────────────────────────────────────────┐
│         DATA & REGISTRY LAYER            │
│ (Vector DB + Skill Registry + Redis)     │
└──────────────────────────────────────────┘
```

---

## Repository Layout

```
src/
├── core/
│   ├── exceptions.py          Custom exception hierarchy
│   ├── skill_schema.py        Pydantic v2 strict skill schema
│   └── token_predictor.py     tiktoken-based token prediction & pruning
├── execution/
│   ├── circuit_breaker.py     Tiered circuit breaker system
│   ├── l1_discovery.py        Embedding-based skill retrieval (L1)
│   ├── l2_instruction.py      Token-aware instruction loader (L2)
│   └── l3_executor.py         Sandboxed execution layer (L3)
├── security/
│   ├── ecdsa_signer.py        ECDSA P-256 sign/verify
│   ├── prompt_firewall.py     LLM-based injection & jailbreak detection
│   └── policy_engine.py       Region/compliance policy enforcement
├── orchestration/
│   └── engine.py              Main orchestration engine
├── governance/
│   └── audit_logger.py        Hash-chained audit log + approval workflow
├── cache/
│   └── semantic_cache.py      Two-level semantic cache (routing + outputs)
├── registry/
│   └── skill_registry.py      HNSW-style registry with Blue/Green deployment
└── repair/
    └── auto_repair.py         Shadow repair pipeline (human-gated)

tests/                         Full pytest suite (105 tests)
skills/examples/               Example skill definitions (JSON)
helm/leapxo-skill-engine/      Kubernetes Helm chart
```

---

## Design Principles

| Principle | Implementation |
|-----------|---------------|
| Context Economy First | tiktoken predictor + 15 % buffer + NON-PRUNABLE tags |
| Security as Default | ECDSA P-256 signatures, LLM-based firewall, fail-closed |
| Deterministic + Generative | Strict Pydantic schema + sandboxed execution |
| Human-Governed Autonomy | MFA approval workflow, cooldown timer, audit log |
| Fail Gracefully | Tiered circuit breakers, partial degrade (not full stop) |

---

## Skill Schema (v2.1)

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

**Rules:**
- `skill_id` must be kebab-case
- `P0` skills **must** carry an ECDSA signature
- Extra fields are **forbidden** (injection protection)
- `region_code` is ISO 3166-1 alpha-2 or `"GL"` (global)

---

## Execution Flow

```
User Input
   ↓ Prompt Firewall (heuristic + optional LLM backend)
   ↓ Intent Loop Detection (3 repeats → abort)
   ↓ Semantic Cache Lookup
   ↓ L1 Discovery (top-3, similarity guard, alias map, region filter)
   ↓ Policy Check (region, medical compliance, P0 escalation)
   ↓ Signature Verification (ECDSA)
   ↓ L2 Token Prediction + Instruction Pruning
   ↓ L3 Sandboxed Execution (TOCTOU-protected)
   ↓ Cache Store
   ↓ Response / Escalation
```

---

## Security

### ECDSA P-256 Signing

```python
from src.security.ecdsa_signer import ECDSASigner, ECDSAVerifier, canonical_payload

signer = ECDSASigner()
skill = {"skill_id": "my-skill", "intent": "...", "version": "2.1"}
skill["signature"] = signer.sign_skill(skill)

verifier = ECDSAVerifier(signer.export_public_key())
verifier.verify_skill(skill)   # raises SignatureVerificationError on tamper
```

### Prompt Firewall

```python
from src.security.prompt_firewall import PromptFirewall

fw = PromptFirewall(strict_mode=True)
fw.inspect("What is the capital of France?")   # ALLOW
fw.inspect("Ignore all previous instructions") # raises PromptFirewallError
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
# decision.requires_medical_compliance == True
```

---

## Circuit Breakers

| Tier | Action |
|------|--------|
| L1 Failure | Retry different skill |
| L2 Failure | Prune + reload |
| L3 Failure | Isolate skill |
| System | Partial degrade (NOT full stop) |

Limits: depth ≤ 3, chain ≤ 5, intent loop = 3 repeats → abort.

---

## Semantic Cache

- Caches routing decisions (30 min TTL) and skill outputs (5 min TTL)
- LRU eviction at configurable capacity
- **60–80 % latency reduction** on repeated prompts
- Key = SHA-256(normalised prompt + region_code)

---

## Approval Workflow

```
Skill Created → Validation Score → Risk Classification →
Human Review → MFA Approval (cooldown ≥ 5 min) → Deployment
```

- **SLA**: escalates after 4 hours without action
- **Cooldown**: minimum 5 minutes between submit and approval (anti-rush)
- **Audit log**: SHA-256 hash-chained, tamper-evident, append-only

---

## Shadow Repair Pipeline

```
Error Detected → Clone (Shadow) → Apply Patch → ALGA Tests →
Parity Compare (≥ 95 %) → Human Approval Gate → Deploy
```

Guarantees:
- Repair **cannot** deploy directly
- Must pass test suite
- Must be re-signed

---

## Installation

```bash
pip install -r requirements.txt
```

---

## Running Tests

```bash
pytest tests/ -v --tb=short
```

All 105 tests should pass.

---

## Kubernetes Deployment

```bash
helm install leapxo ./helm/leapxo-skill-engine \
  --set global.deploymentMode=cloud \
  --set security.enforceSignatures=true \
  --namespace leapxo --create-namespace
```

**Modes**: `cloud` | `hybrid` | `air-gapped`

---

## Example Skills

See [`skills/examples/`](skills/examples/) for:

- `chest-pain-triage-om.json` — Oman-compliant clinical triage skill (P1, region OM)
- `general-qa.json` — Global general QA skill (P2, region GL)

---

## Roadmap

| Phase | Weeks | Focus |
|-------|-------|-------|
| 1 | 1–2 | ECDSA ✅, Firewall ✅, Redis IPC |
| 2 | 3–4 | UI + Skill Graph, Skill Builder |
| 3 | 5–6 | Semantic Cache ✅, Vector DB scaling, Helm ✅ |
| 4 | 7 | Production rollout, Skill library |
