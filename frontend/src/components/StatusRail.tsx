import type { EdgeStats, EdgeStatus } from "../api/types";

function Cell({ label, value, tone, id }: { label: string; value: string | number; tone?: string; id?: string }) {
  return (
    <div className="cell">
      <div className="label">{label}</div>
      <div className={`value ${tone ?? ""}`} data-testid={id}>{value}</div>
    </div>
  );
}

export default function StatusRail({ status, stats, live }: { status: EdgeStatus | null; stats: EdgeStats | null; live: boolean }) {
  const link = status?.connectivity ?? stats?.connectivity ?? "UNKNOWN";
  const ready = status?.status === "READY";
  return (
    <section className="rail" aria-label="Edge status">
      <Cell label="Device" value={status?.device_id ?? "—"} id="device" />
      <Cell label="Edge state" value={ready ? "READY" : status ? status.status : "UNAVAILABLE"} tone={ready ? "ok" : "bad"} />
      <Cell label="Local AI" value={ready ? "LOCAL" : "—"} tone={ready ? "ok" : undefined} />
      <Cell label="Qdrant Edge" value={ready ? "OPEN" : "—"} tone={ready ? "ok" : undefined} />
      <Cell label="Fleet link" value={link} tone={link === "ONLINE" ? "ok" : "warn"} id="fleet-link" />
      <Cell label="Pending sync" value={stats?.pending_sync ?? "—"} tone={stats && stats.pending_sync > 0 ? "warn" : undefined} id="pending-sync" />
      <Cell label="Conflicts" value={stats?.open_conflict_count ?? "—"} tone={stats && stats.open_conflict_count > 0 ? "bad" : undefined} id="conflicts" />
      <Cell label="Live feed" value={live ? "CONNECTED" : "RECONNECTING"} tone={live ? "ok" : "warn"} />
    </section>
  );
}
