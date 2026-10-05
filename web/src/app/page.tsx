"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Delta, Empty, Loading, Meter, Section } from "@/components/kit";
import { DashboardHero } from "@/components/dashboard-hero";
import { MarketOverviewCards } from "@/components/finance/market-views";
import { ClassTag, Composition, OutcomeRange } from "@/components/finance/shared";
import { PositionsTable, WalletSummary } from "@/components/finance/wallet-views";
import { useApp } from "@/lib/app-context";
import { api } from "@/lib/api";
import { inr, pct, years } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useData } from "@/lib/use-data";

const SEV: Record<string, string> = { high: "bg-negative", medium: "bg-caution", info: "bg-faint" };

export default function Overview() {
  const { state, wallet } = useApp();
  const market = useData(() => api.market(), []);
  const plan = useData(
    () => api.planFor("recommended"),
    [state?.recommended, state?.profile.amount, state?.profile.horizon_years, state?.profile.risk, state?.profile.target_return_pct],
    !!state?.profile_set,
  );
  const health = useData(() => api.walletHealth(), [wallet?.valuation.total_value], !!wallet?.valuation.positions.length);
  const p = plan.data;
  const issues = health.data?.issues ?? [];

  return (
    <div className="space-y-6">
      <DashboardHero asOf={state?.as_of} plan={p} planLoading={plan.loading} />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Section title="Market" description="NIFTY 50, volatility and the detected regime">
          {market.data ? <MarketOverviewCards o={market.data.overview} open cols={3} /> : <Loading label="Reading the market" />}
        </Section>

        <Section title="Portfolio" description="Demo money" actions={<CardLink href="/wallet">Manage</CardLink>}>
          {wallet ? <WalletSummary v={wallet.valuation} compact /> : <Loading />}
        </Section>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Section
          title="Tomorrow's plan"
          description={
            state?.profile_set && state.recommended
              ? `${state.recommended} · ${inr(state.profile.amount)} · ${years(state.profile.horizon_years)} · ${state.profile.risk} risk · ${state.profile.target_return_pct}% target`
              : "Set a profile to get a recommendation"
          }
          actions={p ? <CardLink href="/planner">Open in planner</CardLink> : null}
        >
          {p ? (
            <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_230px]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Asset</TableHead>
                    <TableHead className="hidden sm:table-cell">Class</TableHead>
                    <TableHead className="w-36 text-right">Weight</TableHead>
                    <TableHead className="text-right">Amount</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {p.plan.map((r) => (
                    <TableRow key={r.symbol}>
                      <TableCell className="font-medium">{r.ticker}</TableCell>
                      <TableCell className="hidden sm:table-cell">
                        <ClassTag cls={r.asset_class} />
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-3">
                          <Meter value={r.weight} max={Math.max(...p.plan.map((x) => x.weight))} color="var(--brand)" className="w-14" />
                          <span className="w-11">{pct(r.weight)}</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-right">{inr(r.invested)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="space-y-6">
                <div className="grid grid-cols-2 gap-x-4 gap-y-5">
                  <Stat label="Expected return" value={pct(p.evaluation.stats.exp_return)} />
                  <Stat label="Volatility" value={pct(p.evaluation.stats.volatility)} />
                  <Stat label="Chance of gain" value={pct(p.evaluation.mc.stats.prob_positive, 0)} />
                  <Stat label="Reach target" value={pct(p.evaluation.mc.stats.prob_target, 0)} />
                </div>
                <Composition rows={p.plan} />
              </div>
              <div className="rounded-xl border border-border bg-background/50 p-4 lg:col-span-2">
                <div className="label mb-1">Value after {years(p.profile.horizon_years)}</div>
                <OutcomeRange
                  low={p.evaluation.mc.stats.worst_case_p5}
                  median={p.evaluation.mc.stats.median_final}
                  high={p.evaluation.mc.stats.best_case_p95}
                  invested={p.profile.amount}
                  target={p.profile.amount * Math.pow(1 + p.profile.target_return_pct / 100, p.profile.horizon_years)}
                />
              </div>
            </div>
          ) : plan.loading ? (
            <Loading label="Building the plan" />
          ) : (
            <Empty
              title="No plan yet"
              action={
                <Link href="/planner" className={cn(buttonVariants({ size: "sm" }))}>
                  Set your profile
                </Link>
              }
            >
              Tell us the amount, horizon, risk tolerance and target, or describe them to the agent in plain words.
            </Empty>
          )}
        </Section>

        <Section title={issues.length ? "Needs attention" : "Health"} description={issues.length ? `${issues.length} things to review` : undefined}>
          {issues.length ? (
            <>
              <ul className="space-y-2">
                {issues.map((i, k) => (
                  <li key={k} className="flex gap-3 rounded-xl border border-border bg-background/50 px-3 py-2.5 text-[13px]">
                    <span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", SEV[i.severity])} />
                    <span className="text-muted-foreground">{i.message}</span>
                  </li>
                ))}
              </ul>
              <Link href="/wallet" className="mt-4 inline-flex items-center gap-1 text-[12.5px] font-medium hover:underline">
                Review fixes <ArrowRight className="size-3.5" />
              </Link>
            </>
          ) : wallet?.valuation.positions.length ? (
            <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
              <span className="size-1.5 rounded-full bg-positive" /> No stop-loss hits, drift or risk breaches.
            </p>
          ) : (
            <p className="text-[13px] text-muted-foreground">No holdings yet. Invest a plan to start tracking stop-losses, drift and risk.</p>
          )}
        </Section>
      </div>

      {wallet && wallet.valuation.positions.length ? (
        <Section
          title="Holdings"
          description={
            <>
              Marked to the latest close · <Delta value={wallet.valuation.pnl}>{pct(wallet.valuation.pnl_pct, 2)}</Delta> since start
            </>
          }
          actions={<CardLink href="/wallet">All positions</CardLink>}
        >
          <PositionsTable v={wallet.valuation} />
        </Section>
      ) : null}
    </div>
  );
}

function CardLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[12.5px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
    >
      {children} <ArrowRight className="size-3.5" />
    </Link>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className="num mt-1 text-[1.25rem] leading-none font-medium tracking-[-0.02em]">{value}</div>
    </div>
  );
}
