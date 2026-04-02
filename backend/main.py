import asyncio
import hashlib
from collections import deque
import heapq
import random
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# -----------------------------
# Configuration constants
# -----------------------------
MIN_TRUST_THRESHOLD = 0.2
MAX_TOKEN_ALLOCATION_FACTOR = 0.2
ADVERSARIAL_SIMULATION_RATE = 0.1
ADVERSARIAL_FAILURE_RATE = 0.3
ADAPTIVE_THRESHOLD_FACTOR = 0.05
FAILURE_WINDOW_SIZE = 50
TRUST_DECAY_FACTOR = 0.9

# -----------------------------
# Embedding & Semantic Similarity
# -----------------------------
def embed_text(text: str) -> set:
    return set(text.lower().split())

def semantic_similarity(prompt: str, output: str) -> float:
    prompt_tokens = embed_text(prompt)
    output_tokens = embed_text(output)
    return len(prompt_tokens & output_tokens) / max(1, len(prompt_tokens))

# -----------------------------
# Multi-Modal Skill DNA
# -----------------------------
class SkillDNA:
    def __init__(self, model_weights: bytes, initial_trust: float = 1.0):
        self.model_hash = hashlib.sha256(model_weights).hexdigest()
        self.trust_score = initial_trust
        self.history = deque(maxlen=100)
        self._lock = asyncio.Lock()
        self.context_memory: Dict[str, Any] = {}
        self.multi_modal_perf: Dict[str, List[float]] = {"text": [], "code": [], "image": []}
        self.human_override: Optional[bool] = None

    async def update_trust(self, delta: float):
        async with self._lock:
            scaled_delta = delta * TRUST_DECAY_FACTOR
            self.trust_score = max(0.0, min(1.0, self.trust_score + scaled_delta))
            self.history.append(self.trust_score)

    async def store_context(self, key: str, value: Any):
        async with self._lock:
            self.context_memory[key] = value

    async def retrieve_context(self, key: str):
        async with self._lock:
            return self.context_memory.get(key)

    async def record_modal_perf(self, modal_type: str, score: float):
        async with self._lock:
            if modal_type in self.multi_modal_perf:
                self.multi_modal_perf[modal_type].append(score)
                recent = self.multi_modal_perf[modal_type][-10:]
                recent_avg = sum(recent) / max(1, len(recent))
                await self.update_trust(recent_avg - 0.5)

    async def set_human_override(self, allow: bool):
        async with self._lock:
            self.human_override = allow

# -----------------------------
# DNA Registry with Auto-Archiving
# -----------------------------
class DNARegistry:
    def __init__(self):
        self._registry: Dict[str, SkillDNA] = {}
        self._archived: Dict[str, SkillDNA] = {}
        self._lock = asyncio.Lock()

    async def register_dna(self, dna: SkillDNA) -> SkillDNA:
        async with self._lock:
            if dna.model_hash not in self._registry:
                self._registry[dna.model_hash] = dna
            return self._registry[dna.model_hash]

    async def best_fit_agent(self) -> Optional[SkillDNA]:
        async with self._lock:
            valid_agents = [d for d in self._registry.values() if d.trust_score >= MIN_TRUST_THRESHOLD]
            if not valid_agents:
                return None
            return max(valid_agents, key=lambda d: d.trust_score)

    async def prune_low_trust(self):
        async with self._lock:
            to_archive = [k for k, d in self._registry.items() if d.trust_score < MIN_TRUST_THRESHOLD]
            for k in to_archive:
                self._archived[k] = self._registry.pop(k)

    def list_agents(self) -> List[Dict[str, Any]]:
        return [
            {
                "model_hash": k,
                "trust_score": d.trust_score,
                "human_override": d.human_override,
                "multi_modal_perf": {
                    m: (sum(v[-10:]) / max(1, len(v[-10:]))) if v else 0.0
                    for m, v in d.multi_modal_perf.items()
                },
            }
            for k, d in self._registry.items()
        ]

    def list_archived(self) -> List[Dict[str, Any]]:
        return [
            {"model_hash": k, "trust_score": d.trust_score}
            for k, d in self._archived.items()
        ]

# -----------------------------
# Meta Agent with Adversarial Simulation
# -----------------------------
class MetaAgent:
    def __init__(self, max_recursion: int = 3):
        self.max_recursion = max_recursion
        self.recursion_heatmap: List[int] = []
        self.validation_history: deque = deque(maxlen=500)

    async def semantic_validation(self, prompt: str, output: str) -> bool:
        similarity = semantic_similarity(prompt, output)
        return similarity > 0.5

    async def review(
        self,
        agent_output: Any,
        prompt: str,
        depth: int = 0,
        adversarial: bool = False,
    ) -> bool:
        self.recursion_heatmap.append(depth)
        if depth >= self.max_recursion:
            return False

        try:
            if not isinstance(agent_output, str) or len(agent_output) == 0:
                return False
            valid = await self.semantic_validation(prompt, agent_output)

            if adversarial:
                valid = valid and (random.random() > ADVERSARIAL_FAILURE_RATE)

            recent_failures = sum(1 for v in self.validation_history if not v)
            threshold_adjustment = ADAPTIVE_THRESHOLD_FACTOR * min(1, recent_failures / FAILURE_WINDOW_SIZE)
            valid = valid and (random.random() > threshold_adjustment)
            self.validation_history.append(valid)
            return valid
        except Exception:
            return False

# -----------------------------
# Orchestrator with Dynamic Priority & Human Override
# -----------------------------
class Orchestrator:
    def __init__(self):
        self.registry = DNARegistry()
        self.meta_agent = MetaAgent()
        self.token_budget = 4096
        self.task_queue: list = []
        self.agent_market: Dict[str, int] = {}

    async def schedule_agent(self, dna: SkillDNA, prompt: str, priority: int):
        heapq.heappush(self.task_queue, (priority, random.random(), dna, prompt))

    async def run_queue(self) -> List[Dict[str, str]]:
        results = []
        while self.task_queue and self.token_budget > 0:
            _, _, dna, prompt = heapq.heappop(self.task_queue)
            if dna.trust_score < MIN_TRUST_THRESHOLD:
                continue

            if dna.human_override is False:
                results.append({"model_hash": dna.model_hash, "result": "Blocked by Human Override"})
                continue

            bid = int(self.token_budget * min(MAX_TOKEN_ALLOCATION_FACTOR, dna.trust_score))
            self.agent_market[dna.model_hash] = bid
            if bid > self.token_budget:
                continue

            adversarial = random.random() < ADVERSARIAL_SIMULATION_RATE
            result = await self.execute_agent(dna, prompt, bid, adversarial)
            results.append({"model_hash": dna.model_hash, "result": result})

        await self.registry.prune_low_trust()
        return results

    async def execute_agent(
        self, dna: SkillDNA, prompt: str, token_allocation: int, adversarial: bool
    ) -> str:
        try:
            await asyncio.sleep(0.01)
            context_snapshot = dict(dna.context_memory)
            output = f"v3.6 output: {prompt} | context keys: {list(context_snapshot.keys())}"

            valid = await self.meta_agent.review(output, prompt, adversarial=adversarial)
            if not valid:
                self.token_budget += token_allocation // 2
                await dna.update_trust(-0.1)
                return "Meta-Review Failed"

            for modal in ["text", "code", "image"]:
                score = random.random()
                await dna.record_modal_perf(modal, score)

            await dna.update_trust(0.05)
            self.token_budget -= token_allocation
            return output
        except Exception:
            await dna.update_trust(-0.2)
            return "Execution Error"

# -----------------------------
# Singleton orchestrator state
# -----------------------------
orchestrator = Orchestrator()

# -----------------------------
# FastAPI app
# -----------------------------
app = FastAPI(title="LeapXO Skill Engine", version="3.6.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Request / Response models ----------

class RegisterAgentRequest(BaseModel):
    label: str
    initial_trust: float = 1.0

class ScheduleTaskRequest(BaseModel):
    model_hash: str
    prompt: str
    priority: int = 3

class HumanOverrideRequest(BaseModel):
    model_hash: str
    allow: bool

# ---------- Endpoints ----------

@app.get("/health")
def health():
    return {"status": "ok", "version": "3.6.0"}

@app.post("/agents/register")
async def register_agent(req: RegisterAgentRequest):
    """Register a new Skill DNA agent identified by a label string."""
    weights = req.label.encode()
    dna = SkillDNA(weights, initial_trust=req.initial_trust)
    await orchestrator.registry.register_dna(dna)
    return {"model_hash": dna.model_hash, "trust_score": dna.trust_score}

@app.get("/agents")
def list_agents():
    """List all active agents."""
    return {"agents": orchestrator.registry.list_agents()}

@app.get("/agents/archived")
def list_archived():
    """List archived (low-trust) agents."""
    return {"archived": orchestrator.registry.list_archived()}

@app.post("/agents/override")
async def set_override(req: HumanOverrideRequest):
    """Set human override for an agent."""
    dna = orchestrator.registry._registry.get(req.model_hash)
    if not dna:
        raise HTTPException(status_code=404, detail="Agent not found")
    await dna.set_human_override(req.allow)
    return {"model_hash": req.model_hash, "human_override": dna.human_override}

@app.post("/tasks/schedule")
async def schedule_task(req: ScheduleTaskRequest):
    """Schedule a prompt task for a registered agent."""
    dna = orchestrator.registry._registry.get(req.model_hash)
    if not dna:
        raise HTTPException(status_code=404, detail="Agent not found")
    await orchestrator.schedule_agent(dna, req.prompt, req.priority)
    return {"queued": True, "queue_length": len(orchestrator.task_queue)}

@app.post("/tasks/run")
async def run_tasks():
    """Execute all queued tasks and return results."""
    results = await orchestrator.run_queue()
    return {
        "results": results,
        "token_budget_remaining": orchestrator.token_budget,
        "agent_market": orchestrator.agent_market,
        "recursion_heatmap": orchestrator.meta_agent.recursion_heatmap,
    }

@app.get("/status")
def status():
    """Return orchestrator status snapshot."""
    return {
        "token_budget": orchestrator.token_budget,
        "queue_length": len(orchestrator.task_queue),
        "active_agents": len(orchestrator.registry._registry),
        "archived_agents": len(orchestrator.registry._archived),
        "agent_market": orchestrator.agent_market,
    }
