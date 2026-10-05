"use client";

/**
 * Floating navigation dock: the "sable" AnimatedTopDock from @designcodeio/threeui (ThreeUI Community, MIT).
 *
 * The package component hardcodes its demo items (SYSTEM / METHOD / WORK ...), so this reproduces its markup,
 * styling and motion with the app's real routes: a light logo button followed by icon + uppercase mono labels,
 * magnified by the package's own proximity controller with the pasted values
 * (variant sable, proximity 122, spring 0.19, damping 0.70, width growth 17, height growth 16, drop 3.5).
 * The wordmark (left) and the controls (right) sit either side of the centred dock.
 */
import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { Activity, Bot, Calculator, LineChart, Moon, RotateCw, Sun, Wallet } from "lucide-react";
import { toast } from "sonner";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Delta } from "@/components/kit";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { inr, pctSigned } from "@/lib/format";
import { cn } from "@/lib/utils";
import { createTopDockController } from "@/vendor/top-dock-controller";

const NAV = [
  { href: "/agent", label: "Agent", icon: Bot },
  { href: "/planner", label: "Planner", icon: LineChart },
  { href: "/simulator", label: "Simulator", icon: Calculator },
  { href: "/market", label: "Markets", icon: Activity },
  { href: "/wallet", label: "Portfolio", icon: Wallet },
];

// AnimatedTopDock props as pasted
const DOCK = { variant: "sable", proximity: 122, spring: 0.19, damping: 0.7, widthGrowth: 17, heightGrowth: 16, drop: 3.5 } as const;

function LogoMark() {
  return (
    // brand mark (public/brand/): history up to today, a point for tomorrow, then the fan of simulated futures
    <svg viewBox="0 0 64 64" aria-hidden className="size-full">
      <rect width="64" height="64" fill="#E8E8E3" />
      <path d="M30 35 Q41 30 54 12 L54 47 Q41 37 30 35Z" fill="#0e5a43" fillOpacity="0.12" />
      <path d="M30 35 Q41 30 54 12M30 35 Q41 37 54 47" fill="none" stroke="#111" strokeOpacity="0.4" strokeWidth="3.2" strokeLinecap="round" />
      <path d="M30 35 Q41 32 54 25" fill="none" stroke="#0e5a43" strokeWidth="4.6" strokeLinecap="round" />
      <path d="M9 44 L16 37 L21 40 L30 35" fill="none" stroke="#111" strokeWidth="4.6" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="30" cy="35" r="5" fill="#E8E8E3" stroke="#111" strokeWidth="3.2" />
    </svg>
  );
}

function IconAction({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger render={<button type="button" aria-label={label} onClick={onClick} disabled={disabled} className="dock-icon-btn" />}>
        {children}
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

export function DockHeader() {
  const pathname = usePathname();
  const { state, setState, run, announce, refresh } = useApp();
  const { resolvedTheme, setTheme } = useTheme();
  const navRef = React.useRef<HTMLElement>(null);
  const [refreshing, setRefreshing] = React.useState(false);
  const auto = state?.autonomy === "auto";

  React.useEffect(() => {
    const el = navRef.current;
    if (!el) return;
    return createTopDockController(el, () => ({ ...DOCK, axis: "x" }));
  }, []);

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
    <header className="dock-wrap">
      <Link href="/" className="dock-word" aria-label="If I Invest Tomorrow, home">
        If I Invest <em>Tomorrow</em>
      </Link>

      <nav ref={navRef} className="dock-nav" aria-label="Primary" data-dock-state="idle" data-dock-max="0.00">
        <Link href="/" data-dock-item className="dock-item dock-logo" aria-label="Overview" aria-current={pathname === "/" ? "page" : undefined}>
          <LogoMark />
        </Link>
        {NAV.map((n) => {
          const active = pathname.startsWith(n.href);
          return (
            <Link key={n.href} href={n.href} data-dock-item className="dock-item dock-link" aria-current={active ? "page" : undefined}>
              <span className="dock-icon" aria-hidden>
                <n.icon strokeWidth={1.4} />
              </span>
              <span className="dock-label">{n.label}</span>
              {n.href === "/wallet" && state?.wallet.pending ? <span className="dock-dot" aria-label="Orders awaiting confirmation" /> : null}
            </Link>
          );
        })}
      </nav>

      <div className="dock-utils">
        <Tooltip>
          <TooltipTrigger render={<label className="dock-auto" />}>
            <span className="dock-auto-label">Auto-trade</span>
            <Switch size="sm" checked={auto} onCheckedChange={toggleAutonomy} aria-label="Auto-trade" />
          </TooltipTrigger>
          <TooltipContent className="max-w-64">
            On: the agent buys, sells and rebalances when you tell it to. Off: it only stages orders for you to confirm.
          </TooltipContent>
        </Tooltip>
        <Link href="/wallet" className="dock-value" aria-label="Portfolio value">
          <span className="num">{state ? inr(state.wallet.total_value) : "—"}</span>
          {state ? <Delta value={state.wallet.pnl}>{pctSigned(state.wallet.pnl_pct, 2)}</Delta> : null}
        </Link>
        <IconAction label="Refresh market data" onClick={refreshData} disabled={refreshing}>
          <RotateCw className={cn("size-[15px]", refreshing && "animate-spin")} />
        </IconAction>
        <IconAction label="Toggle theme" onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}>
          <Sun className="hidden size-[15px] dark:block" />
          <Moon className="size-[15px] dark:hidden" />
        </IconAction>
      </div>
    </header>
  );
}
