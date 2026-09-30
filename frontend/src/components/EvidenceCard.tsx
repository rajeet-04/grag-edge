import { useLayoutEffect, useRef } from "react";
import { animate } from "animejs";
import type { SearchHit } from "../api/types";
import { EASE, reducedMotion } from "../motion";
import { ChipIcon, FleetIcon } from "./Icons";

const fmt = (n?: number | null) => (n === null || n === undefined ? "n/a" : n.toFixed(2));

/** Evidence card with a provenance header. The origin reveal is directional: a LOCAL hit draws in from the
 *  robot's side (left), a FLEET hit arrives along the wire from the fleet side (right). `index` staggers a result list. */
export default function EvidenceCard({ hit, advanced, index = 0 }: { hit: SearchHit; advanced: boolean; index?: number }) {
  const origin = String(hit.origin).toUpperCase().includes("FLEET") ? "FLEET" : "LOCAL";
  const fleet = origin === "FLEET";
  const card = useRef<HTMLElement>(null);
  const bar = useRef<HTMLSpanElement>(null);
  const tag = useRef<HTMLSpanElement>(null);

  useLayoutEffect(() => {
    if (reducedMotion() || !card.current || !bar.current || !tag.current) return;
    const delay = Math.min(index, 7) * 60;
    const dir = fleet ? 1 : -1;
    const anims = [
      animate(card.current, { translateY: [10, 0], duration: 380, delay, ease: EASE }),
      animate(bar.current, { scaleX: [0, 1], duration: 620, delay: delay + 60, ease: EASE }),
      animate(tag.current, { translateX: [dir * 36, 0], duration: 520, delay: delay + 40, ease: EASE }),
    ];
    return () => anims.forEach((a) => a.cancel());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <article className="card evidence" data-testid="evidence-card" data-origin={origin} ref={card}>
      <span className="prov-bar" ref={bar} aria-hidden="true" style={{ transformOrigin: fleet ? "right" : "left" }} />
      <div className="row prov">
        <span className="prov-tag" ref={tag}>
          {fleet ? <FleetIcon width={16} height={16} /> : <ChipIcon width={16} height={16} />}
          <span className={`badge origin ${fleet ? "fleet" : "local"}`}>{origin}</span>
        </span>
        <span className="prov-hint">{fleet ? "synced from fleet" : "stored on this robot"}</span>
      </div>
      <div className="row">
        <span className="badge">{hit.device_id}</span>
        <span className="badge">rev {hit.revision}</span>
        <span className="badge">confidence {fmt(hit.confidence)}</span>
        <span className="badge">{hit.sync_state}</span>
        <span className="badge">score {fmt(hit.score)}</span>
      </div>
      <div className="content">{hit.content}</div>
      <div className="mono muted">
        {hit.source_type}{hit.source_id ? `:${hit.source_id}` : ""} · {hit.memory_id}
      </div>
      {advanced && (
        <div className="mono">dense {fmt(hit.dense_score)} · sparse {fmt(hit.sparse_score)} · combined {fmt(hit.score)}</div>
      )}
    </article>
  );
}
