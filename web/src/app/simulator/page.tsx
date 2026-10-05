"use client";

import * as React from "react";
import { Plus, Search, X } from "lucide-react";
import { Slider } from "@/components/ui/slider";
import { Empty, Loading, PageHeader, Section, Swatch } from "@/components/kit";
import { BreakdownTable, EndDistribution, ProjectionChart, ProjectionTable, SimFigures } from "@/components/finance/sim-views";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { CLASS_COLOR, CLASS_LABEL, inr, pct } from "@/lib/format";
import type { AssetRow, SimHolding, SimPreset, SimResult } from "@/lib/types";
import { useData } from "@/lib/use-data";
import { cn } from "@/lib/utils";

interface Row {
  asset: string; // ticker
  weight: number; // relative weight, shown as a share of the total
}

const YEARS = [1, 3, 5, 7, 10];

function Field({ label, hint, children }: { label: string; hint?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="space-y-2 border-b border-border pb-5">
      <div className="flex items-baseline justify-between">
        <span className="label">{label}</span>
        {hint ? <span className="text-[12.5px]">{hint}</span> : null}
      </div>
      {children}
    </div>
  );
}

function MoneyInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const n = Number(value) || 0;
  return (
    <div className="flex items-center rounded-xl border border-border bg-background/70 focus-within:ring-3 focus-within:ring-brand/15 focus-within:border-foreground/40">
      <span className="pl-3 text-[15px] text-faint">₹</span>
      <input
        inputMode="numeric"
        placeholder={placeholder}
        value={n ? n.toLocaleString("en-IN") : ""}
        onChange={(e) => onChange(e.target.value.replace(/[^\d]/g, ""))}
        className="num h-10 w-full bg-transparent px-2 text-[15px] font-medium outline-none placeholder:text-faint"
      />
    </div>
  );
}

function AssetPicker({ assets, taken, onAdd }: { assets: AssetRow[]; taken: Set<string>; onAdd: (ticker: string) => void }) {
  const [q, setQ] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const hits = assets
    .filter((a) => !taken.has(a.ticker) && (q === "" || (a.ticker + a.name + a.sector + CLASS_LABEL[a.asset_class]).toLowerCase().includes(q.toLowerCase())))
    .slice(0, q ? 9 : 7);
  return (
    <div ref={ref} className="relative">
      <div className="flex items-center rounded-xl border border-border bg-background/70 focus-within:ring-3 focus-within:ring-brand/15 px-2.5 focus-within:border-foreground/40">
        <Search className="size-3.5 text-faint" />
        <input
          value={q}
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          placeholder="Add a stock, ETF, gold, bonds…"
          className="h-9 w-full bg-transparent px-2 text-[13px] outline-none placeholder:text-faint"
        />
      </div>
      {open ? (
        <div className="absolute inset-x-0 top-[calc(100%+4px)] z-30 max-h-72 overflow-auto rounded-md border border-border bg-popover py-1 shadow-lg">
          {hits.length ? (
            hits.map((a) => (
              <button
                key={a.symbol}
                type="button"
                onClick={() => {
                  onAdd(a.ticker);
                  setQ("");
                  setOpen(false);
                }}
                className="flex w-full items-center gap-2.5 px-3 py-1.5 text-left hover:bg-foreground/[0.05]"
              >
                <Swatch color={CLASS_COLOR[a.asset_class]} />
                <span className="w-24 shrink-0 text-[13px] font-medium">{a.ticker}</span>
                <span className="min-w-0 flex-1 truncate text-[12px] text-muted-foreground">{a.name}</span>
                <span className="num text-[12px] text-muted-foreground">{pct(a.expected_return, 1)}</span>
              </button>
            ))
          ) : (
            <div className="px-3 py-2 text-[12.5px] text-muted-foreground">No matching asset.</div>
          )}
        </div>
      ) : null}
    </div>
  );
}

export default function SimulatorPage() {
  const { run } = useApp();
  const assets = useData(() => api.assets(), []);
  const presets = useData(() => api.simPresets(), []);
  const [amount, setAmount] = React.useState("100000");
  const [monthly, setMonthly] = React.useState("0");
  const [years, setYears] = React.useState(5);
  const [rows, setRows] = React.useState<Row[]>([
    { asset: "NIFTYBEES", weight: 60 },
    { asset: "GOLDBEES", weight: 25 },
    { asset: "LTGILTBEES", weight: 15 },
  ]);
  const [presetId, setPresetId] = React.useState<string>("");
  const [sim, setSim] = React.useState<SimResult | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const seq = React.useRef(0);

  const total = rows.reduce((s, r) => s + (r.weight || 0), 0);
  const byTicker = React.useMemo(() => new Map((assets.data ?? []).map((a) => [a.ticker, a])), [assets.data]);

  // live re-run (debounced) whenever an input changes
  const key = JSON.stringify([amount, monthly, years, rows]);
  React.useEffect(() => {
    const amt = Number(amount) || 0;
    const mon = Number(monthly) || 0;
    const holdings: SimHolding[] = rows.filter((r) => r.weight > 0).map((r) => ({ asset: r.asset, weight: r.weight }));
    if ((amt <= 0 && mon <= 0) || !holdings.length) return;
    const id = ++seq.current;
    const t = setTimeout(async () => {
      setBusy(true);
      const out = await run(() => api.simulate({ amount: amt, monthly: mon, years, holdings }));
      if (id !== seq.current) return; // a newer request superseded this one
      setBusy(false);
      if (out) {
        setSim(out);
        setError(null);
      } else {
        setError("The simulation could not run. Check the amount and the chosen assets.");
      }
    }, 450);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  function applyPreset(p: SimPreset) {
    setPresetId(p.id);
    setRows(p.holdings.map((h) => ({ asset: h.ticker, weight: h.weight })));
  }
  const setWeight = (i: number, w: number) => {
    setPresetId("");
    setRows((r) => r.map((x, k) => (k === i ? { ...x, weight: Math.max(0, Math.min(100, w)) } : x)));
  };
  const equalise = () => setRows((r) => r.map((x) => ({ ...x, weight: Math.round((100 / r.length) * 10) / 10 })));
  const add = (ticker: string) => {
    setPresetId("");
    setRows((r) => [...r, { asset: ticker, weight: r.length ? Math.round((100 / (r.length + 1)) * 10) / 10 : 100 }]);
  };

  const yearsLabel = years === 1 ? "1 year" : `${years} years`;

  return (
    <div>
      <PageHeader
        eyebrow="Simulator"
        title="What could it become?"
        description="Put in an amount, choose where it goes, and see the range of outcomes year by year: simulated ten thousand ways, with fat tails and market regimes."
      />

      <div className="grid gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <div className="card-x space-y-5 p-5">
            <Field label="Invest now">
              <MoneyInput value={amount} onChange={setAmount} />
              <div className="flex gap-3 text-[12px]">
                {[25000, 100000, 500000, 1000000].map((v) => (
                  <button key={v} type="button" onClick={() => setAmount(String(v))} className={cn("hover:text-foreground", Number(amount) === v ? "font-medium text-foreground" : "text-muted-foreground")}>
                    {v >= 100000 ? `${v / 100000}L` : `${v / 1000}K`}
                  </button>
                ))}
              </div>
            </Field>
            <Field label="Add every month" hint={<span className="text-faint">optional SIP</span>}>
              <MoneyInput value={monthly === "0" ? "" : monthly} onChange={(v) => setMonthly(v || "0")} placeholder="0" />
              <div className="flex gap-3 text-[12px]">
                {[0, 2000, 5000, 10000, 25000].map((v) => (
                  <button key={v} type="button" onClick={() => setMonthly(String(v))} className={cn("hover:text-foreground", Number(monthly) === v ? "font-medium text-foreground" : "text-muted-foreground")}>
                    {v === 0 ? "None" : `${v / 1000}K`}
                  </button>
                ))}
              </div>
            </Field>
            <Field label="For how long" hint={<span className="num font-medium">{yearsLabel}</span>}>
              <Slider min={1} max={10} step={1} value={[years]} onValueChange={(v) => setYears(Array.isArray(v) ? v[0] : (v as number))} />
              <div className="flex justify-between text-[11px] text-faint">
                {YEARS.map((y) => (
                  <button key={y} type="button" onClick={() => setYears(y)} className="hover:text-foreground">
                    {y}y
                  </button>
                ))}
              </div>
            </Field>

            <div className="space-y-3">
              <div className="flex items-baseline justify-between">
                <span className="label">Where to invest</span>
                {rows.length > 1 ? (
                  <button type="button" onClick={equalise} className="text-[12px] text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
                    Equal weights
                  </button>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {(presets.data ?? []).map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    title={p.description}
                    onClick={() => applyPreset(p)}
                    className={cn(
                      "rounded-[4px] border px-2 py-0.5 text-[12px] transition-colors",
                      presetId === p.id ? "border-foreground bg-foreground text-background" : "border-rule text-muted-foreground hover:border-foreground/40 hover:text-foreground",
                    )}
                  >
                    {p.label.replace(/ \(.*\)/, "")}
                  </button>
                ))}
              </div>

              <div className="divide-y divide-border rounded-md border border-border bg-surface">
                {rows.length === 0 ? <div className="px-3 py-4 text-[12.5px] text-muted-foreground">Pick a preset or add an asset below.</div> : null}
                {rows.map((r, i) => {
                  const a = byTicker.get(r.asset);
                  const share = total > 0 ? (r.weight / total) * 100 : 0;
                  return (
                    <div key={r.asset} className="flex items-center gap-2.5 px-3 py-2">
                      <Swatch color={a ? CLASS_COLOR[a.asset_class] : "var(--faint)"} />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[13px] font-medium">{r.asset}</div>
                        <div className="truncate text-[11.5px] text-muted-foreground">
                          {a ? `${a.name} · exp. ${pct(a.expected_return, 1)}` : ""}
                        </div>
                      </div>
                      <div className="flex items-center rounded-lg border border-border bg-background/70 focus-within:border-foreground/40">
                        <input
                          inputMode="decimal"
                          value={r.weight}
                          onChange={(e) => setWeight(i, Number(e.target.value.replace(/[^\d.]/g, "")) || 0)}
                          aria-label={`${r.asset} weight`}
                          className="num h-7 w-12 bg-transparent px-1.5 text-right text-[13px] outline-none"
                        />
                        <span className="pr-1.5 text-[12px] text-faint">%</span>
                      </div>
                      <span className="num w-11 text-right text-[11.5px] text-muted-foreground" title="Share of the total">
                        {total > 0 && Math.abs(total - 100) > 0.05 ? `${share.toFixed(0)}%` : ""}
                      </span>
                      <button type="button" aria-label={`Remove ${r.asset}`} onClick={() => { setPresetId(""); setRows((x) => x.filter((_, k) => k !== i)); }} className="text-faint hover:text-negative">
                        <X className="size-3.5" />
                      </button>
                    </div>
                  );
                })}
              </div>
              <div className="flex items-center justify-between text-[12px]">
                <span className={cn(Math.abs(total - 100) < 0.05 ? "text-positive" : "text-muted-foreground")}>
                  {Math.abs(total - 100) < 0.05 ? "Weights add up to 100%" : `Weights total ${total.toFixed(0)}% — scaled to 100%`}
                </span>
                <span className="flex items-center gap-1 text-faint">
                  <Plus className="size-3" /> add
                </span>
              </div>
              <AssetPicker assets={assets.data ?? []} taken={new Set(rows.map((r) => r.asset))} onAdd={add} />
            </div>
          </div>
        </aside>

        <div className="min-w-0 space-y-6">
          {!sim ? (
            error ? (
              <Empty title="Could not simulate">{error}</Empty>
            ) : (
              <Loading label="Simulating thousands of futures" className="min-h-96" />
            )
          ) : (
            <div className={cn("space-y-6 transition-opacity", busy && "opacity-60")}>
              <SimFigures sim={sim} />
              <Section
                title={`Projection over ${yearsLabel}`}
                description={`${inr(sim.inputs.amount)} now${sim.inputs.monthly ? ` and ${inr(sim.inputs.monthly)} every month` : ""} in ${sim.breakdown.length} asset${sim.breakdown.length > 1 ? "s" : ""}. Expected return ${pct(sim.portfolio.expected_return)} a year, volatility ${pct(sim.portfolio.volatility)}.`}
              >
                <ProjectionChart sim={sim} />
              </Section>
              <ProjectionTable sim={sim} />
              <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
                <BreakdownTable sim={sim} />
                <Section title="Spread of final outcomes" description={`After ${yearsLabel}. Green beats a fixed deposit; grey gains less; red is a loss.`}>
                  <EndDistribution sim={sim} />
                </Section>
              </div>
              <p className="max-w-3xl text-[12px] leading-relaxed text-faint">
                Projections are model-based simulations using each asset&apos;s CAPM and history-based expected return (with a small ML tilt), the last five years of volatility
                and correlation, and today&apos;s market regime. They are not forecasts or guarantees, and ignore taxes and fund expenses beyond the 0.1% trading cost already
                reflected in prices. Demo purposes only.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
