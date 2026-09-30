/** Placeholder with the final element's footprint, so data arriving causes no layout shift. Hidden from assistive tech. */
export default function Skeleton({ h = 16, w = "100%", className = "" }: { h?: number | string; w?: number | string; className?: string }) {
  return <span className={`skel ${className}`} aria-hidden="true" style={{ height: h, width: w }} />;
}

export function SkeletonCards({ count = 3, h = 88 }: { count?: number; h?: number }) {
  return (
    <div aria-hidden="true">
      {Array.from({ length: count }, (_, i) => <div key={i} className="card skel-card" style={{ minHeight: h }}><span className="skel" style={{ height: 12, width: "38%" }} /><span className="skel" style={{ height: 12, width: `${86 - i * 14}%`, marginTop: 10 }} /></div>)}
    </div>
  );
}
