"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { CLASS_COLOR, CLASS_LABEL, inr, pct } from "@/lib/format";
import { Swatch } from "@/components/kit";

/**
 * Horizontal outcome range: 5th–95th percentile band, median tick, invested and target markers.
 * A compact, honest way to show "what could happen" without a chart frame.
 */
export function OutcomeRange({
  low,
  median,
  high,
  invested,
  target,
  min,
  max,
  className,
}: {
  low: number;
  median: number;
  high: number;
  invested: number;
  target?: number | null;
  min?: number;
  max?: number;
  className?: string;
}) {
  const lo = Math.min(min ?? low, invested, low) * 0.97;
  const hi = Math.max(max ?? high, target ?? 0, high) * 1.02;
  const x = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;
  return (
    <div className={cn("pt-2", className)}>
      <div className="relative h-7">
        <div className="absolute inset-x-0 top-1/2 h-px bg-rule" />
        <div className="absolute top-1/2 h-2 -translate-y-1/2 rounded-full bg-chart-1/25" style={{ left: x(low), width: `calc(${x(high)} - ${x(low)})` }} />
        <div className="absolute top-0 bottom-0 border-l border-dashed border-muted-foreground" style={{ left: x(invested) }} />
        {target ? <div className="absolute top-0 bottom-0 w-[1.5px] -translate-x-1/2 bg-brand" style={{ left: x(target) }} /> : null}
        <div className="absolute top-1/2 h-4 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground" style={{ left: x(median) }} />
      </div>
      <div className="relative mt-2 h-9 text-[11.5px]">
        <Edge at={x(low)} label="Worst 5%" value={inr(low)} align="left" />
        <Edge at={x(median)} label="Median" value={inr(median)} align="center" strong />
        <Edge at={x(high)} label="Best 5%" value={inr(high)} align="right" />
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="h-3 border-l border-dashed border-muted-foreground" /> Invested <span className="num text-foreground">{inr(invested)}</span>
        </span>
        {target ? (
          <span className="flex items-center gap-1.5">
            <span className="h-3 w-[1.5px] bg-brand" /> Target <span className="num text-foreground">{inr(target)}</span>
          </span>
        ) : null}
      </div>
    </div>
  );
}

function Edge({ at, label, value, align, strong }: { at: string; label: string; value: string; align: "left" | "center" | "right"; strong?: boolean }) {
  const tr = align === "left" ? "translate-x-0" : align === "right" ? "-translate-x-full" : "-translate-x-1/2";
  return (
    <div className={cn("absolute whitespace-nowrap", tr, align === "right" && "text-right", align === "center" && "text-center")} style={{ left: at }}>
      <div className="text-faint">{label}</div>
      <div className={cn("num", strong ? "font-semibold text-foreground" : "text-muted-foreground")}>{value}</div>
    </div>
  );
}

/** Stacked 100% bar by asset class with a legend. */
export function Composition({ rows, className }: { rows: { asset_class: string; weight: number }[]; className?: string }) {
  const parts = React.useMemo(() => {
    const acc: Record<string, number> = {};
    rows.forEach((r) => (acc[r.asset_class] = (acc[r.asset_class] ?? 0) + r.weight));
    const order = ["stock", "etf", "gold", "bond", "cash"];
    return order.filter((k) => acc[k] > 0).map((k) => ({ k, w: acc[k] }));
  }, [rows]);
  const total = parts.reduce((s, p) => s + p.w, 0) || 1;
  return (
    <div className={className}>
      <div className="flex h-2.5 w-full overflow-hidden rounded-full">
        {parts.map((p, i) => (
          <div
            key={p.k}
            className={cn(i > 0 && "border-l-2 border-surface")}
            style={{ width: `${(p.w / total) * 100}%`, background: CLASS_COLOR[p.k] }}
            title={`${CLASS_LABEL[p.k]} ${pct(p.w)}`}
          />
        ))}
      </div>
      <div className="mt-3 space-y-1.5">
        {parts.map((p) => (
          <div key={p.k} className="flex items-center gap-2 text-[13px]">
            <Swatch color={CLASS_COLOR[p.k]} />
            <span className="text-muted-foreground">{CLASS_LABEL[p.k]}</span>
            <span className="num ml-auto font-medium">{pct(p.w / total, 1)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Bar centred on zero: negatives grow left, positives right. */
export function DivergingBar({ value, max, breach }: { value: number; max: number; breach?: boolean }) {
  const w = Math.min(50, (Math.abs(value) / (max || 1)) * 50);
  return (
    <div className="relative h-3 w-full">
      <div className="absolute top-0 bottom-0 left-1/2 w-px bg-rule" />
      <div
        className={cn("absolute top-0.5 bottom-0.5 rounded-[2px]", value >= 0 ? "bg-positive/70" : breach ? "bg-negative" : "bg-negative/45")}
        style={value >= 0 ? { left: "50%", width: `${w}%` } : { right: "50%", width: `${w}%` }}
      />
    </div>
  );
}

/** p5–p95 range with a median tick on a shared scale (used to compare options in a table). */
export function RangeBar({ low, median, high, min, max, marker }: { low: number; median: number; high: number; min: number; max: number; marker?: number }) {
  const x = (v: number) => `${((v - min) / (max - min || 1)) * 100}%`;
  return (
    <div className="relative h-4 w-full min-w-40">
      <div className="absolute inset-x-0 top-1/2 h-px bg-border" />
      {marker != null ? <div className="absolute top-0 bottom-0 border-l border-dashed border-faint" style={{ left: x(marker) }} /> : null}
      <div className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-foreground/20" style={{ left: x(low), width: `calc(${x(high)} - ${x(low)})` }} />
      <div className="absolute top-1/2 h-3 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground" style={{ left: x(median) }} />
    </div>
  );
}

/** Coloured class/sector tag with a swatch. */
export function ClassTag({ cls }: { cls: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground">
      <Swatch color={CLASS_COLOR[cls] ?? "var(--faint)"} />
      {CLASS_LABEL[cls] ?? cls}
    </span>
  );
}

export function LimitNote({ ok, breaches, risk }: { ok: boolean; breaches: string[]; risk: string }) {
  return ok ? (
    <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
      <span className="size-1.5 rounded-full bg-positive" /> Within your {risk}-risk limits for volatility, stress loss and one-year VaR.
    </p>
  ) : (
    <p className="flex items-start gap-2 text-[13px] text-negative">
      <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-negative" /> Outside your {risk}-risk limits: {breaches.join("; ")}.
    </p>
  );
}
