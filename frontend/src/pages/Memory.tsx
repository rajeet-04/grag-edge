import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { MemoryFilters, MemoryRecord } from "../api/types";
import MemoryDetail from "../components/MemoryDetail";

const SYNC_STATES = ["", "LOCAL_DIRTY", "LOCAL_ONLY", "AWAITING_APPROVAL", "QUEUED", "UPLOADING", "UPLOADED", "RETRY_WAIT", "SNAPSHOT_PENDING", "SYNCHRONIZED"];
const TYPES = ["", "observation", "procedure", "incident", "operator_note", "learned_fact"];
const IMPORTANCE = ["", "low", "normal", "high", "critical"];

export default function Memory() {
  const [draft, setDraft] = useState<MemoryFilters>({});
  const [rows, setRows] = useState<MemoryRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<MemoryRecord | null>(null);

  const load = useCallback(async (filters: MemoryFilters) => {
    try {
      setRows(await api.memories(filters));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);
  useEffect(() => { load({}); }, [load]);

  const set = (key: keyof MemoryFilters) => (e: { target: { value: string } }) => setDraft((d) => ({ ...d, [key]: e.target.value }));
  const toIso = (v?: string) => (v ? new Date(v).toISOString() : undefined);
  const apply = () => load({ ...draft, from_time: toIso(draft.from_time), to_time: toIso(draft.to_time) });

  async function open(row: MemoryRecord) {
    try { setSelected(await api.memory(row.memory_id)); } catch { setSelected(row); }
  }

  return (
    <div>
      <h2>Memory</h2>
      <div className="panel">
        <div className="row">
          <label>Source <input value={draft.source ?? ""} onChange={set("source")} /></label>
          <label>Type <select value={draft.memory_type ?? ""} onChange={set("memory_type")}>{TYPES.map((t) => <option key={t} value={t}>{t || "any"}</option>)}</select></label>
          <label>Sync state <select value={draft.sync_state ?? ""} onChange={set("sync_state")}>{SYNC_STATES.map((t) => <option key={t} value={t}>{t || "any"}</option>)}</select></label>
          <label>Importance <select value={draft.importance ?? ""} onChange={set("importance")}>{IMPORTANCE.map((t) => <option key={t} value={t}>{t || "any"}</option>)}</select></label>
          <label>Device <input value={draft.device_id ?? ""} onChange={set("device_id")} /></label>
          <label>Tag <input value={draft.tag ?? ""} onChange={set("tag")} /></label>
          <label>From <input type="datetime-local" value={draft.from_time ?? ""} onChange={set("from_time")} /></label>
          <label>To <input type="datetime-local" value={draft.to_time ?? ""} onChange={set("to_time")} /></label>
          <button onClick={apply}>Apply filters</button>
        </div>
      </div>
      {error && <div className="banner error" role="alert">Could not load memories: {error}</div>}
      {selected && <MemoryDetail record={selected} onClose={() => setSelected(null)} />}
      {rows && rows.length === 0 && <p className="empty">No memories match these filters. Clear a filter, or wait for new observations to be recorded.</p>}
      {rows?.map((r) => (
        <article key={r.memory_id} className="card" data-testid="memory-row" tabIndex={0} role="button"
          onClick={() => open(r)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(r); } }}>
          <div className="row">
            <span className="badge">{r.sync_state}</span><span className="badge">{r.memory_type}</span>
            <span className="badge">rev {r.revision}</span><span className="badge">{r.device_id}</span>
          </div>
          <div className="content">{r.content}</div>
          <div className="mono" style={{ color: "var(--muted)" }}>{r.memory_id}</div>
        </article>
      ))}
    </div>
  );
}
