"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { Loading, PageHeader, Section, Segmented } from "@/components/kit";
import { EquityChart, HealthCard, OrdersCard, PendingCard, PositionsTable, TradesTable, WalletSummary } from "@/components/finance/wallet-views";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import type { ActionResponse, Artifact, HealthData } from "@/lib/types";
import { cn } from "@/lib/utils";

function Action({ title, body, onClick, disabled, busy, primary }: { title: string; body: string; onClick: () => void; disabled?: boolean; busy?: boolean; primary?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "group flex flex-col items-start rounded-lg border p-4 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-45",
        primary ? "border-foreground bg-foreground text-background" : "border-border bg-surface hover:border-foreground/40",
      )}
    >
      <span className="text-[13.5px] font-semibold">{busy ? "Working…" : title}</span>
      <span className={cn("mt-1 text-[12.5px] leading-snug", primary ? "text-background/70" : "text-muted-foreground")}>{body}</span>
    </button>
  );
}

export default function WalletPage() {
  const { wallet, state, setState, apply, run, announce, refresh } = useApp();
  const [busy, setBusy] = React.useState<string | null>(null);
  const [health, setHealth] = React.useState<HealthData | null>(null);
  const [lastOrders, setLastOrders] = React.useState<Artifact | null>(null);
  const [tradeOpen, setTradeOpen] = React.useState(false);
  const [fundsOpen, setFundsOpen] = React.useState(false);
  const [resetOpen, setResetOpen] = React.useState(false);
  const [side, setSide] = React.useState<"BUY" | "SELL">("BUY");
  const [asset, setAsset] = React.useState("");
  const [by, setBy] = React.useState<"amt" | "qty">("amt");
  const [val, setVal] = React.useState("");
  const [funds, setFunds] = React.useState("100000");
  const [tickers, setTickers] = React.useState<string[]>([]);

  React.useEffect(() => {
    api.assets().then((a) => setTickers(a.map((x) => x.ticker))).catch(() => undefined);
  }, []);

  async function act(key: string, fn: () => Promise<ActionResponse>) {
    setBusy(key);
    const r = await run(fn);
    setBusy(null);
    if (r) {
      announce(r);
      const o = r.artifacts.find((a) => a.kind === "orders");
      setLastOrders(o ?? null);
      setHealth(null);
    }
  }

  async function checkHealth() {
    setBusy("health");
    const h = await run(() => api.walletHealth());
    setBusy(null);
    if (h) setHealth(h);
  }

  async function toggleAutopilot(on: boolean) {
    const s = await run(() => api.setAutopilot(on));
    if (!s) return;
    setState(s);
    if (on) await act("auto", () => api.autopilotRun());
  }

  async function submitTrade() {
    const n = Number(val.replace(/,/g, ""));
    if (!asset || !(n > 0)) return;
    setTradeOpen(false);
    setVal("");
    await act("trade", () => api.trade({ side, asset, ...(by === "qty" ? { quantity: Math.floor(n) } : { amount_rs: n }) }));
  }

  if (!wallet) return <Loading label="Loading portfolio" />;
  const v = wallet.valuation;
  const has = v.positions.length > 0;

  return (
    <div className="space-y-12">
      <PageHeader
        eyebrow="Portfolio · demo money"
        title="Your portfolio"
        description="Orders fill at the latest close with 0.05% brokerage and 0.05% slippage. Nothing here touches a real account."
        actions={
          <>
            <Button variant="ghost" className="h-9" onClick={() => setFundsOpen(true)}>
              Add funds
            </Button>
            <Button variant="ghost" className="h-9 text-muted-foreground" onClick={() => setResetOpen(true)}>
              Reset
            </Button>
            <Button className="h-9 px-4" onClick={() => { setSide("BUY"); setTradeOpen(true); }}>
              Trade
            </Button>
          </>
        }
      />

      <WalletSummary v={v} />

      {wallet.pending ? (
        <PendingCard
          p={wallet.pending}
          busy={busy !== null}
          onConfirm={async () => {
            setBusy("confirm");
            const r = await run(() => api.confirm(), "Orders executed");
            setBusy(null);
            if (r) apply(r);
          }}
          onCancel={async () => {
            setBusy("cancel");
            const r = await run(() => api.cancel(), "Staged orders discarded");
            setBusy(null);
            if (r) apply(r);
          }}
        />
      ) : null}

      <Section
        title="Management"
        description="The agent can do all of this from chat too. A click here is an explicit instruction and executes immediately."
        actions={
          <label className="flex cursor-pointer items-center gap-2.5 text-[12.5px] text-muted-foreground">
            Autopilot
            <Switch size="sm" checked={!!state?.autopilot} onCheckedChange={toggleAutopilot} aria-label="Autopilot" />
          </label>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Action primary title="Invest the plan" body="Buy the recommended plan for your profile." onClick={() => void act("invest", () => api.invest())} disabled={busy !== null} busy={busy === "invest"} />
          <Action title="Auto-manage" body="Sell stop-losses, trim drift, de-risk, deploy idle cash." onClick={() => void act("auto", () => api.autoManage())} disabled={busy !== null || !has} busy={busy === "auto"} />
          <Action title="Rebalance" body="Bring holdings back to the selected strategy's weights." onClick={() => void act("rebalance", () => api.rebalance())} disabled={busy !== null || !has} busy={busy === "rebalance"} />
          <Action title="Health check" body="Review the portfolio without trading." onClick={() => void checkHealth()} disabled={busy !== null} busy={busy === "health"} />
        </div>
        <p className="mt-3 text-[12px] text-faint">
          Autopilot runs the same review the moment it is switched on and after every market-data refresh.
        </p>
      </Section>

      {health ? <HealthCard d={health} busy={busy !== null} onApply={health.orders.length ? () => void act("auto", () => api.autoManage()) : undefined} /> : null}
      {lastOrders && lastOrders.kind === "orders" ? <OrdersCard d={lastOrders.data} /> : null}

      <Section title="Holdings" description={has ? `${v.positions.length} positions, marked to the latest close` : undefined}>
        <PositionsTable v={v} busy={busy} onSell={(ticker) => void act("sell-" + ticker, () => api.trade({ side: "SELL", asset: ticker }))} />
      </Section>

      <div className="grid gap-12 xl:grid-cols-2">
        <Section title="Value over time">
          <EquityChart w={wallet} />
        </Section>
        <Section title="Trade history" description={wallet.trades?.length ? `${wallet.trades.length} most recent` : undefined}>
          <TradesTable trades={wallet.trades ?? []} />
        </Section>
      </div>

      <Dialog open={tradeOpen} onOpenChange={setTradeOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>New order</DialogTitle>
            <DialogDescription>Executes immediately at the latest close, with demo money.</DialogDescription>
          </DialogHeader>
          <div className="space-y-5 py-1">
            <Segmented className="w-full" value={side} onChange={setSide} options={[{ value: "BUY", label: "Buy" }, { value: "SELL", label: "Sell" }]} />
            <div className="space-y-1.5">
              <div className="label">Asset</div>
              <input
                list="tickers"
                value={asset}
                onChange={(e) => setAsset(e.target.value.toUpperCase())}
                placeholder="TCS, GOLDBEES, NIFTYBEES…"
                className="h-10 w-full rounded-md border border-rule bg-surface px-3 text-[14px] outline-none placeholder:text-faint focus:border-foreground/40"
              />
              <datalist id="tickers">
                {tickers.map((t) => (
                  <option key={t} value={t} />
                ))}
              </datalist>
            </div>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="label">{by === "amt" ? "Amount" : "Shares"}</span>
                <Segmented size="sm" value={by} onChange={setBy} options={[{ value: "amt", label: "₹" }, { value: "qty", label: "Qty" }]} />
              </div>
              <input
                inputMode="numeric"
                value={val}
                onChange={(e) => setVal(e.target.value.replace(/[^\d]/g, ""))}
                placeholder={by === "amt" ? "25,000" : "10"}
                className="num h-10 w-full rounded-md border border-rule bg-surface px-3 text-[14px] outline-none placeholder:text-faint focus:border-foreground/40"
              />
              {side === "SELL" ? <p className="text-[12px] text-faint">To sell a whole position, use Sell in the holdings table.</p> : null}
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setTradeOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => void submitTrade()} disabled={!asset || !val}>
              Place {side === "BUY" ? "buy" : "sell"} order
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={fundsOpen} onOpenChange={setFundsOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Add demo funds</DialogTitle>
            <DialogDescription>Top up the virtual cash balance.</DialogDescription>
          </DialogHeader>
          <div className="flex items-center rounded-md border border-rule bg-surface focus-within:border-foreground/40">
            <span className="pl-3 text-faint">₹</span>
            <input inputMode="numeric" value={funds ? Number(funds).toLocaleString("en-IN") : ""} onChange={(e) => setFunds(e.target.value.replace(/[^\d]/g, ""))} className="num h-10 w-full bg-transparent px-2 text-[14px] outline-none" />
          </div>
          <DialogFooter>
            <Button
              onClick={async () => {
                const r = await run(() => api.addFunds(Number(funds)), "Funds added");
                if (r) apply(r);
                setFundsOpen(false);
              }}
            >
              Add funds
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={resetOpen} onOpenChange={setResetOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Reset the portfolio?</DialogTitle>
            <DialogDescription>Removes every holding and trade and restores ₹10,00,000 of virtual cash.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setResetOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={async () => {
                const r = await run(() => api.resetWallet(), "Portfolio reset");
                if (r) {
                  apply(r);
                  setHealth(null);
                  setLastOrders(null);
                  void refresh();
                }
                setResetOpen(false);
              }}
            >
              Reset
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
