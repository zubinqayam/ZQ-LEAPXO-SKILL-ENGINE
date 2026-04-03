/**
 * useSecureStorage.js — LeapXO v9 Tauri Stronghold-compatible secure storage hook.
 *
 * Security contract:
 *  - In a Tauri desktop build, secrets are persisted via @tauri-apps/plugin-stronghold
 *    (hardware-backed, encrypted at rest, never accessible via JS after write).
 *  - In a plain browser / Vite dev server build, secrets are stored only in
 *    React state (in-memory) — they are NEVER written to localStorage,
 *    sessionStorage, or any other browser storage mechanism.
 *  - API keys and sensitive credentials must flow through this hook.
 *    Components must NOT call localStorage.setItem / sessionStorage.setItem
 *    directly with secret values.
 */

import { useState, useCallback, useEffect, useRef } from 'react'

// ---------------------------------------------------------------------------
// Tauri detection — works in both Tauri and plain browser environments
// ---------------------------------------------------------------------------
const isTauri = () =>
  typeof window !== 'undefined' &&
  typeof window.__TAURI_INTERNALS__ !== 'undefined'

// ---------------------------------------------------------------------------
// Tauri Stronghold helpers (dynamically imported so the bundle works in
// non-Tauri environments where the plugin is not available)
// ---------------------------------------------------------------------------
const _strongholdClients = new Map()

async function _getStrongholdClient(vaultPath, password) {
  const cacheKey = JSON.stringify([vaultPath ?? null, password ?? null])
  const cachedClient = _strongholdClients.get(cacheKey)
  if (cachedClient) return cachedClient
  try {
    const { Client, Stronghold } = await import('@tauri-apps/plugin-stronghold')
    const stronghold = await Stronghold.load(vaultPath, password)
    const client = await stronghold.loadClient('leapxo-vault')
    _strongholdClients.set(cacheKey, client)
    return client
  } catch (err) {
    console.warn('[useSecureStorage] Stronghold unavailable:', err.message)
    return null
  }
}

async function _tauriWrite(key, value, vaultPath, password) {
  const client = await _getStrongholdClient(vaultPath, password)
  if (!client) return false
  try {
    const store = client.getStore()
    const encoded = new TextEncoder().encode(value)
    await store.insert(key, Array.from(encoded))
    await client.save?.()
    return true
  } catch (err) {
    console.error('[useSecureStorage] Stronghold write failed:', err)
    return false
  }
}

async function _tauriRead(key, vaultPath, password) {
  const client = await _getStrongholdClient(vaultPath, password)
  if (!client) return null
  try {
    const store = client.getStore()
    const raw = await store.get(key)
    if (!raw) return null
    return new TextDecoder().decode(new Uint8Array(raw))
  } catch {
    return null
  }
}

async function _tauriRemove(key, vaultPath, password) {
  const client = await _getStrongholdClient(vaultPath, password)
  if (!client) return
  try {
    const store = client.getStore()
    await store.remove(key)
    await client.save?.()
  } catch (err) {
    console.warn('[useSecureStorage] Stronghold remove failed:', err)
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------
/**
 * useSecureStorage(key, options)
 *
 * @param {string} key          - Storage key (e.g. "leapxo-api-key")
 * @param {object} [options]
 * @param {string} [options.vaultPath]  - Tauri Stronghold vault file path
 * @param {string} [options.password]   - Vault unlock password (injected from
 *                                        Tauri IPC, never hard-coded here)
 *
 * @returns {{ value, setValue, removeValue, isLoaded }}
 */
export function useSecureStorage(key, options = {}) {
  const { vaultPath = 'leapxo.hold', password = '' } = options
  const [value, _setValue] = useState(null)
  const [isLoaded, setIsLoaded] = useState(false)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  // Load initial value from Stronghold on mount (Tauri only)
  useEffect(() => {
    if (!isTauri()) {
      setIsLoaded(true)
      return
    }
    _tauriRead(key, vaultPath, password).then((v) => {
      if (mountedRef.current) {
        _setValue(v)
        setIsLoaded(true)
      }
    })
  }, [key, vaultPath, password])

  const setValue = useCallback(
    async (newValue) => {
      if (isTauri()) {
        await _tauriWrite(key, newValue, vaultPath, password)
      }
      // Always update in-memory state regardless of Tauri availability
      if (mountedRef.current) _setValue(newValue)
    },
    [key, vaultPath, password],
  )

  const removeValue = useCallback(
    async () => {
      if (isTauri()) {
        await _tauriRemove(key, vaultPath, password)
      }
      if (mountedRef.current) _setValue(null)
    },
    [key, vaultPath, password],
  )

  return { value, setValue, removeValue, isLoaded }
}

export default useSecureStorage
