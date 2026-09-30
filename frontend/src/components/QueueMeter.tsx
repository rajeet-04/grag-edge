import { useEffect, useState } from "react";

export interface Segment { key: string; label: string; count: number; tone: "ok" | "warn" | "bad" | "info" }

/** Stacked queue meter. Segments are laid out with translateX/scaleX inside a fixed track, so when the queue
 *  drains the bar glides (CSS transition) without touching layout. Purely visual: the numbers live in the text next to it. */
export function SegmentBar({ segments }: { segments: Segment[] }) {
  // Mount collapsed, then expand next frame so the CSS transition plays the first fill too.
  const [armed, setArmed] = useState(false);
  useEffect(() => { const id = requestAnimationFrame(() => setArmed(true)); return () => cancelAnimationFrame(id); }, []);
  const total = segments.reduce((n, s) => n + s.count, 0);
  let start = 0;
  return (
    <div className="segbar" aria-hidden="true">
      {segments.map((s) => {
        const len = total === 0 || !armed ? 0 : s.count / total;
        const style = { transform: `translateX(${start * 100}%) scaleX(${len})` };
        start += len;
        return <span key={s.key} className={`seg seg-${s.tone}`} style={style} />;
      })}
    </div>
  );
}

/** Drain progress: how much of the work seen so far has already reached the fleet. */
export function DrainMeter({ pending, synced, link }: { pending: number; synced: number; link: string }) {
  const total = pending + synced;
  const pct = total === 0 ? 100 : Math.round((synced / total) * 100);
  const state = pending === 0 ? "idle" : link === "ONLINE" ? "draining" : "held";
  return (
    <div className="meter" data-drain={state}>
      <span className="meter-label">Sync queue</span>
      <div className="meter-track" role="progressbar" aria-label="Sync queue progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
        <span className="meter-fill" style={{ transform: `scaleX(${pct / 100})` }} />
      </div>
      <span className="meter-val mono">{pending === 0 ? "queue empty" : `${pending} waiting`}</span>
    </div>
  );
}
