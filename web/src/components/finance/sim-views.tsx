"use client";

import * as React from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, ReferenceLine, XAxis, YAxis } from "recharts";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Delta, Figure, Figures, Meter, Section, Swatch } from "@/components/kit";
import { cn } from "@/lib/utils";
import { CLASS_COLOR, CLASS_LABEL, compactInr, inr, inrSigned, num, pct, pctSigned } from "@/lib/format";
import type { SimResult } from "@/lib/types";

const cfg: ChartConfig = {
  band90: { label: "5th–95th percentile", color: "var(--chart-1)" },
  band50: { label: "25th–75th percentile", color: "var(--chart-1)" },
  p50: { label: "Median outcome", color: "var(--chart-1)" },
  invested: { label: "Money you put in", color: "var(--muted-foreground)" },
  fd: { label: "Fixed deposit", color: "var(--chart-4)" },
  nifty: { label: "NIFTY 50 (expected)", color: "var(--chart-3)" },
};

function Tip({ active, payload }: { active?: boolean; payload?: { payload: Record<string, number> }[] }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  const rows: [string, number, string?][] = [
    ["Best 5%", r.p95],
    ["Median", r.p50, "font-semibold"],
    ["Worst 5%", r.p5],
    ["You put in", r.invested, "text-muted-foreground"],
    ["Fixed deposit", r.fd, "text-muted-foreground"],
    ["NIFTY expected", r.nifty, "text-muted-foreground"],
  ];
  return (
    <div className="rounded-md border border-border bg-popover px-3 py-2 text-[12px] shadow-sm">
      <div className="mb-1 font-medium">
        Year {Math.floor(r.month / 12)}
        {r.month % 12 ? `, month ${r.month % 12}` : ""}
      </div>
      <div className="grid grid-cols-[auto_auto] gap-x-5 gap-y-0.5">
        {rows.map(([k, v, c]) => (
          <React.Fragment key={k}>
            <span className={cn("text-muted-foreground", c?.includes("semibold") && "text-foreground")}>{k}</span>
            <span className={cn("num text-right", c)}>{inr(v)}</span>
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

export function ProjectionChart({ sim, height = 360 }: { sim: SimResult; height?: number }) {
  const data = React.useMemo(
    () => sim.fan.map((f) => ({ ...f, band90: [f.p5, f.p95] as [number, number], band50: [f.p25, f.p75] as [number, number] })),
    [sim.fan],
  );
  const years = sim.inputs.years;
  return (
    <>
      <ChartContainer config={cfg} className="w-full" style={{ height }}>
        <AreaChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
          <CartesianGrid vertical={false} strokeDasharray="2 4" />
          <XAxis
            dataKey="month"
            type="number"
            domain={[0, years * 12]}
            ticks={Array.from({ length: years + 1 }, (_, i) => i * 12)}
            tickFormatter={(v) => `${Number(v) / 12}y`}
            tickLine={false}
            axisLine={false}
            tickMargin={8}
          />
          <YAxis tickFormatter={(v) => compactInr(Number(v))} width={62} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
          <ChartTooltip cursor={{ stroke: "var(--rule)" }} content={<Tip />} />
          <Area dataKey="band90" stroke="none" fill="var(--color-band90)" fillOpacity={0.1} isAnimationActive={false} />
          <Area dataKey="band50" stroke="none" fill="var(--color-band50)" fillOpacity={0.2} isAnimationActive={false} />
          <Line dataKey="invested" stroke="var(--color-invested)" strokeWidth={1.25} strokeDasharray="2 4" dot={false} isAnimationActive={false} />
          <Line dataKey="fd" stroke="var(--color-fd)" strokeWidth={1.25} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
          <Line dataKey="nifty" stroke="var(--color-nifty)" strokeWidth={1.25} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
          <Line dataKey="p50" stroke="var(--color-p50)" strokeWidth={2.25} dot={false} isAnimationActive={false} />
        </AreaChart>
      </ChartContainer>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-muted-foreground">
        <span className="flex items-center gap-1.5"><span className="h-0.5 w-4 bg-chart-1" /> Median outcome</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-4 rounded-[2px] bg-chart-1/30" /> Middle 50%</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-4 rounded-[2px] bg-chart-1/12" /> 90% of outcomes</span>
        <span className="flex items-center gap-1.5"><span className="w-4 border-t border-dotted border-muted-foreground" /> Money you put in</span>
        <span className="flex items-center gap-1.5"><span className="w-4 border-t border-dashed border-chart-4" /> Fixed deposit at {pct(sim.summary.fd_rate, 1)}</span>
        <span className="flex items-center gap-1.5"><span className="w-4 border-t border-dashed border-chart-3" /> NIFTY 50 at {pct(sim.summary.nifty_rate, 1)}</span>
      </div>
    </>
  );
}

export function EndDistribution({ sim, height = 200 }: { sim: SimResult; height?: number }) {
  const inv = sim.summary.total_invested;
  const nearest = (v: number) => sim.hist.reduce((b, h) => (Math.abs(h.x - v) < Math.abs(b.x - v) ? h : b), sim.hist[0])?.x;
  return (
    <ChartContainer config={{ pct: { label: "% of outcomes", color: "var(--chart-1)" } }} className="w-full" style={{ height }}>
      <BarChart data={sim.hist} margin={{ left: 0, right: 8, top: 8, bottom: 0 }} barCategoryGap={1}>
        <CartesianGrid vertical={false} strokeDasharray="2 4" />
        <XAxis dataKey="x" tickFormatter={(v) => compactInr(Number(v))} tickLine={false} axisLine={false} minTickGap={40} tickMargin={8} />
        <YAxis tickFormatter={(v) => `${Number(v).toFixed(0)}%`} width={34} tickLine={false} axisLine={false} />
        <ChartTooltip
          cursor={{ fill: "var(--foreground)", fillOpacity: 0.04 }}
          content={({ active, payload }) =>
            active && payload?.length ? (
              <div className="rounded-md border border-border bg-popover px-3 py-2 text-[12px] shadow-sm">
                <div className="num font-medium">≈ {inr(Number(payload[0].payload.x))}</div>
                <div className="text-muted-foreground">{Number(payload[0].payload.pct).toFixed(2)}% of outcomes</div>
              </div>
            ) : null
          }
        />
        <Bar dataKey="pct" radius={[2, 2, 0, 0]} isAnimationActive={false}>
          {sim.hist.map((h) => (
            <Cell key={h.x} fill={h.x >= sim.summary.fd_final ? "var(--positive)" : h.x >= inv ? "var(--faint)" : "var(--negative)"} fillOpacity={0.75} />
          ))}
        </Bar>
        <ReferenceLine x={nearest(inv)} stroke="var(--foreground)" strokeDasharray="2 3" />
      </BarChart>
    </ChartContainer>
  );
}

export function SimFigures({ sim }: { sim: SimResult }) {
  const s = sim.summary;
  return (
    <Figures cols={6}>
      <Figure label="Expected value" size="lg" value={inr(s.expected_final)} sub={<Delta value={s.expected_gain}>{inrSigned(s.expected_gain)} on {inr(s.total_invested)}</Delta>} />
      <Figure label="Median outcome" value={inr(s.median_final)} sub={`${pct(s.median_annual_return)} a year`} />
      <Figure label="Worst case (5%)" value={inr(s.p5_final)} sub={`best case ${inr(s.p95_final)}`} />
      <Figure label="Chance of profit" value={pct(s.prob_profit, 0)} sub={`${pct(s.prob_loss_10, 0)} chance of losing 10%+`} />
      <Figure label="Beats fixed deposit" value={pct(s.prob_beat_fd, 0)} sub={`FD gives ${inr(s.fd_final)}`} />
      <Figure label="Beats NIFTY 50" value={pct(s.prob_beat_nifty, 0)} sub={`NIFTY expected ${inr(s.nifty_final)}`} />
    </Figures>
  );
}

function csv(sim: SimResult) {
  const head = ["Year", "Invested", "Worst 5%", "Lower quartile", "Median", "Upper quartile", "Best 5%", "Expected", "Median gain", "Median return", "Chance of profit", "Fixed deposit", "NIFTY expected"];
  const rows = sim.table.map((r) => [r.year, r.invested, r.p5, r.p25, r.median, r.p75, r.p95, r.expected, r.median_gain, r.median_return, r.prob_profit, r.fd, r.nifty].map((v) => (typeof v === "number" ? Math.round(v * 10000) / 10000 : v)));
  return [head, ...rows].map((r) => r.join(",")).join("\n");
}

export function ProjectionTable({ sim }: { sim: SimResult }) {
  const last = sim.table[sim.table.length - 1];
  function download() {
    const blob = new Blob([csv(sim)], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `projection-${sim.inputs.years}y.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  }
  return (
    <Section
      title="Year by year"
      description="Value of the investment at the end of each year. “Worst” and “Best” are the 5th and 95th percentile of the simulated outcomes."
      actions={
        <Button size="xs" variant="ghost" onClick={download}>
          <Download /> CSV
        </Button>
      }
    >
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Year</TableHead>
            <TableHead className="text-right">You put in</TableHead>
            <TableHead className="hidden text-right md:table-cell">Worst 5%</TableHead>
            <TableHead className="text-right">Median</TableHead>
            <TableHead className="hidden text-right md:table-cell">Best 5%</TableHead>
            <TableHead className="hidden text-right lg:table-cell">Expected</TableHead>
            <TableHead className="text-right">Median gain</TableHead>
            <TableHead className="text-right">Return</TableHead>
            <TableHead className="hidden text-right lg:table-cell">Chance of profit</TableHead>
            <TableHead className="hidden text-right xl:table-cell">Fixed deposit</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sim.table.map((r) => (
            <TableRow key={r.year} className={cn(r.year === last.year && "font-medium")}>
              <TableCell>{r.year}</TableCell>
              <TableCell className="text-right text-muted-foreground">{inr(r.invested)}</TableCell>
              <TableCell className="hidden text-right text-muted-foreground md:table-cell">{inr(r.p5)}</TableCell>
              <TableCell className="text-right">{inr(r.median)}</TableCell>
              <TableCell className="hidden text-right text-muted-foreground md:table-cell">{inr(r.p95)}</TableCell>
              <TableCell className="hidden text-right lg:table-cell">{inr(r.expected)}</TableCell>
              <TableCell className={cn("text-right", r.median_gain >= 0 ? "text-positive" : "text-negative")}>{inrSigned(r.median_gain)}</TableCell>
              <TableCell className={cn("text-right", r.median_return >= 0 ? "text-positive" : "text-negative")}>{pctSigned(r.median_return)}</TableCell>
              <TableCell className="hidden text-right lg:table-cell">{pct(r.prob_profit, 0)}</TableCell>
              <TableCell className="hidden text-right text-muted-foreground xl:table-cell">{inr(r.fd)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
        <TableFooter className="border-t border-rule bg-transparent">
          <TableRow className="hover:bg-transparent">
            <TableCell colSpan={2} className="text-[12px] text-muted-foreground">
              After {last.year} year{last.year > 1 ? "s" : ""}
            </TableCell>
            <TableCell className="hidden md:table-cell" />
            <TableCell className="text-right font-semibold">{inr(last.median)}</TableCell>
            <TableCell className="hidden md:table-cell" />
            <TableCell className="hidden lg:table-cell" />
            <TableCell colSpan={2} className="text-right text-[12px] text-muted-foreground">
              median outcome
            </TableCell>
            <TableCell className="hidden lg:table-cell" />
            <TableCell className="hidden xl:table-cell" />
          </TableRow>
        </TableFooter>
      </Table>
    </Section>
  );
}

export function BreakdownTable({ sim }: { sim: SimResult }) {
  const maxW = Math.max(...sim.breakdown.map((b) => b.weight));
  return (
    <Section title="Where the money goes" description="Each holding's share, model expected return and what it contributes to the portfolio's return">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Asset</TableHead>
            <TableHead className="w-40 text-right">Share</TableHead>
            <TableHead className="text-right">Amount</TableHead>
            <TableHead className="hidden text-right md:table-cell">Expected return</TableHead>
            <TableHead className="hidden text-right md:table-cell">Volatility</TableHead>
            <TableHead className="hidden text-right lg:table-cell">Adds to return</TableHead>
            <TableHead className="text-right">Projected value</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sim.breakdown.map((b) => (
            <TableRow key={b.symbol}>
              <TableCell>
                <div className="flex items-center gap-2">
                  <Swatch color={CLASS_COLOR[b.asset_class]} />
                  <span className="font-medium">{b.ticker}</span>
                </div>
                <div className="pl-4 text-[12px] text-muted-foreground">
                  {b.name} · {b.asset_class === "stock" ? b.sector : CLASS_LABEL[b.asset_class]}
                </div>
              </TableCell>
              <TableCell className="text-right">
                <div className="flex items-center justify-end gap-3">
                  <Meter value={b.weight} max={maxW} className="hidden w-16 sm:block" />
                  <span className="w-12">{pct(b.weight)}</span>
                </div>
              </TableCell>
              <TableCell className="text-right">{inr(b.amount)}</TableCell>
              <TableCell className="hidden text-right md:table-cell">{pct(b.expected_return)}</TableCell>
              <TableCell className="hidden text-right text-muted-foreground md:table-cell">{pct(b.volatility)}</TableCell>
              <TableCell className="hidden text-right text-muted-foreground lg:table-cell">{pct(b.contribution, 2)}</TableCell>
              <TableCell className="text-right">{inr(b.projected)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <p className="mt-3 text-[12px] text-faint">
        Portfolio: expected return {pct(sim.portfolio.expected_return)} a year · volatility {pct(sim.portfolio.volatility)} (next month {pct(sim.portfolio.next_month_volatility)}) · beta {num(sim.portfolio.beta)} · Sharpe {num(sim.portfolio.sharpe)}.
        “Projected value” compounds each asset at its own expected return, so it differs a little from the simulated median.
      </p>
    </Section>
  );
}
