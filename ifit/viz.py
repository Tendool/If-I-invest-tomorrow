"""Plotly charts shared by the dashboard and the chat (palette: validated categorical order)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import config as C
from . import data as D

BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
INK, MUTED, GRID = "#52514e", "#898781", "rgba(137,135,129,0.25)"

# colour follows the entity, never its rank
STRATEGY_COLORS = {"Max Return": ORANGE, "Min Risk": BLUE, "Max Sharpe": AQUA,
                   "Goal-Based": VIOLET, "Crash-Resistant": MAGENTA}
CLASS_COLORS = {"stock": BLUE, "etf": AQUA, "gold": YELLOW, "bond": VIOLET, "cash": MUTED}
REGIME_COLORS = [AQUA, YELLOW, RED]


def _layout(fig: go.Figure, title: str = "", height: int = 380, legend: bool = True) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0, font=dict(size=15)), height=height, margin=dict(l=10, r=10, t=48, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(size=12),
        showlegend=legend, legend=dict(orientation="h", y=-0.18, x=0), hovermode="closest")
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    return fig


def money(x: float) -> str:
    return f"Rs.{x:,.0f}"


# --------------------------------------------------------------------------- #
def fig_allocation(plan: pd.DataFrame) -> go.Figure:
    by_cls = plan.groupby("asset_class").weight.sum()
    fig = go.Figure(go.Pie(
        labels=[c.title() for c in by_cls.index], values=by_cls.values, hole=0.62, sort=False,
        marker=dict(colors=[CLASS_COLORS[c] for c in by_cls.index], line=dict(color="rgba(0,0,0,0)", width=2)),
        textinfo="label+percent", hovertemplate="%{label}: %{percent}<extra></extra>"))
    return _layout(fig, "Allocation by asset class", 320, legend=False)


def fig_holdings_bar(plan: pd.DataFrame) -> go.Figure:
    d = plan.sort_values("weight")
    fig = go.Figure(go.Bar(
        y=d.ticker, x=d.weight * 100, orientation="h", marker_color=[CLASS_COLORS[c] for c in d.asset_class],
        text=[f"{w:.1%}  ({money(a)})" for w, a in zip(d.weight, d.target_amount)], textposition="outside",
        hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
    fig.update_xaxes(title="Weight (%)", range=[0, max(d.weight) * 100 * 1.45])
    return _layout(fig, "Holdings", max(260, 28 * len(d) + 90), legend=False)


def fig_fan(mc, title: str = "Portfolio value - simulated range") -> go.Figure:
    f = mc.fan
    fig = go.Figure()
    for i in range(min(len(mc.sample_paths), 25)):
        fig.add_trace(go.Scatter(x=mc.grid_years, y=mc.sample_paths[i], mode="lines", showlegend=False,
                                 line=dict(width=0.7, color="rgba(42,120,214,0.18)"), hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=f.year, y=f.p95, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=f.year, y=f.p5, fill="tonexty", fillcolor="rgba(42,120,214,0.14)",
                             line=dict(width=0), name="5th-95th percentile", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=f.year, y=f.p75, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=f.year, y=f.p25, fill="tonexty", fillcolor="rgba(42,120,214,0.28)",
                             line=dict(width=0), name="25th-75th percentile", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=f.year, y=f.p50, name="Median", line=dict(color=BLUE, width=2.5),
                             hovertemplate="Year %{x:.1f}: Rs.%{y:,.0f}<extra>Median</extra>"))
    if mc.target is not None:
        tv = mc.amount * (1 + mc.target) ** f.year
        fig.add_trace(go.Scatter(x=f.year, y=tv, name=f"Target ({mc.target:.0%} p.a.)",
                                 line=dict(color=ORANGE, width=2, dash="dash"),
                                 hovertemplate="Target Rs.%{y:,.0f}<extra></extra>"))
    fig.add_hline(y=mc.amount, line=dict(color=MUTED, width=1, dash="dot"))
    fig.update_xaxes(title="Years")
    fig.update_yaxes(title="Portfolio value (Rs.)", tickformat=",")
    return _layout(fig, title, 400)


def fig_distribution(mc) -> go.Figure:
    centers = (mc.hist_edges[:-1] + mc.hist_edges[1:]) / 2
    width = mc.hist_edges[1] - mc.hist_edges[0]
    tgt_val = mc.amount * (1 + mc.target) ** mc.years if mc.target is not None else None
    cols = [(GREEN if c >= (tgt_val or mc.amount) else (YELLOW if c >= mc.amount else RED)) for c in centers]
    fig = go.Figure(go.Bar(x=centers, y=mc.hist_counts / mc.n_paths * 100, width=width * 0.92,
                           marker_color=cols, hovertemplate="Rs.%{x:,.0f}: %{y:.2f}% of paths<extra></extra>"))
    fig.add_vline(x=mc.amount, line=dict(color=INK, dash="dot"), annotation_text="invested", annotation_position="top")
    if tgt_val:
        fig.add_vline(x=tgt_val, line=dict(color=ORANGE, dash="dash"), annotation_text="target", annotation_position="top")
    fig.update_xaxes(title="Final value (Rs.)", tickformat=",")
    fig.update_yaxes(title="% of simulated paths")
    p = mc.stats
    return _layout(fig, f"Distribution of final value  |  green: target met ({p['prob_target']:.0%}), "
                        f"yellow: profit, red: loss ({1 - p['prob_positive']:.0%})" if p["prob_target"] is not None
                   else "Distribution of final value", 360, legend=False)


def fig_frontier(front: dict, board: dict | None = None) -> go.Figure:
    fig = go.Figure()
    c = front["cloud"]
    fig.add_trace(go.Scatter(x=c.vol * 100, y=c.ret * 100, mode="markers", name="Random portfolios",
                             marker=dict(size=4, color=c.sharpe, colorscale=[[0, "#cde2fb"], [1, "#0d366b"]],
                                         opacity=0.5, showscale=False), hoverinfo="skip"))
    a = front["assets"]
    fig.add_trace(go.Scatter(x=a.vol * 100, y=a.ret * 100, mode="markers", name="Single assets",
                             text=[D.short(s) for s in a.index], marker=dict(size=7, color=MUTED, symbol="diamond"),
                             hovertemplate="%{text}<br>vol %{x:.1f}% ret %{y:.1f}%<extra></extra>"))
    fr = front["frontier"]
    fig.add_trace(go.Scatter(x=fr.volatility * 100, y=fr.exp_return * 100, mode="lines", name="Efficient frontier",
                             line=dict(color=INK, width=2.5)))
    if board:
        for n, e in board.items():
            fig.add_trace(go.Scatter(x=[e.stats["volatility"] * 100], y=[e.stats["exp_return"] * 100],
                                     mode="markers+text", name=n, text=[n], textposition="top center",
                                     marker=dict(size=13, color=STRATEGY_COLORS[n], line=dict(color="white", width=2))))
    fig.update_xaxes(title="Volatility (% p.a.)")
    fig.update_yaxes(title="Expected return (% p.a.)")
    return _layout(fig, "Risk-return: efficient frontier and the five strategies", 460)


def fig_strategy_bars(board: dict) -> go.Figure:
    names = list(board)
    fig = go.Figure()
    fig.add_bar(name="Expected return %", x=names, y=[board[n].stats["exp_return"] * 100 for n in names], marker_color=BLUE)
    fig.add_bar(name="Volatility %", x=names, y=[board[n].stats["volatility"] * 100 for n in names], marker_color=ORANGE)
    fig.add_bar(name="P(reach target) %", x=names, y=[board[n].mc.stats["prob_target"] * 100 for n in names], marker_color=AQUA)
    fig.update_layout(barmode="group", bargap=0.25)
    fig.update_yaxes(title="%")
    return _layout(fig, "Strategy comparison", 380)


def fig_strategy_paths(board: dict) -> go.Figure:
    fig = go.Figure()
    for n, e in board.items():
        f = e.mc.fan
        fig.add_trace(go.Scatter(x=f.year, y=f.p50, name=n, line=dict(color=STRATEGY_COLORS[n], width=2.2)))
    fig.update_xaxes(title="Years")
    fig.update_yaxes(title="Median portfolio value (Rs.)", tickformat=",")
    return _layout(fig, "Median growth of each strategy", 360)


def fig_stress(stress: pd.DataFrame) -> go.Figure:
    d = stress.iloc[::-1]
    fig = go.Figure(go.Bar(
        y=d.scenario, x=d.portfolio_return * 100, orientation="h",
        marker_color=[GREEN if v >= 0 else (RED if not s else ORANGE) for v, s in zip(d.portfolio_return, d.survives)],
        text=[f"{v:+.1%}" for v in d.portfolio_return], textposition="outside",
        hovertemplate="%{y}<br>%{x:.2f}%<extra></extra>"))
    fig.update_xaxes(title="Portfolio return (%)  |  red = breaches your loss limit")
    return _layout(fig, "Stress tests", 420, legend=False)


def fig_timing(t: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(name="5th percentile", x=t.strategy, y=t.p5_final, marker_color=YELLOW)
    fig.add_bar(name="Median", x=t.strategy, y=t.median_final, marker_color=BLUE)
    fig.add_bar(name="95th percentile", x=t.strategy, y=t.p95_final, marker_color=AQUA)
    fig.update_layout(barmode="group", bargap=0.25)
    fig.update_yaxes(title="Final value (Rs.)", tickformat=",")
    return _layout(fig, "Invest now vs wait vs SIP - final wealth", 380)


def fig_backtest(curves: pd.DataFrame, amount: float) -> go.Figure:
    fig = go.Figure()
    for n in curves.columns:
        col = STRATEGY_COLORS.get(n, MUTED)
        dash = "dot" if "NIFTY" in n or "Equal" in n else "solid"
        fig.add_trace(go.Scatter(x=curves.index, y=curves[n] * amount, name=n, line=dict(color=col, width=2, dash=dash)))
    fig.update_yaxes(title="Portfolio value (Rs.)", tickformat=",")
    return _layout(fig, "Walk-forward backtest", 400)


def fig_corr(corr: pd.DataFrame) -> go.Figure:
    lab = [D.short(s) for s in corr.index]
    fig = go.Figure(go.Heatmap(z=corr.values, x=lab, y=lab, zmin=-0.2, zmax=1,
                               colorscale=[[0, "#f0efec"], [1, "#0d366b"]], colorbar=dict(thickness=10)))
    fig.update_yaxes(autorange="reversed")
    return _layout(fig, "Correlation of daily returns (5y)", 560, legend=False)


def fig_regimes(md, regime) -> go.Figure:
    m = md.market.reindex(regime.labels.index)
    fig = go.Figure()
    for k, nm in enumerate(regime.names):
        s = m.where(regime.labels == k)
        fig.add_trace(go.Scattergl(x=s.index, y=s, mode="markers", marker=dict(size=3, color=REGIME_COLORS[k]), name=nm))
    fig.update_yaxes(title="NIFTY 50", type="log")
    return _layout(fig, "NIFTY 50 coloured by detected market regime", 380)


def fig_price(md, symbols: list[str]) -> go.Figure:
    fig = go.Figure()
    cols = [BLUE, ORANGE, AQUA, VIOLET, MAGENTA, YELLOW, GREEN, RED]
    for i, s in enumerate(symbols):
        px = md.prices[s].dropna()
        fig.add_trace(go.Scatter(x=px.index, y=px / px.iloc[0] * 100, name=D.short(s), line=dict(color=cols[i % 8], width=1.8)))
    fig.update_yaxes(title="Indexed (start = 100)")
    return _layout(fig, "Price performance (indexed)", 380)


def fig_anomaly(an, md) -> go.Figure:
    s = an.market_score
    fl = s[an.market_flags]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index, y=s, name="Anomaly score", line=dict(color=BLUE, width=1.2)))
    fig.add_trace(go.Scatter(x=fl.index, y=fl, mode="markers", name="Flagged", marker=dict(color=RED, size=5)))
    return _layout(fig, "Market anomaly score (Isolation Forest)", 300)


def fig_equity(eq: pd.DataFrame, start: float) -> go.Figure:
    fig = go.Figure(go.Scatter(x=eq.asof, y=eq.total, mode="lines+markers", line=dict(color=BLUE, width=2)))
    fig.add_hline(y=start, line=dict(color=MUTED, dash="dot"))
    fig.update_yaxes(title="Wallet value (Rs.)", tickformat=",")
    return _layout(fig, "Demo wallet value", 300, legend=False)
