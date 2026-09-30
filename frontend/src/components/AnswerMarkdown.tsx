import { lazy, Suspense, useMemo, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const MermaidDiagram = lazy(() => import("./MermaidDiagram"));

/** True while the last ``` / ~~~ fence is still open (a streamed, partial answer). */
export function hasOpenFence(text: string): boolean {
  let open = false;
  for (const line of text.split("\n")) if (/^ {0,3}(```|~~~)/.test(line)) open = !open;
  return open;
}

const text = (n: ReactNode): string => (Array.isArray(n) ? n.map(text).join("") : typeof n === "string" ? n : "");

/** Model answers are untrusted: markdown only. No rehype-raw, so embedded HTML is never parsed into elements,
 *  and react-markdown's default urlTransform strips javascript: URLs. */
export default function AnswerMarkdown({ text: source }: { text: string }) {
  const open = hasOpenFence(source);
  const components = useMemo<Components>(() => ({
    h1: ({ children }) => <h3>{children}</h3>, // the panel title is the h2
    h2: ({ children }) => <h3>{children}</h3>,
    h3: ({ children }) => <h4>{children}</h4>,
    h4: ({ children }) => <h5>{children}</h5>,
    h5: ({ children }) => <h5>{children}</h5>,
    h6: ({ children }) => <h5>{children}</h5>,
    a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
    table: ({ children }) => <div className="md-table" role="region" aria-label="Table, scrollable" tabIndex={0}><table>{children}</table></div>,
    pre: ({ children }) => <>{children}</>,
    code: ({ className, children }) => {
      const lang = /language-(\w+)/.exec(className ?? "")?.[1];
      const body = text(children);
      if (!lang && !body.includes("\n")) return <code className="md-inline">{body}</code>;
      if (lang === "mermaid" && !open) {
        return <Suspense fallback={<div className="md-diagram-loading muted mono" role="status">Rendering diagram…</div>}><MermaidDiagram source={body.replace(/\n$/, "")} /></Suspense>;
      }
      return <pre tabIndex={0}><code className={className}>{body.replace(/\n$/, "")}</code></pre>;
    },
  }), [open]);
  return <div className="answer-md"><ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{source}</ReactMarkdown></div>;
}
