/**
 * Redis IPC – In-memory mock
 *
 * Provides a TTL-aware key/value store that mirrors the Redis API surface.
 * Replace with a real Redis client (e.g. `ioredis`) in production:
 *
 *   import Redis from "ioredis";
 *   const client = new Redis(process.env.REDIS_URL);
 *   export const setState = (key, value, ttlMs = 5000) =>
 *     client.set(key, JSON.stringify(value), "PX", ttlMs);
 *   export const getState = async (key) => {
 *     const raw = await client.get(key);
 *     return raw ? JSON.parse(raw) : null;
 *   };
 */

const DEFAULT_TTL_MS = 5_000;
const memoryStore = new Map();

/**
 * Write a value with a TTL.
 * @param {string} key
 * @param {*} value
 * @param {number} [ttlMs]
 */
export function setState(key, value, ttlMs = DEFAULT_TTL_MS) {
  memoryStore.set(key, { value, expiresAt: Date.now() + ttlMs });
}

/**
 * Read a value; returns null if missing or expired.
 * @param {string} key
 * @returns {*|null}
 */
export function getState(key) {
  const entry = memoryStore.get(key);
  if (!entry) return null;
  if (Date.now() > entry.expiresAt) {
    memoryStore.delete(key);
    return null;
  }
  return entry.value;
}

/**
 * Delete a key explicitly.
 * @param {string} key
 */
export function deleteState(key) {
  memoryStore.delete(key);
}

/**
 * Flush all entries (useful in tests).
 */
export function flushAll() {
  memoryStore.clear();
}
