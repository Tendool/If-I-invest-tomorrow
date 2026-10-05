const inrFmt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const inr2Fmt = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const inr = (x: number | null | undefined, decimals = 0) =>
  x == null || Number.isNaN(x) ? "-" : `${x < 0 ? "-" : ""}₹${(decimals ? inr2Fmt : inrFmt).format(Math.abs(x))}`;

export const inrSigned = (x: number) => `${x >= 0 ? "+" : "-"}₹${inrFmt.format(Math.abs(x))}`;

export const compactInr = (x: number) => {
  const a = Math.abs(x);
  const s = x < 0 ? "-" : "";
  if (a >= 1e7) return `${s}₹${(a / 1e7).toFixed(2)}Cr`;
  if (a >= 1e5) return `${s}₹${(a / 1e5).toFixed(2)}L`;
  if (a >= 1e3) return `${s}₹${(a / 1e3).toFixed(0)}K`;
  return `${s}₹${a.toFixed(0)}`;
};

/** x is a fraction (0.123 -> "12.3%") */
export const pct = (x: number | null | undefined, d = 1) =>
  x == null || Number.isNaN(x) ? "-" : `${(x * 100).toFixed(d)}%`;

export const pctSigned = (x: number | null | undefined, d = 1) =>
  x == null || Number.isNaN(x) ? "-" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(d)}%`;

export const num = (x: number | null | undefined, d = 2) =>
  x == null || Number.isNaN(x) ? "-" : x.toFixed(d);

export const toneOf = (x: number) => (x > 0 ? "text-positive" : x < 0 ? "text-negative" : "");
export const toneName = (x: number): "positive" | "negative" | null => (x > 0 ? "positive" : x < 0 ? "negative" : null);

export const CLASS_LABEL: Record<string, string> = {
  stock: "Stocks",
  etf: "Index ETFs",
  gold: "Gold",
  bond: "Bonds",
  cash: "Cash / Liquid",
};

export const CLASS_COLOR: Record<string, string> = {
  stock: "var(--chart-1)",
  etf: "var(--chart-3)",
  gold: "var(--chart-4)",
  bond: "var(--chart-7)",
  cash: "var(--faint)",
};

export const shortDate = (iso: string) => {
  const d = new Date(iso + "T00:00:00");
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
};

export const STRATEGY_COLOR: Record<string, string> = {
  "Max Return": "var(--chart-2)",
  "Min Risk": "var(--chart-1)",
  "Max Sharpe": "var(--chart-3)",
  "Goal-Based": "var(--chart-7)",
  "Crash-Resistant": "var(--chart-5)",
};

export const REGIME_COLORS = ["var(--chart-3)", "var(--chart-4)", "var(--chart-8)"];

/** "1 year", "3 years" */
export function years(n: number): string {
  return `${n} year${n === 1 ? "" : "s"}`;
}
