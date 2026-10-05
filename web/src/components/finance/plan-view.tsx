"use client";

import * as React from "react";
import { Figure, Figures, Meter, Section, Swatch } from "@/components/kit";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CLASS_COLOR, CLASS_LABEL, inr, num, pct, shortDate, years } from "@/lib/format";
import type { PlanData } from "@/lib/types";
import { Composition, LimitNote, OutcomeRange } from "./shared";

export function PlanView({ data, actions, compact }: { data: PlanData; actions?: React.ReactNode; compact?: boolean }) {
  const e = data.evaluation;
  const m = e.mc.stats;
  const p = data.profile;
  const target = p.amount * Math.pow(1 + p.target_return_pct / 100, p.horizon_years);
  const totalInvested = data.plan.reduce((s, r) => s + r.invested, 0);
  const maxW = Math.max(...data.plan.map((r) => r.weight));

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <div className="label">Tomorrow&apos;s plan · {inr(p.amount)} · {p.horizon_years} yr · {p.risk} risk</div>
          <div className="mt-1.5 flex flex-wrap items-baseline gap-3">
            <h2 className={compact ? "display text-[1.6rem] leading-tight" : "display text-[2rem] leading-tight"}>{data.strategy}</h2>
            {data.strategy === data.recommended ? (
              <span className="rounded-[4px] border border-brand/40 px-1.5 py-0.5 text-[11px] font-medium tracking-[0.04em] text-brand uppercase">
                Recommended
              </span>
            ) : null}
          </div>
          <p className="mt-1 max-w-xl text-[13.5px] text-muted-foreground">{e.blurb}</p>
        </div>
        {actions}
      </div>

      <Figures cols={6}>
        <Figure label="Expected return" value={pct(e.stats.exp_return)} sub="per year" />
        <Figure label="Volatility" value={pct(e.stats.volatility)} sub={e.stats.near_term_vol != null ? `next month ${pct(e.stats.near_term_vol)}` : "per year"} />
        <Figure label="Chance of gain" value={pct(m.prob_positive, 0)} sub={`over ${p.horizon_years} yr`} />
        <Figure label={`${p.target_return_pct}% target`} value={pct(m.prob_target, 0)} sub="10,000 simulations" tone={m.prob_target != null && m.prob_target < 0.4 ? "caution" : null} />
        <Figure label="Drawdown" value={pct(m.exp_max_drawdown)} sub={`1 in 20: ${pct(m.p95_max_drawdown, 0)}`} />
        <Figure label="Stress tests" value={`${e.stress.filter((s) => s.survives).length} of ${e.stress.length}`} sub={`Sharpe ${num(e.stats.sharpe)} · β ${num(e.stats.beta)}`} />
      </Figures>

      <LimitNote ok={e.within_limits} breaches={e.breaches} risk={p.risk} />

      <div className="grid gap-6 2xl:grid-cols-[minmax(0,1fr)_320px]">
        <Section title="Allocation" description={`Whole shares at the close of ${shortDate(data.data_as_of)}, after 0.1% trading costs`}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Asset</TableHead>
                <TableHead className="w-36 text-right">Weight</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead className="hidden text-right 2xl:table-cell">Price</TableHead>
                <TableHead className="text-right">Shares</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.plan.map((r) => (
                <TableRow key={r.symbol}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Swatch color={CLASS_COLOR[r.asset_class]} />
                      <span className="font-medium">{r.ticker}</span>
                    </div>
                    <div className="pl-4 text-[12px] text-muted-foreground">
                      {r.name} · {r.asset_class === "stock" ? r.sector : CLASS_LABEL[r.asset_class]}
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-3">
                      <Meter value={r.weight} max={maxW} className="hidden w-16 sm:block" />
                      <span className="w-12">{pct(r.weight)}</span>
                    </div>
                  </TableCell>
                  {/* what the whole shares cost, so the rows add up to the total below */}
                  <TableCell className="text-right">{inr(r.invested)}</TableCell>
                  <TableCell className="hidden text-right text-muted-foreground 2xl:table-cell">{inr(r.price, 2)}</TableCell>
                  <TableCell className="text-right font-medium">{r.shares}</TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter className="border-t border-rule bg-transparent">
              <TableRow className="hover:bg-transparent">
                <TableCell className="font-medium">Total</TableCell>
                <TableCell className="text-right">100.0%</TableCell>
                <TableCell className="text-right font-medium">{inr(totalInvested)}</TableCell>
                <TableCell className="hidden 2xl:table-cell" />
                <TableCell className="text-right text-[12px] text-muted-foreground">cash left {inr(data.cash_left)}</TableCell>
              </TableRow>
            </TableFooter>
          </Table>
        </Section>

        <div className="grid gap-6 md:grid-cols-2 2xl:grid-cols-1 2xl:content-start">
          <Section title="Composition">
            <Composition rows={data.plan} />
          </Section>
          <Section title={`Value after ${years(p.horizon_years)}`} description="Simulated range of outcomes">
            <OutcomeRange low={m.worst_case_p5} median={m.median_final} high={m.best_case_p95} invested={p.amount} target={target} />
          </Section>
        </div>
      </div>
    </div>
  );
}
