/** Word-level "where do these two versions diverge" summary: trims the shared leading and trailing
 *  words and returns what is unique to each side. Pure; used by the conflict resolve panel. */
export interface DiffSummary { same: boolean; a: string; b: string }

const words = (s: string) => s.split(/\s+/).filter(Boolean);
const clip = (s: string, n = 140) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

export function diffSummary(a: string, b: string): DiffSummary {
  const x = words(a), y = words(b);
  let start = 0;
  while (start < x.length && start < y.length && x[start] === y[start]) start++;
  let endX = x.length, endY = y.length;
  while (endX > start && endY > start && x[endX - 1] === y[endY - 1]) { endX--; endY--; }
  const ma = x.slice(start, endX).join(" "), mb = y.slice(start, endY).join(" ");
  return { same: ma === "" && mb === "", a: clip(ma), b: clip(mb) };
}
