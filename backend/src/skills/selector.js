/**
 * Skill Registry
 *
 * In production this list would be loaded from PostgreSQL / a vector DB.
 * Each skill is matched against the incoming prompt at L1 selection.
 */

const skills = [
  {
    id: "triage-basic",
    skill_id: "triage-basic",
    version: "1.0.0",
    intent: "medical triage",
    output_format: "text",
    region_code: "OM",
    security_level: "high"
  },
  {
    id: "dev-assist",
    skill_id: "dev-assist",
    version: "1.0.0",
    intent: "software development assistance",
    output_format: "text",
    region_code: "GLOBAL",
    security_level: "standard"
  },
  {
    id: "enterprise-query",
    skill_id: "enterprise-query",
    version: "1.0.0",
    intent: "enterprise data query",
    output_format: "json",
    region_code: "GLOBAL",
    security_level: "high"
  }
];

/**
 * Skill Selector – L1
 *
 * Matches the prompt to the most relevant registered skill.
 * Currently uses simple keyword matching; replace with vector-similarity
 * search (HNSW) for production.
 *
 * @param {string} prompt
 * @returns {Promise<object>} matched skill
 */
export async function selectSkill(prompt) {
  const lower = prompt.toLowerCase();

  for (const skill of skills) {
    const keywords = skill.intent.split(" ");
    if (keywords.some((kw) => lower.includes(kw))) {
      return skill;
    }
  }

  // Default fallback skill
  if (skills.length === 0) {
    throw new Error("No skills registered in the registry");
  }
  return skills[0];
}

/**
 * Returns the full skill registry as a graph structure.
 * @returns {{ nodes: object[], edges: object[] }}
 */
export function getSkillGraph() {
  return {
    nodes: skills.map((s) => ({ id: s.skill_id, intent: s.intent, region: s.region_code })),
    edges: [] // dependency edges; populated once skill_dependencies table is wired
  };
}
