"use client";

import * as React from "react";
import { CartesianGrid, Line, LineChart, Scatter, ScatterChart, XAxis, YAxis, ZAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Section, Swatch } from "@/components/kit";
import { cn } from "@/lib/utils";
import { compactInr, inr, num, pct, STRATEGY_COLOR, years } from "@/lib/format";
import type { FrontierData, StrategiesData } from "@/lib/types";

export function StrategiesView({
  data,
  frontier,
  onSelect,
  selected,
}: {
  data: StrategiesData;
  frontier?: FrontierData | null;
  onSelect?: (name: string) => void;
  selected?: string;
}) {
  const names = data.strategies.map((s) => s.strategy);
  const best = Math.max(...data.strategies.map((s) => s.mc.stats.prob_target ?? 0));

  const lineData = React.useMemo(() => {
    const fanYears = data.strategies[0]?.mc.fan.map((f) => f.year) ?? [];
    return fanYears.map((y, i) => {
      const row: Record<string, number> = { year: y };
      data.strategies.forEach((s) => (row[s.strategy] = s.mc.fan[i]?.p50));
      return row;
    });
  }, [data.strategies]);
  const lineCfg: ChartConfig = Object.fromEntries(names.map((n) => [n, { label: n, color: STRATEGY_COLOR[n] }]));

  // weights matrix: union of assets, sorted by the recommended strategy's weight
  const matrix = React.useMemo(() => {
    const rec = data.strategies.find((s) => s.recommended) ?? data.strategies[0];
    const tickers = new Map<string, number>();
    data.strategies.forEach((s) => s.weights.forEach((w) => tickers.set(w.ticker, Math.max(tickers.get(w.ticker) ?? 0, w.weight))));
    const recW = Object.fromEntries(rec.weights.map((w) => [w.ticker, w.weight]));
    return [...tickers.keys()].sort((a, b) => (recW[b] ?? 0) - (recW[a] ?? 0) || (tickers.get(b) ?? 0) - (tickers.get(a) ?? 0));
  }, [data.strategies]);

  return (
    <div className="space-y-6">
      <div className="border-l-2 border-brand pl-4">
        <div className="label text-brand">Recommendation</div>
        <p className="mt-1 max-w-3xl text-[14px] leading-relaxed">
          <span className="font-semibold">{data.recommended}.</span> {data.why}
        </p>
      </div>

      <Section
        title="Five strategies, one profile"
        description={`${inr(data.profile.amount)} over ${years(data.profile.horizon_years)}, ${data.profile.risk} risk, ${data.profile.target_return_pct}% target${onSelect ? " · select a row to open its plan" : ""}`}
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Strategy</TableHead>
              <TableHead className="text-right">Return</TableHead>
              <TableHead className="text-right">Volatility</TableHead>
              <TableHead className="text-right">Sharpe</TableHead>
              <TableHead className="hidden text-right xl:table-cell">Chance of gain</TableHead>
              <TableHead className="text-right">Reach target</TableHead>
              <TableHead className="hidden text-right 2xl:table-cell">Drawdown</TableHead>
              <TableHead className="text-right">Median value</TableHead>
              <TableHead className="hidden text-right 2xl:table-cell">Worst 5%</TableHead>
              <TableHead className="text-right">Risk limits</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.strategies.map((s) => (
              <TableRow
                key={s.strategy}
                onClick={() => onSelect?.(s.strategy)}
                className={cn(onSelect && "cursor-pointer", selected === s.strategy && "bg-foreground/[0.035]")}
              >
                <TableCell>
                  <div className="flex items-center gap-2.5">
                    <Swatch color={STRATEGY_COLOR[s.strategy]} />
                    <span className="font-medium">{s.strategy}</span>
                    {s.recommended ? <span className="text-[10.5px] font-medium tracking-[0.06em] text-brand uppercase">Rec.</span> : null}
                  </div>
                </TableCell>
                <TableCell className="text-right">{pct(s.stats.exp_return)}</TableCell>
                <TableCell className="text-right">{pct(s.stats.volatility)}</TableCell>
                <TableCell className="text-right">{num(s.stats.sharpe)}</TableCell>
                <TableCell className="hidden text-right xl:table-cell">{pct(s.mc.stats.prob_positive, 0)}</TableCell>
                <TableCell className={cn("text-right", (s.mc.stats.prob_target ?? 0) === best && "font-semibold")}>{pct(s.mc.stats.prob_target, 0)}</TableCell>
                <TableCell className="hidden text-right 2xl:table-cell">{pct(s.mc.stats.exp_max_drawdown)}</TableCell>
                <TableCell className="text-right">{compactInr(s.mc.stats.median_final)}</TableCell>
                <TableCell className="hidden text-right text-muted-foreground 2xl:table-cell">{compactInr(s.mc.stats.worst_case_p5)}</TableCell>
                <TableCell className="text-right">
                  {s.within_limits ? (
                    <span className="text-[12px] text-muted-foreground">Within</span>
                  ) : (
                    <span className="text-[12px] text-negative" title={s.breaches.join("; ")}>
                      Breach
                    </span>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>

      <div className="grid gap-6 xl:grid-cols-2">
        <Section title="Risk and return" description={frontier ? "Efficient frontier, random portfolios and single assets" : "Expected return against volatility"}>
          <RiskReturnChart data={data} frontier={frontier} />
        </Section>
        <Section title="Median growth" description="Typical path of each strategy">
          <ChartContainer config={lineCfg} className="h-[320px] w-full">
            <LineChart data={lineData} margin={{ left: 0, right: 8, top: 8 }}>
              <CartesianGrid vertical={false} strokeDasharray="2 4" />
              <XAxis dataKey="year" type="number" domain={[0, "dataMax"]} tickFormatter={(v) => `${Number(v).toFixed(0)}y`} tickLine={false} axisLine={false} tickMargin={8} />
              <YAxis tickFormatter={(v) => compactInr(Number(v))} width={58} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
              <ChartTooltip content={<ChartTooltipContent labelFormatter={(_, p) => `Year ${Number(p?.[0]?.payload?.year ?? 0).toFixed(1)}`} formatter={(v, n) => (
                <div className="flex w-full items-center justify-between gap-4">
                  <span className="flex items-center gap-1.5 text-muted-foreground"><Swatch color={STRATEGY_COLOR[String(n)]} />{String(n)}</span>
                  <span className="num font-medium">{inr(Number(v))}</span>
                </div>
              )} />} />
              {names.map((n) => (
                <Line key={n} dataKey={n} stroke={STRATEGY_COLOR[n]} strokeWidth={n === data.recommended ? 2.25 : 1.5} dot={false} isAnimationActive={false} />
              ))}
            </LineChart>
          </ChartContainer>
          <StrategyLegend names={names} />
        </Section>
      </div>

      <Section title="Weights by strategy" description="Darker cells hold more of the portfolio">
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="border-b border-rule">
                <th className="label py-2 pr-3 text-left font-medium">Asset</th>
                {data.strategies.map((s) => (
                  <th key={s.strategy} className="label px-1 py-2 text-right font-medium">
                    {s.strategy}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrix.map((t) => (
                <tr key={t} className="border-b border-border/60">
                  <td className="py-1.5 pr-3 font-medium">{t}</td>
                  {data.strategies.map((s) => {
                    const w = s.weights.find((x) => x.ticker === t)?.weight ?? 0;
                    return (
                      <td key={s.strategy} className="px-1 py-1">
                        <div
                          className="num rounded-[3px] px-2 py-1 text-right"
                          style={{ background: w ? `color-mix(in oklch, var(--foreground) ${Math.min(30, 6 + w * 85)}%, transparent)` : undefined }}
                        >
                          {w ? pct(w, 0) : <span className="text-faint">·</span>}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}

function StrategyLegend({ names }: { names: string[] }) {
  return (
    <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-muted-foreground">
      {names.map((n) => (
        <span key={n} className="flex items-center gap-1.5">
          <Swatch color={STRATEGY_COLOR[n]} /> {n}
        </span>
      ))}
    </div>
  );
}

export function RiskReturnChart({ data, frontier }: { data: StrategiesData; frontier?: FrontierData | null }) {
  const cfg: ChartConfig = { pt: { label: "Portfolio", color: "var(--foreground)" } };
  const strategies = frontier
    ? frontier.strategies
    : data.strategies.map((s) => ({ strategy: s.strategy, vol: s.stats.volatility, ret: s.stats.exp_return }));
  const f = frontier ? frontier.frontier.map((p) => ({ x: p.vol * 100, y: p.ret * 100 })).sort((a, b) => a.x - b.x) : [];
  return (
    <>
      <ChartContainer config={cfg} className="h-[320px] w-full">
        <ScatterChart margin={{ left: 0, right: 16, top: 16, bottom: 0 }}>
          <CartesianGrid strokeDasharray="2 4" />
          <XAxis type="number" dataKey="x" name="Volatility" unit="%" domain={["auto", "auto"]} tickLine={false} axisLine={false} tickFormatter={(v) => Number(v).toFixed(0)} tickMargin={8} />
          <YAxis type="number" dataKey="y" name="Return" unit="%" domain={["auto", "auto"]} width={40} tickLine={false} axisLine={false} tickFormatter={(v) => Number(v).toFixed(0)} />
          <ZAxis range={[22, 22]} />
          <ChartTooltip
            cursor={{ strokeDasharray: "3 3", stroke: "var(--rule)" }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0].payload as { x: number; y: number; t?: string; label?: string };
              return (
                <div className="rounded-md border border-border bg-popover px-3 py-2 text-[12px] shadow-sm">
                  {d.label || d.t ? <div className="mb-0.5 font-medium">{d.label ?? d.t}</div> : null}
                  <div className="num text-muted-foreground">Return {d.y.toFixed(1)}% · Vol {d.x.toFixed(1)}%</div>
                </div>
              );
            }}
          />
          {frontier ? (
            <>
              <Scatter data={frontier.cloud.map((p) => ({ x: p.vol * 100, y: p.ret * 100 }))} fill="var(--faint)" fillOpacity={0.22} isAnimationActive={false} />
              <Scatter data={frontier.assets.map((p) => ({ x: p.vol * 100, y: p.ret * 100, t: p.ticker }))} fill="var(--faint)" shape={(props: { cx?: number; cy?: number }) => <path d={`M${(props.cx ?? 0) - 3},${props.cy} h6 M${props.cx},${(props.cy ?? 0) - 3} v6`} stroke="var(--faint)" strokeWidth={1.2} />} isAnimationActive={false} />
              <Scatter data={f} fill="var(--foreground)" line={{ stroke: "var(--foreground)", strokeWidth: 1.5 }} lineType="joint" shape={() => <g />} isAnimationActive={false} />
            </>
          ) : null}
          {strategies.map((s) => (
            <Scatter
              key={s.strategy}
              data={[{ x: s.vol * 100, y: s.ret * 100, label: s.strategy }]}
              isAnimationActive={false}
              shape={(props: { cx?: number; cy?: number }) => <circle cx={props.cx} cy={props.cy} r={5.5} fill={STRATEGY_COLOR[s.strategy]} stroke="var(--background)" strokeWidth={2} />}
            />
          ))}
        </ScatterChart>
      </ChartContainer>
      <StrategyLegend names={strategies.map((s) => s.strategy)} />
      {frontier ? (
        <div className="mt-1.5 flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-muted-foreground">
          <span className="flex items-center gap-1.5"><span className="h-px w-4 bg-foreground" /> Efficient frontier</span>
          <span className="flex items-center gap-1.5"><span className="size-1.5 rounded-full bg-faint/50" /> Random portfolios</span>
          <span className="flex items-center gap-1.5"><span className="text-[11px] leading-none">+</span> Single assets</span>
        </div>
      ) : null}
    </>
  );
}
