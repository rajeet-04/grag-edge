import { animate } from "animejs";
import { useLayoutEffect, useRef, useState, type RefObject } from "react";

/** Motion policy for the console (Operate mode): motion explains state, never delays data.
 *  - Everything is opt-out via prefers-reduced-motion; without matchMedia (jsdom, old embeds) we also stay still.
 *  - Entrances move transform only (text keeps full contrast the whole time; nothing shifts layout).
 *  - Durations stay under ~450 ms; stagger is capped so a page never takes longer than that to settle. */
export const reducedMotion = (): boolean =>
  typeof window === "undefined" || typeof window.matchMedia !== "function" || window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export const EASE = "outExpo";
const STAGGER_MS = 38;
const STAGGER_CAP = 8;

/** Staged entrance for elements matching `selector` inside `ref`. Only elements not yet seen
 *  (tracked with data-in) animate, so live-updating lists never replay for rows that were already on screen. */
export function useEntrance(ref: RefObject<HTMLElement>, selector: string, key: unknown, from: { x?: number; y?: number } = { y: 10 }) {
  useLayoutEffect(() => {
    const root = ref.current;
    if (!root) return;
    const fresh = Array.from(root.querySelectorAll<HTMLElement>(`${selector}:not([data-in])`));
    fresh.forEach((el) => el.setAttribute("data-in", ""));
    if (reducedMotion() || fresh.length === 0) return;
    const targets = fresh.slice(0, 24);
    const anim = animate(targets, {
      translateY: [from.y ?? 0, 0],
      translateX: [from.x ?? 0, 0],
      duration: 380,
      ease: EASE,
      delay: (_el?: unknown, i = 0) => Math.min(i, STAGGER_CAP) * STAGGER_MS,
      onComplete: () => targets.forEach((el) => { el.style.transform = ""; }),
    });
    return () => { anim.cancel(); targets.forEach((el) => { el.style.transform = ""; }); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
}

/** Tween an integer toward its new value (old -> new, ~450 ms). The first value and non-numbers render immediately. */
export function useCountUp(value: number | string | null | undefined, duration = 450): string | number {
  const prev = useRef(value);
  const [shown, setShown] = useState<number | null>(null);
  useLayoutEffect(() => {
    const from = prev.current;
    prev.current = value;
    if (typeof from !== "number" || typeof value !== "number" || from === value || reducedMotion()) { setShown(null); return; }
    const box = { v: from };
    setShown(from);
    const anim = animate(box, {
      v: value, duration, ease: EASE,
      onUpdate: () => setShown(Math.round(box.v)),
      onComplete: () => setShown(null),
    });
    return () => { anim.cancel(); setShown(null); };
  }, [value, duration]);
  return shown ?? value ?? "—";
}

/** Brief border flash on an element when `value` changes (not on first render). */
export function useFlashOnChange(ref: RefObject<HTMLElement>, value: unknown) {
  const prev = useRef(value);
  useLayoutEffect(() => {
    const was = prev.current;
    prev.current = value;
    if (was === undefined || was === null || was === "—") return; // first real value is not a "change"
    if (reducedMotion() || !ref.current?.animate) return;
    ref.current.animate(
      [{ borderColor: "var(--accent)" }, { borderColor: "var(--line)" }],
      { duration: 1100, easing: "cubic-bezier(0.16, 1, 0.3, 1)" },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
}
