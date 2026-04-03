import express from "express";
import cors from "cors";
import { orchestrate } from "./orchestrator.js";
import { skillSchema } from "./skills/schema.js";

const app = express();
const PORT = process.env.PORT || 4000;

// Restrict CORS to explicitly listed origins (comma-separated env var).
// In development, omit CORS_ALLOWED_ORIGINS to allow all origins.
const allowedOrigins = (process.env.CORS_ALLOWED_ORIGINS || "")
  .split(",")
  .map((o) => o.trim())
  .filter(Boolean);

const corsOptions = {
  origin(origin, callback) {
    // Allow server-to-server requests (no Origin header) unconditionally.
    if (!origin) return callback(null, true);
    // If no allowlist configured, allow everything (dev mode).
    if (allowedOrigins.length === 0) return callback(null, true);
    if (allowedOrigins.includes(origin)) return callback(null, true);
    return callback(new Error("Not allowed by CORS"));
  }
};

app.use(cors(corsOptions));
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
    const msg = err.message || "Internal server error";
    if (msg === "Blocked by firewall") return res.status(403).json({ error: msg });
    if (msg.startsWith("Token limit exceeded")) return res.status(413).json({ error: msg });
    if (msg === "No skills registered in the registry") return res.status(503).json({ error: msg });
    console.error("[/execute] Unexpected error:", err);
    res.status(500).json({ error: "Internal server error" });
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

  if (skill === null || typeof skill !== "object" || Array.isArray(skill)) {
    return res.status(400).json({ error: "Request body must be a JSON object" });
  }

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
