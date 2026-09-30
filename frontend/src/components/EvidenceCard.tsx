import type { SearchHit } from "../api/types";

const fmt = (n?: number | null) => (n === null || n === undefined ? "n/a" : n.toFixed(2));

export default function EvidenceCard({ hit, advanced }: { hit: SearchHit; advanced: boolean }) {
  const origin = String(hit.origin).toUpperCase().includes("FLEET") ? "FLEET" : "LOCAL";
  return (
    <article className="card" data-testid="evidence-card">
      <div className="row">
        <span className={`badge ${origin === "FLEET" ? "" : "ok"}`}>{origin}</span>
        <span className="badge">{hit.device_id}</span>
        <span className="badge">rev {hit.revision}</span>
        <span className="badge">confidence {fmt(hit.confidence)}</span>
        <span className="badge">{hit.sync_state}</span>
        <span className="badge">score {fmt(hit.score)}</span>
      </div>
      <div className="content">{hit.content}</div>
      <div className="mono" style={{ color: "var(--muted)" }}>
        {hit.source_type}{hit.source_id ? `:${hit.source_id}` : ""} · {hit.memory_id}
      </div>
      {advanced && (
        <div className="mono">dense {fmt(hit.dense_score)} · sparse {fmt(hit.sparse_score)} · combined {fmt(hit.score)}</div>
      )}
    </article>
  );
}
