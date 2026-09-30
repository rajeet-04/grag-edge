import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { ConflictRecord, MemoryRecord, Resolution } from "../api/types";
import { useEdgeEvents } from "../hooks/useEdgeEvents";

type Detail = Awaited<ReturnType<typeof api.conflict>>;

function Side({ title, m }: { title: string; m: MemoryRecord | null }) {
  return (
    <div className="card">
      <h2>{title}</h2>
      {m ? (<>
        <div className="mono">{m.device_id} · rev {m.revision}</div>
        <div className="content">{m.content}</div>
      </>) : <p className="empty">Content unavailable.</p>}
    </div>
  );
}

export default function Conflicts() {
  const [items, setItems] = useState<ConflictRecord[] | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [merged, setMerged] = useState("");
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => { if (detail) panel.current?.focus(); }, [detail]);
  useEffect(() => () => { alive.current = false; }, []);

  const load = useCallback(async () => {
    try { const c = await api.conflicts(); if (alive.current) { setItems(c); setError(null); } }
    catch (err) { if (alive.current) setError(err instanceof Error ? err.message : String(err)); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEdgeEvents(() => { load(); }, () => { load(); });

  async function open(id: string) {
    try { setDetail(await api.conflict(id)); setMerged(""); setError(null); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }
  async function resolve(resolution: Resolution) {
    if (!detail) return;
    try {
      await api.resolveConflict(detail.conflict.conflict_id, resolution, resolution === "MERGE" ? merged : undefined);
      setDetail(null);
      await load();
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }

  return (
    <div>
      <h2>Conflicts</h2>
      {error && <div className="banner error" role="alert">Conflict action failed: {error}</div>}
      {items && items.length === 0 && <p className="empty">No open conflicts. Local and fleet memories agree.</p>}
      <div className="row">
        {items?.map((c) => <button key={c.conflict_id} onClick={() => open(c.conflict_id)} className="mono">{c.conflict_id}</button>)}
      </div>
      {detail && (
        <div className="panel" ref={panel} tabIndex={-1} role="region" aria-label="Resolve conflict">
          <h2>Resolve <span className="mono">{detail.conflict.conflict_id}</span></h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 8 }}>
            <Side title="Local" m={detail.local} />
            <Side title="Fleet" m={detail.fleet} />
          </div>
          <div className="row">
            <button onClick={() => resolve("KEEP_LOCAL")}>Keep local</button>
            <button onClick={() => resolve("ACCEPT_FLEET")}>Accept fleet</button>
          </div>
          <label>Merged content
            <textarea style={{ width: "100%", minHeight: 80 }} value={merged} onChange={(e) => setMerged(e.target.value)} />
          </label>
          <div className="row"><button onClick={() => resolve("MERGE")} disabled={!merged.trim()}>Merge</button></div>
        </div>
      )}
    </div>
  );
}
