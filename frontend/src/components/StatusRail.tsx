import { useRef } from "react";
import type { EdgeStats, EdgeStatus } from "../api/types";
import { useCountUp, useEntrance, useFlashOnChange } from "../motion";

/** Metric cell. Numbers roll to their new value and the cell edge flashes once on change; `loading` keeps the
 *  footprint (no layout shift) and shimmers until the first response arrives. */
export function Cell({ label, value, tone, id, live, loading, mono }: { label: string; value: string | number | null | undefined; tone?: string; id?: string; live?: boolean; loading?: boolean; mono?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const shown = useCountUp(value);
  useFlashOnChange(ref, value);
  return (
    <div className="cell" ref={ref} data-tone={tone ?? "none"} data-loading={loading ? "" : undefined}>
      <div className="label">{label}</div>
      <div className={`value ${tone ?? ""} ${mono ? "mono" : ""}`} data-testid={id} aria-live={live ? "polite" : undefined}>{shown}</div>
    </div>
  );
}

export default function StatusRail({ status, stats, live, loading = false }: { status: EdgeStatus | null; stats: EdgeStats | null; live: boolean; loading?: boolean }) {
  const link = status?.connectivity ?? stats?.connectivity ?? "UNKNOWN";
  const ready = status?.status === "READY";
  const root = useRef<HTMLElement>(null);
  useEntrance(root, ".cell", "mount");
  return (
    <section className="rail rail-status" aria-label="Edge status" ref={root}>
      <Cell label="Device" value={status?.device_id ?? "—"} id="device" loading={loading} />
      <Cell label="Edge state" value={loading ? "—" : ready ? "READY" : status ? status.status : "UNAVAILABLE"} tone={loading ? undefined : ready ? "ok" : "bad"} loading={loading} />
      <Cell label="Local AI" value={ready ? "LOCAL" : "—"} tone={ready ? "ok" : undefined} loading={loading} />
      <Cell label="Qdrant Edge" value={ready ? "OPEN" : "—"} tone={ready ? "ok" : undefined} loading={loading} />
      <Cell label="Fleet link" value={loading ? "—" : link} tone={loading ? undefined : link === "ONLINE" ? "ok" : "warn"} id="fleet-link" live loading={loading} />
      <Cell label="Pending sync" value={stats?.pending_sync ?? "—"} tone={stats && stats.pending_sync > 0 ? "warn" : undefined} id="pending-sync" loading={loading} />
      <Cell label="Conflicts" value={stats?.open_conflict_count ?? "—"} tone={stats && stats.open_conflict_count > 0 ? "bad" : undefined} id="conflicts" loading={loading} />
      <Cell label="Live feed" value={live ? "CONNECTED" : "RECONNECTING"} tone={live ? "ok" : "warn"} />
    </section>
  );
}
