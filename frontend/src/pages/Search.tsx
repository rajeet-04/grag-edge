import { FormEvent, useState } from "react";
import { api } from "../api/client";
import type { SearchHit } from "../api/types";
import EvidenceCard from "../components/EvidenceCard";

export default function Search() {
  const [mode, setMode] = useState<"memory" | "ask">("memory");
  const [q, setQ] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [answer, setAnswer] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    setError(null);
    try {
      if (mode === "ask") {
        setAnswer(await api.ask(q));
        setHits(null);
      } else {
        setHits((await api.search(q)).results);
        setAnswer(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h2>Search</h2>
      <form onSubmit={submit} className="panel">
        <div className="row" role="radiogroup" aria-label="Search mode">
          <label><input type="radio" name="mode" checked={mode === "memory"} onChange={() => setMode("memory")} /> Memory search</label>
          <label><input type="radio" name="mode" checked={mode === "ask"} onChange={() => setMode("ask")} /> Ask GRAG</label>
          <label><input type="checkbox" checked={advanced} onChange={(e) => setAdvanced(e.target.checked)} /> Advanced scores</label>
        </div>
        <div className="row">
          <input type="search" aria-label="Query" style={{ flex: 1, minWidth: 200 }} value={q} onChange={(e) => setQ(e.target.value)}
            placeholder={mode === "ask" ? "Ask a question of local + fleet memory" : "Search memories"} />
          <button type="submit" disabled={busy}>{mode === "ask" ? "Ask" : "Search"}</button>
        </div>
      </form>
      {error && <div className="banner error" role="alert">Request failed: {error}</div>}
      {answer !== null && <div className="panel"><h2>Answer</h2><div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{answer}</div></div>}
      {hits && hits.length === 0 && <p className="empty">No matching memories. Try different words, or check the Memory page for what is stored.</p>}
      <div aria-live="polite">{hits !== null && hits.length > 0 && <span className="sr-only">{hits.length} results</span>}</div>
      {hits?.map((h) => <EvidenceCard key={`${h.origin}:${h.memory_id}`} hit={h} advanced={advanced} />)}
    </div>
  );
}
