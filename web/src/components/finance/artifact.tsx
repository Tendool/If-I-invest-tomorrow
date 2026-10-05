"use client";

import * as React from "react";
import type { Artifact } from "@/lib/types";
import { AssetDetailView, MarketOverviewCards, ModelsView } from "./market-views";
import { MonteCarloView } from "./mc-view";
import { PlanView } from "./plan-view";
import { BacktestView, StressView, TimingView } from "./risk-views";
import { StrategiesView } from "./strategies-view";
import { HealthCard, OrdersCard, PendingCard, PositionsTable, SipsTable, TradesTable, WalletSummary } from "./wallet-views";

/** Render any tool artifact the agent produced (shown inside the chat). */
export function ArtifactView({ a }: { a: Artifact }) {
  switch (a.kind) {
    case "plan":
      return <PlanView data={a.data} compact />;
    case "strategies":
      return <StrategiesView data={a.data} />;
    case "montecarlo":
      return <MonteCarloView data={a.data} />;
    case "stress":
      return <StressView data={a.data} />;
    case "timing":
      return <TimingView data={a.data} />;
    case "backtest":
      return <BacktestView data={a.data} />;
    case "market":
      return <MarketOverviewCards o={a.data} />;
    case "models":
      return <ModelsView data={a.data} />;
    case "asset":
      return <AssetDetailView a={a.data} />;
    case "wallet":
      return (
        <div className="space-y-6">
          <WalletSummary v={a.data.valuation} />
          <PositionsTable v={a.data.valuation} />
          {a.data.pending ? <PendingCard p={a.data.pending} /> : null}
        </div>
      );
    case "trades":
      return <TradesTable trades={a.data.trades} />;
    case "orders":
      return <OrdersCard d={a.data} />;
    case "health":
      return <HealthCard d={a.data} />;
    case "sips":
      return <SipsTable sips={a.data.sips} />;
    default:
      return null;
  }
}
