import { FormEvent, useState } from "react";
import { api } from "../api/client";
import type { SearchHit } from "../api/types";
import EvidenceCard from "../components/EvidenceCard";
import { SegmentBar } from "../components/QueueMeter";
import { SkeletonCards } from "../components/Skeleton";

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

  const local = hits?.filter((h) => !String(h.origin).toUpperCase().includes("FLEET")).length ?? 0;
  return (
    <div>
      <h2 className="page-title">Search</h2>
      <form onSubmit={submit} className="panel">
        <div className="row" role="radiogroup" aria-label="Search mode">
          <label><input type="radio" name="mode" checked={mode === "memory"} onChange={() => setMode("memory")} /> Memory search</label>
          <label><input type="radio" name="mode" checked={mode === "ask"} onChange={() => setMode("ask")} /> Ask GRAG</label>
          <label><input type="checkbox" checked={advanced} onChange={(e) => setAdvanced(e.target.checked)} /> Advanced scores</label>
        </div>
        <div className="row">
          <input type="search" aria-label="Query" style={{ flex: 1, minWidth: 200 }} value={q} onChange={(e) => setQ(e.target.value)}
            placeholder={mode === "ask" ? "Ask a question of local + fleet memory" : "Search memories"} />
          <button type="submit" className="primary" disabled={busy} aria-busy={busy || undefined}>{mode === "ask" ? "Ask" : "Search"}</button>
        </div>
      </form>
      {error && <div className="banner error" role="alert">Request failed: {error}</div>}
      {busy && <SkeletonCards count={mode === "ask" ? 1 : 3} h={mode === "ask" ? 110 : 132} />}
      {!busy && answer !== null && <div className="panel enter"><h2>Answer</h2><div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{answer}</div></div>}
      {!busy && hits && hits.length === 0 && <p className="empty">No matching memories. Try different words, or check the Memory page for what is stored.</p>}
      <div aria-live="polite">
        {!busy && hits !== null && hits.length > 0 && (
          <div className="tally" key={hits.length + ":" + local}>
            <span>{hits.length} results</span>
            <SegmentBar segments={[{ key: "l", label: "local", count: local, tone: "ok" }, { key: "f", label: "fleet", count: hits.length - local, tone: "info" }]} />
            <span className="mono muted">{local} local · {hits.length - local} fleet</span>
          </div>
        )}
      </div>
      {!busy && hits?.map((h, i) => <EvidenceCard key={`${h.origin}:${h.memory_id}`} hit={h} advanced={advanced} index={i} />)}
    </div>
  );
}
