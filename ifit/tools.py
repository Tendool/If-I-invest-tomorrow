"""Tool layer exposed to the Qwen agent.

Every tool returns a *compact* JSON-serialisable dict (numbers already in human units: percentages
as ``*_pct``, money in rupees) so a 4B model can narrate them without unit mistakes.  Rich objects
(tables / chart data) are pushed to ``session.emit`` and rendered by the UI independently of the LLM.
"""
from __future__ import annotations

import json
import re
import traceback

import numpy as np
import pandas as pd

from . import config as C
from . import data as D
from .engine import STRATEGIES, STRATEGY_BLURB
from .session import Session
from .wallet import WalletError

AFFIRM = re.compile(r"\b(yes|yep|yeah|yup|confirm|confirmed|go ahead|proceed|execute|do it|approve|approved|"
                    r"place it|place the|sure|ok|okay|invest it|buy it|sell it|go for it|please do)\b", re.I)
NEGATE = re.compile(r"\b(no|nope|don't|dont|do not|cancel|stop|not now|wait|abort|never)\b", re.I)


def user_confirmed(text: str) -> bool:
    return bool(AFFIRM.search(text or "")) and not NEGATE.search(text or "")


def _r(x, n=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def _pct(x, n=1):
    return _r(float(x) * 100, n)


def _inr(x):
    return int(round(float(x)))


_MENTION = {"Max Return": r"max(imum)?[ -]?return|aggressive", "Min Risk": r"min(imum)?[ -]?risk|min(imum)?[ -]?var|safest|defensive",
            "Max Sharpe": r"sharpe", "Goal-Based": r"goal", "Crash-Resistant": r"crash|resistant|proof"}


def _resolve_strategy(s: Session, name: str | None) -> str:
    s.ensure_board()
    if not name or str(name).strip().lower() in ("", "recommended", "best", "default", "auto", "none"):
        return s.selected_strategy or s.recommended
    # guard against the small model re-using a strategy from earlier in the chat: an explicit
    # strategy argument only counts if the user's current message actually names it.
    if s.last_user_text:
        t = re.sub(r"[^a-z]", "", str(name).lower())
        named = [n for n, rx in _MENTION.items() if re.search(rx, s.last_user_text, re.I)]
        want = next((v for k_, v in {"maxreturn": "Max Return", "minrisk": "Min Risk", "maxsharpe": "Max Sharpe",
                                      "goalbased": "Goal-Based", "crashresistant": "Crash-Resistant"}.items()
                     if t == k_ or t in k_ or k_ in t), None)
        if want and named and want not in named:
            return s.selected_strategy or s.recommended
        if want and not named:
            return s.selected_strategy or s.recommended
    t = re.sub(r"[^a-z]", "", str(name).lower())
    table = {"maxreturn": "Max Return", "return": "Max Return", "aggressive": "Max Return",
             "minrisk": "Min Risk", "minimumrisk": "Min Risk", "risk": "Min Risk", "minvariance": "Min Risk",
             "maxsharpe": "Max Sharpe", "sharpe": "Max Sharpe", "goalbased": "Goal-Based", "goal": "Goal-Based",
             "crashresistant": "Crash-Resistant", "crash": "Crash-Resistant", "crashproof": "Crash-Resistant"}
    for k, v in table.items():
        if t == k:
            return v
    for k, v in table.items():
        if k in t or t in k:
            return v
    raise ValueError(f"unknown strategy {name!r}; choose one of {STRATEGIES}")


def _profile_dict(s: Session) -> dict:
    p = s.profile.normalised()
    return dict(amount_rs=_inr(p.amount), horizon_years=p.horizon_years, risk_tolerance=p.risk,
                target_return_pct=_pct(p.target_return), preferred_sectors=p.preferred_sectors,
                profile_provided_by_user=s.profile_confirmed)


# ----------------------------------------------------------------------------- #
# Tool implementations
# ----------------------------------------------------------------------------- #
def get_market_overview(s: Session) -> dict:
    """Current market snapshot: NIFTY level/returns, India VIX, market regime, anomalies."""
    o = s.engine.market_overview()
    s.emit("market", "Market overview", o)
    return dict(
        as_of=o["as_of"], nifty_close=_r(o["nifty_close"], 0), nifty_1d_pct=_pct(o["nifty_1d"], 2),
        nifty_1m_pct=_pct(o["nifty_1m"]), nifty_1y_pct=_pct(o["nifty_1y"]),
        nifty_drawdown_from_peak_pct=_pct(o["nifty_drawdown_from_peak"]),
        nifty_volatility_1m_pct=_pct(o["nifty_vol_1m"]), india_vix=_r(o["india_vix"], 1),
        market_regime=o["regime"],
        regime_probability_pct={k: _pct(v, 0) for k, v in o["regime_probabilities"].items()},
        anomaly_detected_today=o["anomaly_today"],
        unusual_stock_moves=[dict(symbol=x["symbol"], move_pct=_pct(x["ret"], 2)) for x in o["unusual_stock_moves"]],
        risk_free_rate_pct=_pct(o["risk_free"]), capm_market_expected_return_pct=_pct(o["market_expected_return"]),
    )


def list_assets(s: Session, sector_or_class: str | None = None) -> dict:
    """List the investable universe (optionally filtered by sector or asset class)."""
    q = (sector_or_class or "").strip().lower()
    funds = bool(re.search(r"fund|etf|mutual|index", q))
    rows = []
    for sym, (name, sector, cls) in C.UNIVERSE.items():
        if funds:
            if cls == "stock":
                continue
        elif q and q not in (sector.lower(), cls, sym.lower(), D.short(sym).lower()) and q not in name.lower():
            continue
        rows.append(dict(ticker=D.short(sym), name=name, sector=sector, asset_class=cls,
                         expected_return_pct=_pct(s.engine.mu[sym]), price=_r(s.engine.md.last_prices()[sym], 2)))
    out = dict(count=len(rows), sectors=C.SECTORS + ["Gold", "Bonds", "Cash", "Broad Market"], assets=rows,
               note="expected_return_pct is this app's model estimate (CAPM + history), not a past return and not a guarantee.")
    if funds or re.search(r"mutual|\bmfs?\b|index fund|\b(navi|sbi|hdfc|uti|icici pru\w*|axis|parag parikh|ppfas|kotak|motilal|mirae|zerodha|groww|dsp|quant|edelweiss|bandhan|franklin|aditya birla|hsbc|invesco)\b", s.last_user_text or "", re.I):
        out["funds_note"] = ("This app has no mutual funds. Its fund-like assets are 6 exchange-traded funds (ETFs): NIFTYBEES "
                             "(NIFTY 50), JUNIORBEES (Nifty Next 50), BANKBEES (Bank NIFTY), GOLDBEES (gold), LTGILTBEES "
                             "(government bonds) and LIQUIDBEES (liquid/cash). Individual stocks are not funds.")
    return out


def analyze_asset(s: Session, asset: str) -> dict:
    """Detailed risk/return analysis of one stock/ETF: beta, CAPM return, volatility, VaR, drawdown, ML forecast."""
    rep = s.engine.asset_report(asset)
    out = dict(
        ticker=D.short(rep["symbol"]), name=rep["name"], sector=rep["sector"], asset_class=rep["asset_class"],
        last_price=_r(rep["last_price"]), return_1m_pct=_pct(rep["ret_1m"]), return_1y_pct=_pct(rep["ret_1y"]),
        beta=_r(rep["beta"]), capm_expected_return_pct=_pct(rep["capm_expected_return"]),
        historical_return_5y_pct=_pct(rep["hist_return_5y"]), volatility_pct=_pct(rep["volatility"]),
        max_drawdown_5y_pct=_pct(rep["max_drawdown"]), daily_var95_pct=_pct(rep["var95_1d"], 2),
        daily_cvar95_pct=_pct(rep["cvar95_1d"], 2), sharpe_5y=_r(rep["sharpe_hist"]),
        ml_forecast_next_21d_pct=_pct(rep["ml_forecast_21d"]), forecast_volatility_next_month_pct=_pct(rep["forecast_vol_21d"]), model_expected_return_pct=_pct(rep["final_expected_return"]),
        rsi14=_r(rep["rsi14"], 0), above_200_day_average=rep["above_200dma"],
    )
    out["daily_var95_rs_per_1000"] = round(float(rep["var95_1d"]) * 1000, 1)
    house = re.search(r"\b(navi|sbi|hdfc|uti|icici|axis|parag parikh|ppfas|kotak|motilal|mirae|zerodha|groww|dsp|tata|quant|"
                      r"edelweiss|bandhan|franklin|aditya birla|hsbc|invesco|nippon)\b", s.last_user_text or "", re.I)
    if house and house.group(1).lower() not in out["name"].lower():
        out["note"] = (f"The user asked about a {house.group(1).title()} fund, which is not in this app's universe. This is the "
                       f"closest asset the app has ({out['ticker']}, {out['name']}); say so clearly.")
    s.emit("asset", f"{out['ticker']} analysis", rep)
    return out


def set_profile(s: Session, amount: float | None = None, horizon_years: float | None = None,
                risk: str | None = None, target_return_pct: float | None = None,
                preferred_sectors: list | str | None = None) -> dict:
    """Set/update the investor profile. Only pass the fields the user actually gave."""
    kw = {}
    if amount is not None:
        kw["amount"] = float(amount)
    if horizon_years is not None:
        kw["horizon_years"] = float(horizon_years)
    if risk is not None:
        kw["risk"] = str(risk)
    if target_return_pct is not None:
        kw["target_return"] = float(target_return_pct) / 100.0
    if preferred_sectors is not None:
        if isinstance(preferred_sectors, str):
            preferred_sectors = [x for x in re.split(r"[,/&]| and ", preferred_sectors) if x.strip()]
        kw["preferred_sectors"] = [str(x) for x in preferred_sectors]
    p = s.set_profile(**kw)
    return dict(status="profile saved", **_profile_dict(s),
                note="Horizon is snapped to 1, 3 or 5 years.")


def get_profile(s: Session) -> dict:
    """Return the current investor profile."""
    return _profile_dict(s)


def _eval_row(name: str, e, recommended: str) -> dict:
    st, m = e.stats, e.mc.stats
    return dict(
        strategy=name, recommended=(name == recommended),
        expected_return_pct=_pct(st["exp_return"]), volatility_pct=_pct(st["volatility"]),
        sharpe=_r(st["sharpe"]), median_cagr_pct=_pct(m["exp_return_median"]),
        prob_positive_pct=_pct(m["prob_positive"], 0), prob_target_pct=_pct(m["prob_target"], 0),
        expected_max_drawdown_pct=_pct(m["exp_max_drawdown"]), var95_1y_pct=_pct(m["var95_1y"]),
        median_final_rs=_inr(m["median_final"]), worst_case_p5_rs=_inr(m["worst_case_p5"]),
        best_case_p95_rs=_inr(m["best_case_p95"]), within_risk_limits=e.within_tolerance,
        limit_breaches=e.breaches, number_of_holdings=int((e.weights > 0).sum()),
    )


def compare_strategies(s: Session) -> dict:
    """Run and compare all five strategies (Max Return, Min Risk, Max Sharpe, Goal-Based, Crash-Resistant)."""
    board = s.ensure_board()
    rows = [_eval_row(n, e, s.recommended) for n, e in board.items()]
    s.emit("strategies", "Strategy comparison", dict(board=board, recommended=s.recommended, why=s.recommended_why,
                                                      profile=s.profile.normalised()))
    return dict(profile=_profile_dict(s), recommended_strategy=s.recommended, why=s.recommended_why,
                strategies=rows)


def resolve_amount(s: Session, amount_rs, cap_to_cash: bool) -> tuple[float | None, str | None]:
    """Turn an amount argument (number, '2,00,000', 'all') into rupees. 'all' = all demo cash. With cap_to_cash the
    amount cannot exceed the wallet's cash. Returns (amount or None for 'use the profile amount', note)."""
    cash = float(s.wallet.cash())
    note = None
    if amount_rs is None or str(amount_rs).strip() == "":
        amt = None
    elif str(amount_rs).strip().lower() in ("all", "max", "everything", "all cash", "full"):
        amt = cash
        note = f"investing all available demo cash (Rs.{cash:,.0f})"
    else:
        amt = float(str(amount_rs).replace(",", "").replace("Rs.", "").replace("₹", "").strip())
        if amt <= 0:
            raise ValueError("amount must be positive")
    if cap_to_cash:
        want = amt if amt is not None else s.profile.normalised().amount
        if want > cash + 1:
            note = f"requested Rs.{want:,.0f} but only Rs.{cash:,.0f} demo cash is available - investing Rs.{cash:,.0f}"
            amt = cash
    return amt, note


def _set_plan_amount(s: Session, amount: float | None) -> None:
    """Re-size the plan to `amount` (the profile amount follows, so every rupee figure matches); keeps the chosen strategy."""
    if amount is None or abs(amount - s.profile.normalised().amount) < 1:
        return
    keep = s.selected_strategy
    s.set_profile(amount=float(amount))
    s.selected_strategy = keep


def _set_plan_horizon(s: Session, horizon_years) -> str | None:
    """Apply a horizon the user asked for. The planner works with 1, 3 or 5 years; anything else is snapped (with a note)."""
    if horizon_years in (None, ""):
        return None
    h = float(horizon_years)
    keep = s.selected_strategy
    p = s.set_profile(horizon_years=max(h, 1.0))
    s.selected_strategy = keep
    if h < 1:
        months = round(h * 12)
        return (f"{months} months is shorter than the planner's shortest horizon (1 year), so this plan uses 1 year. Over a few months "
                f"stock returns are mostly noise: money needed that soon usually belongs in the liquid fund (LIQUIDBEES), not in shares.")
    if abs(p.horizon_years - h) > 0.01:
        return f"the planner works with 1, 3 or 5-year horizons; {h:g} years was rounded to {p.horizon_years} years"
    return None


def get_investment_plan(s: Session, strategy: str | None = None, amount_rs: float | str | None = None,
                        horizon_years: float | None = None) -> dict:
    """Tomorrow's investment plan: asset allocation with rupee amounts and whole-share quantities.
    amount_rs re-sizes the plan to that many rupees ('all' = all demo cash); horizon_years changes the horizon."""
    amt, note = resolve_amount(s, amount_rs, cap_to_cash=False)
    hnote = _set_plan_horizon(s, horizon_years)
    if hnote:
        note = f"{note}; {hnote}" if note else hnote
    _set_plan_amount(s, amt)
    name = _resolve_strategy(s, strategy)
    board = s.ensure_board()
    e = board[name]
    p = s.profile.normalised()
    plan = s.engine.build_plan(e.weights, p)
    s.selected_strategy, s.last_plan = name, plan
    s.emit("plan", f"Tomorrow's Investment Plan - {name}", dict(plan=plan, evaluation=e, profile=p,
                                                                  recommended=s.recommended))
    m = e.mc.stats
    return dict(
        strategy=name, is_recommended=(name == s.recommended), profile=_profile_dict(s),
        data_as_of=str(s.engine.md.last_date.date()),
        allocation=[dict(ticker=r.ticker, name=r.name, sector=r.sector, weight_pct=_pct(r.weight, 1),
                         amount_rs=_inr(r.target_amount), price=_r(r.price), shares=int(r.shares))
                    for r in plan.itertuples()],
        cash_left_rs=_inr(plan.attrs["cash_left"]),
        expected_return_pct=_pct(e.stats["exp_return"]), expected_volatility_pct=_pct(e.stats["volatility"]),
        sharpe=_r(e.stats["sharpe"]), portfolio_beta=_r(e.stats["beta"]),
        next_month_volatility_pct=_pct(e.stats.get("near_term_vol")),
        prob_positive_return_pct=_pct(m["prob_positive"], 0), prob_achieving_target_pct=_pct(m["prob_target"], 0),
        expected_max_drawdown_pct=_pct(m["exp_max_drawdown"]), p95_max_drawdown_pct=_pct(m["p95_max_drawdown"]),
        median_final_value_rs=_inr(m["median_final"]), worst_case_5pct_rs=_inr(m["worst_case_p5"]),
        best_case_95pct_rs=_inr(m["best_case_p95"]),
        plan_amount_rs=_inr(p.amount), **({"note": note} if note else {}),
        within_risk_limits=e.within_tolerance, limit_breaches=e.breaches,
        stress_survival=f"{int(e.stress.survives.sum())}/{len(e.stress)} scenarios within loss limit",
        next_step="Ask the user if they want to stage this plan in the demo wallet.",
    )


def run_monte_carlo(s: Session, strategy: str | None = None) -> dict:
    """Monte Carlo (10,000 paths) results for a strategy: outcome distribution, probabilities, drawdowns."""
    name = _resolve_strategy(s, strategy)
    e = s.ensure_board()[name]
    m, p = e.mc.stats, s.profile.normalised()
    s.emit("montecarlo", f"Monte Carlo - {name}", dict(mc=e.mc, strategy=name, profile=p))
    return dict(
        strategy=name, paths=e.mc.n_paths, horizon_years=p.horizon_years, invested_rs=_inr(p.amount),
        target_return_pct=_pct(p.target_return),
        median_annual_return_pct=_pct(m["exp_return_median"]), mean_annual_return_pct=_pct(m["exp_return_mean"]),
        simulated_volatility_pct=_pct(m["exp_volatility"]),
        prob_positive_pct=_pct(m["prob_positive"], 1), prob_beat_risk_free_pct=_pct(m["prob_beat_riskfree"], 1),
        prob_achieving_target_pct=_pct(m["prob_target"], 1), prob_loss_over_10pct=_pct(m["prob_loss_gt_10"], 1),
        prob_any_loss_in_year1_pct=_pct(m["prob_loss_1y"], 1),
        median_final_rs=_inr(m["median_final"]), worst_case_5pct_rs=_inr(m["worst_case_p5"]),
        best_case_95pct_rs=_inr(m["best_case_p95"]), absolute_worst_rs=_inr(m["absolute_worst"]),
        absolute_best_rs=_inr(m["absolute_best"]),
        var95_1y_pct=_pct(m["var95_1y"]), cvar95_1y_pct=_pct(m["cvar95_1y"]),
        expected_max_drawdown_pct=_pct(m["exp_max_drawdown"]), p95_max_drawdown_pct=_pct(m["p95_max_drawdown"]),
    )


def stress_test(s: Session, strategy: str | None = None) -> dict:
    """Stress-test a strategy: -2/-5/-10% market shocks, sector crash, interest-rate & oil shocks, historical crashes."""
    name = _resolve_strategy(s, strategy)
    e = s.ensure_board()[name]
    p = s.profile.normalised()
    shock_mc = s.engine.shock_monte_carlo(e.weights, p)
    s.emit("stress", f"Stress test - {name}", dict(stress=e.stress, shock_mc=shock_mc, strategy=name, profile=p))
    lim = C.RISK_PROFILES[p.risk]["max_stress_loss"]
    return dict(
        strategy=name, loss_limit_pct=_pct(lim, 0),
        scenarios=[dict(scenario=r.scenario, portfolio_return_pct=_pct(r.portfolio_return, 2),
                        pnl_rs=_inr(r.pnl), survives=bool(r.survives), biggest_hits=r.top_hits)
                   for r in e.stress.itertuples()],
        survival=f"{int(e.stress.survives.sum())}/{len(e.stress)} scenarios within the loss limit",
        monte_carlo_after_shock=[dict(scenario=r.scenario, median_final_rs=_inr(r.median_final),
                                      prob_positive_pct=_pct(r.prob_positive, 0),
                                      prob_target_pct=_pct(r.prob_target, 0))
                                 for r in shock_mc.itertuples()],
    )


def compare_timing(s: Session, strategy: str | None = None) -> dict:
    """Invest now vs wait 1/3/6 months vs SIP (monthly instalments) using simulation on the same paths."""
    name = _resolve_strategy(s, strategy)
    e = s.ensure_board()[name]
    p = s.profile.normalised()
    df = s.engine.timing(e.weights, p)
    s.emit("timing", f"Invest now vs wait vs SIP - {name}", dict(table=df, strategy=name, profile=p))
    return dict(
        strategy=name, market_regime_now=s.engine.regime.current_name, horizon_years=p.horizon_years,
        options=[dict(option=r.strategy, median_final_rs=_inr(r.median_final), expected_final_rs=_inr(r.expected_final),
                      worst_5pct_rs=_inr(r.p5_final), prob_profit_pct=_pct(r.prob_profit, 0),
                      prob_beats_lump_sum_pct=None if pd.isna(r.prob_beats_lump_sum) else _pct(r.prob_beats_lump_sum, 0))
                 for r in df.itertuples()],
        note="Uninvested money earns the risk-free rate while waiting.",
    )


def run_backtest(s: Session, years: int = 3) -> dict:
    """Walk-forward backtest of the strategies over the last N years (weights chosen only from data before the start)."""
    years = int(max(1, min(5, round(float(years)))))
    bt = s.engine.backtest(s.profile.normalised(), years)
    s.emit("backtest", f"Backtest - last {years} years", bt)
    return dict(start=bt["start"], end=bt["end"], years=years,
                results=[dict(strategy=r.strategy, total_return_pct=_pct(r.total_return), cagr_pct=_pct(r.cagr),
                              volatility_pct=_pct(r.volatility), sharpe=_r(r.sharpe),
                              max_drawdown_pct=_pct(r.max_drawdown), final_value_rs=_inr(r.final_value))
                         for r in bt["table"].itertuples()],
                note="Past performance does not guarantee future results.")


def _vol_model_summary() -> dict | None:
    """Measured walk-forward accuracy of the volatility model (models/vol_model_meta.json)."""
    p = C.MODELS_DIR / "vol_model_meta.json"
    if not p.exists():
        return None
    m = json.loads(p.read_text(encoding="utf-8"))
    return dict(model=m["model"], test_period=m["years"], r2=_r(m["r2"], 3), avg_error_pct=_pct(m["err"], 1),
                best_naive_r2=_r(max(m["naive_21d_r2"], m["naive_63d_r2"]), 3), naive_last_month_r2=_r(m["naive_21d_r2"], 3),
                within_asset_r2=_r(m["within_asset_r2"], 3))


def get_model_report(s: Session) -> dict:
    """How the ML models were validated (walk-forward) and what the market-regime model found."""
    est, reg = s.engine.estimator, s.engine.regime
    t = est.metrics
    s.emit("models", "ML model report", dict(metrics=t, regimes=reg.stats, importance=est.feature_importance))
    return dict(
        selected_model=est.model_name, ml_weight_in_expected_returns_pct=_pct(est.skill_weight, 0),
        walk_forward_results=[dict(model=i, rmse=_r(r.get("rmse"), 4), direction_accuracy_pct=_pct(r.get("dir_acc"), 1),
                                   information_coefficient=_r(r.get("ic_cross_section"), 3)) for i, r in t.iterrows()],
        regimes=[dict(regime=i, share_of_days_pct=_pct(r.share, 0), annual_return_pct=_pct(r.ann_return),
                      annual_vol_pct=_pct(r.ann_vol)) for i, r in reg.stats.iterrows()],
        current_regime=reg.current_name,
        volatility_model=_vol_model_summary(),
        note="IC near 0.02-0.05 is typical for monthly return prediction: the ML view is used only as a small tilt. "
             "Volatility is the forecast with real skill. Report these measured numbers only; do not round them up.",
    )


# ----------------------------- demo wallet ------------------------------------ #
def wallet_status(s: Session) -> dict:
    """Demo wallet: cash, holdings marked to the latest close, profit/loss."""
    md = s.engine.md
    v = s.wallet.valuation(md.last_prices(), asof=str(md.last_date.date()))
    pos = v["positions"]
    s.emit("wallet", "Demo wallet", dict(valuation=v, equity=s.wallet.equity_curve(), pending=s.wallet.pending()))
    out = dict(
        demo_money_notice="virtual money only - no real trades", as_of=str(md.last_date.date()),
        cash_rs=_inr(v["cash"]), invested_value_rs=_inr(v["invested_value"]), total_value_rs=_inr(v["total_value"]),
        starting_cash_rs=_inr(v["starting_cash"]), pnl_rs=_inr(v["pnl"]), pnl_pct=_pct(v["pnl_pct"], 2),
        positions=[dict(ticker=D.short(r.symbol), qty=int(r.qty), avg_cost=_r(r.avg_cost), price=_r(r.price),
                        value_rs=_inr(r.value), pnl_rs=_inr(r.pnl), pnl_pct=_pct(r.pnl_pct, 2))
                   for r in pos.itertuples()] if len(pos) else [],
    )
    pend = s.wallet.pending()
    if pend:
        out["staged_order_waiting_for_confirmation"] = pend["label"]
    return out


def wallet_history(s: Session, limit: int = 15) -> dict:
    """Recent demo trades."""
    t = s.wallet.trades(int(limit))
    s.emit("trades", "Trade history", t)
    return dict(trades=[dict(time=r.ts, side=r.side, ticker=D.short(r.symbol), qty=int(r.qty), price=_r(r.price),
                             fee=_r(r.fee)) for r in t.itertuples()] if len(t) else [])


def confirm_pending_order(s: Session) -> dict:
    """Execute the staged order(s) with demo money. Only works if the user's latest message confirms."""
    if not user_confirmed(s.last_user_text):
        return dict(error="REFUSED: the user has not explicitly confirmed in their latest message. "
                          "Ask them to reply 'confirm' first.")
    try:
        res = s.wallet.confirm_pending()
    except WalletError as e:
        return dict(error=str(e))
    md = s.engine.md
    v = s.wallet.valuation(md.last_prices(), asof=str(md.last_date.date()))
    return dict(status="EXECUTED with demo money", filled=[dict(side=r["side"], ticker=D.short(r["symbol"]),
                name=C.UNIVERSE[r["symbol"]][0], sector=C.UNIVERSE[r["symbol"]][1], qty=r["qty"],
                price=_r(r["price"]), fee=_r(r["fee"])) for r in res],
                cash_left_rs=_inr(v["cash"]), total_value_rs=_inr(v["total_value"]))


def cancel_pending_order(s: Session) -> dict:
    """Discard the staged order(s)."""
    return dict(cancelled=s.wallet.cancel_pending())


def add_demo_funds(s: Session, amount: float) -> dict:
    """Top up the demo wallet with virtual money."""
    try:
        cash = s.wallet.add_demo_funds(float(amount))
    except WalletError as e:
        return dict(error=str(e))
    return dict(status="demo funds added", cash_rs=_inr(cash))


def reset_wallet(s: Session) -> dict:
    """Wipe the demo wallet back to Rs.10,00,000 of virtual cash. Needs the user to say 'reset' and confirm."""
    if not ("reset" in s.last_user_text.lower() and user_confirmed(s.last_user_text)):
        return dict(error="REFUSED: ask the user to reply 'yes, reset' to confirm wiping the demo wallet.")
    s.wallet.reset()
    return dict(status="wallet reset", cash_rs=_inr(s.wallet.cash()))


def refresh_market_data(s: Session) -> dict:
    """Download the latest prices from Yahoo Finance and rebuild all analytics (takes ~1 minute)."""
    status = D.download_all(verbose=False)
    failed = [k for k, v in status.items() if v.startswith("FAILED")]
    D.build_dataset()
    D._CACHE.clear()
    from .engine import Engine
    s.engine = Engine()
    s.board = None
    return dict(status="data refreshed", as_of=str(s.engine.md.last_date.date()), failed=failed)


# ----------------------------------------------------------------------------- #
# Registry + JSON schemas
# ----------------------------------------------------------------------------- #
def _fn(name, desc, props=None, required=None):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


from .tools_trading import (invest_plan, trade, rebalance_portfolio, check_portfolio,  # noqa: E402
                             auto_manage_portfolio, set_autonomy)
from .sip import start_sip, sip_status, stop_sip, project_sip, run_due_sips  # noqa: E402

_AMOUNT = {"type": "string", "description": "Rupees to invest, e.g. 200000; 'all' = all demo cash. Omit to use the profile amount."}
_STRAT = {"type": "string", "description": "Max Return | Min Risk | Max Sharpe | Goal-Based | Crash-Resistant. Omit for the recommended one."}

TOOL_FUNCS = {f.__name__: f for f in [
    get_market_overview, list_assets, analyze_asset, set_profile, get_profile, compare_strategies,
    get_investment_plan, run_monte_carlo, stress_test, compare_timing, run_backtest, get_model_report,
    wallet_status, wallet_history, invest_plan, trade, rebalance_portfolio, check_portfolio,
    auto_manage_portfolio, set_autonomy, confirm_pending_order,
    cancel_pending_order, add_demo_funds, reset_wallet, refresh_market_data,
    start_sip, sip_status, stop_sip, project_sip, run_due_sips]}

TOOL_SCHEMAS = [
    _fn("get_market_overview", "Current Indian market snapshot: NIFTY, India VIX, market regime, anomalies."),
    _fn("list_assets", "List investable stocks/ETFs/gold/bonds (optionally filter by sector or asset class).",
        {"sector_or_class": {"type": "string", "description": "e.g. IT, Banking, Pharma, gold, etf"}}),
    _fn("analyze_asset", "Risk/return analysis of one stock or ETF (beta, CAPM, volatility, VaR, ML forecast).",
        {"asset": {"type": "string", "description": "ticker or name, e.g. TCS, HDFCBANK, Gold"}}, ["asset"]),
    _fn("set_profile", "Save the investor profile. Pass only the fields the user stated.",
        {"amount": {"type": "number", "description": "investment amount in rupees"},
         "horizon_years": {"type": "number", "description": "1, 3 or 5"},
         "risk": {"type": "string", "enum": ["low", "medium", "high"]},
         "target_return_pct": {"type": "number", "description": "target annual return in percent, e.g. 12"},
         "preferred_sectors": {"type": "array", "items": {"type": "string"},
                               "description": "e.g. [\"IT\",\"Banking\",\"Gold\"]"}}),
    _fn("get_profile", "Show the current investor profile."),
    _fn("compare_strategies", "Evaluate all five strategies for the current profile and recommend one."),
    _fn("get_investment_plan", "Tomorrow's investment plan: allocation, rupee amounts, shares, expected return, "
                               "volatility, probability of reaching the target.", {"strategy": _STRAT, "amount_rs": _AMOUNT,
                               "horizon_years": {"type": "number"}}),
    _fn("run_monte_carlo", "Monte Carlo simulation results (probabilities, best/median/worst outcomes, drawdown).",
        {"strategy": _STRAT}),
    _fn("stress_test", "Stress test: -2/-5/-10% market shocks, sector crash, interest-rate, oil shock, "
                       "historical crashes, and survival.", {"strategy": _STRAT}),
    _fn("compare_timing", "Compare investing now vs waiting vs SIP.", {"strategy": _STRAT}),
    _fn("run_backtest", "Walk-forward backtest of the strategies over the last N years.",
        {"years": {"type": "number", "description": "1 to 5"}}),
    _fn("get_model_report", "How the ML return models and market-regime model were validated."),
    _fn("wallet_status", "Demo wallet balance, holdings and profit/loss."),
    _fn("wallet_history", "Recent demo trades.", {"limit": {"type": "number"}}),
    _fn("invest_plan", "INVEST: buy every asset of the current plan with demo money (executes when the user told you to).",
        {"strategy": _STRAT, "amount_rs": _AMOUNT}),
    _fn("trade", "BUY or SELL one asset in the demo wallet by quantity or rupee amount. asset='all' + SELL liquidates everything.",
        {"side": {"type": "string", "enum": ["BUY", "SELL"]}, "asset": {"type": "string"},
         "quantity": {"type": "number"}, "amount_rs": {"type": "number"}}, ["side", "asset"]),
    _fn("rebalance_portfolio", "Rebalance current holdings to a strategy's target weights (sells and buys).",
        {"strategy": _STRAT}),
    _fn("check_portfolio", "Health-check the demo portfolio (stop-loss, drift, risk, regime, idle cash) and propose fixes."),
    _fn("auto_manage_portfolio", "Do whatever the portfolio needs now: stop-loss sells, trims, de-risking, rebalancing, deploying idle cash."),
    _fn("set_autonomy", "Set agent autonomy: 'auto' = execute trades when asked, 'ask' = stage and wait for confirmation.",
        {"mode": {"type": "string", "enum": ["auto", "ask"]}}, ["mode"]),
    _fn("confirm_pending_order", "Execute the staged order(s). Call ONLY after the user says confirm/yes."),
    _fn("cancel_pending_order", "Cancel the staged order(s)."),
    _fn("add_demo_funds", "Add virtual money to the demo wallet.", {"amount": {"type": "number"}}, ["amount"]),
    _fn("reset_wallet", "Reset the demo wallet to Rs.10,00,000 (only if the user asks to reset and confirms)."),
    _fn("refresh_market_data", "Download the latest market data (about a minute)."),
    _fn("start_sip", "START a monthly SIP with demo money: invests amount_rs now and every month for `months` months.",
        {"amount_rs": {"type": "number", "description": "rupees per month"}, "months": {"type": "number"}, "strategy": _STRAT}),
    _fn("project_sip", "Projection of a monthly SIP: what amount_rs every month could grow to over `years` (worst/median/best).",
        {"monthly_rs": {"type": "number"}, "years": {"type": "number"}, "initial_rs": {"type": "number"}, "strategy": _STRAT}),
    _fn("sip_status", "List the user's SIPs (monthly amount, instalments done, invested, next date)."),
    _fn("stop_sip", "Stop one SIP (sip_id) or all SIPs; holdings already bought are kept.", {"sip_id": {"type": "number"}}),
]


def call_tool(s: Session, name: str, args: dict | None) -> dict:
    fn = TOOL_FUNCS.get(name)
    if fn is None:
        return dict(error=f"unknown tool {name!r}. Available: {sorted(TOOL_FUNCS)}")
    args = dict(args or {})
    # tolerate small-model slips: unknown argument names are dropped, strings -> numbers
    import inspect
    sig = inspect.signature(fn).parameters
    clean = {k: v for k, v in args.items() if k in sig and k != "s"}
    try:
        return fn(s, **clean)
    except (ValueError, KeyError, TypeError) as e:
        return dict(error=f"{type(e).__name__}: {e}")
    except Exception as e:                                   # pragma: no cover
        return dict(error=f"{type(e).__name__}: {e}", trace=traceback.format_exc(limit=3))
