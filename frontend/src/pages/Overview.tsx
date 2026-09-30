import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { ActivityEvent, EdgeStats, EdgeStatus } from "../api/types";
import LinkStrip, { type LinkState } from "../components/LinkStrip";
import { Cell } from "../components/StatusRail";
import ActivityFeed from "../components/ActivityFeed";
import StatusRail from "../components/StatusRail";
import { useEdgeEvents } from "../hooks/useEdgeEvents";
import { useEntrance } from "../motion";

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
  const [settled, setSettled] = useState(false);
  const page = useRef<HTMLDivElement>(null);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const refresh = useCallback(async () => {
    const [s, st] = await Promise.allSettled([api.status(), api.stats()]);
    if (!alive.current) return;
    setSettled(true);
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

  const connectivity = status?.connectivity ?? stats?.connectivity;
  const link: LinkState = connectivity === "ONLINE" ? "ONLINE" : connectivity === "OFFLINE" ? "OFFLINE" : "UNKNOWN";
  const loading = !settled;
  useEntrance(page, ".linkstrip, .panel", "mount");
  return (
    <div ref={page}>
      <h2 className="page-title">Overview</h2>
      {error && <div className="banner error" role="alert">Edge API problem: {error}. Retrying automatically; the console shows the last known state.</div>}
      <LinkStrip link={link} pending={stats?.pending_sync ?? 0} synced={stats?.sync_success_count ?? 0} />
      <StatusRail status={status} stats={stats} live={live} loading={loading} />
      <section className="rail" aria-label="Metrics" aria-busy={stats ? undefined : true}>
        <Cell label="Local memories" value={stats?.local_memory_count} loading={!stats} />
        <Cell label="Fleet memories" value={stats?.fleet_memory_count} loading={!stats} />
        <Cell label="Synced" value={stats?.sync_success_count} loading={!stats} />
        <Cell label="Failures" value={stats?.sync_failure_count} tone={stats && stats.sync_failure_count > 0 ? "bad" : undefined} loading={!stats} />
        <Cell label="Last sync" value={stats ? stats.last_sync ?? "never" : null} mono loading={!stats} />
      </section>
      <div className="panel"><h2>Live activity</h2><ActivityFeed events={events} /></div>
    </div>
  );
}
