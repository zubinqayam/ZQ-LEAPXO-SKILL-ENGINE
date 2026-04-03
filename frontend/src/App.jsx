import { useState, useEffect, useCallback } from 'react'
import { useSecureStorage } from './hooks/useSecureStorage'

const API = ''  // proxied via vite dev server
const VERSION = '9.0.0'

/* ─── tiny fetch helpers ─── */
async function apiFetch(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? res.statusText)
  }
  return res.json()
}

/* ─── colour helpers ─── */
function trustColour(score) {
  if (score >= 0.7) return '#22c55e'
  if (score >= 0.4) return '#f59e0b'
  return '#ef4444'
}

/* ─── sub-components ─── */
function Badge({ value }) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 12,
        fontSize: 12,
        background: trustColour(value),
        color: '#fff',
        fontWeight: 700,
      }}
    >
      {(value * 100).toFixed(1)}%
    </span>
  )
}

function Card({ title, children }) {
  return (
    <section style={styles.card}>
      <h3 style={styles.cardTitle}>{title}</h3>
      {children}
    </section>
  )
}

function Notice({ msg, type }) {
  if (!msg) return null
  const bg = type === 'error' ? '#fef2f2' : '#f0fdf4'
  const border = type === 'error' ? '#fca5a5' : '#86efac'
  const color = type === 'error' ? '#991b1b' : '#166534'
  return (
    <p style={{ background: bg, border: `1px solid ${border}`, color, borderRadius: 6, padding: '8px 12px', margin: '8px 0', fontSize: 13 }}>
      {msg}
    </p>
  )
}

/* ─── main app ─── */
export default function App() {
  const [agents, setAgents] = useState([])
  const [archived, setArchived] = useState([])
  const [status, setStatus] = useState(null)
  const [results, setResults] = useState([])
  const [notice, setNotice] = useState({ msg: '', type: '' })
  const [vaultStatus, setVaultStatus] = useState(null)

  /* register form */
  const [label, setLabel] = useState('')
  const [initTrust, setInitTrust] = useState(1.0)

  /* schedule form */
  const [selHash, setSelHash] = useState('')
  const [prompt, setPrompt] = useState('')
  const [priority, setPriority] = useState(3)

  /* Secure storage for any client-side config — no localStorage */
  const { value: savedLabel, setValue: saveLabel } = useSecureStorage('leapxo-last-label')

  const notify = (msg, type = 'info') => setNotice({ msg, type })

  const refresh = useCallback(async () => {
    try {
      const [ag, ar, st, vs] = await Promise.all([
        apiFetch('/agents'),
        apiFetch('/agents/archived'),
        apiFetch('/status'),
        apiFetch('/vault/status'),
      ])
      setAgents(ag.agents)
      setArchived(ar.archived)
      setStatus(st)
      setVaultStatus(vs)
      if (ag.agents.length && !selHash) setSelHash(ag.agents[0].model_hash)
    } catch (e) {
      notify(e.message, 'error')
    }
  }, [selHash])

  useEffect(() => { refresh() }, [])   // intentional: run once on mount  // eslint-disable-line react-hooks/exhaustive-deps

  async function handleRegister(e) {
    e.preventDefault()
    try {
      const data = await apiFetch('/agents/register', {
        method: 'POST',
        body: JSON.stringify({ label, initial_trust: Number(initTrust) }),
      })
      notify(`Registered: ${data.model_hash.slice(0, 16)}…`, 'success')
      await saveLabel(label)
      setLabel('')
      refresh()
    } catch (err) {
      notify(err.message, 'error')
    }
  }

  async function handleSchedule(e) {
    e.preventDefault()
    try {
      const data = await apiFetch('/tasks/schedule', {
        method: 'POST',
        body: JSON.stringify({ model_hash: selHash, prompt, priority: Number(priority) }),
      })
      notify(`Task queued — queue length: ${data.queue_length}`, 'success')
      setPrompt('')
      refresh()
    } catch (err) {
      notify(err.message, 'error')
    }
  }

  async function handleRun() {
    try {
      const data = await apiFetch('/tasks/run', { method: 'POST' })
      setResults(data.results ?? [])
      notify(`Run complete — ${data.results.length} result(s). Tokens remaining: ${data.token_budget_remaining}`, 'success')
      refresh()
    } catch (err) {
      notify(err.message, 'error')
    }
  }

  async function handleOverride(hash, allow) {
    try {
      await apiFetch('/agents/override', {
        method: 'POST',
        body: JSON.stringify({ model_hash: hash, allow }),
      })
      notify(`Override set: ${allow ? 'ALLOW' : 'BLOCK'}`, 'success')
      refresh()
    } catch (err) {
      notify(err.message, 'error')
    }
  }

  return (
    <div style={styles.root}>
      {/* ── Header ── */}
      <header style={styles.header}>
        <div style={styles.logoArea}>
          <span style={styles.keyhole}>⬡</span>
          <div>
            <h1 style={styles.title}>LeapXO Skill Engine</h1>
            <p style={styles.subtitle}>Keyhole UI — v{VERSION} Adaptive Cognitive Market</p>
          </div>
        </div>
        {status && (
          <div style={styles.statusBadges}>
            <Pill label="Token Budget" value={status.token_budget} />
            <Pill label="Queue" value={status.queue_length} />
            <Pill label="Active Agents" value={status.active_agents} />
            <Pill label="Archived" value={status.archived_agents} />
            {vaultStatus && (
              <Pill
                label="Vault"
                value={vaultStatus.api_key_set ? '🔒 Secured' : '⚠ Unset'}
              />
            )}
          </div>
        )}
      </header>

      <Notice msg={notice.msg} type={notice.type} />

      <div style={styles.grid}>
        {/* ── Register ── */}
        <Card title="Register Agent">
          <form onSubmit={handleRegister} style={styles.form}>
            <label style={styles.label}>Agent Label</label>
            <input
              style={styles.input}
              value={label}
              onChange={e => setLabel(e.target.value)}
              placeholder="e.g. my-skill-agent"
              required
            />
            <label style={styles.label}>Initial Trust (0–1)</label>
            <input
              style={styles.input}
              type="number"
              min="0"
              max="1"
              step="0.05"
              value={initTrust}
              onChange={e => setInitTrust(e.target.value)}
            />
            <button style={styles.btn} type="submit">Register</button>
          </form>
        </Card>

        {/* ── Schedule ── */}
        <Card title="Schedule Task">
          <form onSubmit={handleSchedule} style={styles.form}>
            <label style={styles.label}>Agent</label>
            <select
              style={styles.input}
              value={selHash}
              onChange={e => setSelHash(e.target.value)}
              required
            >
              {agents.map(a => (
                <option key={a.model_hash} value={a.model_hash}>
                  {a.model_hash.slice(0, 16)}… (trust {(a.trust_score * 100).toFixed(0)}%)
                </option>
              ))}
            </select>
            <label style={styles.label}>Prompt</label>
            <textarea
              style={{ ...styles.input, height: 72, resize: 'vertical' }}
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              placeholder="Enter skill prompt…"
              required
            />
            <label style={styles.label}>Priority (1 = highest)</label>
            <input
              style={styles.input}
              type="number"
              min="1"
              max="10"
              value={priority}
              onChange={e => setPriority(e.target.value)}
            />
            <button style={styles.btn} type="submit">Schedule</button>
          </form>
        </Card>

        {/* ── Run Queue ── */}
        <Card title="Execute Queue">
          <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 12 }}>
            Run all queued tasks through the orchestrator. Low-trust agents ({'<'}20%) are auto-archived after each run.
          </p>
          <button style={{ ...styles.btn, background: '#7c3aed' }} onClick={handleRun}>
            ▶ Run Queue
          </button>
          {results.length > 0 && (
            <div style={{ marginTop: 16 }}>
              {results.map((r, i) => (
                <div key={i} style={styles.resultRow}>
                  <span style={styles.hashChip}>{r.model_hash.slice(0, 14)}…</span>
                  <span style={styles.resultText}>{r.result}</span>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* ── Active Agents ── */}
        <Card title="Active Agents">
          {agents.length === 0 ? (
            <p style={{ fontSize: 13, color: '#9ca3af' }}>No active agents. Register one above.</p>
          ) : (
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Hash</th>
                  <th style={styles.th}>Trust</th>
                  <th style={styles.th}>Text</th>
                  <th style={styles.th}>Code</th>
                  <th style={styles.th}>Image</th>
                  <th style={styles.th}>Override</th>
                </tr>
              </thead>
              <tbody>
                {agents.map(a => (
                  <tr key={a.model_hash}>
                    <td style={styles.td}>{a.model_hash.slice(0, 10)}…</td>
                    <td style={styles.td}><Badge value={a.trust_score} /></td>
                    <td style={styles.td}>{(a.multi_modal_perf.text * 100).toFixed(0)}%</td>
                    <td style={styles.td}>{(a.multi_modal_perf.code * 100).toFixed(0)}%</td>
                    <td style={styles.td}>{(a.multi_modal_perf.image * 100).toFixed(0)}%</td>
                    <td style={styles.td}>
                      <button
                        style={{ ...styles.smallBtn, background: '#16a34a' }}
                        onClick={() => handleOverride(a.model_hash, true)}
                        title="Allow"
                      >✓</button>
                      <button
                        style={{ ...styles.smallBtn, background: '#dc2626', marginLeft: 4 }}
                        onClick={() => handleOverride(a.model_hash, false)}
                        title="Block"
                      >✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <button style={{ ...styles.btn, marginTop: 12, background: '#64748b' }} onClick={refresh}>
            ↻ Refresh
          </button>
        </Card>

        {/* ── Archived Agents ── */}
        {archived.length > 0 && (
          <Card title={`Archived Agents (${archived.length})`}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Hash</th>
                  <th style={styles.th}>Final Trust</th>
                </tr>
              </thead>
              <tbody>
                {archived.map(a => (
                  <tr key={a.model_hash}>
                    <td style={styles.td}>{a.model_hash.slice(0, 16)}…</td>
                    <td style={styles.td}><Badge value={a.trust_score} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </div>
  )
}

function Pill({ label, value }) {
  return (
    <div style={styles.pill}>
      <span style={{ fontSize: 11, color: '#94a3b8' }}>{label}</span>
      <span style={{ fontSize: 18, fontWeight: 700, color: '#e2e8f0' }}>{value}</span>
    </div>
  )
}

/* ─── styles ─── */
const styles = {
  root: {
    minHeight: '100vh',
    background: '#0f172a',
    color: '#e2e8f0',
    fontFamily: "'Inter', system-ui, sans-serif",
    padding: '0 0 40px',
  },
  header: {
    background: 'linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%)',
    borderBottom: '1px solid #1e293b',
    padding: '20px 32px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: 16,
  },
  logoArea: { display: 'flex', alignItems: 'center', gap: 16 },
  keyhole: { fontSize: 40, color: '#818cf8' },
  title: { margin: 0, fontSize: 22, fontWeight: 800, color: '#c7d2fe' },
  subtitle: { margin: 0, fontSize: 12, color: '#64748b' },
  statusBadges: { display: 'flex', gap: 16, flexWrap: 'wrap' },
  pill: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 8,
    padding: '6px 14px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    minWidth: 80,
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
    gap: 20,
    padding: '24px 32px',
  },
  card: {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 12,
    padding: 20,
  },
  cardTitle: {
    margin: '0 0 16px',
    fontSize: 15,
    fontWeight: 700,
    color: '#a5b4fc',
    borderBottom: '1px solid #334155',
    paddingBottom: 10,
  },
  form: { display: 'flex', flexDirection: 'column', gap: 8 },
  label: { fontSize: 12, color: '#94a3b8', marginBottom: 2 },
  input: {
    background: '#0f172a',
    border: '1px solid #334155',
    borderRadius: 6,
    color: '#e2e8f0',
    padding: '8px 10px',
    fontSize: 13,
    outline: 'none',
    width: '100%',
    boxSizing: 'border-box',
  },
  btn: {
    background: '#4f46e5',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    padding: '9px 18px',
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: 13,
    alignSelf: 'flex-start',
  },
  smallBtn: {
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    padding: '3px 8px',
    cursor: 'pointer',
    fontSize: 12,
  },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 12 },
  th: {
    textAlign: 'left',
    padding: '6px 8px',
    color: '#64748b',
    borderBottom: '1px solid #334155',
    fontWeight: 600,
    whiteSpace: 'nowrap',
  },
  td: {
    padding: '7px 8px',
    borderBottom: '1px solid #1e293b',
    color: '#cbd5e1',
    whiteSpace: 'nowrap',
  },
  resultRow: {
    display: 'flex',
    gap: 8,
    alignItems: 'flex-start',
    marginBottom: 8,
    background: '#0f172a',
    borderRadius: 6,
    padding: '8px 10px',
  },
  hashChip: {
    background: '#312e81',
    color: '#a5b4fc',
    borderRadius: 4,
    padding: '2px 6px',
    fontSize: 11,
    fontFamily: 'monospace',
    whiteSpace: 'nowrap',
  },
  resultText: { fontSize: 12, color: '#94a3b8', wordBreak: 'break-word' },
}
