const MAX_PROMPT_LENGTH = 2000;

/**
 * Skill Executor – L2 + L3
 *
 * L2: applies the skill instruction template to the prompt.
 * L3: executes the assembled instruction (simulated; replace with LLM call).
 *
 * @param {object} skill  – skill definition from the registry
 * @param {string} prompt – sanitised user prompt
 * @returns {Promise<string>} execution result
 */
export async function executeSkill(skill, prompt) {
  // Token guard (L2)
  if (prompt.length > MAX_PROMPT_LENGTH) {
    throw new Error(`Token limit exceeded (max ${MAX_PROMPT_LENGTH} characters)`);
  }

  // L2 – assemble instruction
  const instruction = `Execute skill [${skill.skill_id} v${skill.version}] – intent: "${skill.intent}" – region: ${skill.region_code}\nPrompt: ${prompt}`;

  // L3 – simulated execution (replace with real LLM / tool call in production)
  const result = await simulateExecution(instruction, skill);

  return result;
}

/**
 * Simulates L3 execution.
 * In production, replace this with an actual LLM API call or tool invocation.
 */
async function simulateExecution(instruction, skill) {
  return `[LEAPXO Skill Engine – ${skill.skill_id}]\n${instruction}`;
}
