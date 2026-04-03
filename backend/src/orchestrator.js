import { firewall } from "./security/firewall.js";
import { selectSkill } from "./skills/selector.js";
import { executeSkill } from "./skills/executor.js";
import { setState } from "./ipc/redis.js";

/**
 * Orchestrates a prompt through the full skill pipeline:
 *   1. Prompt Firewall   – blocks unsafe inputs
 *   2. Skill Selection   – L1: choose the best skill
 *   3. Skill Execution   – L2+L3: run the skill and return results
 *
 * @param {string} prompt
 * @returns {Promise<string>} result
 */
export async function orchestrate(prompt) {
  // Step 1 – Prompt Firewall
  const safe = await firewall(prompt);
  if (!safe) throw new Error("Blocked by firewall");

  // Step 2 – Skill Selection (L1)
  const skill = await selectSkill(prompt);

  // Step 3 – Skill Execution (L2 + L3)
  const result = await executeSkill(skill, prompt);

  // Persist result to IPC state store
  setState(`result:${Date.now()}`, { skill: skill.skill_id, result });

  return result;
}
