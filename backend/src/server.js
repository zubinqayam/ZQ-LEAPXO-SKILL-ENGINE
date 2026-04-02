import express from "express";
import cors from "cors";
import { orchestrate } from "./orchestrator.js";
import { skillSchema } from "./skills/schema.js";

const app = express();
const PORT = process.env.PORT || 4000;

app.use(cors());
app.use(express.json());

// POST /execute – run a skill against a prompt
app.post("/execute", async (req, res) => {
  const { prompt } = req.body;

  if (!prompt || typeof prompt !== "string") {
    return res.status(400).json({ error: "prompt is required and must be a string" });
  }

  try {
    const result = await orchestrate(prompt);
    res.json({ result });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// GET /skills/graph – return the current skill graph
app.get("/skills/graph", async (req, res) => {
  const { getSkillGraph } = await import("./skills/selector.js");
  res.json(getSkillGraph());
});

// POST /skills – register a new skill (stub; wire to DB in production)
app.post("/skills", async (req, res) => {
  const skill = req.body;
  const required = skillSchema.required;
  const missing = required.filter((k) => !skill[k]);

  if (missing.length) {
    return res.status(400).json({ error: `Missing required fields: ${missing.join(", ")}` });
  }

  res.status(201).json({ message: "Skill registered (stub)", skill });
});

// GET /health – liveness/readiness probe
app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

// POST /skills/:id/approve – approve a skill (stub)
app.post("/skills/:id/approve", async (req, res) => {
  const { id } = req.params;
  const { approver_id, risk_level } = req.body;

  if (!approver_id) {
    return res.status(400).json({ error: "approver_id is required" });
  }

  res.json({
    message: "Skill approved (stub)",
    skill_id: id,
    approver_id,
    risk_level: risk_level || "low",
    status: "approved"
  });
});

app.listen(PORT, () => console.log(`LEAPXO Skill Engine API running on port ${PORT}`))
  .on("error", (err) => {
    console.error(`Failed to start server on port ${PORT}:`, err.message);
    process.exit(1);
  });
