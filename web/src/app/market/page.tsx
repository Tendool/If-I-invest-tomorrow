"use client";

import * as React from "react";
import { Empty, Loading, PageHeader, Section, TabStrip } from "@/components/kit";
import { AnomalyChart, AssetDetailView, AssetsTable, CorrelationHeatmap, MarketOverviewCards, ModelsView, RegimeChart } from "@/components/finance/market-views";
import { api } from "@/lib/api";
import { useData } from "@/lib/use-data";

type Tab = "regimes" | "assets" | "correlation" | "anomalies" | "models";
const TABS: { value: Tab; label: string }[] = [
  { value: "regimes", label: "Regimes" },
  { value: "assets", label: "Assets" },
  { value: "correlation", label: "Correlation" },
  { value: "anomalies", label: "Anomalies" },
  { value: "models", label: "Models" },
];

function Wait({ d, label, children }: { d: { loading: boolean; error: string | null }; label: string; children: React.ReactNode }) {
  if (d.error) return <Empty title="Could not load">{d.error}</Empty>;
  if (d.loading) return <Loading label={label} />;
  return <>{children}</>;
}

export default function MarketPage() {
  const market = useData(() => api.market(), []);
  const [tab, setTab] = React.useState<Tab>("regimes");
  const corr = useData(() => api.correlation(), [], tab === "correlation");
  const assets = useData(() => api.assets(), [], tab === "assets");
  const models = useData(() => api.models(), [], tab === "models");
  const [picked, setPicked] = React.useState("");
  const detail = useData(() => api.asset(picked), [picked], !!picked);

  return (
    <div className="space-y-12">
      <PageHeader
        eyebrow="Markets"
        title="The market, read by the models"
        description="Regime detection, anomaly screening, correlations, per-asset risk analytics and how the forecasting models were validated."
      />
      {market.data ? <MarketOverviewCards o={market.data.overview} /> : <Wait d={market} label="Reading the market"><span /></Wait>}

      <div className="space-y-8">
        <TabStrip tabs={TABS} value={tab} onChange={setTab} />

        {tab === "regimes" ? (
          <Section title="NIFTY 50 by market regime" description="Each day is classified from 21- and 63-day return, volatility, drawdown and India VIX">
            <Wait d={market} label="Loading regimes">{market.data ? <RegimeChart data={market.data} /> : null}</Wait>
          </Section>
        ) : null}

        {tab === "assets" ? (
          <div className="grid gap-12 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
            <Section title="Investable universe" description="26 NSE stocks, index ETFs, gold, government bonds and a liquid fund · select a row">
              <Wait d={assets} label="Loading assets">{assets.data ? <AssetsTable rows={assets.data} onSelect={setPicked} selected={picked} /> : null}</Wait>
            </Section>
            <div className="xl:sticky xl:top-32 xl:self-start">
              {picked ? (
                <Wait d={detail} label="Loading asset">{detail.data ? <AssetDetailView a={detail.data} /> : null}</Wait>
              ) : (
                <Empty title="Select an asset">Its price history against the index, beta, CAPM and model returns, volatility and drawdown appear here.</Empty>
              )}
            </div>
          </div>
        ) : null}

        {tab === "correlation" ? (
          <Section title="Correlation of daily returns" description="Last five years · gold, bonds and cash are what diversify an equity portfolio">
            <Wait d={corr} label="Computing correlations">{corr.data ? <CorrelationHeatmap labels={corr.data.labels} matrix={corr.data.matrix} /> : null}</Wait>
          </Section>
        ) : null}

        {tab === "anomalies" ? (
          <Section title="Market anomaly score" description="Isolation Forest on market state; red points are the most unusual 2% of days">
            <Wait d={market} label="Loading anomalies">{market.data ? <AnomalyChart data={market.data} /> : null}</Wait>
          </Section>
        ) : null}

        {tab === "models" ? (
          <Wait d={models} label="Loading model report">{models.data ? <ModelsView data={models.data} regimes={market.data?.regimes} market={market.data} /> : null}</Wait>
        ) : null}
      </div>
    </div>
  );
}
