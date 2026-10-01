"use client";

import * as React from "react";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { ArrowDown, ArrowUp, Search } from "lucide-react";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Delta, Figure, Figures, Meter, Section, Swatch } from "@/components/kit";
import { cn } from "@/lib/utils";
import { CLASS_LABEL, inr, num, pct, pctSigned, REGIME_COLORS, shortDate, toneName, toneOf } from "@/lib/format";
import type { AssetDetail, AssetRow, MarketData, MarketOverview, ModelsData } from "@/lib/types";
import { ClassTag } from "./shared";

export function MarketOverviewCards({ o, open }: { o: MarketOverview; open?: boolean }) {
  const probs = Object.entries(o.regime_probabilities);
  return (
    <div className="space-y-4">
      <Figures cols={6} open={open}>
        <Figure label="NIFTY 50" value={o.nifty_close.toLocaleString("en-IN", { maximumFractionDigits: 0 })} sub={<Delta value={o.nifty_1d}>{pctSigned(o.nifty_1d, 2)} today</Delta>} />
        <Figure label="One month" value={pctSigned(o.nifty_1m)} tone={toneName(o.nifty_1m)} />
        <Figure label="One year" value={pctSigned(o.nifty_1y)} tone={toneName(o.nifty_1y)} />
        <Figure label="Off the high" value={pct(o.nifty_drawdown_from_peak)} tone={o.nifty_drawdown_from_peak < -0.1 ? "negative" : null} />
        <Figure label="India VIX" value={o.india_vix.toFixed(1)} sub={`1-month vol ${pct(o.nifty_vol_1m, 0)}`} />
        <Figure label="Regime" value={<span className="text-[1.05rem]">{o.regime}</span>} sub={`${pct(Math.max(...probs.map(([, p]) => p)), 0)} confidence`} />
      </Figures>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5 text-[12.5px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className={cn("size-1.5 rounded-full", o.anomaly_today ? "bg-negative" : "bg-positive")} />
          {o.anomaly_today ? "Unusual market conditions today" : "No market-wide anomaly today"}
        </span>
        {o.unusual_stock_moves.length ? (
          <span>
            Unusual moves:{" "}
            {o.unusual_stock_moves.map((m, i) => (
              <span key={m.symbol}>
                {i ? ", " : ""}
                <span className="font-medium text-foreground">{m.symbol}</span> <span className={toneOf(m.ret)}>{pctSigned(m.ret, 1)}</span>
              </span>
            ))}
          </span>
        ) : null}
        <span className="ml-auto text-faint">Close of {shortDate(o.as_of)}</span>
      </div>
    </div>
  );
}

export function RegimeChart({ data }: { data: MarketData }) {
  const names = data.regime_names;
  const rows = data.timeline.map((t) => ({
    date: t.date,
    r0: t.regime === 0 ? t.nifty : null,
    r1: t.regime === 1 ? t.nifty : null,
    r2: t.regime === 2 ? t.nifty : null,
  }));
  const cfg: ChartConfig = {
    r0: { label: names[0], color: REGIME_COLORS[0] },
    r1: { label: names[1], color: REGIME_COLORS[1] },
    r2: { label: names[2], color: REGIME_COLORS[2] },
  };
  return (
    <>
      <ChartContainer config={cfg} className="h-[320px] w-full">
        <LineChart data={rows} margin={{ left: 0, right: 8, top: 8 }}>
          <CartesianGrid vertical={false} strokeDasharray="2 4" />
          <XAxis dataKey="date" tickLine={false} axisLine={false} minTickGap={60} tickMargin={8} tickFormatter={(v) => String(v).slice(0, 4)} />
          <YAxis scale="log" domain={["auto", "auto"]} width={50} tickLine={false} axisLine={false} tickFormatter={(v) => Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })} />
          <ChartTooltip content={<ChartTooltipContent labelFormatter={(v) => shortDate(String(v))} formatter={(v, n) => (
            <div className="flex w-full items-center justify-between gap-4">
              <span className="flex items-center gap-1.5 text-muted-foreground"><Swatch color={cfg[String(n)]?.color as string} />{cfg[String(n)]?.label}</span>
              <span className="num font-medium">{Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</span>
            </div>
          )} />} />
          {["r0", "r1", "r2"].map((k) => (
            <Line key={k} dataKey={k} stroke="none" dot={{ r: 1.6, fill: `var(--color-${k})`, strokeWidth: 0 }} activeDot={{ r: 3.5 }} isAnimationActive={false} connectNulls={false} />
          ))}
        </LineChart>
      </ChartContainer>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-muted-foreground">
        {names.map((n, i) => (
          <span key={n} className="flex items-center gap-1.5">
            <Swatch color={REGIME_COLORS[i]} /> {n}
          </span>
        ))}
      </div>
    </>
  );
}

export function AnomalyChart({ data }: { data: MarketData }) {
  const rows = data.anomalies.map((a) => ({ date: a.date, score: a.score, flagged: a.flagged ? a.score : null }));
  const cfg: ChartConfig = { score: { label: "Anomaly score", color: "var(--muted-foreground)" }, flagged: { label: "Flagged", color: "var(--negative)" } };
  return (
    <ChartContainer config={cfg} className="h-[240px] w-full">
      <LineChart data={rows} margin={{ left: 0, right: 8, top: 8 }}>
        <CartesianGrid vertical={false} strokeDasharray="2 4" />
        <XAxis dataKey="date" tickLine={false} axisLine={false} minTickGap={60} tickMargin={8} tickFormatter={(v) => String(v).slice(0, 4)} />
        <YAxis width={40} tickLine={false} axisLine={false} domain={["auto", "auto"]} tickFormatter={(v) => Number(v).toFixed(2)} />
        <ChartTooltip content={<ChartTooltipContent labelFormatter={(v) => shortDate(String(v))} formatter={(v) => Number(v).toFixed(3)} />} />
        <Line dataKey="score" stroke="var(--color-score)" strokeWidth={1} dot={false} isAnimationActive={false} />
        <Line dataKey="flagged" stroke="none" dot={{ r: 2.5, fill: "var(--color-flagged)", strokeWidth: 0 }} isAnimationActive={false} />
      </LineChart>
    </ChartContainer>
  );
}

export function CorrelationHeatmap({ labels, matrix }: { labels: string[]; matrix: number[][] }) {
  const [hover, setHover] = React.useState<[number, number] | null>(null);
  return (
    <div>
      <div className="mb-3 h-5 text-[12.5px] text-muted-foreground">
        {hover ? (
          <>
            <span className="font-medium text-foreground">{labels[hover[0]]}</span> and <span className="font-medium text-foreground">{labels[hover[1]]}</span>:{" "}
            <span className="num font-medium text-foreground">{matrix[hover[0]][hover[1]].toFixed(2)}</span>
          </>
        ) : (
          "Hover a cell to read the correlation."
        )}
      </div>
      <div className="overflow-x-auto" onMouseLeave={() => setHover(null)}>
        <div className="inline-grid gap-[2px]" style={{ gridTemplateColumns: `76px repeat(${labels.length}, 17px)` }}>
          <div />
          {labels.map((l, j) => (
            <div key={l} className={cn("h-[70px] text-[9.5px] leading-none", hover?.[1] === j ? "text-foreground" : "text-faint")} style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}>
              {l}
            </div>
          ))}
          {matrix.map((row, i) => (
            <React.Fragment key={labels[i]}>
              <div className={cn("pr-2 text-right text-[9.5px] leading-[17px]", hover?.[0] === i ? "text-foreground" : "text-faint")}>{labels[i]}</div>
              {row.map((v, j) => (
                <div
                  key={j}
                  className={cn("size-[17px] rounded-[2px]", hover && (hover[0] === i || hover[1] === j) && "outline outline-1 outline-foreground/30")}
                  style={{ background: `color-mix(in oklch, var(--chart-1) ${Math.round(Math.max(0, v) * 92)}%, var(--muted))` }}
                  onMouseEnter={() => setHover([i, j])}
                />
              ))}
            </React.Fragment>
          ))}
        </div>
      </div>
      <div className="mt-4 flex items-center gap-3 text-[11.5px] text-faint">
        <span>0</span>
        <div className="h-1.5 w-40 rounded-full" style={{ background: "linear-gradient(to right, var(--muted), var(--chart-1))" }} />
        <span>1</span>
        <span className="ml-2">Pale cells diversify each other.</span>
      </div>
    </div>
  );
}

export function AssetsTable({ rows, onSelect, selected }: { rows: AssetRow[]; onSelect: (t: string) => void; selected?: string }) {
  const [q, setQ] = React.useState("");
  const [sort, setSort] = React.useState<{ key: keyof AssetRow; dir: 1 | -1 }>({ key: "expected_return", dir: -1 });
  const filtered = rows
    .filter((r) => (r.ticker + r.name + r.sector + r.asset_class).toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => {
      const x = a[sort.key],
        y = b[sort.key];
      return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y))) * sort.dir;
    });
  const maxE = Math.max(...rows.map((r) => r.expected_return));
  const head = (key: keyof AssetRow, label: string, right = true, cls = "") => (
    <TableHead className={cn(right && "text-right", cls)}>
      <button className="inline-flex items-center gap-1 uppercase hover:text-foreground" onClick={() => setSort((s) => ({ key, dir: s.key === key ? ((-s.dir) as 1 | -1) : -1 }))}>
        {label}
        {sort.key === key ? sort.dir === 1 ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" /> : null}
      </button>
    </TableHead>
  );
  return (
    <div className="space-y-4">
      <div className="relative max-w-xs">
        <Search className="absolute top-2 left-2.5 size-4 text-faint" />
        <Input className="h-8 bg-surface pl-8 text-[13px]" placeholder="Filter by name, sector or class" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="max-h-[560px] overflow-auto">
        <Table>
          <TableHeader className="sticky top-0 z-10 bg-background">
            <TableRow>
              {head("ticker", "Asset", false)}
              {head("sector", "Class", false, "hidden 2xl:table-cell")}
              {head("price", "Price")}
              {head("beta", "Beta")}
              {head("capm_return", "CAPM", true, "hidden 2xl:table-cell")}
              {head("hist_return", "5-yr hist.", true, "hidden xl:table-cell")}
              {head("expected_return", "Model exp.")}
              {head("vol", "Vol")}
              {head("mdd", "Max DD", true, "hidden 2xl:table-cell")}
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((r) => (
              <TableRow key={r.symbol} className={cn("cursor-pointer", selected === r.ticker && "bg-foreground/[0.04]")} onClick={() => onSelect(r.ticker)}>
                <TableCell>
                  <div className="font-medium">{r.ticker}</div>
                  <div className="text-[12px] text-muted-foreground">{r.name}</div>
                </TableCell>
                <TableCell className="hidden 2xl:table-cell">
                  {r.asset_class === "stock" ? <span className="text-[12px] text-muted-foreground">{r.sector}</span> : <ClassTag cls={r.asset_class} />}
                </TableCell>
                <TableCell className="text-right">{inr(r.price, 2)}</TableCell>
                <TableCell className="text-right">{num(r.beta)}</TableCell>
                <TableCell className="hidden text-right text-muted-foreground 2xl:table-cell">{pct(r.capm_return)}</TableCell>
                <TableCell className={cn("hidden text-right xl:table-cell", toneOf(r.hist_return))}>{pct(r.hist_return)}</TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-2.5">
                    <Meter value={Math.max(0, r.expected_return)} max={maxE} className="hidden w-12 sm:block" color="var(--brand)" />
                    <span className="w-11 font-medium">{pct(r.expected_return)}</span>
                  </div>
                </TableCell>
                <TableCell className="text-right">{pct(r.vol)}</TableCell>
                <TableCell className="hidden text-right text-muted-foreground 2xl:table-cell">{pct(r.mdd)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

export function AssetDetailView({ a }: { a: AssetDetail }) {
  const t = a.symbol.replace(".NS", "");
  const cfg: ChartConfig = { asset: { label: t, color: "var(--foreground)" }, nifty: { label: "NIFTY 50", color: "var(--faint)" } };
  return (
    <div className="space-y-6">
      <div>
        <div className="label">
          {a.sector} · {CLASS_LABEL[a.asset_class]}
        </div>
        <div className="mt-1 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h3 className="display text-[1.9rem] leading-tight">
            {t} <span className="text-muted-foreground">· {a.name}</span>
          </h3>
          <span className="num text-[15px] font-medium">{inr(a.last_price, 2)}</span>
          <Delta value={a.ret_today} className="text-[13px]">
            {pctSigned(a.ret_today, 2)} today
          </Delta>
        </div>
      </div>
      <Figures cols={3}>
        <Figure label="Beta" value={num(a.beta)} sub="vs NIFTY 50" />
        <Figure label="CAPM return" value={pct(a.capm_expected_return)} />
        <Figure label="Model expected" value={pct(a.final_expected_return)} sub={`ML 21-day ${pctSigned(a.ml_forecast_21d)}`} />
        <Figure label="Volatility" value={pct(a.volatility)} sub={`1-day VaR ${pct(a.var95_1d, 2)}`} />
        <Figure label="Max drawdown" value={pct(a.max_drawdown)} sub="5 years" tone="negative" />
        <Figure label="Trend" value={<span className="text-[1.05rem]">{a.above_200dma ? "Above" : "Below"} 200-day avg</span>} sub={`RSI ${a.rsi14.toFixed(0)} · 1y ${pctSigned(a.ret_1y, 0)}`} />
      </Figures>
      <Section title="Three years against the index" description="Both rebased to 100">
        <ChartContainer config={cfg} className="h-[260px] w-full">
          <LineChart data={a.series} margin={{ left: 0, right: 8, top: 8 }}>
            <CartesianGrid vertical={false} strokeDasharray="2 4" />
            <XAxis dataKey="date" tickLine={false} axisLine={false} minTickGap={60} tickMargin={8} tickFormatter={(v) => new Date(String(v)).toLocaleDateString("en-IN", { month: "short", year: "2-digit" })} />
            <YAxis width={36} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
            <ChartTooltip content={<ChartTooltipContent labelFormatter={(v) => shortDate(String(v))} formatter={(v, n) => (
              <div className="flex w-full items-center justify-between gap-4">
                <span className="text-muted-foreground">{n === "asset" ? t : "NIFTY 50"}</span>
                <span className="num font-medium">{Number(v).toFixed(1)}</span>
              </div>
            )} />} />
            <Line dataKey="nifty" stroke="var(--color-nifty)" strokeWidth={1.25} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
            <Line dataKey="asset" stroke="var(--color-asset)" strokeWidth={1.75} dot={false} isAnimationActive={false} />
          </LineChart>
        </ChartContainer>
      </Section>
    </div>
  );
}

const MODEL_COLS: [string, string, (v: number) => string][] = [
  ["rmse", "RMSE", (v) => v.toFixed(4)],
  ["mae", "MAE", (v) => v.toFixed(4)],
  ["dir_acc", "Direction", (v) => pct(v, 1)],
  ["ic_cross_section", "IC cross-section", (v) => v.toFixed(3)],
  ["ic_pooled", "IC pooled", (v) => v.toFixed(3)],
];

export function ModelsView({ data, regimes, market }: { data: ModelsData; regimes?: MarketData["regimes"]; market?: MarketData | null }) {
  const imp = data.importance;
  const maxImp = Math.max(...imp.map((i) => i.value), 1e-9);
  const rg = regimes ?? data.regimes;
  return (
    <div className="space-y-10">
      <Section
        title="Return models, validated walk-forward"
        description="Expanding window from 2021 to 2026 with purged targets: every forecast uses only the past"
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Model</TableHead>
              {MODEL_COLS.map(([, l]) => (
                <TableHead key={l} className="text-right">
                  {l}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.metrics.map((m) => {
              const sel = String(m.model) === data.selected;
              return (
                <TableRow key={String(m.model)} className={cn(String(m.model).includes("baseline") && "text-muted-foreground")}>
                  <TableCell className={cn(sel && "font-semibold")}>
                    {String(m.model)}
                    {sel ? <span className="ml-2 text-[10.5px] font-medium tracking-[0.06em] text-brand uppercase">In use</span> : null}
                  </TableCell>
                  {MODEL_COLS.map(([k, , f]) => (
                    <TableCell key={k} className="text-right">
                      {m[k] == null ? <span className="text-faint">—</span> : f(Number(m[k]))}
                    </TableCell>
                  ))}
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        <p className="mt-4 max-w-3xl text-[13px] leading-relaxed text-muted-foreground">
          Monthly stock returns are close to unpredictable: no model beats the naive baseline on error, and the information coefficient is small but
          positive. The forecast is therefore only a relative tilt on top of the CAPM and history prior, weighted at{" "}
          <span className="font-medium text-foreground">{pct(data.skill_weight ?? 0, 0)}</span> according to the measured skill.
        </p>
      </Section>

      <div className="grid gap-10 xl:grid-cols-2">
        {imp.length ? (
          <Section title="What the model looks at" description="Feature importance of the model in use">
            <div className="space-y-2">
              {imp.map((f) => (
                <div key={f.feature} className="grid grid-cols-[150px_1fr_52px] items-center gap-3 text-[12.5px]">
                  <span className="truncate font-mono text-[12px] text-muted-foreground">{f.feature}</span>
                  <Meter value={f.value} max={maxImp} />
                  <span className="num text-right">{f.value.toFixed(3)}</span>
                </div>
              ))}
            </div>
          </Section>
        ) : null}
        {rg ? (
          <Section title="Market regimes" description="Gaussian mixture on NIFTY return, volatility, drawdown and India VIX">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Regime</TableHead>
                  <TableHead className="text-right">Share of days</TableHead>
                  <TableHead className="text-right">Return</TableHead>
                  <TableHead className="text-right">Volatility</TableHead>
                  <TableHead className="text-right">Avg VIX</TableHead>
                  {market ? <TableHead className="text-right">Persistence</TableHead> : null}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rg.map((r, i) => (
                  <TableRow key={r.regime}>
                    <TableCell>
                      <span className="flex items-center gap-2">
                        <Swatch color={REGIME_COLORS[i]} />
                        <span className="font-medium">{r.regime}</span>
                      </span>
                    </TableCell>
                    <TableCell className="text-right">{pct(r.share, 0)}</TableCell>
                    <TableCell className={cn("text-right", toneOf(r.ann_return))}>{pctSigned(r.ann_return)}</TableCell>
                    <TableCell className="text-right">{pct(r.ann_vol)}</TableCell>
                    <TableCell className="text-right">{r.avg_vix.toFixed(1)}</TableCell>
                    {market ? <TableCell className="text-right">{pct(market.transition[i][i], 1)}</TableCell> : null}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {market ? <p className="mt-3 text-[12px] text-faint">Persistence is the chance a regime carries over to the next trading day.</p> : null}
          </Section>
        ) : null}
      </div>
    </div>
  );
}
