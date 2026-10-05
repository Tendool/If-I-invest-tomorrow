"use client";

import * as React from "react";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Delta, Figure, Figures, Section, Swatch } from "@/components/kit";
import { cn } from "@/lib/utils";
import { compactInr, inr, inrSigned, num, pct, pctSigned, shortDate, STRATEGY_COLOR, toneOf, years } from "@/lib/format";
import type { BacktestData, StressData, TimingData } from "@/lib/types";
import { DivergingBar, RangeBar } from "./shared";

export function StressView({ data }: { data: StressData }) {
  const survived = data.stress.filter((s) => s.survives).length;
  const worst = data.stress.reduce((a, b) => (b.portfolio_return < a.portfolio_return ? b : a), data.stress[0]);
  const maxAbs = Math.max(data.loss_limit, ...data.stress.map((s) => Math.abs(s.portfolio_return)));
  return (
    <div className="space-y-6">
      <div>
        <div className="label">Stress tests · {data.strategy}</div>
        <p className="mt-1.5 max-w-3xl text-[13.5px] text-muted-foreground">
          Instant shocks applied through each holding&apos;s market beta, sector, rate and oil sensitivities, plus replays of real Indian market
          crashes. A scenario passes if the loss stays within your {data.profile.risk}-risk limit of {pct(data.loss_limit, 0)}.
        </p>
      </div>
      <Figures cols={4}>
        <Figure label="Scenarios passed" value={`${survived} of ${data.stress.length}`} tone={survived === data.stress.length ? "positive" : null} />
        <Figure label="Worst scenario" value={pctSigned(worst.portfolio_return)} sub={worst.scenario.replace("Replay: ", "")} tone="negative" />
        <Figure label="Worst loss" value={inr(Math.abs(Math.min(0, worst.pnl)))} sub={`on ${inr(data.profile.amount)}`} />
        <Figure label="Loss limit" value={pct(data.loss_limit, 0)} sub={`${data.profile.risk} risk`} />
      </Figures>

      <Section title="Scenario impact" description="Immediate change in portfolio value">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Scenario</TableHead>
              <TableHead className="hidden w-[34%] md:table-cell" />
              <TableHead className="text-right">Return</TableHead>
              <TableHead className="text-right">P&amp;L</TableHead>
              <TableHead className="text-right">Result</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.stress.map((s) => (
              <TableRow key={s.scenario}>
                <TableCell className="whitespace-normal">
                  <div className="font-medium">{s.scenario.replace("Replay: ", "")}</div>
                  <div className="text-[12px] text-muted-foreground">
                    {s.scenario.startsWith("Replay") ? "Historical replay" : "Instant shock"}
                    {s.top_hits ? ` · hardest hit: ${s.top_hits}` : ""}
                  </div>
                </TableCell>
                <TableCell className="hidden md:table-cell">
                  <DivergingBar value={s.portfolio_return} max={maxAbs} breach={!s.survives} />
                </TableCell>
                <TableCell className={cn("text-right", toneOf(s.portfolio_return))}>{pctSigned(s.portfolio_return, 2)}</TableCell>
                <TableCell className="text-right">{inrSigned(s.pnl)}</TableCell>
                <TableCell className={cn("text-right text-[12px]", s.survives ? "text-muted-foreground" : "font-medium text-negative")}>
                  {s.survives ? "Pass" : "Fail"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>

      <Section title="After the shock" description={`The shock hits tomorrow, then ${years(data.profile.horizon_years)} of simulated markets follow from a bear regime`}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Scenario</TableHead>
              <TableHead className="text-right">Day-one impact</TableHead>
              <TableHead className="text-right">Median value</TableHead>
              <TableHead className="text-right">Median return</TableHead>
              <TableHead className="text-right">Chance of gain</TableHead>
              <TableHead className="text-right">Reach target</TableHead>
              <TableHead className="hidden text-right md:table-cell">Worst 5%</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.shock_mc.map((r) => (
              <TableRow key={r.scenario}>
                <TableCell className="font-medium">{r.scenario}</TableCell>
                <TableCell className={cn("text-right", toneOf(r.day0_impact))}>{r.day0_impact ? pctSigned(r.day0_impact) : "—"}</TableCell>
                <TableCell className="text-right">{inr(r.median_final)}</TableCell>
                <TableCell className="text-right">{pct(r.median_cagr)}</TableCell>
                <TableCell className="text-right">{pct(r.prob_positive, 0)}</TableCell>
                <TableCell className="text-right">{pct(r.prob_target, 0)}</TableCell>
                <TableCell className="hidden text-right text-muted-foreground md:table-cell">{inr(r.worst_case_p5)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>
    </div>
  );
}

export function TimingView({ data }: { data: TimingData }) {
  const min = Math.min(...data.table.map((t) => t.p5_final)) * 0.97;
  const max = Math.max(...data.table.map((t) => t.p95_final)) * 1.02;
  const base = data.table[0];
  const best = data.table.reduce((a, b) => (b.median_final > a.median_final ? b : a), base);
  return (
    <div className="space-y-8">
      <div>
        <div className="label">Invest now, wait, or SIP · {data.strategy}</div>
        <p className="mt-1.5 max-w-3xl text-[13.5px] text-muted-foreground">
          Every option is run on the same simulated markets. Money not yet invested earns the risk-free rate. Today&apos;s regime: {data.regime}.
        </p>
      </div>
      <div className="border-l-2 border-brand pl-4 text-[14px] leading-relaxed">
        <span className="font-semibold">{best.strategy}</span> has the highest median outcome ({inr(best.median_final)}).
        {best === base
          ? " With a positive expected return, time in the market usually beats waiting; staggering mainly narrows the bad outcomes."
          : ` It beats investing everything now in ${pct(best.prob_beats_lump_sum ?? 0, 0)} of simulated futures.`}
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Option</TableHead>
            <TableHead className="hidden w-[30%] md:table-cell">Range of outcomes · 5th–95th</TableHead>
            <TableHead className="text-right">Median</TableHead>
            <TableHead className="text-right">Worst 5%</TableHead>
            <TableHead className="text-right">Chance of gain</TableHead>
            <TableHead className="text-right">Beats lump sum</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.table.map((t) => (
            <TableRow key={t.strategy}>
              <TableCell className={cn(t === best && "font-semibold")}>{t.strategy}</TableCell>
              <TableCell className="hidden md:table-cell">
                <RangeBar low={t.p5_final} median={t.median_final} high={t.p95_final} min={min} max={max} marker={data.profile.amount} />
              </TableCell>
              <TableCell className="text-right font-medium">{inr(t.median_final)}</TableCell>
              <TableCell className="text-right text-muted-foreground">{inr(t.p5_final)}</TableCell>
              <TableCell className="text-right">{pct(t.prob_profit, 0)}</TableCell>
              <TableCell className="text-right">{t.prob_beats_lump_sum == null ? <span className="text-faint">—</span> : pct(t.prob_beats_lump_sum, 0)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <p className="text-[12px] text-faint">Dashed line marks the amount invested. Bars span the 5th to 95th percentile; the tick is the median.</p>
    </div>
  );
}

export function BacktestView({ data, amount: amountProp }: { data: BacktestData; amount?: number }) {
  const first = data.table[0];
  const amount = amountProp && amountProp > 1 ? amountProp : first ? first.final_value / (1 + first.total_return) : 1;
  const cfg: ChartConfig = Object.fromEntries(data.series.map((s) => [s, { label: s, color: STRATEGY_COLOR[s] ?? "var(--muted-foreground)" }]));
  const rows = data.curves.map((r) => {
    const o: Record<string, number | string> = { date: r.date };
    data.series.forEach((s) => (o[s] = Number(r[s]) * amount));
    return o;
  });
  const bench = data.table.find((r) => r.strategy.includes("NIFTY"));
  const isRef = (s: string) => s.includes("NIFTY") || s.includes("Equal");
  return (
    <div className="space-y-8">
      <div>
        <div className="label">
          Walk-forward backtest · {shortDate(data.start)} – {shortDate(data.end)}
        </div>
        <p className="mt-1.5 max-w-3xl text-[13.5px] text-muted-foreground">
          Each strategy is chosen using only data available before the start date, then held with quarterly rebalancing. The ML signal is left out
          so nothing leaks from the future. Past results are no guarantee.
        </p>
      </div>
      <Section title="Growth of the portfolio">
        <ChartContainer config={cfg} className="h-[340px] w-full">
          <LineChart data={rows} margin={{ left: 0, right: 8, top: 8 }}>
            <CartesianGrid vertical={false} strokeDasharray="2 4" />
            <XAxis dataKey="date" tickLine={false} axisLine={false} minTickGap={60} tickMargin={8} tickFormatter={(v) => new Date(String(v)).toLocaleDateString("en-IN", { month: "short", year: "2-digit" })} />
            <YAxis tickFormatter={(v) => compactInr(Number(v))} width={58} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
            <ChartTooltip content={<ChartTooltipContent labelFormatter={(v) => shortDate(String(v))} formatter={(v, n) => (
              <div className="flex w-full items-center justify-between gap-4">
                <span className="flex items-center gap-1.5 text-muted-foreground"><Swatch color={STRATEGY_COLOR[String(n)] ?? "var(--muted-foreground)"} />{String(n)}</span>
                <span className="num font-medium">{inr(Number(v))}</span>
              </div>
            )} />} />
            {data.series.map((s) => (
              <Line key={s} dataKey={s} stroke={STRATEGY_COLOR[s] ?? "var(--muted-foreground)"} strokeWidth={isRef(s) ? 1.25 : 1.75} strokeDasharray={isRef(s) ? "4 3" : undefined} dot={false} isAnimationActive={false} />
            ))}
          </LineChart>
        </ChartContainer>
      </Section>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Strategy</TableHead>
            <TableHead className="text-right">Total return</TableHead>
            <TableHead className="text-right">vs NIFTY</TableHead>
            <TableHead className="text-right">CAGR</TableHead>
            <TableHead className="text-right">Volatility</TableHead>
            <TableHead className="text-right">Sharpe</TableHead>
            <TableHead className="text-right">Max drawdown</TableHead>
            <TableHead className="text-right">Final value</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.table.map((r) => (
            <TableRow key={r.strategy} className={cn(isRef(r.strategy) && "text-muted-foreground")}>
              <TableCell>
                <span className="flex items-center gap-2.5">
                  <Swatch color={STRATEGY_COLOR[r.strategy] ?? "var(--faint)"} />
                  <span className={cn(!isRef(r.strategy) && "font-medium")}>{r.strategy}</span>
                </span>
              </TableCell>
              <TableCell className={cn("text-right", toneOf(r.total_return))}>{pctSigned(r.total_return)}</TableCell>
              <TableCell className="text-right">
                {bench && !r.strategy.includes("NIFTY") ? <Delta value={r.total_return - bench.total_return}>{pct(Math.abs(r.total_return - bench.total_return))}</Delta> : <span className="text-faint">—</span>}
              </TableCell>
              <TableCell className="text-right">{pct(r.cagr)}</TableCell>
              <TableCell className="text-right">{pct(r.volatility)}</TableCell>
              <TableCell className="text-right">{num(r.sharpe)}</TableCell>
              <TableCell className="text-right">{pct(r.max_drawdown)}</TableCell>
              <TableCell className="text-right">{inr(r.final_value)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
