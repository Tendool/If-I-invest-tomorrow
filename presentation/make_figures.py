"""Generate the figures for the final-review slides from the real engine output.

    python presentation/make_figures.py

Writes vector PDFs to presentation/figures/ and the numbers used in the slides to
presentation/figures/numbers.json (so the deck never quotes a number the engine did not produce).
"""
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ifit import config as C, risk  # noqa: E402
from ifit.engine import Engine, UserProfile  # noqa: E402

OUT = ROOT / "presentation" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# palette shared with the web app (validated categorical order)
INK, MUTED, FAINT, RULE, BRAND = "#17160f", "#6b685e", "#9b978b", "#d6d2c6", "#0e5a43"
POS, NEG, CAUTION = "#157046", "#b3361f", "#9a6400"
C1, C2, C3, C4, C5, C6, C7, C8 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"
STRAT = {"Max Return": C2, "Min Risk": C1, "Max Sharpe": C3, "Goal-Based": C7, "Crash-Resistant": C5}
CLASS = {"stock": C1, "etf": C3, "gold": C4, "bond": C7, "cash": FAINT}
REGIME = [C3, C4, C8]

plt.rcParams.update({
    "font.family": "Segoe UI", "font.size": 8, "axes.edgecolor": RULE, "axes.labelcolor": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": "#e6e3da", "grid.linestyle": (0, (2, 3)), "grid.linewidth": 0.8,
    "xtick.color": FAINT, "ytick.color": FAINT, "xtick.labelsize": 7, "ytick.labelsize": 7,
    "xtick.major.size": 0, "ytick.major.size": 0, "legend.frameon": False, "legend.fontsize": 7, "axes.labelsize": 7.5,
    "text.color": INK, "figure.facecolor": "none", "axes.facecolor": "none", "savefig.facecolor": "none",
    "pdf.fonttype": 42, "axes.axisbelow": True,
})


def lakh(x, _=None):
    return f"₹{x / 1e5:.2f}L" if abs(x) >= 1e5 else f"₹{x / 1e3:.0f}K"


def save(fig, name):
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    print("wrote", name)


def main():
    eng = Engine()
    p = UserProfile(100_000, 3, "medium", 0.12, []).normalised()
    board = eng.run_all(p)
    rec, why = eng.recommend(board, p)
    e = board[rec]
    plan = eng.build_plan(e.weights, p)
    timing = eng.timing(e.weights, p)
    shock = eng.shock_monte_carlo(e.weights, p)
    bt = eng.backtest(p, 3)
    ov = eng.market_overview()
    reg = eng.regime
    md = eng.md

    # ---------------------------------------------------------------- regimes
    fig, ax = plt.subplots(figsize=(6.85, 1.95))
    m = md.market.reindex(reg.labels.index)
    for k, nm in enumerate(reg.names):
        s = m.where(reg.labels == k)
        ax.scatter(s.index, s.values, s=1.4, color=REGIME[k], label=nm, linewidths=0)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.legend(loc="upper left", markerscale=3.5, ncol=3, handletextpad=0.2)
    ax.set_ylabel("NIFTY 50 (log)")
    save(fig, "regimes")

    # --------------------------------------------------------------- frontier
    fr = eng.frontier(p)
    fig, ax = plt.subplots(figsize=(3.6, 2.75))
    cl = fr["cloud"]
    ax.scatter(cl.vol * 100, cl.ret * 100, s=3, color=FAINT, alpha=0.25, linewidths=0, label="Random portfolios")
    a = fr["assets"]
    ax.scatter(a.vol * 100, a.ret * 100, s=18, marker="+", color=MUTED, linewidths=0.9, label="Single assets")
    f = fr["frontier"].sort_values("volatility")
    ax.plot(f.volatility * 100, f.exp_return * 100, color=INK, lw=1.6, label="Efficient frontier")
    for n, ev in board.items():
        ax.scatter(ev.stats["volatility"] * 100, ev.stats["exp_return"] * 100, s=34, color=STRAT[n], edgecolors="white", linewidths=1.1, zorder=5, label=n)
    ax.set_xlabel("Volatility (% p.a.)")
    ax.set_ylabel("Expected return (% p.a.)")
    ax.grid(axis="x")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3, fontsize=6.5, handletextpad=0.2, columnspacing=0.9)
    save(fig, "frontier")

    # -------------------------------------------------------------------- fan
    mc = e.mc
    fan = mc.fan
    fig, ax = plt.subplots(figsize=(3.85, 2.45))
    ax.fill_between(fan.year, fan.p5, fan.p95, color=C1, alpha=0.12, lw=0, label="90% of paths")
    ax.fill_between(fan.year, fan.p25, fan.p75, color=C1, alpha=0.25, lw=0, label="Middle 50%")
    ax.plot(fan.year, fan.p50, color=C1, lw=2, label="Median")
    ax.plot(fan.year, p.amount * (1 + p.target_return) ** fan.year, color=BRAND, lw=1.4, ls=(0, (5, 4)), label="12% target path")
    ax.set_xlim(0, 3)
    ax.axhline(p.amount, color=FAINT, lw=0.9, ls=(0, (2, 3)))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lakh))
    ax.set_xlabel("Years")
    ax.legend(loc="upper left", fontsize=6.5)
    save(fig, "fan")

    # ----------------------------------------------------------- distribution
    term = mc.terminal
    tgt = p.amount * (1 + p.target_return) ** p.horizon_years
    fig, ax = plt.subplots(figsize=(3.85, 2.35))
    bins = np.linspace(np.percentile(term, 0.2), np.percentile(term, 99.6), 48)
    counts, edges = np.histogram(term, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    cols = [POS if c >= tgt else (FAINT if c >= p.amount else NEG) for c in centers]
    ax.bar(centers, counts / len(term) * 100, width=(edges[1] - edges[0]) * 0.9, color=cols, alpha=0.85)
    ax.axvline(p.amount, color=INK, lw=0.9, ls=(0, (2, 3)))
    ax.axvline(tgt, color=BRAND, lw=1.2, ls=(0, (4, 3)))
    tr = matplotlib.transforms.blended_transform_factory(ax.transData, ax.transAxes)
    ax.text(p.amount, 1.01, "invested", fontsize=6.5, color=INK, ha="center", va="bottom", transform=tr)
    ax.text(tgt, 1.01, "target", fontsize=6.5, color=BRAND, ha="center", va="bottom", transform=tr)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lakh))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.set_xlabel("Value after 3 years")
    save(fig, "distribution")

    # ------------------------------------------------------------------ stress
    st = e.stress.iloc[::-1]
    lim = C.RISK_PROFILES[p.risk]["max_stress_loss"]
    fig, ax = plt.subplots(figsize=(4.15, 2.75))
    vals = st.portfolio_return * 100
    colors = [POS if v >= 0 else (NEG if not s else "#d99a8c") for v, s in zip(vals, st.survives)]
    ax.barh([s.replace("Replay: ", "") for s in st.scenario], vals, color=colors, height=0.62)
    ax.axvline(0, color=RULE, lw=1)
    ax.axvline(-lim * 100, color=NEG, lw=0.9, ls=(0, (3, 3)))
    ax.text(-lim * 100, len(st) - 0.4, f" loss limit {lim:.0%}", color=NEG, fontsize=6.5, va="bottom")
    for i, v in enumerate(vals):
        ax.text(v + (0.4 if v >= 0 else -0.4), i, f"{v:+.1f}%", va="center", ha="left" if v >= 0 else "right", fontsize=6.5, color=INK)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x")
    ax.set_xlabel("Immediate portfolio return (%)")
    ax.tick_params(axis="y", labelsize=6.8, labelcolor=INK)
    ax.set_xlim(min(vals.min() * 1.3, -lim * 100 * 1.15), max(4, vals.max() * 2))
    save(fig, "stress")

    # ---------------------------------------------------------------- backtest
    cv = bt["curves"] * p.amount
    fig, ax = plt.subplots(figsize=(6.85, 1.85))
    for n in cv.columns:
        ref = "NIFTY" in n or "Equal" in n
        ax.plot(cv.index, cv[n], lw=1.1 if ref else 1.6, ls=(0, (4, 3)) if ref else "-", color=STRAT.get(n, MUTED if "NIFTY" in n else FAINT), label=n)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lakh))
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.02), ncol=1, fontsize=6.5)
    save(fig, "backtest")

    # -------------------------------------------------------------- allocation
    pl = plan.sort_values("weight")
    fig, ax = plt.subplots(figsize=(3.2, 2.2))
    ax.barh(pl.ticker, pl.weight * 100, color=[CLASS[c] for c in pl.asset_class], height=0.62)
    for i, (w, amt) in enumerate(zip(pl.weight, pl.target_amount)):
        ax.text(w * 100 + 0.4, i, f"{w:.1%}  ₹{amt:,.0f}", va="center", fontsize=6.5)
    ax.grid(axis="y", visible=False)
    ax.set_xticks([])
    ax.set_xlim(0, pl.weight.max() * 100 * 1.75)
    ax.tick_params(axis="y", labelsize=7, labelcolor=INK)
    save(fig, "allocation")

    # ------------------------------------------------------------ correlation
    corr = eng.rm.corr
    fig, ax = plt.subplots(figsize=(5.2, 4.6))
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list("ink", ["#efede7", C1])
    ax.imshow(corr.values.clip(0, 1), cmap=cmap, vmin=0, vmax=1)
    lab = [s.replace(".NS", "") for s in corr.index]
    ax.set_xticks(range(len(lab)), lab, rotation=90, fontsize=5.5)
    ax.set_yticks(range(len(lab)), lab, fontsize=5.5)
    ax.grid(False)
    save(fig, "correlation")

    # ----------------------------------------------------------------- numbers
    s = mc.stats
    num = dict(
        as_of=str(md.last_date.date()), n_assets=len(eng.rm.symbols), n_days=int(len(md.prices)),
        start=str(md.prices.index[0].date()),
        regime=ov["regime"], nifty=ov["nifty_close"], vix=ov["india_vix"],
        recommended=rec, why=why,
        exp_return=e.stats["exp_return"], vol=e.stats["volatility"], sharpe=e.stats["sharpe"], beta=e.stats["beta"],
        p_pos=s["prob_positive"], p_target=s["prob_target"], mdd=s["exp_max_drawdown"], mdd95=s["p95_max_drawdown"],
        var1y=s["var95_1y"], cvar1y=s["cvar95_1y"], p5=s["worst_case_p5"], p50=s["median_final"], p95=s["best_case_p95"],
        stress_pass=int(e.stress.survives.sum()), stress_n=len(e.stress),
        plan=[dict(t=r.ticker, cls=r.asset_class, sector=r.sector, w=r.weight, amt=r.target_amount, sh=int(r.shares), px=r.price) for r in plan.itertuples()],
        board={n: dict(ret=b.stats["exp_return"], vol=b.stats["volatility"], sharpe=b.stats["sharpe"], ppos=b.mc.stats["prob_positive"],
                       ptgt=b.mc.stats["prob_target"], med=b.mc.stats["median_final"], ok=b.within_tolerance) for n, b in board.items()},
        stress=[dict(sc=r.scenario, r=r.portfolio_return, ok=bool(r.survives)) for r in e.stress.itertuples()],
        shock=[dict(sc=r.scenario, d0=r.day0_impact, med=r.median_final, pt=r.prob_target) for r in shock.itertuples()],
        timing=[dict(o=r.strategy, med=r.median_final, pp=r.prob_profit, beat=(None if pd.isna(r.prob_beats_lump_sum) else r.prob_beats_lump_sum)) for r in timing.itertuples()],
        backtest=[dict(s=r.strategy, tr=r.total_return, cagr=r.cagr, vol=r.volatility, sharpe=r.sharpe, mdd=r.max_drawdown) for r in bt["table"].itertuples()],
        bt_start=bt["start"], bt_end=bt["end"],
        ml=[dict(m=i, rmse=r.rmse, dir=r.dir_acc, ic=(None if pd.isna(r.ic_cross_section) else r.ic_cross_section)) for i, r in eng.estimator.metrics.iterrows()],
        ml_selected=eng.estimator.model_name, ml_weight=eng.estimator.skill_weight,
        regimes=[dict(r=i, share=r.share, ret=r.ann_return, vol=r.ann_vol, vix=r.avg_vix) for i, r in reg.stats.iterrows()],
        persistence=[float(reg.transition[i][i]) for i in range(3)],
        erp=eng.rm.erp, mkt_ret=eng.rm.market_return, rf=C.RISK_FREE,
    )
    (OUT / "numbers.json").write_text(json.dumps(num, indent=1, default=float), encoding="utf-8")
    print("wrote numbers.json")


if __name__ == "__main__":
    main()
