"use client";

import * as React from "react";
import { Area, AreaChart, CartesianGrid, ReferenceLine, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Delta, Empty, Figure, Figures, Meter } from "@/components/kit";
import { cn } from "@/lib/utils";
import { compactInr, inr, inrSigned, pct, pctSigned, toneName, toneOf } from "@/lib/format";
import type { HealthData, OrderRow, OrdersData, PendingOrders, SipRow, Trade, Valuation, WalletData } from "@/lib/types";

export function Side({ side }: { side: "BUY" | "SELL" }) {
  return (
    <span className={cn("text-[11px] font-semibold tracking-[0.06em]", side === "BUY" ? "text-positive" : "text-negative")}>{side}</span>
  );
}

export function WalletSummary({ v, compact }: { v: Valuation; compact?: boolean }) {
  if (compact) {
    return (
      <div>
        <div className="label">Portfolio value</div>
        <div className="display num mt-1 text-[2.4rem] leading-none">{inr(v.total_value)}</div>
        <div className="mt-2 text-[13px]">
          <Delta value={v.pnl}>
            {inrSigned(v.pnl)} ({pctSigned(v.pnl_pct, 2)})
          </Delta>
          <span className="text-muted-foreground"> since start</span>
        </div>
        <div className="mt-5 grid grid-cols-2 gap-4 border-t border-rule pt-4">
          <div>
            <div className="label">Cash</div>
            <div className="num mt-1 text-[15px] font-medium">{inr(v.cash)}</div>
          </div>
          <div>
            <div className="label">Invested</div>
            <div className="num mt-1 text-[15px] font-medium">{inr(v.invested_value)}</div>
            <div className="text-[12px] text-muted-foreground">{v.positions.length} positions</div>
          </div>
        </div>
      </div>
    );
  }
  return (
    <Figures cols={5}>
      <Figure label="Portfolio value" size="lg" value={inr(v.total_value)} sub={<Delta value={v.pnl}>{inrSigned(v.pnl)} ({pctSigned(v.pnl_pct, 2)})</Delta>} />
      <Figure label="Cash" value={inr(v.cash)} sub={`${pct(v.cash / Math.max(v.total_value, 1), 0)} of portfolio`} />
      <Figure label="Invested" value={inr(v.invested_value)} sub={`${v.positions.length} positions`} />
      <Figure label="Unrealised P&L" value={inrSigned(v.positions.reduce((s, p) => s + p.pnl, 0))} tone={toneName(v.positions.reduce((s, p) => s + p.pnl, 0))} />
      <Figure label="Starting capital" value={inr(v.starting_cash)} sub="virtual money" />
    </Figures>
  );
}

export function PositionsTable({ v, onSell, busy }: { v: Valuation; onSell?: (ticker: string) => void; busy?: string | null }) {
  if (!v.positions.length) return <Empty title="No holdings yet">Build a plan and invest it, or ask the agent to invest for you.</Empty>;
  const maxW = Math.max(...v.positions.map((p) => p.value));
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Holding</TableHead>
          <TableHead className="text-right">Qty</TableHead>
          <TableHead className="hidden text-right md:table-cell">Avg cost</TableHead>
          <TableHead className="text-right">Price</TableHead>
          <TableHead className="text-right">Value</TableHead>
          <TableHead className="hidden w-36 text-right lg:table-cell">Weight</TableHead>
          <TableHead className="text-right">P&amp;L</TableHead>
          {onSell ? <TableHead className="w-16" /> : null}
        </TableRow>
      </TableHeader>
      <TableBody>
        {v.positions.map((p) => (
          <TableRow key={p.symbol} className="group">
            <TableCell>
              <div className="font-medium">{p.ticker}</div>
              <div className="text-[12px] text-muted-foreground">
                {p.name} · {p.sector}
              </div>
            </TableCell>
            <TableCell className="text-right">{p.qty}</TableCell>
            <TableCell className="hidden text-right text-muted-foreground md:table-cell">{inr(p.avg_cost, 2)}</TableCell>
            <TableCell className="text-right">{inr(p.price, 2)}</TableCell>
            <TableCell className="text-right font-medium">{inr(p.value)}</TableCell>
            <TableCell className="hidden lg:table-cell">
              <div className="flex items-center justify-end gap-3">
                <Meter value={p.value} max={maxW} className="w-16" />
                <span className="w-10 text-right">{pct(p.value / Math.max(v.invested_value, 1), 0)}</span>
              </div>
            </TableCell>
            <TableCell className={cn("text-right", toneOf(p.pnl))}>
              <div>{inrSigned(p.pnl)}</div>
              <div className="text-[11.5px]">{pctSigned(p.pnl_pct, 2)}</div>
            </TableCell>
            {onSell ? (
              <TableCell className="text-right">
                <Button
                  size="xs"
                  variant="ghost"
                  disabled={!!busy}
                  className="text-muted-foreground opacity-60 group-hover:opacity-100 hover:text-negative"
                  onClick={() => onSell(p.ticker)}
                >
                  Sell
                </Button>
              </TableCell>
            ) : null}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function OrdersTable({ orders }: { orders: OrderRow[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-14">Side</TableHead>
          <TableHead>Asset</TableHead>
          <TableHead className="text-right">Qty</TableHead>
          <TableHead className="text-right">Price</TableHead>
          <TableHead className="text-right">Value</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {orders.map((o, i) => (
          <TableRow key={`${o.symbol}-${i}`}>
            <TableCell>
              <Side side={o.side} />
            </TableCell>
            <TableCell>
              <span className="font-medium">{o.ticker}</span> <span className="text-[12px] text-muted-foreground">{o.name}</span>
            </TableCell>
            <TableCell className="text-right">{o.qty}</TableCell>
            <TableCell className="text-right text-muted-foreground">{inr(o.price, 2)}</TableCell>
            <TableCell className="text-right">{inr(o.value)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function Notice({ tone, title, meta, children, actions }: { tone: "caution" | "positive" | "neutral"; title: string; meta?: React.ReactNode; children: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className={cn("rounded-2xl border bg-card shadow-[var(--shadow-card)]", tone === "caution" ? "border-caution/40" : tone === "positive" ? "border-positive/35" : "border-border")}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3">
        <div className="flex items-center gap-2.5">
          <span className={cn("size-1.5 rounded-full", tone === "caution" ? "bg-caution" : tone === "positive" ? "bg-positive" : "bg-faint")} />
          <span className="text-[13px] font-semibold">{title}</span>
          {meta ? <span className="text-[12.5px] text-muted-foreground">{meta}</span> : null}
        </div>
        {actions}
      </div>
      <div className="px-5 py-3">{children}</div>
    </div>
  );
}

export function PendingCard({ p, onConfirm, onCancel, busy }: { p: PendingOrders; onConfirm?: () => void; onCancel?: () => void; busy?: boolean }) {
  return (
    <Notice
      tone="caution"
      title="Orders awaiting your confirmation"
      meta={`${p.label} · buys ${inr(p.buy_cost)}${p.sell_proceeds ? ` · sells ${inr(p.sell_proceeds)}` : ""}`}
      actions={
        onConfirm ? (
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>
              Discard
            </Button>
            <Button size="sm" onClick={onConfirm} disabled={busy}>
              Confirm orders
            </Button>
          </div>
        ) : null
      }
    >
      <OrdersTable orders={p.orders} />
    </Notice>
  );
}

export function OrdersCard({ d }: { d: OrdersData }) {
  return (
    <Notice
      tone={d.executed ? "positive" : "caution"}
      title={d.executed ? "Executed with demo money" : "Staged, awaiting confirmation"}
      meta={`${d.label} · portfolio ${inr(d.total_value)} · cash ${inr(d.cash)}`}
    >
      <OrdersTable orders={d.orders} />
    </Notice>
  );
}

const SEV: Record<string, string> = { high: "bg-negative", medium: "bg-caution", info: "bg-faint" };
const CODE: Record<string, string> = {
  STOP_LOSS: "Stop-loss",
  DRIFT: "Concentration",
  RISK_BREACH: "Risk limit",
  BEAR_REGIME: "Market regime",
  IDLE_CASH: "Idle cash",
};

export function HealthCard({ d, onApply, busy }: { d: HealthData; onApply?: () => void; busy?: boolean }) {
  const healthy = d.issues.length === 0;
  return (
    <Notice
      tone={healthy ? "positive" : "caution"}
      title={healthy ? "Portfolio is healthy" : `${d.issues.length} item${d.issues.length > 1 ? "s" : ""} need attention`}
      meta={`Regime: ${d.regime}`}
      actions={
        d.orders.length && onApply ? (
          <Button size="sm" onClick={onApply} disabled={busy}>
            Apply {d.orders.length} trade{d.orders.length > 1 ? "s" : ""}
          </Button>
        ) : null
      }
    >
      {d.metrics && Object.keys(d.metrics).length ? (
        <div className="mb-3 flex flex-wrap gap-x-8 gap-y-2 text-[12.5px]">
          <span className="text-muted-foreground">Expected return <span className="num font-medium text-foreground">{pct(d.metrics.exp_return)}</span></span>
          <span className="text-muted-foreground">
            Volatility <span className={cn("num font-medium", d.metrics.volatility > d.metrics.vol_limit ? "text-negative" : "text-foreground")}>{pct(d.metrics.volatility)}</span>
            <span className="text-faint"> / limit {pct(d.metrics.vol_limit, 0)}</span>
          </span>
          <span className="text-muted-foreground">Beta <span className="num font-medium text-foreground">{d.metrics.beta?.toFixed(2)}</span></span>
          <span className="text-muted-foreground">Equity <span className="num font-medium text-foreground">{pct(d.metrics.equity_share, 0)}</span></span>
        </div>
      ) : null}
      {healthy ? (
        <p className="text-[13px] text-muted-foreground">No stop-loss hits, no concentration drift, risk within your limits. Nothing to do.</p>
      ) : (
        <ul className="divide-y divide-border">
          {d.issues.map((i, k) => (
            <li key={k} className="flex items-start gap-3 py-2 text-[13px]">
              <span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", SEV[i.severity])} />
              <span className="w-28 shrink-0 font-medium">{CODE[i.code] ?? i.code}</span>
              <span className="text-muted-foreground">{i.message}</span>
            </li>
          ))}
        </ul>
      )}
      {d.orders.length ? (
        <div className="mt-3 border-t border-border pt-3">
          <div className="label mb-1">Proposed trades · {d.label.replace("auto-manage: ", "")}</div>
          <OrdersTable orders={d.orders} />
        </div>
      ) : null}
    </Notice>
  );
}

export function SipsTable({ sips, onStop, busy }: { sips: SipRow[]; onStop?: (id: number) => void; busy?: string | null }) {
  if (!sips.length)
    return <Empty title="No SIPs yet">Start one here or ask the agent, e.g. &ldquo;start a SIP of 10,000 for 12 months&rdquo;.</Empty>;
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>SIP</TableHead>
          <TableHead className="text-right">Every month</TableHead>
          <TableHead className="text-right">Instalments</TableHead>
          <TableHead className="text-right">Invested</TableHead>
          <TableHead className="text-right">Next</TableHead>
          {onStop ? <TableHead className="w-20" /> : null}
        </TableRow>
      </TableHeader>
      <TableBody>
        {sips.map((s) => {
          const active = s.status === "active";
          return (
            <TableRow key={s.id} className={cn(!active && "text-muted-foreground")}>
              <TableCell>
                <span className="font-medium">#{s.id}</span> <span className="text-muted-foreground">{s.strategy}</span>
              </TableCell>
              <TableCell className="text-right">{inr(s.monthly_amount_rs)}</TableCell>
              <TableCell className="text-right">
                {s.instalments_done} / {s.instalments_total}
              </TableCell>
              <TableCell className="text-right">{inr(s.invested_rs)}</TableCell>
              <TableCell className="text-right text-[12.5px]">
                {active && s.next_date
                  ? new Date(s.next_date).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })
                  : s.status}
              </TableCell>
              {onStop ? (
                <TableCell className="text-right">
                  {active ? (
                    <button
                      disabled={!!busy}
                      onClick={() => onStop(s.id)}
                      className="text-[12px] text-muted-foreground underline-offset-4 hover:text-negative hover:underline disabled:opacity-40"
                    >
                      Stop
                    </button>
                  ) : null}
                </TableCell>
              ) : null}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

export function TradesTable({ trades }: { trades: Trade[] }) {
  if (!trades.length) return <Empty title="No trades yet">Executed orders will appear here.</Empty>;
  return (
    <div className="max-h-[440px] overflow-auto">
      <Table>
        <TableHeader className="sticky top-0 z-10 bg-background">
          <TableRow>
            <TableHead>Time</TableHead>
            <TableHead className="w-14">Side</TableHead>
            <TableHead>Asset</TableHead>
            <TableHead className="text-right">Qty</TableHead>
            <TableHead className="text-right">Price</TableHead>
            <TableHead className="hidden text-right md:table-cell">Fee</TableHead>
            <TableHead className="hidden lg:table-cell">Reason</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {trades.map((t) => (
            <TableRow key={t.id}>
              <TableCell className="text-[12px] text-muted-foreground">
                {new Date(t.ts).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
              </TableCell>
              <TableCell>
                <Side side={t.side} />
              </TableCell>
              <TableCell className="font-medium">{t.ticker}</TableCell>
              <TableCell className="text-right">{t.qty}</TableCell>
              <TableCell className="text-right">{inr(t.price, 2)}</TableCell>
              <TableCell className="hidden text-right text-muted-foreground md:table-cell">{inr(t.fee, 2)}</TableCell>
              <TableCell className="hidden max-w-56 truncate text-[12px] text-muted-foreground lg:table-cell">{t.note?.replace("order:", "")}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function EquityChart({ w }: { w: WalletData }) {
  const cfg: ChartConfig = { total: { label: "Portfolio value", color: "var(--foreground)" } };
  if (w.equity.length < 2)
    return <Empty title="Not enough history yet">The value curve starts once the portfolio has been valued on two market dates.</Empty>;
  return (
    <ChartContainer config={cfg} className="h-56 w-full">
      <AreaChart data={w.equity} margin={{ left: 0, right: 8, top: 8 }}>
        <CartesianGrid vertical={false} strokeDasharray="2 4" />
        <XAxis dataKey="asof" tickLine={false} axisLine={false} tickMargin={8} />
        <YAxis tickFormatter={(v) => compactInr(Number(v))} width={58} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
        <ChartTooltip content={<ChartTooltipContent formatter={(v) => inr(Number(v))} />} />
        <ReferenceLine y={w.valuation.starting_cash} strokeDasharray="2 3" stroke="var(--faint)" />
        <Area dataKey="total" stroke="var(--color-total)" strokeWidth={1.5} fill="var(--color-total)" fillOpacity={0.06} />
      </AreaChart>
    </ChartContainer>
  );
}
