import { useRef } from "react";
import type { ActivityEvent } from "../api/types";
import { useEntrance } from "../motion";

const kind = (t: string) => (/DOWN|FAIL|RETRY/.test(t) ? "warn" : /CONFLICT/.test(t) ? "bad" : /UP|COMPLETED|APPROVED|RESOLVED|CREATED|REVISED|STARTED/.test(t) ? "ok" : "none");

export default function ActivityFeed({ events }: { events: ActivityEvent[] }) {
  const ref = useRef<HTMLUListElement>(null);
  useEntrance(ref, "li", events[0]?.event_id ?? "", { y: -6 });
  if (events.length === 0) {
    return <p className="empty">No activity yet. Memory, sync and conflict events will appear here as they happen.</p>;
  }
  return (
    <ul className="feed" tabIndex={0} aria-label="Live activity feed" ref={ref}>
      {events.map((e) => (
        <li key={e.event_id}>
          <span className="badge mono" data-kind={kind(e.event_type)}>{e.event_type}</span>
          <span>{e.message}</span>{" "}
          <span className="mono stamp">{e.timestamp ?? ""}</span>
        </li>
      ))}
    </ul>
  );
}
