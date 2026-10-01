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
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

/** Unboxed section: a title row on a hairline rule, then content. */
export function Section({
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
    <section className={cn("min-w-0", className)}>
      {title || actions ? (
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3 border-b border-rule pb-2.5">
          <div className="min-w-0">
            {title ? <h2 className="text-[13px] font-semibold tracking-[-0.005em]">{title}</h2> : null}
            {description ? <p className="mt-0.5 text-[12.5px] text-muted-foreground">{description}</p> : null}
          </div>
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

/** Raised surface with an optional header. */
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
    <div className={cn("min-w-0 rounded-lg border border-border bg-surface", className)}>
      {title || actions ? (
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 pt-4 pb-3">
          <div className="min-w-0">
            {title ? <h3 className="text-[13px] font-semibold tracking-[-0.005em]">{title}</h3> : null}
            {description ? <p className="mt-0.5 text-[12.5px] leading-snug text-muted-foreground">{description}</p> : null}
          </div>
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
      <div className={cn("px-5 py-4", bodyClassName)}>{children}</div>
    </div>
  );
}

/** A row of key figures separated by vertical hairlines (wraps to a grid on small screens). */
export function Figures({ children, className, cols, open }: { children: React.ReactNode; className?: string; cols?: number; open?: boolean }) {
  const n = cols ?? React.Children.count(children);
  const lg = { 2: "lg:grid-cols-2", 3: "lg:grid-cols-3", 4: "lg:grid-cols-4", 5: "lg:grid-cols-5", 6: "lg:grid-cols-6" }[n] ?? "lg:grid-cols-6";
  return (
    <div className={cn("grid grid-cols-2 gap-y-5 py-4 sm:grid-cols-3", open ? "border-b border-rule pt-1" : "border-y border-rule", lg, className)}>
      {children}
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
    <div className={cn("min-w-0 border-rule pr-4 lg:border-l lg:px-4 lg:first:border-l-0 lg:first:pl-0", className)}>
      <div className="label truncate">{label}</div>
      <div
        className={cn(
          "num mt-1.5 truncate leading-none font-medium tracking-[-0.02em]",
          size === "lg" ? "text-[1.7rem]" : "text-[1.3rem]",
          tone === "positive" && "text-positive",
          tone === "negative" && "text-negative",
          tone === "caution" && "text-caution",
        )}
      >
        {value}
      </div>
      {sub ? <div className="mt-1.5 truncate text-[12px] text-muted-foreground">{sub}</div> : null}
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
    <div className="flex min-h-40 flex-col items-center justify-center rounded-lg border border-dashed border-rule px-6 py-10 text-center">
      {title ? <div className="text-[14px] font-medium">{title}</div> : null}
      {children ? <div className="mt-1 max-w-md text-[13px] text-muted-foreground">{children}</div> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function Loading({ label = "Loading", className }: { label?: string; className?: string }) {
  return (
    <div className={cn("flex min-h-48 items-center justify-center gap-3 text-[13px] text-muted-foreground", className)}>
      <span className="relative flex size-2">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-brand/60" />
        <span className="relative inline-flex size-2 rounded-full bg-brand" />
      </span>
      {label}
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
    <div role="radiogroup" className={cn("inline-flex rounded-md border border-rule bg-surface p-0.5", className)}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={cn(
            "flex-1 rounded-[5px] font-medium whitespace-nowrap transition-colors",
            size === "sm" ? "h-6 px-2 text-[12px]" : "h-7 px-3 text-[12.5px]",
            o.value === value ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Underline tab strip. */
export function TabStrip<T extends string>({ tabs, value, onChange, className }: { tabs: { value: T; label: string }[]; value: T; onChange: (v: T) => void; className?: string }) {
  return (
    <div className={cn("no-scrollbar flex gap-6 overflow-x-auto overflow-y-hidden border-b border-rule", className)}>
      {tabs.map((t) => (
        <button
          key={t.value}
          type="button"
          onClick={() => onChange(t.value)}
          className={cn(
            "relative -mb-px py-2.5 text-[13px] whitespace-nowrap transition-colors",
            t.value === value ? "font-medium text-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {t.label}
          {t.value === value ? <span className="absolute inset-x-0 bottom-0 h-[2px] bg-foreground" /> : null}
        </button>
      ))}
    </div>
  );
}
