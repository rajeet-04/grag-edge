import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { MemoryRecord, SyncQueueItem, SyncStatus } from "../api/types";
import { useEdgeEvents } from "../hooks/useEdgeEvents";

export default function Sync() {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [queue, setQueue] = useState<SyncQueueItem[] | null>(null);
  const [approvals, setApprovals] = useState<MemoryRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const load = useCallback(async () => {
    try {
      const [s, q, a] = await Promise.all([api.syncStatus(), api.syncQueue(), api.memories({ sync_state: "AWAITING_APPROVAL" })]);
      if (!alive.current) return;
      setStatus(s); setQueue(q); setApprovals(a); setError(null);
    } catch (err) {
      if (alive.current) setError(err instanceof Error ? err.message : String(err));
    }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEdgeEvents(() => { load(); }, () => { load(); });

  async function act(fn: () => Promise<unknown>) {
    try { await fn(); await load(); } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }

  const link = status && typeof status.connectivity === "object" ? status.connectivity.connectivity : status?.connectivity;
  return (
    <div>
      <h2>Sync</h2>
      {error && <div className="banner error" role="alert">Sync data unavailable: {error}. The edge keeps working locally; this page retries on the next event.</div>}
      {link === "OFFLINE" && <div className="banner">Fleet link offline. Items stay queued and retry automatically when the link returns.</div>}
      {status && (
        <section className="rail" aria-label="Sync counts">
          <div className="cell"><div className="label">Pending</div><div className="value" data-testid="count-pending">{status.pending}</div></div>
          <div className="cell"><div className="label">Queued</div><div className="value">{status.queued}</div></div>
          <div className="cell"><div className="label">Retry wait</div><div className="value warn" data-testid="count-retry">{status.retry_wait}</div></div>
          <div className="cell"><div className="label">Uploading</div><div className="value">{status.uploading + status.uploaded + status.snapshot_pending}</div></div>
          <div className="cell"><div className="label">Synchronized</div><div className="value ok">{status.synchronized}</div></div>
          <div className="cell"><div className="label">Last attempt</div><div className="value mono">{status.last_attempt_at ?? "never"}</div></div>
        </section>
      )}
      <div className="row"><button onClick={() => act(api.runSync)}>Run sync now</button></div>
      <div className="panel">
        <h2>Awaiting approval</h2>
        {approvals.length === 0 && <p className="empty">Nothing is waiting for operator approval.</p>}
        {approvals.map((m) => (
          <div className="card" key={m.memory_id}>
            <div className="content">{m.content}</div>
            <div className="mono">{m.memory_id} · policy: {(m.sync_reason_codes ?? []).join(", ") || "none recorded"}</div>
            <div className="row">
              <button onClick={() => act(() => api.approve(m.memory_id))}>Approve upload</button>
              <button onClick={() => act(() => api.reject(m.memory_id))}>Keep local</button>
            </div>
          </div>
        ))}
      </div>
      <div className="panel">
        <h2>Queue</h2>
        {queue && queue.length === 0 && <p className="empty">The sync queue is empty. New memories eligible for the fleet will appear here.</p>}
        {queue?.map((i) => (
          <div className="card" key={i.memory_id + i.status}>
            <span className="badge">{i.status}</span><span className="badge">retries {i.retry_count}</span>
            <span className="mono"> {i.memory_id}</span>
            {i.last_error && <div className="warn mono">{i.last_error}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
