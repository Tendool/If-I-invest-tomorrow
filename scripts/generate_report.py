"""Generate the proposal's "Expected Outcomes" for a sample investor (no LLM needed).

    python scripts/generate_report.py [amount] [years] [risk] [target%]

Writes reports/sample_report.md and reports/sample_dashboard.html (interactive charts).
"""
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import plotly.io as pio  # noqa: E402

from ifit import config as C, viz as V  # noqa: E402
from ifit.engine import Engine, UserProfile  # noqa: E402


def main():
    a = sys.argv[1:]
    p = UserProfile(float(a[0]) if a else 100_000, int(a[1]) if len(a) > 1 else 3,
                    a[2] if len(a) > 2 else "medium", float(a[3]) / 100 if len(a) > 3 else 0.12).normalised()
    eng = Engine()
    board = eng.run_all(p)
    rec, why = eng.recommend(board, p)
    e = board[rec]
    plan = eng.build_plan(e.weights, p)
    timing = eng.timing(e.weights, p)
    shock = eng.shock_monte_carlo(e.weights, p)
    bt = eng.backtest(p, 3)
    ov = eng.market_overview()
    m = e.mc.stats

    L = [f"# If I Invest Tomorrow - sample report\n",
         f"*Data as of {ov['as_of']} - {p.describe()}*\n",
         f"**Market:** NIFTY {ov['nifty_close']:,.0f} ({ov['nifty_1d']:+.2%} today, {ov['nifty_1y']:+.1%} 1y), India VIX {ov['india_vix']:.1f}, "
         f"regime **{ov['regime']}**, anomaly today: {ov['anomaly_today']}\n",
         f"## Tomorrow's Investment Plan - {rec} (recommended)\n{why}\n",
         "| Asset | Sector | Weight | Amount | Shares @ price |", "|---|---|---|---|---|"]
    for r in plan.itertuples():
        L.append(f"| {r.ticker} - {r.name} | {r.sector} | {r.weight:.1%} | Rs.{r.target_amount:,.0f} | {r.shares} @ Rs.{r.price:,.2f} |")
    L += ["", "## Financial insights",
          f"- Expected return **{e.stats['exp_return']:.1%}**, expected volatility **{e.stats['volatility']:.1%}**, Sharpe {e.stats['sharpe']:.2f}, beta {e.stats['beta']:.2f}",
          f"- Probability of positive return **{m['prob_positive']:.0%}**, probability of achieving {p.target_return:.0%} target **{m['prob_target']:.0%}**",
          f"- Expected max drawdown {m['exp_max_drawdown']:.1%} (95th pct {m['p95_max_drawdown']:.1%}); 1y VaR95 {m['var95_1y']:.1%}, CVaR95 {m['cvar95_1y']:.1%}",
          f"- Outcomes after {p.horizon_years}y: worst 5% Rs.{m['worst_case_p5']:,.0f} | median Rs.{m['median_final']:,.0f} | best 5% Rs.{m['best_case_p95']:,.0f}",
          "", "## Stress tests", "| Scenario | Portfolio return | P&L | Within loss limit |", "|---|---|---|---|"]
    for r in e.stress.itertuples():
        L.append(f"| {r.scenario} | {r.portfolio_return:+.1%} | Rs.{r.pnl:,.0f} | {'yes' if r.survives else 'NO'} |")
    L += ["", "## Five strategies compared",
          "| Strategy | Exp. return | Volatility | Sharpe | P(positive) | P(target) | Median final | Within limits |", "|---|---|---|---|---|---|---|---|"]
    for n, b in board.items():
        s = b.mc.stats
        L.append(f"| {n}{' *' if n == rec else ''} | {b.stats['exp_return']:.1%} | {b.stats['volatility']:.1%} | {b.stats['sharpe']:.2f} | "
                 f"{s['prob_positive']:.0%} | {s['prob_target']:.0%} | Rs.{s['median_final']:,.0f} | {'yes' if b.within_tolerance else 'no'} |")
    L += ["", "## Monte Carlo after a day-0 shock", "| Scenario | Day-0 impact | Median final | P(target) |", "|---|---|---|---|"]
    for r in shock.itertuples():
        L.append(f"| {r.scenario} | {r.day0_impact:+.1%} | Rs.{r.median_final:,.0f} | {r.prob_target:.0%} |")
    L += ["", "## Invest now vs wait vs SIP", "| Option | Median final | P(profit) | P(beats lump sum) |", "|---|---|---|---|"]
    for r in timing.itertuples():
        pb = "-" if r.prob_beats_lump_sum != r.prob_beats_lump_sum else f"{r.prob_beats_lump_sum:.0%}"
        L.append(f"| {r.strategy} | Rs.{r.median_final:,.0f} | {r.prob_profit:.0%} | {pb} |")
    L += ["", f"## Walk-forward backtest {bt['start']} -> {bt['end']}", "| Strategy | Total return | CAGR | Vol | Sharpe | Max DD |", "|---|---|---|---|---|---|"]
    for r in bt["table"].itertuples():
        L.append(f"| {r.strategy} | {r.total_return:+.1%} | {r.cagr:.1%} | {r.volatility:.1%} | {r.sharpe:.2f} | {r.max_drawdown:.1%} |")
    L += ["", "## ML validation (walk-forward 2021-2026)", eng.estimator.metrics.round(4).to_markdown(),
          f"\nSelected: {eng.estimator.model_name}; ML weight in expected returns {eng.estimator.skill_weight:.0%}.\n",
          "*Model-based simulation on historical data - not investment advice; no real money is used.*"]
    (C.REPORTS_DIR / "sample_report.md").write_text("\n".join(L), encoding="utf-8")

    figs = [V.fig_allocation(plan), V.fig_holdings_bar(plan), V.fig_fan(e.mc), V.fig_distribution(e.mc),
            V.fig_frontier(eng.frontier(p), board), V.fig_strategy_bars(board), V.fig_strategy_paths(board),
            V.fig_stress(e.stress), V.fig_timing(timing), V.fig_backtest(bt["curves"], p.amount),
            V.fig_regimes(eng.md, eng.regime), V.fig_corr(eng.rm.corr)]
    html = ["<html><head><meta charset='utf-8'><title>If I Invest Tomorrow - sample dashboard</title></head>"
            "<body style='font-family:sans-serif;max-width:1100px;margin:auto'>"
            f"<h1>If I Invest Tomorrow</h1><p>{p.describe()} - recommended: <b>{rec}</b></p>"]
    for i, f in enumerate(figs):
        html.append(pio.to_html(f, full_html=False, include_plotlyjs="cdn" if i == 0 else False))
    html.append("</body></html>")
    (C.REPORTS_DIR / "sample_dashboard.html").write_text("\n".join(html), encoding="utf-8")
    print("wrote reports/sample_report.md and reports/sample_dashboard.html")
    print("\n".join(L[:30]))


if __name__ == "__main__":
    main()
