import * as React from "react";
import { cn } from "@/lib/utils";

/** Page title block: small eyebrow, serif title, one-line description, actions on the right. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-wrap items-end justify-between gap-x-8 gap-y-4 pb-6", className)}>
      <div className="min-w-0 max-w-2xl">
        {eyebrow ? <div className="label mb-2">{eyebrow}</div> : null}
        <h1 className="display text-[2.15rem] leading-[1.05] text-foreground sm:text-[2.6rem]">{title}</h1>
        {description ? <p className="mt-2.5 text-[14px] leading-relaxed text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="page-actions flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

/** A card: title row, then content. `plain` drops the card (for sections nested inside another card). */
export function Section({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
  plain,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  plain?: boolean;
}) {
  return (
    <section className={cn("min-w-0", !plain && "card-x p-5 sm:p-6", className)}>
      {title || actions ? (
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {title ? <h2 className="text-[14.5px] font-semibold tracking-[-0.01em]">{title}</h2> : null}
            {description ? <p className="mt-1 text-[12.5px] leading-snug text-muted-foreground">{description}</p> : null}
          </div>
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

/** Raised surface with an optional header (same card as Section, with a divided header). */
export function Panel({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <div className={cn("card-x min-w-0", className)}>
      {title || actions ? (
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 pt-4 pb-3">
          <div className="min-w-0">
            {title ? <h3 className="text-[13.5px] font-semibold tracking-[-0.005em]">{title}</h3> : null}
            {description ? <p className="mt-0.5 text-[12.5px] leading-snug text-muted-foreground">{description}</p> : null}
          </div>
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
      <div className={cn("px-5 py-4", bodyClassName)}>{children}</div>
    </div>
  );
}

/** Key figures as a group of tiles divided by hairlines (2 / 3 / n columns as the screen grows). */
export function Figures({ children, className, cols, open }: { children: React.ReactNode; className?: string; cols?: number; open?: boolean }) {
  const n = cols ?? React.Children.count(children);
  const lg = { 2: "lg:grid-cols-2", 3: "lg:grid-cols-3", 4: "lg:grid-cols-4", 5: "lg:grid-cols-5", 6: "lg:grid-cols-3 2xl:grid-cols-6" }[n] ?? "lg:grid-cols-3 2xl:grid-cols-6";
  return (
    // `open`: the group sits inside another card, so it is an inset outline rather than a second raised card
    <div className={cn(open ? "overflow-hidden rounded-xl border border-border" : "card-x overflow-hidden", className)}>
      {/* tiles draw their right/bottom hairlines; the negative margin tucks the outermost ones under the card edge */}
      <div className={cn("-mr-px -mb-px grid grid-cols-2 sm:grid-cols-3", lg)}>{children}</div>
    </div>
  );
}

export function Figure({
  label,
  value,
  sub,
  tone,
  size = "md",
  className,
}: {
  label: React.ReactNode;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "positive" | "negative" | "caution" | null;
  size?: "md" | "lg";
  className?: string;
}) {
  return (
    <div className={cn("min-w-0 border-r border-b border-border px-4 py-4 sm:px-5", className)}>
      <div className="label truncate">{label}</div>
      <div
        className={cn(
          "num mt-2 truncate leading-none font-medium tracking-[-0.02em]",
          size === "lg" ? "text-[1.75rem]" : "text-[1.35rem]",
          tone === "positive" && "text-positive",
          tone === "negative" && "text-negative",
          tone === "caution" && "text-caution",
        )}
      >
        {value}
      </div>
      {sub ? <div className="mt-2 truncate text-[12px] text-muted-foreground">{sub}</div> : null}
    </div>
  );
}

/** Signed change with a small triangle; colour carries meaning, the glyph keeps it readable without colour. */
export function Delta({ value, children, className }: { value: number; children: React.ReactNode; className?: string }) {
  const up = value > 0;
  const flat = value === 0;
  return (
    <span className={cn("num inline-flex items-center gap-1", flat ? "text-muted-foreground" : up ? "text-positive" : "text-negative", className)}>
      {flat ? null : <span aria-hidden className="text-[0.7em]">{up ? "▲" : "▼"}</span>}
      {children}
    </span>
  );
}

/** Thin horizontal proportion bar. */
export function Meter({ value, max = 1, color, className }: { value: number; max?: number; color?: string; className?: string }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className={cn("h-1 w-full overflow-hidden rounded-full bg-foreground/[0.07]", className)}>
      <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color ?? "var(--muted-foreground)" }} />
    </div>
  );
}

export function Swatch({ color, className }: { color: string; className?: string }) {
  return <span aria-hidden className={cn("inline-block size-2 shrink-0 rounded-[2px]", className)} style={{ background: color }} />;
}

export function Empty({ title, children, action }: { title?: React.ReactNode; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex min-h-40 flex-col items-center justify-center rounded-2xl border border-dashed border-rule bg-card/50 px-6 py-10 text-center">
      {title ? <div className="text-[14px] font-medium">{title}</div> : null}
      {children ? <div className="mt-1 max-w-md text-[13px] text-muted-foreground">{children}</div> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

/** The brand mark in motion: history runs up to "tomorrow", then simulated futures fan out one by one. */
const FAN = ["M30 35 Q41 30 54 12", "M30 35 Q41 31 54 18", "M30 35 Q41 33 54 31", "M30 35 Q41 35 54 39", "M30 35 Q41 37 54 47"];

export function FanLoader({ className }: { className?: string }) {
  return (
    <svg viewBox="4 6 56 46" aria-hidden className={cn("fan-loader", className)}>
      <path className="fan-cone" d="M30 35 Q41 30 54 12 L54 47 Q41 37 30 35Z" />
      {FAN.map((d, i) => (
        <path key={d} d={d} pathLength={1} className="fan-path" style={{ animationDelay: `${i * 0.16}s` }} />
      ))}
      <path d="M30 35 Q41 32 54 25" pathLength={1} className="fan-path fan-median" style={{ animationDelay: "0.4s" }} />
      <path d="M9 44 L16 37 L21 40 L30 35" className="fan-history" />
      <circle cx="30" cy="35" r="3.6" className="fan-dot" />
    </svg>
  );
}

export function Loading({ label = "Loading", className }: { label?: string; className?: string }) {
  return (
    <div role="status" className={cn("flex min-h-48 flex-col items-center justify-center gap-3 text-[13px] text-muted-foreground", className)}>
      <FanLoader className="h-11 w-auto" />
      <span className="loading-label">{label}</span>
    </div>
  );
}

/** Small key/value line used in side rails. */
export function KV({ k, v, className }: { k: React.ReactNode; v: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-baseline justify-between gap-4 py-1.5 text-[13px]", className)}>
      <span className="text-muted-foreground">{k}</span>
      <span className="num text-right font-medium">{v}</span>
    </div>
  );
}

/** Compact segmented control (single choice). */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  className,
  size = "md",
}: {
  options: { value: T; label: React.ReactNode }[];
  value: T;
  onChange: (v: T) => void;
  className?: string;
  size?: "sm" | "md";
}) {
  return (
    <div role="radiogroup" className={cn("inline-flex rounded-xl border border-border bg-muted/70 p-1", className)}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={cn(
            "flex-1 rounded-lg font-medium whitespace-nowrap transition-all",
            size === "sm" ? "h-6 px-2 text-[12px]" : "h-8 px-3 text-[12.5px]",
            o.value === value ? "bg-foreground text-background shadow-sm" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Pill tabs on a soft track. */
export function TabStrip<T extends string>({ tabs, value, onChange, className }: { tabs: { value: T; label: string }[]; value: T; onChange: (v: T) => void; className?: string }) {
  return (
    <div className={cn("no-scrollbar flex max-w-full overflow-x-auto", className)}>
      <div role="tablist" className="inline-flex gap-1 rounded-xl border border-border bg-muted/70 p-1">
        {tabs.map((t) => (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={t.value === value}
            onClick={() => onChange(t.value)}
            className={cn(
              "h-8 rounded-lg px-3.5 text-[13px] whitespace-nowrap transition-all",
              t.value === value ? "bg-card font-medium text-foreground shadow-[0_1px_2px_rgba(0,0,0,0.08),0_0_0_1px_var(--border)]" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
    </div>
  );
}
