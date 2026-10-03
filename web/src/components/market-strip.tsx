"use client";

/**
 * Market tape with a 3D "barrel" scroll: a continuous marquee whose items sit on a cylinder, so those in the
 * middle face the viewer and those near the edges turn away and recede. Shows every index, macro series and
 * investable asset with its latest 1-day change; values that changed since the last poll flash.
 */
import * as React from "react";
import { useApp } from "@/lib/app-context";
import type { TapeItem } from "@/lib/types";
import { cn } from "@/lib/utils";

const SPEED = 46; // px per second
const STRENGTH = { rotate: 52, depth: 120, fade: 0.78 };

function fmtValue(it: TapeItem) {
  if (it.fmt === "usd") return `$${it.value.toFixed(2)}`;
  return it.value >= 1000
    ? it.value.toLocaleString("en-IN", { maximumFractionDigits: it.kind === "index" ? 2 : 0, minimumFractionDigits: it.kind === "index" ? 2 : 0 })
    : it.value.toFixed(2);
}

function Entry({ it, flash }: { it: TapeItem; flash?: boolean }) {
  const up = it.change > 0;
  const flat = it.change === 0;
  return (
    <span className={cn("tape-item", flash && "tape-flash")} data-tape-item>
      <span className="tape-label">{it.label}</span>
      <span className="num tape-value">{fmtValue(it)}</span>
      <span className={cn("num tape-change", flat ? "text-muted-foreground" : up ? "text-positive" : "text-negative")}>
        {flat ? "" : up ? "▲" : "▼"} {Math.abs(it.change * 100).toFixed(2)}%
      </span>
    </span>
  );
}

export function MarketStrip() {
  const { state } = useApp();
  const items = React.useMemo(() => state?.tape ?? [], [state?.tape]);
  const hostRef = React.useRef<HTMLDivElement>(null);
  const trackRef = React.useRef<HTMLDivElement>(null);
  const prev = React.useRef<Map<string, number>>(new Map());
  const [flashing, setFlashing] = React.useState<Set<string>>(new Set());

  // flash entries whose value changed since the previous poll
  React.useEffect(() => {
    const changed = new Set<string>();
    items.forEach((it) => {
      const old = prev.current.get(it.label);
      if (old !== undefined && old !== it.value) changed.add(it.label);
      prev.current.set(it.label, it.value);
    });
    if (changed.size) {
      setFlashing(changed);
      const t = setTimeout(() => setFlashing(new Set()), 2400);
      return () => clearTimeout(t);
    }
  }, [items]);

  // 3D barrel scroll
  React.useEffect(() => {
    const host = hostRef.current;
    const track = trackRef.current;
    if (!host || !track || !items.length) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let raf = 0;
    let last = performance.now();
    let offset = 0;
    let paused = false;
    let loopW = 0;
    let half = 0;
    let els: HTMLElement[] = [];
    let lefts: number[] = [];
    let widths: number[] = [];

    const measure = () => {
      els = Array.from(track.querySelectorAll<HTMLElement>("[data-tape-item]"));
      lefts = els.map((e) => e.offsetLeft);
      widths = els.map((e) => e.offsetWidth);
      loopW = track.scrollWidth / 2;
      half = host.clientWidth / 2;
    };

    const paint = () => {
      track.style.transform = `translate3d(${-offset}px,0,0)`;
      for (let i = 0; i < els.length; i++) {
        const cx = lefts[i] + widths[i] / 2 - offset - half;
        const t = Math.max(-1.35, Math.min(1.35, cx / half));
        const a = Math.abs(t);
        els[i].style.transform = `translateZ(${(-(a ** 1.6) * STRENGTH.depth).toFixed(1)}px) rotateY(${(-t * STRENGTH.rotate).toFixed(1)}deg)`;
        els[i].style.opacity = String(Math.max(0.06, 1 - a ** 1.4 * STRENGTH.fade));
      }
    };

    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      if (!paused && !reduced.matches && loopW > 0) {
        offset += SPEED * dt;
        if (offset >= loopW) offset -= loopW;
      }
      paint();
      raf = requestAnimationFrame(tick);
    };

    measure();
    const ro = new ResizeObserver(() => {
      measure();
      paint();
    });
    ro.observe(host);
    ro.observe(track);
    const enter = () => (paused = true);
    const leave = () => (paused = false);
    host.addEventListener("pointerenter", enter);
    host.addEventListener("pointerleave", leave);
    const vis = () => {
      cancelAnimationFrame(raf);
      if (!document.hidden) {
        last = performance.now();
        raf = requestAnimationFrame(tick);
      }
    };
    document.addEventListener("visibilitychange", vis);
    void document.fonts?.ready.then(() => {
      measure();
      paint();
    });
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      host.removeEventListener("pointerenter", enter);
      host.removeEventListener("pointerleave", leave);
      document.removeEventListener("visibilitychange", vis);
    };
  }, [items.length]);

  const row = (suffix: string) =>
    items.map((it) => <Entry key={it.label + suffix} it={it} flash={flashing.has(it.label)} />);

  return (
    <div className="tape" aria-label="Market tape">
      <div className="tape-stage" ref={hostRef}>
        {items.length ? (
          <div className="tape-track" ref={trackRef}>
            {row("a")}
            {row("b")}
          </div>
        ) : (
          <span className="px-4 text-[12px] text-faint">Connecting to market data…</span>
        )}
      </div>
    </div>
  );
}
