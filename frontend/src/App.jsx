import { useState } from "react";

export default function App() {
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const sendPrompt = async () => {
    if (!input.trim()) return;
    setLoading(true);
    setError("");
    setOutput("");

    try {
      const res = await fetch("/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: input })
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.error || "An error occurred");
      } else {
        setOutput(data.result);
      }
    } catch (err) {
      setError("Failed to connect to the skill engine.");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendPrompt();
    }
  };

  return (
    <div className="app-container">
      <header>
        <h1>LEAPXO Skill Engine</h1>
        <p className="subtitle">v2.1 – AI Orchestration Platform</p>
      </header>

      <main>
        <div className="input-group">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Enter your prompt here… (Enter to submit)"
            rows={4}
            disabled={loading}
          />
          <button onClick={sendPrompt} disabled={loading || !input.trim()}>
            {loading ? "Processing…" : "Execute Skill"}
          </button>
        </div>

        {error && <div className="result error">{error}</div>}
        {output && <div className="result success">{output}</div>}
      </main>
    </div>
  );
}
