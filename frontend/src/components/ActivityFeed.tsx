import type { ActivityEvent } from "../api/types";

export default function ActivityFeed({ events }: { events: ActivityEvent[] }) {
  if (events.length === 0) {
    return <p className="empty">No activity yet. Memory, sync and conflict events will appear here as they happen.</p>;
  }
  return (
    <ul className="feed" tabIndex={0} aria-label="Live activity feed">
      {events.map((e) => (
        <li key={e.event_id}>
          <span className="badge mono">{e.event_type}</span>
          <span>{e.message}</span>{" "}
          <span className="mono" style={{ color: "var(--muted)" }}>{e.timestamp ?? ""}</span>
        </li>
      ))}
    </ul>
  );
}
