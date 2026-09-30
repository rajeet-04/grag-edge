import { useEffect, useRef } from "react";
import { animate } from "animejs";
import { reducedMotion } from "../motion";
import { ChipIcon, FleetIcon } from "./Icons";
import { DrainMeter } from "./QueueMeter";

export type LinkState = "ONLINE" | "OFFLINE" | "UNKNOWN";

const CAPTION: Record<LinkState, string> = {
  ONLINE: "Fleet link is up. New memories sync as they are created; fleet knowledge is searchable here.",
  OFFLINE: "Fleet link is offline. GRAG is operating locally; new memories queue and sync when the link returns.",
  UNKNOWN: "Checking the fleet link…",
};

/** The console's signature: this robot, the wire to the fleet, and what travels on it.
 *  ONLINE  -> the wire is whole and packets travel end to end.
 *  OFFLINE -> the wire breaks; packets run to the break and stop (they are queued, not lost).
 *  Geometry and colour transition in CSS (interruptible, reduced-motion aware); the packet loop is anime.js. */
export default function LinkStrip({ link, pending, synced }: { link: LinkState; pending: number; synced: number }) {
  const wire = useRef<HTMLDivElement>(null);
  const packet = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const lane = wire.current, dot = packet.current;
    if (!lane || !dot || link === "UNKNOWN" || reducedMotion()) return;
    const width = () => lane.clientWidth - 8;
    const anim = link === "ONLINE"
      ? animate(dot, { translateX: [0, width], duration: 2400, ease: "inOutSine", loop: true, alternate: true })
      : animate(dot, { translateX: [0, () => width() * 0.4], opacity: [1, 1, 0], duration: 1700, ease: "outQuad", loop: true, loopDelay: 500 });
    return () => { anim.cancel(); dot.style.transform = ""; dot.style.opacity = ""; };
  }, [link]);

  return (
    <section className="linkstrip" data-link={link} aria-label="Fleet link status">
      <div className="ls-node ls-edge">
        <span className="ls-icon"><ChipIcon /></span>
        <span className="ls-label">This robot</span>
        <span className="ls-sub">local AI + memory</span>
      </div>
      <div className="ls-wire" ref={wire} aria-hidden="true">
        <span className="ls-half ls-l" />
        <span className="ls-half ls-r" />
        <span className="ls-break" />
        <span className="ls-packet" ref={packet} />
      </div>
      <div className="ls-node ls-fleet">
        <span className="ls-icon"><FleetIcon /></span>
        <span className="ls-label">Fleet</span>
        <span className="ls-sub">shared memory</span>
      </div>
      <p className="ls-caption">{CAPTION[link]}</p>
      <DrainMeter pending={pending} synced={synced} link={link} />
    </section>
  );
}
