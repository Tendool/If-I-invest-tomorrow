"use client";

/**
 * Market tape: a flat, continuous ticker (CSS animation over two copies of the row) with every index, macro
 * series and investable asset and its latest 1-day change. Pauses on hover; values that changed since the
 * last poll flash.
 */
import * as React from "react";
import { useApp } from "@/lib/app-context";
import type { TapeItem } from "@/lib/types";
import { cn } from "@/lib/utils";

const SPEED = 46; // px per second

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

  // constant speed whatever the number of items: the loop length (one copy of the row) sets the duration
  React.useEffect(() => {
    const track = trackRef.current;
    if (!track || !items.length) return;
    const set = () => track.style.setProperty("--tape-duration", `${(track.scrollWidth / 2 / SPEED).toFixed(1)}s`);
    set();
    const ro = new ResizeObserver(set);
    ro.observe(track);
    return () => ro.disconnect();
  }, [items.length]);

  const row = (suffix: string) =>
    items.map((it) => <Entry key={it.label + suffix} it={it} flash={flashing.has(it.label)} />);

  return (
    <div className="tape" aria-label="Market tape">
      <div className="tape-stage">
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
