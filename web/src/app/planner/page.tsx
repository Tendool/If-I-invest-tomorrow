"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Slider } from "@/components/ui/slider";
import { Empty, Loading, PageHeader, Segmented, Swatch, TabStrip } from "@/components/kit";
import { MonteCarloView } from "@/components/finance/mc-view";
import { PlanView } from "@/components/finance/plan-view";
import { BacktestView, StressView, TimingView } from "@/components/finance/risk-views";
import { StrategiesView } from "@/components/finance/strategies-view";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { inr, STRATEGY_COLOR } from "@/lib/format";
import type { Risk, StrategiesData } from "@/lib/types";
import { useData } from "@/lib/use-data";
import { cn } from "@/lib/utils";

type Tab = "plan" | "strategies" | "montecarlo" | "stress" | "timing" | "backtest";
const TABS: { value: Tab; label: string }[] = [
  { value: "plan", label: "Plan" },
  { value: "strategies", label: "Strategies" },
  { value: "montecarlo", label: "Monte Carlo" },
  { value: "stress", label: "Stress tests" },
  { value: "timing", label: "Now, wait or SIP" },
  { value: "backtest", label: "Backtest" },
];

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

export default function PlannerPage() {
  const { state, setState, run, announce } = useApp();
  const [amount, setAmount] = React.useState("200000");
  const [horizon, setHorizon] = React.useState<"1" | "3" | "5">("3");
  const [risk, setRisk] = React.useState<Risk>("medium");
  const [target, setTarget] = React.useState(12);
  const [sectors, setSectors] = React.useState<string[]>([]);
  const [board, setBoard] = React.useState<StrategiesData | null>(null);
  const [building, setBuilding] = React.useState(false);
  const [strategy, setStrategy] = React.useState("");
  const [tab, setTab] = React.useState<Tab>("plan");
  const [years, setYears] = React.useState<"1" | "2" | "3" | "4" | "5">("3");
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [investing, setInvesting] = React.useState(false);
  const hydrated = React.useRef(false);

  React.useEffect(() => {
    if (state && !hydrated.current) {
      hydrated.current = true;
      const p = state.profile;
      setAmount(String(p.amount));
      setHorizon(String(p.horizon_years) as "1" | "3" | "5");
      setRisk(p.risk);
      setTarget(p.target_return_pct);
      setSectors(p.preferred_sectors);
      if (state.profile_set) void build(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  async function build(save = true) {
    setBuilding(true);
    const out = await run(async () => {
      if (save) {
        const amt = Number(amount.replace(/,/g, ""));
        if (!(amt >= 1000)) throw new Error("Enter an amount of at least ₹1,000");
        setState(await api.setProfile({ amount: amt, horizon_years: Number(horizon), risk, target_return_pct: target, preferred_sectors: sectors }));
      }
      return api.plan();
    });
    setBuilding(false);
    if (out) {
      setBoard(out.strategies);
      setState(out.state);
      setStrategy((cur) => (save ? out.strategies.recommended : cur || out.strategies.recommended));
    }
  }

  const sel = strategy || board?.recommended || "";
  const on = (t: Tab) => !!board && tab === t;
  // `board` is a new object after every build, so every view re-fetches for the new inputs even when the
  // recommended strategy keeps its name (changing only the horizon, risk, target or sectors)
  const plan = useData(() => api.planFor(sel), [sel, board, state?.profile.amount], on("plan"));
  const mc = useData(() => api.monteCarlo(sel), [sel, board], on("montecarlo"));
  const stress = useData(() => api.stress(sel), [sel, board], on("stress"));
  const timing = useData(() => api.timing(sel), [sel, board], on("timing"));
  const backtest = useData(() => api.backtest(Number(years)), [years, board], on("backtest"));
  const frontier = useData(() => api.frontier(), [board, state?.profile.risk], on("strategies"));

  async function invest() {
    setInvesting(true);
    const r = await run(() => api.invest(sel));
    setInvesting(false);
    setConfirmOpen(false);
    if (r) announce(r);
  }

  const amt = Number(amount.replace(/,/g, "")) || 0;
  const toggleSector = (s: string) => setSectors((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));
  const block = (d: { loading: boolean; error: string | null; data: unknown }, label: string, node: React.ReactNode) =>
    d.error ? <Empty title="Could not load">{d.error}</Empty> : d.loading && !d.data ? <Loading label={label} /> : d.data ? node : null;

  return (
    <div>
      <PageHeader
        eyebrow="Planner"
        title="Design tomorrow's investment"
        description="Five optimised strategies for your profile, each simulated ten thousand times and stress-tested against shocks and past crashes."
      />

      <div className="grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-32 lg:self-start">
          <div className="card-x space-y-5 p-5">
            <Field label="Amount">
              <div className="flex items-center rounded-xl border border-border bg-background/70 focus-within:ring-3 focus-within:ring-brand/15 focus-within:border-foreground/40">
                <span className="pl-3 text-[15px] text-faint">₹</span>
                <input
                  inputMode="numeric"
                  value={amt ? amt.toLocaleString("en-IN") : ""}
                  onChange={(e) => setAmount(e.target.value.replace(/[^\d]/g, ""))}
                  className="num h-10 w-full bg-transparent px-2 text-[15px] font-medium outline-none"
                />
              </div>
              <div className="flex gap-3 text-[12px]">
                {[50000, 100000, 500000, 1000000].map((v) => (
                  <button key={v} type="button" onClick={() => setAmount(String(v))} className={cn("hover:text-foreground", amt === v ? "font-medium text-foreground" : "text-muted-foreground")}>
                    {v >= 100000 ? `${v / 100000}L` : `${v / 1000}K`}
                  </button>
                ))}
              </div>
            </Field>
            <Field label="Horizon">
              <Segmented className="w-full" value={horizon} onChange={setHorizon} options={(["1", "3", "5"] as const).map((y) => ({ value: y, label: `${y} year${y === "1" ? "" : "s"}` }))} />
            </Field>
            <Field label="Risk tolerance">
              <Segmented className="w-full" value={risk} onChange={setRisk} options={(["low", "medium", "high"] as const).map((r) => ({ value: r, label: r[0].toUpperCase() + r.slice(1) }))} />
            </Field>
            <Field label="Target return" hint={<span className="num font-medium">{target.toFixed(1)}% a year</span>}>
              <Slider className="pt-1" min={4} max={30} step={0.5} value={[target]} onValueChange={(v) => setTarget(Array.isArray(v) ? v[0] : (v as number))} />
              <div className="flex justify-between text-[11px] text-faint">
                <span>4%</span>
                <span>30%</span>
              </div>
            </Field>
            <Field label="Preferred sectors" hint={sectors.length ? <button className="text-muted-foreground hover:text-foreground" onClick={() => setSectors([])}>Clear</button> : <span className="text-faint">Any</span>}>
              <div className="flex flex-wrap gap-1.5">
                {(state?.sectors ?? []).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => toggleSector(s)}
                    className={cn(
                      "rounded-[4px] border px-2 py-0.5 text-[12px] transition-colors",
                      sectors.includes(s) ? "border-foreground bg-foreground text-background" : "border-rule text-muted-foreground hover:border-foreground/40 hover:text-foreground",
                    )}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </Field>
            <Button className="cta-glow h-10 w-full text-[13.5px]" onClick={() => void build(true)} disabled={building}>
              {building ? "Optimising and simulating…" : board ? "Update plan" : "Build plan"}
            </Button>
          </div>
        </aside>

        <div className="min-w-0">
          {!board ? (
            building ? (
              <Loading label="Optimising five strategies and running 50,000 simulated paths" className="min-h-96" />
            ) : (
              <Empty title="Your plan will appear here">Set the amount, horizon, risk and target on the left, then build the plan.</Empty>
            )
          ) : (
            <div className="relative space-y-8" aria-busy={building}>
              {building ? (
                // the shown plan is for the previous inputs while a new one is computed: veil it so it is not read or invested
                <div className="absolute -inset-2 z-20 bg-background/75 backdrop-blur-[2px]">
                  <div className="sticky top-1/3">
                    <Loading label="Re-optimising for your new inputs" />
                  </div>
                </div>
              ) : null}
              <div className="flex flex-wrap items-center gap-x-1 gap-y-2">
                {board.strategies.map((s) => (
                  <button
                    key={s.strategy}
                    onClick={() => setStrategy(s.strategy)}
                    className={cn(
                      "flex items-center gap-2 rounded-md border px-3 py-1.5 text-[12.5px] transition-colors",
                      sel === s.strategy ? "border-foreground bg-surface font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <Swatch color={STRATEGY_COLOR[s.strategy]} />
                    {s.strategy}
                    {s.recommended ? <span className="text-[10px] font-semibold tracking-[0.06em] text-brand uppercase">Rec</span> : null}
                  </button>
                ))}
              </div>

              <TabStrip tabs={TABS} value={tab} onChange={setTab} />

              <div className="pt-2">
                {tab === "plan"
                  ? block(
                      plan,
                      "Building the plan",
                      plan.data ? (
                        <PlanView
                          data={plan.data}
                          actions={
                            <Button className="cta-glow h-9 px-4" onClick={() => setConfirmOpen(true)} disabled={building}>
                              Invest this plan
                            </Button>
                          }
                        />
                      ) : null,
                    )
                  : null}
                {tab === "strategies" ? (
                  <StrategiesView data={board} frontier={frontier.data} selected={sel} onSelect={(n) => { setStrategy(n); setTab("plan"); }} />
                ) : null}
                {tab === "montecarlo" ? block(mc, "Loading the simulation", mc.data ? <MonteCarloView data={mc.data} /> : null) : null}
                {tab === "stress" ? block(stress, "Running shock scenarios", stress.data ? <StressView data={stress.data} /> : null) : null}
                {tab === "timing" ? block(timing, "Simulating timing options", timing.data ? <TimingView data={timing.data} /> : null) : null}
                {tab === "backtest" ? (
                  <div className="space-y-6">
                    <div className="flex items-center gap-3">
                      <span className="label">Window</span>
                      <Segmented size="sm" value={years} onChange={setYears} options={(["1", "2", "3", "4", "5"] as const).map((y) => ({ value: y, label: `${y}y` }))} />
                    </div>
                    {block(backtest, "Back-testing", backtest.data ? <BacktestView data={backtest.data} amount={amt || 100000} /> : null)}
                  </div>
                ) : null}
              </div>
            </div>
          )}
        </div>
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Invest the {sel} plan?</DialogTitle>
            <DialogDescription>
              Buys {plan.data ? `${plan.data.plan.length} assets worth about ${inr(plan.data.plan.reduce((s, r) => s + r.invested, 0))}` : "the plan"} in your
              demo portfolio at the latest close, including brokerage and slippage. No real money is used.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => void invest()} disabled={investing}>
              {investing ? "Placing orders…" : "Invest"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
