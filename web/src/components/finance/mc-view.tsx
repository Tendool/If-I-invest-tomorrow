"use client";

import * as React from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, ReferenceLine, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart";
import { Figure, Figures, Section, Swatch } from "@/components/kit";
import { compactInr, inr, pct } from "@/lib/format";
import type { MCData } from "@/lib/types";
import { OutcomeRange } from "./shared";

const fanCfg: ChartConfig = {
  band90: { label: "5th–95th percentile", color: "var(--chart-1)" },
  band50: { label: "25th–75th percentile", color: "var(--chart-1)" },
  p50: { label: "Median", color: "var(--chart-1)" },
  target: { label: "Target path", color: "var(--brand)" },
};

function Tip({ children }: { children: React.ReactNode }) {
  return <div className="rounded-md border border-border bg-popover px-3 py-2 text-[12px] shadow-sm">{children}</div>;
}

function FanTooltip({ active, payload }: { active?: boolean; payload?: { payload: Record<string, number> }[] }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  const rows: [string, number, boolean?][] = [
    ["95th", r.p95],
    ["75th", r.p75],
    ["Median", r.p50, true],
    ["25th", r.p25],
    ["5th", r.p5],
  ];
  return (
    <Tip>
      <div className="mb-1 font-medium">Year {Number(r.year).toFixed(1)}</div>
      <div className="grid grid-cols-[auto_auto] gap-x-5 gap-y-0.5">
        {rows.map(([k, v, b]) => (
          <React.Fragment key={k}>
            <span className={b ? "font-medium" : "text-muted-foreground"}>{k}</span>
            <span className={`num text-right ${b ? "font-medium" : ""}`}>{inr(v)}</span>
          </React.Fragment>
        ))}
        {r.target ? (
          <>
            <span className="text-brand">Target</span>
            <span className="num text-right text-brand">{inr(r.target)}</span>
          </>
        ) : null}
      </div>
    </Tip>
  );
}

export function FanChart({ mc, height = 300 }: { mc: MCData["mc"]; height?: number }) {
  const data = React.useMemo(
    () =>
      mc.fan.map((f) => ({
        ...f,
        band90: [f.p5, f.p95] as [number, number],
        band50: [f.p25, f.p75] as [number, number],
        target: mc.target != null ? mc.amount * Math.pow(1 + mc.target, f.year) : undefined,
      })),
    [mc],
  );
  return (
    <ChartContainer config={fanCfg} className="w-full" style={{ height }}>
      <AreaChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
        <CartesianGrid vertical={false} strokeDasharray="2 4" />
        <XAxis dataKey="year" type="number" domain={[0, "dataMax"]} tickFormatter={(v) => `${Number(v).toFixed(0)}y`} tickLine={false} axisLine={false} tickMargin={8} />
        <YAxis tickFormatter={(v) => compactInr(Number(v))} width={58} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
        <ChartTooltip cursor={{ stroke: "var(--rule)" }} content={<FanTooltip />} />
        <Area dataKey="band90" stroke="none" fill="var(--color-band90)" fillOpacity={0.1} isAnimationActive={false} />
        <Area dataKey="band50" stroke="none" fill="var(--color-band50)" fillOpacity={0.2} isAnimationActive={false} />
        <Line dataKey="p50" stroke="var(--color-p50)" strokeWidth={2} dot={false} isAnimationActive={false} />
        {mc.target != null ? <Line dataKey="target" stroke="var(--color-target)" strokeWidth={1.5} strokeDasharray="5 4" dot={false} isAnimationActive={false} /> : null}
        <ReferenceLine y={mc.amount} stroke="var(--faint)" strokeDasharray="2 3" />
      </AreaChart>
    </ChartContainer>
  );
}

export function FanLegend({ target }: { target: boolean }) {
  return (
    <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-muted-foreground">
      <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 bg-chart-1" /> Median</span>
      <span className="flex items-center gap-1.5"><span className="h-2.5 w-4 rounded-[2px] bg-chart-1/30" /> Middle 50%</span>
      <span className="flex items-center gap-1.5"><span className="h-2.5 w-4 rounded-[2px] bg-chart-1/12" /> 90% of paths</span>
      {target ? <span className="flex items-center gap-1.5"><span className="w-4 border-t-[1.5px] border-dashed border-brand" /> Target path</span> : null}
      <span className="flex items-center gap-1.5"><span className="w-4 border-t border-dashed border-faint" /> Amount invested</span>
    </div>
  );
}

export function DistributionChart({ mc, height = 260 }: { mc: MCData["mc"]; height?: number }) {
  const hist = mc.hist ?? [];
  const targetVal = mc.target != null ? mc.amount * Math.pow(1 + mc.target, mc.years) : null;
  const nearest = (v: number) => hist.reduce((b, h) => (Math.abs(h.x - v) < Math.abs(b.x - v) ? h : b), hist[0])?.x;
  const color = (x: number) => (targetVal != null && x >= targetVal ? "var(--positive)" : x >= mc.amount ? "var(--faint)" : "var(--negative)");
  if (!hist.length) return null;
  return (
    <ChartContainer config={{ pct: { label: "% of paths", color: "var(--chart-1)" } }} className="w-full" style={{ height }}>
      <BarChart data={hist} margin={{ left: 0, right: 8, top: 8, bottom: 0 }} barCategoryGap={1}>
        <CartesianGrid vertical={false} strokeDasharray="2 4" />
        <XAxis dataKey="x" tickFormatter={(v) => compactInr(Number(v))} tickLine={false} axisLine={false} minTickGap={36} tickMargin={8} />
        <YAxis tickFormatter={(v) => `${Number(v).toFixed(0)}%`} width={34} tickLine={false} axisLine={false} />
        <ChartTooltip
          cursor={{ fill: "var(--foreground)", fillOpacity: 0.04 }}
          content={({ active, payload }) =>
            active && payload?.length ? (
              <Tip>
                <div className="num font-medium">≈ {inr(Number(payload[0].payload.x))}</div>
                <div className="text-muted-foreground">{Number(payload[0].payload.pct).toFixed(2)}% of paths</div>
              </Tip>
            ) : null
          }
        />
        <Bar dataKey="pct" radius={[2, 2, 0, 0]} isAnimationActive={false}>
          {hist.map((h) => (
            <Cell key={h.x} fill={color(h.x)} fillOpacity={0.75} />
          ))}
        </Bar>
        <ReferenceLine x={nearest(mc.amount)} stroke="var(--foreground)" strokeDasharray="2 3" />
        {targetVal != null ? <ReferenceLine x={nearest(targetVal)} stroke="var(--brand)" strokeDasharray="4 3" /> : null}
      </BarChart>
    </ChartContainer>
  );
}

export function MonteCarloView({ data }: { data: MCData }) {
  const m = data.mc.stats;
  const p = data.profile;
  const target = p.amount * Math.pow(1 + p.target_return_pct / 100, p.horizon_years);
  return (
    <div className="space-y-8">
      <div>
        <div className="label">Monte Carlo · {data.strategy}</div>
        <p className="mt-1.5 max-w-3xl text-[13.5px] text-muted-foreground">
          {data.mc.n_paths.toLocaleString("en-IN")} simulated futures with fat-tailed daily returns and a three-state market regime that starts
          from today&apos;s reading ({data.regime}).
        </p>
      </div>
      <Figures cols={6}>
        <Figure label="Median return" value={pct(m.exp_return_median)} sub="per year" />
        <Figure label="Volatility" value={pct(m.exp_volatility)} sub="simulated" />
        <Figure label="Chance of gain" value={pct(m.prob_positive, 0)} />
        <Figure label="Reach target" value={pct(m.prob_target, 0)} />
        <Figure label="1-yr VaR 95%" value={pct(m.var95_1y)} sub="loss not exceeded 19 in 20 years" />
        <Figure label="1-yr CVaR 95%" value={pct(m.cvar95_1y)} sub="average of the worst 5%" />
      </Figures>

      <Section title={`Value after ${p.horizon_years} years`} description="5th to 95th percentile of simulated outcomes">
        <OutcomeRange low={m.worst_case_p5} median={m.median_final} high={m.best_case_p95} invested={p.amount} target={target} />
        <p className="mt-2 text-[12px] text-faint">
          Extremes across all paths: {inr(m.absolute_worst)} to {inr(m.absolute_best)}.
        </p>
      </Section>

      <div className="grid gap-10 xl:grid-cols-2">
        <Section title="Growth paths" description="How the range of outcomes widens over time">
          <FanChart mc={data.mc} />
          <FanLegend target={data.mc.target != null} />
        </Section>
        <Section title="Distribution of final value" description="Share of paths ending at each value">
          <DistributionChart mc={data.mc} />
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-muted-foreground">
            <span className="flex items-center gap-1.5"><Swatch color="var(--positive)" /> Target met</span>
            <span className="flex items-center gap-1.5"><Swatch color="var(--faint)" /> Gain, below target</span>
            <span className="flex items-center gap-1.5"><Swatch color="var(--negative)" /> Loss</span>
          </div>
        </Section>
      </div>
    </div>
  );
}
