"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { Moon, RotateCw, Sun } from "lucide-react";
import { toast } from "sonner";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Delta } from "@/components/kit";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { cn } from "@/lib/utils";
import { inr, pctSigned, shortDate } from "@/lib/format";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/agent", label: "Agent" },
  { href: "/planner", label: "Planner" },
  { href: "/market", label: "Markets" },
  { href: "/wallet", label: "Portfolio" },
];

function Wordmark() {
  return (
    <Link href="/" className="group flex shrink-0 items-baseline gap-2.5">
      <span className="flex size-6 translate-y-[3px] items-center justify-center rounded-[5px] bg-foreground text-background">
        <svg viewBox="0 0 16 16" className="size-3.5" aria-hidden>
          <path d="M2.5 12.5 6.5 8l2.5 2.5L13.5 4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <span className="display text-[1.32rem] leading-none whitespace-nowrap">
        If I Invest <span className="italic">Tomorrow</span>
      </span>
    </Link>
  );
}

function IconButton({ label, onClick, children, disabled }: { label: string; onClick: () => void; children: React.ReactNode; disabled?: boolean }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            type="button"
            aria-label={label}
            onClick={onClick}
            disabled={disabled}
            className="flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-foreground/[0.05] hover:text-foreground disabled:opacity-50"
          />
        }
      >
        {children}
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

function TickerItem({ label, value, change }: { label: string; value: string; change?: number }) {
  return (
    <span className="flex items-baseline gap-1.5 whitespace-nowrap">
      <span className="text-faint">{label}</span>
      <span className="num text-foreground">{value}</span>
      {change !== undefined ? <Delta value={change}>{pctSigned(Math.abs(change), 2).replace("+", "")}</Delta> : null}
    </span>
  );
}

export function SiteHeader() {
  const pathname = usePathname();
  const { state, setState, run, announce, refresh } = useApp();
  const { resolvedTheme, setTheme } = useTheme();
  const [refreshing, setRefreshing] = React.useState(false);
  const auto = state?.autonomy === "auto";
  const t = state?.ticker;

  async function toggleAutonomy(on: boolean) {
    const s = await run(() => api.setAutonomy(on ? "auto" : "ask"));
    if (s) {
      setState(s);
      toast(on ? "Auto-trade on" : "Auto-trade off", {
        description: on ? "The agent executes trades when you instruct it." : "The agent stages orders and waits for your confirmation.",
      });
    }
  }

  async function refreshData() {
    setRefreshing(true);
    const id = toast.loading("Fetching the latest market data…");
    const r = await run(() => api.refreshData());
    toast.dismiss(id);
    setRefreshing(false);
    if (r) {
      announce(r);
      await refresh();
    }
  }

  return (
    <header className="sticky top-0 z-30 border-b border-rule bg-background/90 backdrop-blur-md supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex h-14 max-w-[1320px] items-center gap-8 px-5 lg:px-8">
        <Wordmark />
        <nav className="-mb-px hidden h-14 items-stretch gap-6 md:flex">
          {NAV.map((n) => {
            const active = n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                className={cn(
                  "relative flex items-center text-[13px] transition-colors",
                  active ? "font-medium text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {n.label}
                {n.href === "/wallet" && state?.wallet.pending ? <span className="ml-1.5 size-1.5 rounded-full bg-caution" /> : null}
                {active ? <span className="absolute inset-x-0 bottom-0 h-[2px] bg-foreground" /> : null}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-5">
          <Tooltip>
            <TooltipTrigger render={<label className="hidden cursor-pointer items-center gap-2 text-[12.5px] text-muted-foreground lg:flex" />}>
              Auto-trade
              <Switch size="sm" checked={auto} onCheckedChange={toggleAutonomy} aria-label="Auto-trade" />
            </TooltipTrigger>
            <TooltipContent className="max-w-64">
              On: the agent buys, sells and rebalances when you tell it to. Off: it only stages orders for you to confirm.
            </TooltipContent>
          </Tooltip>
          <Link href="/wallet" className="hidden text-right leading-tight sm:block">
            <div className="num text-[13px] font-medium">{state ? inr(state.wallet.total_value) : "—"}</div>
            <div className="text-[11px]">
              {state ? <Delta value={state.wallet.pnl}>{pctSigned(state.wallet.pnl_pct, 2)}</Delta> : null}
            </div>
          </Link>
          <div className="flex items-center gap-0.5">
            <IconButton label="Refresh market data" onClick={refreshData} disabled={refreshing}>
              <RotateCw className={cn("size-4", refreshing && "animate-spin")} />
            </IconButton>
            <IconButton label="Toggle theme" onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}>
              <Sun className="hidden size-4 dark:block" />
              <Moon className="size-4 dark:hidden" />
            </IconButton>
          </div>
        </div>
      </div>

      {/* mobile nav */}
      <nav className="no-scrollbar flex gap-5 overflow-x-auto border-t border-border px-5 md:hidden">
        {NAV.map((n) => {
          const active = n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
          return (
            <Link key={n.href} href={n.href} className={cn("relative py-2.5 text-[13px] whitespace-nowrap", active ? "font-medium" : "text-muted-foreground")}>
              {n.label}
              {active ? <span className="absolute inset-x-0 bottom-0 h-[2px] bg-foreground" /> : null}
            </Link>
          );
        })}
      </nav>

      {/* market strip */}
      <div className="border-t border-border bg-surface/60">
        <div className="no-scrollbar mx-auto flex h-8 max-w-[1320px] items-center gap-6 overflow-x-auto px-5 text-[12px] lg:px-8">
          {t ? (
            <>
              <TickerItem label="NIFTY 50" value={t.nifty.toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 })} change={t.nifty_1d} />
              {t.banknifty ? <TickerItem label="BANK NIFTY" value={t.banknifty.toLocaleString("en-IN", { maximumFractionDigits: 0 })} /> : null}
              <TickerItem label="INDIA VIX" value={t.vix.toFixed(2)} />
              <TickerItem label="USD/INR" value={t.usdinr.toFixed(2)} />
              <TickerItem label="BRENT" value={`$${t.brent.toFixed(2)}`} />
              <span className="flex items-baseline gap-1.5 whitespace-nowrap">
                <span className="text-faint">REGIME</span>
                <span className="text-foreground">{state?.regime}</span>
              </span>
            </>
          ) : (
            <span className="text-faint">Connecting to market data…</span>
          )}
          <span className="ml-auto flex items-center gap-4 whitespace-nowrap text-faint">
            {state ? <span>Close of {shortDate(state.as_of)}</span> : null}
            <span className="hidden items-center gap-1.5 sm:flex">
              <span className={cn("size-1.5 rounded-full", state ? "bg-positive" : "bg-faint")} />
              {state?.llm ?? "model"}
            </span>
          </span>
        </div>
      </div>
    </header>
  );
}
