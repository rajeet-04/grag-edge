import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { ActivityEvent, EdgeStats, EdgeStatus } from "../api/types";
import ActivityFeed from "../components/ActivityFeed";
import StatusRail from "../components/StatusRail";
import { useEdgeEvents } from "../hooks/useEdgeEvents";

const MAX_ROWS = 200;

export function mergeEvents(current: ActivityEvent[], incoming: ActivityEvent[]): ActivityEvent[] {
  const seen = new Set(current.map((e) => e.event_id));
  const fresh = incoming.filter((e) => !seen.has(e.event_id) && seen.add(e.event_id));
  return [...fresh, ...current].slice(0, MAX_ROWS);
}

export default function Overview() {
  const [status, setStatus] = useState<EdgeStatus | null>(null);
  const [stats, setStats] = useState<EdgeStats | null>(null);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const refresh = useCallback(async () => {
    const [s, st] = await Promise.allSettled([api.status(), api.stats()]);
    if (!alive.current) return;
    if (s.status === "fulfilled") setStatus(s.value);
    if (st.status === "fulfilled") setStats(st.value);
    const failed = s.status === "rejected" ? s : st.status === "rejected" ? st : null;
    setError(failed ? String((failed as PromiseRejectedResult).reason?.message ?? failed.reason) : null);
  }, []);

  useEffect(() => {
    refresh();
    api.activity(100).then((rows) => alive.current && setEvents((cur) => mergeEvents(cur, rows))).catch(() => undefined);
  }, [refresh]);

  const live = useEdgeEvents((event) => {
    setEvents((cur) => mergeEvents(cur, [event]));
    refresh();
  }, () => {
    refresh();
    api.activity(100).then((rows) => alive.current && setEvents((cur) => mergeEvents(cur, rows))).catch(() => undefined);
  });

  const offline = (status?.connectivity ?? stats?.connectivity) === "OFFLINE";
  return (
    <div>
      <h2>Overview</h2>
      {error && <div className="banner error" role="alert">Edge API problem: {error}. Retrying automatically; the console shows the last known state.</div>}
      {offline && <div className="banner">Fleet link is offline. GRAG is operating locally; new memories queue and sync when the link returns.</div>}
      <StatusRail status={status} stats={stats} live={live} />
      {stats && (
        <section className="rail" aria-label="Metrics">
          <div className="cell"><div className="label">Local memories</div><div className="value">{stats.local_memory_count}</div></div>
          <div className="cell"><div className="label">Fleet memories</div><div className="value">{stats.fleet_memory_count}</div></div>
          <div className="cell"><div className="label">Synced</div><div className="value">{stats.sync_success_count}</div></div>
          <div className="cell"><div className="label">Failures</div><div className="value">{stats.sync_failure_count}</div></div>
          <div className="cell"><div className="label">Last sync</div><div className="value mono">{stats.last_sync ?? "never"}</div></div>
        </section>
      )}
      <div className="panel"><h2>Live activity</h2><ActivityFeed events={events} /></div>
    </div>
  );
}
