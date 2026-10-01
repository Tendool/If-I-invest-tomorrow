"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Delta, Empty, Loading, Meter, PageHeader, Section } from "@/components/kit";
import { MarketOverviewCards } from "@/components/finance/market-views";
import { ClassTag, Composition, OutcomeRange } from "@/components/finance/shared";
import { PositionsTable, WalletSummary } from "@/components/finance/wallet-views";
import { useApp } from "@/lib/app-context";
import { api } from "@/lib/api";
import { inr, pct, shortDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useData } from "@/lib/use-data";

const SEV: Record<string, string> = { high: "bg-negative", medium: "bg-caution", info: "bg-faint" };

export default function Overview() {
  const { state, wallet } = useApp();
  const market = useData(() => api.market(), []);
  const plan = useData(() => api.planFor("recommended"), [state?.recommended, state?.profile.amount], !!state?.profile_set);
  const health = useData(() => api.walletHealth(), [wallet?.valuation.total_value], !!wallet?.valuation.positions.length);

  return (
    <div className="space-y-14">
      <PageHeader
        eyebrow={state ? `Overview · close of ${shortDate(state.as_of)}` : "Overview"}
        title={
          <>
            If you invest <span className="italic">tomorrow</span>
          </>
        }
        description="What to buy, how much of each, and the probability that it reaches your goal — simulated, stress-tested and executable with demo money."
        actions={
          <>
            <Link href="/planner" className={cn(buttonVariants({ variant: "outline" }), "h-9 px-3.5")}>
              Build a plan
            </Link>
            <Link href="/agent" className={cn(buttonVariants(), "h-9 px-3.5")}>
              Ask the agent <ArrowRight />
            </Link>
          </>
        }
      />

      <Section title="Market" description="NIFTY 50, volatility and the detected regime">
        {market.data ? <MarketOverviewCards o={market.data.overview} open /> : <Loading label="Reading the market" />}
      </Section>

      <div className="grid gap-14 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Section
          title="Tomorrow's plan"
          description={
            state?.profile_set && state.recommended
              ? `${state.recommended} · ${inr(state.profile.amount)} · ${state.profile.horizon_years} yr · ${state.profile.risk} risk · ${state.profile.target_return_pct}% target`
              : "Set a profile to get a recommendation"
          }
          actions={
            plan.data ? (
              <Link href="/planner" className="flex items-center gap-1 text-[12.5px] font-medium hover:underline">
                Open in planner <ArrowRight className="size-3.5" />
              </Link>
            ) : null
          }
        >
          {plan.data ? (
            <div className="grid gap-10 md:grid-cols-[minmax(0,1fr)_240px]">
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
                  {plan.data.plan.map((r) => (
                    <TableRow key={r.symbol}>
                      <TableCell className="font-medium">{r.ticker}</TableCell>
                      <TableCell className="hidden sm:table-cell">
                        <ClassTag cls={r.asset_class} />
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-3">
                          <Meter value={r.weight} max={Math.max(...plan.data!.plan.map((x) => x.weight))} className="w-14" />
                          <span className="w-11">{pct(r.weight)}</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-right">{inr(r.target_amount)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="space-y-8">
                <div className="grid grid-cols-2 gap-x-4 gap-y-5">
                  <Stat label="Expected return" value={pct(plan.data.evaluation.stats.exp_return)} />
                  <Stat label="Volatility" value={pct(plan.data.evaluation.stats.volatility)} />
                  <Stat label="Chance of gain" value={pct(plan.data.evaluation.mc.stats.prob_positive, 0)} />
                  <Stat label="Reach target" value={pct(plan.data.evaluation.mc.stats.prob_target, 0)} />
                </div>
                <Composition rows={plan.data.plan} />
              </div>
              <div className="md:col-span-2">
                <div className="label mb-1">Value after {plan.data.profile.horizon_years} years</div>
                <OutcomeRange
                  low={plan.data.evaluation.mc.stats.worst_case_p5}
                  median={plan.data.evaluation.mc.stats.median_final}
                  high={plan.data.evaluation.mc.stats.best_case_p95}
                  invested={plan.data.profile.amount}
                  target={plan.data.profile.amount * Math.pow(1 + plan.data.profile.target_return_pct / 100, plan.data.profile.horizon_years)}
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

        <div className="space-y-12">
          <Section title="Portfolio" actions={<Link href="/wallet" className="text-[12.5px] font-medium hover:underline">Manage</Link>}>
            {wallet ? <WalletSummary v={wallet.valuation} compact /> : <Loading />}
          </Section>

          {health.data && health.data.issues.length ? (
            <Section title="Needs attention">
              <ul className="divide-y divide-border">
                {health.data.issues.map((i, k) => (
                  <li key={k} className="flex gap-3 py-2.5 text-[13px]">
                    <span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", SEV[i.severity])} />
                    <span className="text-muted-foreground">{i.message}</span>
                  </li>
                ))}
              </ul>
              <Link href="/wallet" className="mt-3 inline-flex items-center gap-1 text-[12.5px] font-medium hover:underline">
                Review fixes <ArrowRight className="size-3.5" />
              </Link>
            </Section>
          ) : wallet?.valuation.positions.length ? (
            <Section title="Health">
              <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
                <span className="size-1.5 rounded-full bg-positive" /> No stop-loss hits, drift or risk breaches.
              </p>
            </Section>
          ) : null}
        </div>
      </div>

      {wallet && wallet.valuation.positions.length ? (
        <Section
          title="Holdings"
          description={
            <>
              Marked to the latest close ·{" "}
              <Delta value={wallet.valuation.pnl}>{pct(wallet.valuation.pnl_pct, 2)}</Delta> since start
            </>
          }
        >
          <PositionsTable v={wallet.valuation} />
        </Section>
      ) : null}
    </div>
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
