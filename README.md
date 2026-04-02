# ZQ-LEAPXO-SKILL-ENGINE

**LEAPXO Skill Engine v2.1** – a production-structured, full-stack AI orchestration platform built with React, Node.js/Express, and a modular Skill execution pipeline.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend (React)                    │
│              Vite · Port 5173 (dev proxy → 4000)        │
└──────────────────────────┬──────────────────────────────┘
                           │ POST /execute
┌──────────────────────────▼──────────────────────────────┐
│                Backend API (Node/Express)                │
│                        Port 4000                        │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│               Orchestrator Engine                       │
│  Firewall → Skill Selector (L1) → Skill Executor (L2+3) │
└──────────────────────────┬──────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
      Security          Skills           IPC/State
     Firewall          Registry          Redis Mock
```

---

## Repository Structure

```
├── frontend/                  # React + Vite frontend
│   ├── src/
│   │   ├── App.jsx            # Main application component
│   │   ├── main.jsx           # React entry point
│   │   └── index.css          # Global styles
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
│
├── backend/                   # Node.js/Express API server
│   ├── src/
│   │   ├── server.js          # Express app + route handlers
│   │   ├── orchestrator.js    # Core orchestration pipeline
│   │   ├── security/
│   │   │   └── firewall.js    # Prompt firewall (LLM guard)
│   │   ├── skills/
│   │   │   ├── selector.js    # L1 skill selection
│   │   │   ├── executor.js    # L2+L3 skill execution
│   │   │   └── schema.js      # JSON Schema for skill payloads
│   │   └── ipc/
│   │       └── redis.js       # TTL-aware in-memory state store
│   ├── .env.example
│   └── package.json
│
├── database/
│   ├── schema.sql             # PostgreSQL production schema
│   └── seed.sql               # Initial skill registry data
│
└── helm/                      # Kubernetes Helm charts
    ├── Chart.yaml
    ├── values.yaml
    └── charts/
        ├── orchestrator/
        └── frontend/
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/execute` | Run a prompt through the skill pipeline |
| `GET` | `/skills/graph` | Return the skill dependency graph |
| `POST` | `/skills` | Register a new skill |
| `POST` | `/skills/:id/approve` | Approve a registered skill |

### POST /execute

**Request**
```json
{ "prompt": "Help me triage a medical emergency" }
```

**Response**
```json
{ "result": "[LEAPXO Skill Engine – triage-basic]\nExecute skill..." }
```

---

## Orchestration Pipeline

```
User Prompt
    │
    ▼
┌─────────────┐
│  Firewall   │ – blocks jailbreak / injection patterns
└──────┬──────┘
       │ safe
       ▼
┌─────────────┐
│  Selector   │ – L1: keyword→vector match → best skill
└──────┬──────┘
       │ skill
       ▼
┌─────────────┐
│  Executor   │ – L2: instruction assembly
│             │ – L3: simulated/real LLM execution
└──────┬──────┘
       │ result
       ▼
  Redis IPC  → Response
```

---

## Getting Started

### Prerequisites

- Node.js ≥ 18
- npm ≥ 9

### 1. Backend

```bash
cd backend
cp .env.example .env
npm install
npm run dev
# → API running on http://localhost:4000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
# → UI running on http://localhost:5173
```

### 3. Database (PostgreSQL)

```bash
psql -U postgres -d leapxo -f database/schema.sql
psql -U postgres -d leapxo -f database/seed.sql
```

### 4. Kubernetes (Helm)

```bash
helm install leapxo ./helm -f helm/values.yaml
```

---

## Security Design

| Layer | Mechanism |
|-------|-----------|
| Prompt Firewall | Pattern-based blocking; replace with LLM moderation API |
| Skill Signatures | ECDSA signing at registration; verified at load time |
| Immutable Audit Log | PostgreSQL trigger prevents UPDATE/DELETE on `audit_logs` |
| Network Policy | Kubernetes NetworkPolicy isolates service-to-service traffic |

---

## Future Extensions

- [ ] ECDSA signature verification module
- [ ] Vector DB integration (HNSW / pgvector)
- [ ] Semantic cache (Redis + prompt hash)
- [ ] Shadow execution engine (A/B skill comparison)
- [ ] Skill graph debugger UI
- [ ] ALGA test automation CI/CD pipeline
- [ ] Real LLM backend integration (OpenAI / local model)
