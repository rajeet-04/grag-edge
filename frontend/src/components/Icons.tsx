// One icon family: 20px grid, 1.6 stroke, square caps. Decorative by default (aria-hidden).
import type { SVGProps } from "react";

const base = { width: 20, height: 20, viewBox: "0 0 20 20", fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "square", strokeLinejoin: "miter", "aria-hidden": true, focusable: false } as const;

export const ChipIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><rect x="5" y="5" width="10" height="10" /><path d="M8 2v3M12 2v3M8 15v3M12 15v3M2 8h3M2 12h3M15 8h3M15 12h3" /><rect x="8" y="8" width="4" height="4" /></svg>
);
export const FleetIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><circle cx="10" cy="10" r="2.2" /><circle cx="3.5" cy="4.5" r="1.5" /><circle cx="16.5" cy="4.5" r="1.5" /><circle cx="3.5" cy="15.5" r="1.5" /><circle cx="16.5" cy="15.5" r="1.5" /><path d="M8.2 8.6 4.7 5.5M11.8 8.6l3.5-3.1M8.2 11.4l-3.5 3.1M11.8 11.4l3.5 3.1" /></svg>
);
export const BrandMark = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} width={22} height={22} viewBox="0 0 22 22" {...p}><path d="M11 1.5 19.5 6.5v9L11 20.5 2.5 15.5v-9z" /><path d="M6.5 11h9M11 6.5v9" strokeWidth={1.2} /><circle cx="11" cy="11" r="1.6" fill="currentColor" stroke="none" /></svg>
);
