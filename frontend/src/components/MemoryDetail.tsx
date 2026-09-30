import { useEffect, useRef } from "react";
import type { MemoryRecord } from "../api/types";

export default function MemoryDetail({ record, onClose }: { record: MemoryRecord; onClose: () => void }) {
  const ref = useRef<HTMLElement>(null);
  // Keyboard users opening a row land in the detail; Escape or Close returns them to the row.
  useEffect(() => { ref.current?.focus(); }, [record.memory_id]);
  return (
    <aside className="panel" data-testid="memory-detail" aria-label="Memory detail" ref={ref} tabIndex={-1}
      onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}>
      <div className="row"><h2 style={{ flex: 1 }}>Memory detail</h2><button onClick={onClose}>Close</button></div>
      <div className="content mono" tabIndex={0} aria-label="Memory content" role="region" style={{ whiteSpace: "pre-wrap", maxHeight: "16em", overflow: "auto" }}>{record.content}</div>
      <dl className="mono">
        <dt>memory_id</dt><dd>{record.memory_id}</dd>
        <dt>logical_id</dt><dd>{record.logical_id}</dd>
        <dt>revision</dt><dd>{record.revision}</dd>
        <dt>device</dt><dd>{record.device_id}</dd>
        <dt>sync</dt><dd>{record.sync_state}</dd>
        <dt>tags</dt><dd>{(record.tags ?? []).join(", ") || "none"}</dd>
      </dl>
    </aside>
  );
}
