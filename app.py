"""If I Invest Tomorrow - Financial Decision Simulator (Streamlit dashboard + Qwen3.5-4B agent).

    streamlit run app.py
"""
from __future__ import annotations

import itertools
import warnings

import pandas as pd
import streamlit as st

warnings.filterwarnings("ignore")

from ifit import config as C                      # noqa: E402
from ifit import data as D                         # noqa: E402
from ifit import viz as V                          # noqa: E402
from ifit import tools as T                        # noqa: E402
from ifit.agent import Agent                       # noqa: E402
from ifit.engine import STRATEGIES, STRATEGY_BLURB, UserProfile  # noqa: E402
from ifit.session import Session                   # noqa: E402
from ifit.wallet import WalletError                # noqa: E402

st.set_page_config(page_title="If I Invest Tomorrow", page_icon="📈", layout="wide")
_key = itertools.count()


def k(prefix: str = "k") -> str:
    return f"{prefix}-{next(_key)}"


def inr(x: float) -> str:
    return f"Rs.{x:,.0f}"


def pct(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%"


# --------------------------------------------------------------------------- #
@st.cache_resource(show_spinner="Loading market data, regime model and return models ...")
def get_session() -> Session:
    return Session.create()


S = get_session()
if "agent" not in st.session_state:
    st.session_state.agent = Agent(S)
    st.session_state.chat = []
AG: Agent = st.session_state.agent


# --------------------------------------------------------------------------- #
# Renderers (used by both the dashboard views and the chat)
# --------------------------------------------------------------------------- #
def r_plan(plan: pd.DataFrame, e, p: UserProfile, recommended: str | None):
    m = e.mc.stats
    star = "  (recommended)" if e.strategy == recommended else ""
    st.subheader(f"Tomorrow's Investment Plan - {e.strategy}{star}")
    st.caption(STRATEGY_BLURB[e.strategy])
    c = st.columns(6)
    c[0].metric("Expected return", pct(e.stats["exp_return"]))
    c[1].metric("Expected volatility", pct(e.stats["volatility"]))
    c[2].metric("P(positive return)", pct(m["prob_positive"], 0))
    c[3].metric(f"P(reach {p.target_return:.0%} target)", pct(m["prob_target"], 0))
    c[4].metric("Expected max drawdown", pct(m["exp_max_drawdown"]))
    c[5].metric("Stress survival", f"{int(e.stress.survives.sum())}/{len(e.stress)}")
    if e.breaches:
        st.warning("Outside your risk limits: " + "; ".join(e.breaches))
    else:
        st.success(f"Within your {p.risk}-risk limits.")
    show = plan[["ticker", "name", "sector", "asset_class", "weight", "target_amount", "price", "shares", "invested"]].copy()
    show.columns = ["Ticker", "Name", "Sector", "Class", "Weight", "Target amount", "Price", "Shares", "Invested"]
    st.dataframe(show, hide_index=True, use_container_width=True, column_config={
        "Weight": st.column_config.NumberColumn(format="percent"),
        "Target amount": st.column_config.NumberColumn(format="Rs.%.0f"),
        "Price": st.column_config.NumberColumn(format="Rs.%.2f"),
        "Invested": st.column_config.NumberColumn(format="Rs.%.0f")})
    st.caption(f"Whole shares at the latest close ({S.engine.md.last_date.date()}). Cash left after costs: "
               f"{inr(plan.attrs.get('cash_left', 0))}.")
    a, b = st.columns([1, 1.4])
    a.plotly_chart(V.fig_allocation(plan), use_container_width=True, key=k("alloc"))
    b.plotly_chart(V.fig_holdings_bar(plan), use_container_width=True, key=k("hold"))
    best = st.columns(3)
    best[0].metric("Worst case (5th pct)", inr(m["worst_case_p5"]))
    best[1].metric("Median outcome", inr(m["median_final"]))
    best[2].metric("Best case (95th pct)", inr(m["best_case_p95"]))


def r_strategies(board, recommended, why, p: UserProfile):
    st.subheader("Five strategies compared")
    st.info(f"Recommended: **{recommended}** - {why}")
    rows = []
    for n, e in board.items():
        m = e.mc.stats
        rows.append({"Strategy": n + (" *" if n == recommended else ""), "Exp. return": e.stats["exp_return"],
                     "Volatility": e.stats["volatility"], "Sharpe": e.stats["sharpe"],
                     "Median CAGR": m["exp_return_median"], "P(positive)": m["prob_positive"],
                     "P(target)": m["prob_target"], "Exp. max DD": m["exp_max_drawdown"],
                     "VaR95 (1y)": m["var95_1y"], "Median final": m["median_final"],
                     "Worst 5%": m["worst_case_p5"], "Best 95%": m["best_case_p95"],
                     "Holdings": int((e.weights > 0).sum()), "Within limits": e.within_tolerance})
    df = pd.DataFrame(rows)
    pc = {c: st.column_config.NumberColumn(format="percent") for c in
          ["Exp. return", "Volatility", "Median CAGR", "P(positive)", "P(target)", "Exp. max DD", "VaR95 (1y)"]}
    pc.update({c: st.column_config.NumberColumn(format="Rs.%.0f") for c in ["Median final", "Worst 5%", "Best 95%"]})
    pc["Sharpe"] = st.column_config.NumberColumn(format="%.2f")
    st.dataframe(df, hide_index=True, use_container_width=True, column_config=pc)
    a, b = st.columns(2)
    a.plotly_chart(V.fig_strategy_bars(board), use_container_width=True, key=k("sbar"))
    b.plotly_chart(V.fig_strategy_paths(board), use_container_width=True, key=k("spath"))
    st.plotly_chart(V.fig_frontier(S.engine.frontier(p), board), use_container_width=True, key=k("front"))
    comp = pd.DataFrame({n: e.weights[e.weights > 0] for n, e in board.items()}).fillna(0)
    comp.index = [D.short(i) for i in comp.index]
    st.markdown("**Weights by strategy**")
    st.dataframe(comp.style.format("{:.1%}").background_gradient(cmap="Blues", axis=None), use_container_width=True)


def r_mc(mc, strategy, p: UserProfile):
    m = mc.stats
    st.subheader(f"Monte Carlo simulation - {strategy}")
    st.caption(f"{mc.n_paths:,} paths - fat-tailed (Student-t) returns - 3-state market-regime switching - "
               f"starting regime: {S.engine.regime.current_name}")
    c = st.columns(6)
    c[0].metric("Median annual return", pct(m["exp_return_median"]))
    c[1].metric("Simulated volatility", pct(m["exp_volatility"]))
    c[2].metric("P(positive)", pct(m["prob_positive"], 0))
    c[3].metric("P(target)", pct(m["prob_target"], 0))
    c[4].metric("VaR 95% (1y)", pct(m["var95_1y"]))
    c[5].metric("CVaR 95% (1y)", pct(m["cvar95_1y"]))
    c = st.columns(5)
    c[0].metric("Absolute worst", inr(m["absolute_worst"]))
    c[1].metric("Worst 5%", inr(m["worst_case_p5"]))
    c[2].metric("Median", inr(m["median_final"]))
    c[3].metric("Best 95%", inr(m["best_case_p95"]))
    c[4].metric("Absolute best", inr(m["absolute_best"]))
    a, b = st.columns(2)
    a.plotly_chart(V.fig_fan(mc), use_container_width=True, key=k("fan"))
    b.plotly_chart(V.fig_distribution(mc), use_container_width=True, key=k("dist"))


def r_stress(stress, shock_mc, strategy, p):
    st.subheader(f"Stress tests - {strategy}")
    st.plotly_chart(V.fig_stress(stress), use_container_width=True, key=k("stress"))
    s = stress.copy()
    s["survives"] = s.survives.map({True: "yes", False: "NO"})
    s.columns = ["Scenario", "Portfolio return", "P&L (Rs.)", "Within loss limit", "Biggest hits"]
    st.dataframe(s, hide_index=True, use_container_width=True, column_config={
        "Portfolio return": st.column_config.NumberColumn(format="percent"),
        "P&L (Rs.)": st.column_config.NumberColumn(format="Rs.%.0f")})
    if shock_mc is not None:
        st.markdown(f"**Monte Carlo after a day-0 shock** (horizon {p.horizon_years}y)")
        d = shock_mc[["scenario", "day0_impact", "median_final", "median_cagr", "prob_positive", "prob_target", "worst_case_p5"]].copy()
        d.columns = ["Scenario", "Day-0 impact", "Median final", "Median CAGR", "P(positive)", "P(target)", "Worst 5%"]
        st.dataframe(d, hide_index=True, use_container_width=True, column_config={
            **{c: st.column_config.NumberColumn(format="percent") for c in ["Day-0 impact", "Median CAGR", "P(positive)", "P(target)"]},
            **{c: st.column_config.NumberColumn(format="Rs.%.0f") for c in ["Median final", "Worst 5%"]}})


def r_timing(t, strategy):
    st.subheader(f"Invest now vs wait vs SIP - {strategy}")
    st.caption(f"Current market regime: {S.engine.regime.current_name}. Uninvested money earns the risk-free rate.")
    st.plotly_chart(V.fig_timing(t), use_container_width=True, key=k("timing"))
    d = t.copy()
    d.columns = ["Option", "Expected final", "Median final", "5th pct", "95th pct", "P(beats lump sum)", "P(profit)", "Median CAGR"]
    st.dataframe(d, hide_index=True, use_container_width=True, column_config={
        **{c: st.column_config.NumberColumn(format="Rs.%.0f") for c in ["Expected final", "Median final", "5th pct", "95th pct"]},
        **{c: st.column_config.NumberColumn(format="percent") for c in ["P(beats lump sum)", "P(profit)", "Median CAGR"]}})


def r_backtest(bt, amount):
    st.subheader(f"Walk-forward backtest: {bt['start']} -> {bt['end']}")
    st.caption("Weights chosen using only data available before the start date, rebalanced quarterly. "
               "ML is excluded to avoid look-ahead; past performance is no guarantee.")
    st.plotly_chart(V.fig_backtest(bt["curves"], amount), use_container_width=True, key=k("bt"))
    d = bt["table"].copy()
    d.columns = ["Strategy", "Total return", "CAGR", "Volatility", "Sharpe", "Max drawdown", f"Final value"]
    st.dataframe(d, hide_index=True, use_container_width=True, column_config={
        **{c: st.column_config.NumberColumn(format="percent") for c in ["Total return", "CAGR", "Volatility", "Max drawdown"]},
        "Final value": st.column_config.NumberColumn(format="Rs.%.0f"), "Sharpe": st.column_config.NumberColumn(format="%.2f")})


def r_market(o: dict):
    st.subheader(f"Market overview - {o['as_of']}")
    c = st.columns(6)
    c[0].metric("NIFTY 50", f"{o['nifty_close']:,.0f}", pct(o["nifty_1d"], 2))
    c[1].metric("1 month", pct(o["nifty_1m"]))
    c[2].metric("1 year", pct(o["nifty_1y"]))
    c[3].metric("From peak", pct(o["nifty_drawdown_from_peak"]))
    c[4].metric("India VIX", f"{o['india_vix']:.1f}")
    c[5].metric("Regime", o["regime"])
    probs = o["regime_probabilities"]
    st.caption("Regime probabilities: " + ", ".join(f"{n} {pct(v, 0)}" for n, v in probs.items()) +
               f" | Anomaly today: {'YES' if o['anomaly_today'] else 'no'}")
    if o["unusual_stock_moves"]:
        st.warning("Unusual moves today: " + ", ".join(f"{x['symbol']} {pct(x['ret'], 1)}" for x in o["unusual_stock_moves"]))


def r_models(metrics, regimes, importance):
    st.subheader("ML models - walk-forward validation (2021-2026, expanding window)")
    st.dataframe(metrics.astype(float).rename(columns={
        "rmse": "RMSE", "mae": "MAE", "dir_acc": "Direction accuracy", "ic_cross_section": "IC (cross-section)",
        "ic_pooled": "IC (pooled)", "n_test": "Test rows"}).style.format("{:.4f}"), use_container_width=True)
    st.caption(f"Selected: {S.engine.estimator.model_name}. ML weight in expected returns = "
               f"{S.engine.estimator.skill_weight:.0%}, set from measured out-of-sample IC. "
               f"Models rarely beat a naive baseline on monthly returns, so ML is only a small tilt.")
    st.markdown("**Market regimes (Gaussian mixture on NIFTY state variables)**")
    st.dataframe(regimes.style.format({"share": "{:.0%}", "ann_return": "{:.1%}", "ann_vol": "{:.1%}",
                                        "avg_drawdown": "{:.1%}", "avg_vix": "{:.1f}"}), use_container_width=True)
    if importance is not None:
        top = importance.head(12)[::-1]
        import plotly.graph_objects as go
        fig = go.Figure(go.Bar(x=top.values, y=top.index, orientation="h", marker_color=V.BLUE))
        st.plotly_chart(V._layout(fig, "Feature importance (selected model)", 340, legend=False), use_container_width=True, key=k("imp"))


def r_asset(rep: dict):
    st.subheader(f"{D.short(rep['symbol'])} - {rep['name']} ({rep['sector']})")
    c = st.columns(6)
    c[0].metric("Price", f"Rs.{rep['last_price']:,.2f}", pct(rep["ret_today"], 2))
    c[1].metric("Beta", f"{rep['beta']:.2f}")
    c[2].metric("CAPM return", pct(rep["capm_expected_return"]))
    c[3].metric("Volatility", pct(rep["volatility"]))
    c[4].metric("Max drawdown", pct(rep["max_drawdown"]))
    c[5].metric("Model expected return", pct(rep["final_expected_return"]))
    st.plotly_chart(V.fig_price(S.engine.md, [rep["symbol"], C.MARKET_SYMBOL.replace("^NSEI", "NIFTYBEES.NS")]),
                    use_container_width=True, key=k("px"))


def r_wallet(valuation, equity, pending):
    st.subheader("Demo wallet (virtual money)")
    c = st.columns(4)
    c[0].metric("Total value", inr(valuation["total_value"]), f"{valuation['pnl']:+,.0f} ({valuation['pnl_pct']:+.2%})")
    c[1].metric("Cash", inr(valuation["cash"]))
    c[2].metric("Invested", inr(valuation["invested_value"]))
    c[3].metric("Started with", inr(valuation["starting_cash"]))
    pos = valuation["positions"]
    if len(pos):
        d = pos[["symbol", "name", "sector", "qty", "avg_cost", "price", "value", "pnl", "pnl_pct"]].copy()
        d["symbol"] = d.symbol.map(D.short)
        d.columns = ["Ticker", "Name", "Sector", "Qty", "Avg cost", "Price", "Value", "P&L", "P&L %"]
        st.dataframe(d, hide_index=True, use_container_width=True, column_config={
            "Avg cost": st.column_config.NumberColumn(format="Rs.%.2f"), "Price": st.column_config.NumberColumn(format="Rs.%.2f"),
            "Value": st.column_config.NumberColumn(format="Rs.%.0f"), "P&L": st.column_config.NumberColumn(format="Rs.%.0f"),
            "P&L %": st.column_config.NumberColumn(format="percent")})
    else:
        st.info("No holdings yet - build a plan and stage it, or ask the agent.")
    if pending:
        r_pending(pending)


def r_pending(pend):
    st.warning(f"Staged order waiting for confirmation: **{pend['label']}** - {len(pend['orders'])} orders, "
               f"buy cost {inr(pend['buy_cost'])}, sell proceeds {inr(pend['sell_proceeds'])}")
    st.dataframe(pd.DataFrame(pend["orders"]), hide_index=True, use_container_width=True)
    a, b, _ = st.columns([1, 1, 4])
    if a.button("Confirm (demo money)", type="primary", key=k("conf")):
        try:
            S.wallet.confirm_pending()
            st.session_state.flash = "Orders executed with demo money."
        except WalletError as e:
            st.session_state.flash = f"Failed: {e}"
        st.rerun()
    if b.button("Cancel", key=k("canc")):
        S.wallet.cancel_pending()
        st.rerun()


def render_artifact(a: dict, in_chat: bool = True):
    kind, pl = a["kind"], a["payload"]
    if kind == "plan":
        r_plan(pl["plan"], pl["evaluation"], pl["profile"], pl["recommended"])
    elif kind == "strategies":
        r_strategies(pl["board"], pl["recommended"], pl["why"], pl["profile"])
    elif kind == "montecarlo":
        r_mc(pl["mc"], pl["strategy"], pl["profile"])
    elif kind == "stress":
        r_stress(pl["stress"], pl["shock_mc"], pl["strategy"], pl["profile"])
    elif kind == "timing":
        r_timing(pl["table"], pl["strategy"])
    elif kind == "backtest":
        r_backtest(pl, S.profile.normalised().amount)
    elif kind == "market":
        r_market(pl)
    elif kind == "models":
        r_models(pl["metrics"], pl["regimes"], pl["importance"])
    elif kind == "asset":
        r_asset(pl)
    elif kind == "wallet":
        r_wallet(pl["valuation"], pl["equity"], pl["pending"])
    elif kind == "trades":
        st.subheader("Trade history")
        if len(pl):
            st.dataframe(pl, hide_index=True, use_container_width=True)


# --------------------------------------------------------------------------- #
# Sidebar: investor profile
# --------------------------------------------------------------------------- #
p0 = S.profile.normalised()
with st.sidebar:
    st.title("📈 If I Invest Tomorrow")
    st.caption("Financial decision simulator - Indian markets - demo money only")
    view = st.radio("View", ["💬 Agent chat", "📋 Tomorrow's plan", "⚖️ Strategies", "🎲 Monte Carlo", "🧪 Stress tests",
                             "⏱️ Timing & backtest", "🔎 Market & models", "👛 Demo wallet"], label_visibility="collapsed")
    st.divider()
    st.subheader("Investor profile")
    with st.form("profile"):
        amount = st.number_input("Investment amount (Rs.)", 1000, 100_000_000, int(p0.amount), step=10_000)
        horizon = st.select_slider("Horizon (years)", [1, 3, 5], p0.horizon_years)
        risk = st.select_slider("Risk tolerance", ["low", "medium", "high"], p0.risk)
        target = st.slider("Target return (% p.a.)", 4.0, 30.0, float(round(p0.target_return * 100, 1)), 0.5)
        opts = C.SECTORS + ["Gold", "Bonds"]
        sectors = st.multiselect("Preferred sectors / assets", opts,
                                 [x for x in opts if x.lower() in {y.lower() for y in p0.preferred_sectors}])
        submitted = st.form_submit_button("Build my plan", type="primary", use_container_width=True)
    if submitted:
        S.set_profile(amount=amount, horizon_years=horizon, risk=risk, target_return=target / 100, preferred_sectors=sectors)
        with st.spinner("Optimising 5 strategies and running 50,000 Monte Carlo paths ..."):
            S.ensure_board()
        S.selected_strategy = None
        S.last_plan = None
    st.divider()
    v = S.wallet.valuation(S.engine.md.last_prices(), asof=str(S.engine.md.last_date.date()), record=False)
    st.metric("Demo wallet", inr(v["total_value"]), f"{v['pnl']:+,.0f}")
    st.caption(f"Data as of {S.engine.md.last_date.date()} - LLM: {C.LLM_MODEL}")

if "flash" in st.session_state:
    st.toast(st.session_state.pop("flash"))


def need_board():
    with st.spinner("Optimising strategies and simulating ..."):
        board = S.ensure_board()
    return board, S.profile.normalised()


def strategy_picker(board, key):
    names = list(board)
    default = S.selected_strategy or S.recommended
    return st.radio("Strategy", names, index=names.index(default), horizontal=True, key=key,
                    format_func=lambda n: n + (" (recommended)" if n == S.recommended else ""))


# --------------------------------------------------------------------------- #
# Views
# --------------------------------------------------------------------------- #
if view.startswith("💬"):
    st.header("Chat with the investment agent")
    st.caption("Powered by Qwen3.5-4B running locally via Ollama. It can analyse the market, build plans, simulate, "
               "stress-test and trade in the demo wallet - always asking before executing.")
    for msg in st.session_state.chat:
        with st.chat_message(msg["role"]):
            if msg.get("tools"):
                with st.expander(f"🔧 Tools used: {', '.join(n for n, _ in msg['tools'])}"):
                    for n, a in msg["tools"]:
                        st.code(f"{n}({a})", language="python")
            st.markdown(msg["text"])
            for art in msg.get("artifacts", []):
                with st.expander(art["title"], expanded=False):
                    render_artifact(art)
    pend = S.wallet.pending()
    if pend:
        r_pending(pend)

    examples = ["I have Rs 1,00,000 for 3 years, medium risk, target 12%. What should I invest in tomorrow?",
                "Compare all five strategies", "Stress test the plan against a market crash",
                "Should I invest now or do a SIP?", "How is the market today?", "Show my demo wallet"]
    cols = st.columns(3)
    clicked = None
    for i, ex in enumerate(examples):
        if cols[i % 3].button(ex, key=f"ex{i}", use_container_width=True):
            clicked = ex
    prompt = st.chat_input("Ask about investing, e.g. 'Put Rs 50,000 in low-risk, 1 year, I like pharma'") or clicked
    if prompt:
        st.session_state.chat.append({"role": "user", "text": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            status = st.status("Thinking ...", expanded=False)
            box = st.empty()
            text, tools, reply = "", [], None
            for ev in AG.stream(prompt):
                if ev.kind == "tool_call":
                    tools.append((ev.name, ev.data))
                    status.update(label=f"Running tool: {ev.name} ...")
                elif ev.kind == "text":
                    text += ev.data
                    box.markdown(text + "▌")
                elif ev.kind == "error":
                    text = f"⚠️ {ev.data}"
                elif ev.kind == "done":
                    reply = ev.data
            status.update(label=f"Done - {len(tools)} tool call(s)", state="complete")
            final = reply.text if reply else text
            box.markdown(final)
            arts = reply.artifacts if reply else []
            for art in arts:
                with st.expander(art["title"], expanded=True):
                    render_artifact(art)
        st.session_state.chat.append({"role": "assistant", "text": final, "tools": tools, "artifacts": arts})
        st.rerun()
    if st.session_state.chat and st.button("Clear chat"):
        st.session_state.chat = []
        AG.reset()
        st.rerun()

elif view.startswith("📋"):
    board, p = need_board()
    name = strategy_picker(board, "pick_plan")
    S.selected_strategy = name
    e = board[name]
    plan = S.engine.build_plan(e.weights, p)
    S.last_plan = plan
    r_plan(plan, e, p, S.recommended)
    st.info(S.recommended_why)
    st.divider()
    pend = S.wallet.pending()
    if pend:
        r_pending(pend)
    elif st.button("Stage this plan in the demo wallet", type="primary"):
        try:
            S.wallet.stage_plan(plan, name)
            st.rerun()
        except WalletError as ex:
            st.error(str(ex))

elif view.startswith("⚖️"):
    board, p = need_board()
    r_strategies(board, S.recommended, S.recommended_why, p)

elif view.startswith("🎲"):
    board, p = need_board()
    name = strategy_picker(board, "pick_mc")
    r_mc(board[name].mc, name, p)

elif view.startswith("🧪"):
    board, p = need_board()
    name = strategy_picker(board, "pick_stress")
    with st.spinner("Running shock simulations ..."):
        sm = S.engine.shock_monte_carlo(board[name].weights, p)
    r_stress(board[name].stress, sm, name, p)

elif view.startswith("⏱️"):
    board, p = need_board()
    name = strategy_picker(board, "pick_time")
    with st.spinner("Simulating ..."):
        r_timing(S.engine.timing(board[name].weights, p), name)
    st.divider()
    yrs = st.slider("Backtest window (years)", 1, 5, 3)
    with st.spinner("Back-testing ..."):
        r_backtest(S.engine.backtest(p, yrs), p.amount)

elif view.startswith("🔎"):
    r_market(S.engine.market_overview())
    t1, t2, t3, t4, t5 = st.tabs(["Regimes", "Anomalies", "Correlation", "Assets", "ML models"])
    with t1:
        st.plotly_chart(V.fig_regimes(S.engine.md, S.engine.regime), use_container_width=True, key=k("reg"))
        st.dataframe(S.engine.regime.stats.style.format({"share": "{:.0%}", "ann_return": "{:.1%}", "ann_vol": "{:.1%}",
                                                          "avg_drawdown": "{:.1%}", "avg_vix": "{:.1f}"}), use_container_width=True)
    with t2:
        st.plotly_chart(V.fig_anomaly(S.engine.anomaly, S.engine.md), use_container_width=True, key=k("anom"))
    with t3:
        st.plotly_chart(V.fig_corr(S.engine.rm.corr), use_container_width=True, key=k("corr"))
    with t4:
        tbl = S.engine.rm.capm.join(S.engine.mu_table[["expected"]])
        tbl.insert(0, "name", [C.UNIVERSE[s][0] for s in tbl.index])
        tbl.insert(1, "sector", [C.UNIVERSE[s][1] for s in tbl.index])
        tbl.index = [D.short(s) for s in tbl.index]
        st.dataframe(tbl[["name", "sector", "beta", "capm_return", "hist_return", "expected", "vol", "mdd", "sharpe_hist"]]
                     .style.format({"beta": "{:.2f}", "capm_return": "{:.1%}", "hist_return": "{:.1%}", "expected": "{:.1%}",
                                    "vol": "{:.1%}", "mdd": "{:.1%}", "sharpe_hist": "{:.2f}"}), use_container_width=True, height=560)
        pick = st.selectbox("Asset detail", [D.short(s) for s in C.UNIVERSE])
        r_asset(S.engine.asset_report(pick))
    with t5:
        est = S.engine.estimator
        r_models(est.metrics, S.engine.regime.stats, est.feature_importance)

else:  # wallet
    md = S.engine.md
    v = S.wallet.valuation(md.last_prices(), asof=str(md.last_date.date()))
    r_wallet(v, S.wallet.equity_curve(), S.wallet.pending())
    eq = S.wallet.equity_curve()
    if len(eq) > 1:
        st.plotly_chart(V.fig_equity(eq, v["starting_cash"]), use_container_width=True, key=k("eq"))
    st.subheader("Trade history")
    tr = S.wallet.trades(100)
    st.dataframe(tr, hide_index=True, use_container_width=True) if len(tr) else st.caption("No trades yet.")
    c1, c2, c3 = st.columns(3)
    add = c1.number_input("Add demo funds (Rs.)", 0, 100_000_000, 0, step=100_000)
    if c1.button("Add funds") and add > 0:
        S.wallet.add_demo_funds(add)
        st.rerun()
    c3.write("")
    if c3.button("Reset wallet to Rs.10,00,000"):
        S.wallet.reset()
        st.rerun()
