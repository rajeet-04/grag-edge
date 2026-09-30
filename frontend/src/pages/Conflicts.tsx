import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { animate } from "animejs";
import { api } from "../api/client";
import type { ConflictRecord, MemoryRecord, Resolution } from "../api/types";
import { SkeletonCards } from "../components/Skeleton";
import { useEdgeEvents } from "../hooks/useEdgeEvents";
import { diffSummary } from "../lib/diff";
import { EASE, reducedMotion } from "../motion";

type Detail = Awaited<ReturnType<typeof api.conflict>>;
type Verdict = "win" | "lose" | "merge";

const SETTLE_MS = 260; // how long the chosen branch is shown as "kept" before the panel closes

function Side({ title, m, other, verdict }: { title: string; m: MemoryRecord | null; other: MemoryRecord | null; verdict?: Verdict }) {
  const d = m && other ? diffSummary(m.content, other.content) : null;
  const mine = d ? d.a : "";
  return (
    <div className="card side" data-side={title.toLowerCase()} data-verdict={verdict}>
      <h2>{title}</h2>
      {m ? (<>
        <div className="mono">{m.device_id} · rev {m.revision}</div>
        <div className="content">{m.content}</div>
        {d && (
          <div className="diff mono">
            <span className="diff-tag">{d.same ? "same text" : "differs"}</span>
            {!d.same && <span className="diff-seg">{mine || "(nothing added here)"}</span>}
          </div>
        )}
      </>) : <p className="empty">Content unavailable.</p>}
    </div>
  );
}

/** The fork: two branches leave the common ancestor. Revealed from the centre outward when the panel opens. */
function Fork() {
  const svg = useRef<SVGSVGElement>(null);
  useLayoutEffect(() => {
    const el = svg.current;
    if (!el || reducedMotion()) return;
    const a = animate(el, { clipPath: ["inset(0 50% 0 50%)", "inset(0 0% 0 0%)"], duration: 520, ease: EASE });
    return () => { a.cancel(); el.style.clipPath = ""; };
  }, []);
  return (
    <svg className="fork" ref={svg} aria-hidden="true" focusable="false">
      <line x1="50%" y1="0" x2="50%" y2="9" /><line x1="25%" y1="9" x2="75%" y2="9" /><line x1="25%" y1="9" x2="25%" y2="24" /><line x1="75%" y1="9" x2="75%" y2="24" />
    </svg>
  );
}

export default function Conflicts() {
  const [items, setItems] = useState<ConflictRecord[] | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [merged, setMerged] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<Resolution | null>(null);
  const alive = useRef(true);
  const token = useRef(0);
  const panel = useRef<HTMLDivElement>(null);
  const sides = useRef<HTMLDivElement>(null);
  useEffect(() => { if (detail) panel.current?.focus(); }, [detail]);
  useEffect(() => () => { alive.current = false; }, []);

  // The two branches slide in from their own side of the fork.
  useLayoutEffect(() => {
    const root = sides.current;
    if (!detail || !root || reducedMotion()) return;
    const l = root.querySelector<HTMLElement>('[data-side="local"]');
    const f = root.querySelector<HTMLElement>('[data-side="fleet"]');
    const anims = [
      l && animate(l, { translateX: [-28, 0], duration: 460, ease: EASE }),
      f && animate(f, { translateX: [28, 0], duration: 460, ease: EASE }),
    ];
    return () => anims.forEach((a) => a && a.cancel());
  }, [detail]);

  const load = useCallback(async () => {
    try { const c = await api.conflicts(); if (alive.current) { setItems(c); setError(null); } }
    catch (err) { if (alive.current) setError(err instanceof Error ? err.message : String(err)); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEdgeEvents(() => { load(); }, () => { load(); });

  async function open(id: string) {
    token.current++;
    try { setDetail(await api.conflict(id)); setMerged(""); setVerdict(null); setError(null); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }
  async function resolve(resolution: Resolution) {
    if (!detail) return;
    try {
      await api.resolveConflict(detail.conflict.conflict_id, resolution, resolution === "MERGE" ? merged : undefined);
      const mine = ++token.current;
      if (!reducedMotion()) {
        // Show the outcome for a beat (kept branch highlighted, the other recedes) while the list reloads.
        setVerdict(resolution);
        await Promise.all([load(), new Promise((r) => setTimeout(r, SETTLE_MS))]);
        if (!alive.current || token.current !== mine) return; // the operator reopened something meanwhile
      } else {
        await load();
      }
      setDetail(null);
      setVerdict(null);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }

  const v = (side: "local" | "fleet"): Verdict | undefined =>
    verdict === null ? undefined : verdict === "MERGE" ? "merge" : (verdict === "KEEP_LOCAL") === (side === "local") ? "win" : "lose";

  return (
    <div>
      <h2 className="page-title">Conflicts</h2>
      {error && <div className="banner error" role="alert">Conflict action failed: {error}</div>}
      {items === null && !error && <SkeletonCards count={1} h={40} />}
      {items && items.length === 0 && <p className="empty">No open conflicts. Local and fleet memories agree.</p>}
      <div className="row">
        {items?.map((c) => <button key={c.conflict_id} onClick={() => open(c.conflict_id)} className="mono conflict-chip">{c.conflict_id}</button>)}
      </div>
      {detail && (
        <div className="panel enter resolve" ref={panel} tabIndex={-1} role="region" aria-label="Resolve conflict" data-verdict={verdict ?? undefined}>
          <h2>Resolve <span className="mono">{detail.conflict.conflict_id}</span></h2>
          <Fork />
          <div className="sides" ref={sides}>
            <Side title="Local" m={detail.local} other={detail.fleet} verdict={v("local")} />
            <Side title="Fleet" m={detail.fleet} other={detail.local} verdict={v("fleet")} />
          </div>
          <div className="row">
            <button className="primary" onClick={() => resolve("KEEP_LOCAL")}>Keep local</button>
            <button className="primary" onClick={() => resolve("ACCEPT_FLEET")}>Accept fleet</button>
          </div>
          <label>Merged content
            <textarea style={{ width: "100%", minHeight: 80 }} value={merged} onChange={(e) => setMerged(e.target.value)} />
          </label>
          <div className="row"><button onClick={() => resolve("MERGE")} disabled={!merged.trim()}>Merge</button></div>
        </div>
      )}
    </div>
  );
}
