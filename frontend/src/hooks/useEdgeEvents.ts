import { useEffect, useRef, useState } from "react";
import { eventsUrl } from "../api/client";
import type { ActivityEvent } from "../api/types";

export const EVENT_TYPES = [
  "DEVICE_STARTED", "CLOUD_LINK_UP", "CLOUD_LINK_DOWN", "MEMORY_CREATED", "MEMORY_REVISED",
  "SYNC_QUEUED", "SYNC_STARTED", "SYNC_RETRY", "SYNC_COMPLETED", "POLICY_LOCAL_ONLY", "POLICY_SYNC_APPROVED",
  "FLEET_REFRESH_STARTED", "FLEET_REFRESH_COMPLETED", "CONFLICT_DETECTED", "CONFLICT_RESOLVED", "message",
];

/** Subscribe to the edge SSE stream. Native EventSource resends Last-Event-ID; if the
 * browser gives up (CLOSED) we reopen with backoff. Consumers must dedupe by event_id. */
export function useEdgeEvents(onEvent: (event: ActivityEvent) => void, onReconnect?: () => void) {
  const [connected, setConnected] = useState(false);
  const handler = useRef(onEvent);
  const reconnect = useRef(onReconnect);
  handler.current = onEvent;
  reconnect.current = onReconnect;

  useEffect(() => {
    let source: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    let attempts = 0;
    let wasDown = false;

    const open = () => {
      if (stopped) return;
      const es = new EventSource(eventsUrl());
      source = es;
      es.onopen = () => {
        attempts = 0;
        setConnected(true);
        if (wasDown) reconnect.current?.();
        wasDown = false;
      };
      es.onerror = () => {
        setConnected(false);
        wasDown = true;
        if (es.readyState === 2 /* CLOSED */ && !stopped) {
          es.close();
          timer = setTimeout(open, Math.min(30000, 1000 * 2 ** attempts++));
        }
      };
      for (const type of EVENT_TYPES) {
        es.addEventListener(type, (raw) => {
          try {
            const evt = JSON.parse((raw as MessageEvent).data) as ActivityEvent;
            handler.current({ ...evt, event_id: evt.event_id ?? (raw as MessageEvent).lastEventId });
          } catch { /* ignore malformed frame */ }
        });
      }
    };
    open();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      source?.close();
    };
  }, []);

  return connected;
}
