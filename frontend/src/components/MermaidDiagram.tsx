import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { useEntrance } from "../motion";

type Mermaid = typeof import("mermaid").default;
let loader: Promise<Mermaid> | null = null;
/** Lazy: the mermaid bundle is only fetched when an answer actually contains a diagram. */
const loadMermaid = () => (loader ??= import("mermaid").then((m) => m.default));
/** mermaid.render mutates document state, so diagrams render one at a time. */
let queue: Promise<unknown> = Promise.resolve();

/** The console follows the OS colour scheme (tokens.css); re-render diagrams when it flips. */
function useDark(): boolean {
  const query = () => (typeof window.matchMedia === "function" ? window.matchMedia("(prefers-color-scheme: light)") : null);
  const [dark, setDark] = useState(() => !query()?.matches);
  useEffect(() => {
    const mq = query();
    if (!mq) return;
    const on = () => setDark(!mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return dark;
}

const token = (name: string, fallback: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

function themeVariables(dark: boolean) {
  const text = token("--text", dark ? "#e8edf2" : "#12161b");
  const line = token("--line", "#8c98a6");
  return {
    darkMode: dark,
    background: token("--surface", "transparent"),
    fontFamily: token("--font-ui", "sans-serif"),
    primaryColor: token("--surface-2", "#1a2027"),
    primaryTextColor: text,
    primaryBorderColor: token("--accent", "#f2b233"),
    lineColor: token("--muted", line),
    secondaryColor: token("--surface-2", "#1a2027"),
    tertiaryColor: token("--surface", "#12161b"),
    textColor: text,
    edgeLabelBackground: token("--surface", "#12161b"),
  };
}

export default function MermaidDiagram({ source }: { source: string }) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const dark = useDark();
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [showSource, setShowSource] = useState(false);
  const holder = useRef<HTMLDivElement>(null);
  const fig = useRef<HTMLElement>(null);
  const run = useRef(0);

  useEffect(() => {
    let live = true;
    const id = `mmd-${uid}-${++run.current}`;
    const job = queue.then(async () => {
      let scratch: HTMLDivElement | null = null;
      try {
        const mermaid = await loadMermaid();
        mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "base", themeVariables: themeVariables(dark), htmlLabels: true, flowchart: { wrappingWidth: 400, nodeSpacing: 28, rankSpacing: 32, padding: 10 } });
        // Measure in our own scratch node so the reduced-motion overrides in tokens.css can be neutralised for it.
        scratch = document.createElement("div");
        scratch.className = "md-scratch";
        document.body.appendChild(scratch);
        const out = await mermaid.render(id, source, scratch);
        if (live) { setSvg(out.svg); setFailed(false); }
      } catch {
        document.getElementById(`d${id}`)?.remove(); // mermaid leaves its error scratch node behind
        if (live) { setFailed(true); setSvg(null); }
      } finally {
        scratch?.remove();
      }
    });
    queue = job;
    return () => { live = false; };
  }, [source, dark, uid]);

  // mermaid returns a sanitised SVG string (securityLevel "strict" runs DOMPurify); it is the only markup injected here.
  useLayoutEffect(() => {
    const el = holder.current;
    if (!el) return;
    el.innerHTML = svg ?? "";
    const node = el.querySelector("svg");
    const vb = node?.getAttribute("viewBox")?.split(/[\s,]+/).map(Number);
    if (node && vb && vb.length === 4 && vb[2] > 0) { // natural size, shrinking only when the column is narrower
      node.removeAttribute("height");
      node.style.width = `${Math.ceil(vb[2])}px`; node.style.maxWidth = "none"; node.style.height = "auto";
    }
  }, [svg]);
  useEntrance(fig as React.RefObject<HTMLElement>, ".md-diagram", svg ? 1 : 0, { y: 6 });

  if (failed) {
    return (
      <div className="md-fallback">
        <pre tabIndex={0}><code>{source}</code></pre>
        <p className="md-note muted">Diagram could not be rendered; showing its source.</p>
      </div>
    );
  }
  return (
    <figure className="md-figure" ref={fig}>
      <div className="md-diagram-scroll" tabIndex={0} role="region" aria-label="Graph reasoning path diagram, scrollable">
        <div className="md-diagram" ref={holder} role="img" aria-label={`Graph reasoning path diagram. Source: ${source.replace(/\s+/g, " ").slice(0, 400)}`} hidden={!svg} />
        {!svg && <div className="md-diagram-loading muted mono" role="status">Rendering diagram…</div>}
      </div>
      <figcaption>
        <span>Graph reasoning path</span>
        <button type="button" className="md-toggle" aria-expanded={showSource} onClick={() => setShowSource((s) => !s)}>
          {showSource ? "Hide source" : "View source"}
        </button>
      </figcaption>
      {showSource && <pre tabIndex={0}><code>{source}</code></pre>}
    </figure>
  );
}
