/**
 * Prompt Firewall – LLM Guard (simulated)
 *
 * Blocks prompts that contain known jailbreak / injection patterns.
 * In production this should be replaced with a real LLM-based moderation
 * endpoint (e.g. OpenAI Moderation API, Perspective API, or a dedicated
 * on-prem guard model).
 *
 * @param {string} prompt
 * @returns {Promise<boolean>} true if prompt is safe, false if blocked
 */

const BLOCKED_PATTERNS = [
  "ignore previous",
  "ignore all previous",
  "bypass",
  "jailbreak",
  "disregard instructions",
  "forget your instructions",
  "act as if",
  "you are now",
  "prompt injection"
];

export async function firewall(prompt) {
  const lower = prompt.toLowerCase();
  return !BLOCKED_PATTERNS.some((pattern) => lower.includes(pattern));
}
