import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { MemoryRecord, SyncQueueItem, SyncStatus } from "../api/types";
import { SegmentBar } from "../components/QueueMeter";
import { SkeletonCards } from "../components/Skeleton";
import { Cell } from "../components/StatusRail";
import { useEdgeEvents } from "../hooks/useEdgeEvents";
import { useEntrance } from "../motion";

export default function Sync() {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [queue, setQueue] = useState<SyncQueueItem[] | null>(null);
  const [approvals, setApprovals] = useState<MemoryRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const page = useRef<HTMLDivElement>(null);
  const queueBox = useRef<HTMLDivElement>(null);
  useEntrance(page, ".rail .cell, .meter-panel", "mount");
  useEntrance(queueBox, ".card", queue);
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
  async function runNow() {
    setRunning(true);
    try { await act(api.runSync); } finally { if (alive.current) setRunning(false); }
  }

  const link = status && typeof status.connectivity === "object" ? status.connectivity.connectivity : status?.connectivity;
  return (
    <div ref={page}>
      <h2 className="page-title">Sync</h2>
      {error && <div className="banner error" role="alert">Sync data unavailable: {error}. The edge keeps working locally; this page retries on the next event.</div>}
      {link === "OFFLINE" && <div className="banner">Fleet link offline. Items stay queued and retry automatically when the link returns.</div>}
      <section className="rail" aria-label="Sync counts" aria-busy={status ? undefined : true}>
        <Cell label="Pending" value={status?.pending} id="count-pending" tone={status && status.pending > 0 ? "warn" : undefined} loading={!status} />
        <Cell label="Queued" value={status?.queued} loading={!status} />
        <Cell label="Retry wait" value={status?.retry_wait} id="count-retry" tone={status && status.retry_wait > 0 ? "warn" : undefined} loading={!status} />
        <Cell label="Uploading" value={status ? status.uploading + status.uploaded + status.snapshot_pending : undefined} tone={status && status.uploading > 0 ? "info" : undefined} loading={!status} />
        <Cell label="Synchronized" value={status?.synchronized} tone="ok" loading={!status} />
        <Cell label="Last attempt" value={status ? status.last_attempt_at ?? "never" : null} mono loading={!status} />
      </section>
      {status && (
        <div className="meter-panel" data-link={link} data-busy={running || undefined}>
          <SegmentBar segments={[
            { key: "p", label: "waiting", count: status.pending + status.queued, tone: "warn" },
            { key: "r", label: "retry", count: status.retry_wait, tone: "bad" },
            { key: "u", label: "uploading", count: status.uploading + status.uploaded + status.snapshot_pending, tone: "info" },
            { key: "s", label: "synchronized", count: status.synchronized, tone: "ok" },
          ]} />
        </div>
      )}
      <div className="row"><button className="primary" onClick={runNow} aria-busy={running || undefined}>Run sync now</button></div>
      <div className="panel">
        <h2>Awaiting approval</h2>
        {approvals.length === 0 && <p className="empty">Nothing is waiting for operator approval.</p>}
        {approvals.map((m) => (
          <div className="card" key={m.memory_id}>
            <div className="content">{m.content}</div>
            <div className="mono">{m.memory_id} · policy: {(m.sync_reason_codes ?? []).join(", ") || "none recorded"}</div>
            <div className="row">
              <button className="primary" onClick={() => act(() => api.approve(m.memory_id))}>Approve upload</button>
              <button onClick={() => act(() => api.reject(m.memory_id))}>Keep local</button>
            </div>
          </div>
        ))}
      </div>
      <div className="panel">
        <h2>Queue</h2>
        {queue === null && !error && <SkeletonCards count={2} h={44} />}
        {queue && queue.length === 0 && <p className="empty">The sync queue is empty. New memories eligible for the fleet will appear here.</p>}
        <div ref={queueBox}>
        {queue?.map((i) => (
          <div className="card" key={i.memory_id + i.status}>
            <span className="badge" data-sync={i.status}>{i.status}</span><span className="badge">retries {i.retry_count}</span>
            <span className="mono"> {i.memory_id}</span>
            {i.last_error && <div className="warn mono">{i.last_error}</div>}
          </div>
        ))}
        </div>
      </div>
    </div>
  );
}
