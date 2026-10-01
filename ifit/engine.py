"""Modules 5-7 orchestration: from a user profile to tomorrow's investment plan.

``Engine`` holds all the (expensive, cached) market analytics.  ``Engine.run_all`` builds the five
strategies of the proposal, evaluates each with Monte Carlo + stress tests and recommends one.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

from . import config as C
from . import data as D
from . import ml, risk, optimizer as O, montecarlo as MC

STRATEGIES = ["Max Return", "Min Risk", "Max Sharpe", "Goal-Based", "Crash-Resistant"]
STRATEGY_BLURB = {
    "Max Return": "Highest expected return allowed by the diversification caps (aggressive).",
    "Min Risk": "Lowest-volatility portfolio on the efficient frontier (defensive).",
    "Max Sharpe": "Best return per unit of risk - the tangency portfolio.",
    "Goal-Based": "Frontier portfolio with the highest simulated probability of hitting your target return.",
    "Crash-Resistant": "Minimises expected tail loss (CVaR) over historical returns AND stress scenarios.",
}


# --------------------------------------------------------------------------- #
# User profile
# --------------------------------------------------------------------------- #
@dataclass
class UserProfile:
    amount: float = 100_000.0
    horizon_years: int = 3
    risk: str = "medium"
    target_return: float = 0.12              # annual, decimal
    preferred_sectors: list[str] = field(default_factory=list)

    def normalised(self) -> "UserProfile":
        r = str(self.risk).strip().lower()
        r = {"moderate": "medium", "med": "medium", "conservative": "low", "aggressive": "high"}.get(r, r)
        if r not in C.RISK_PROFILES:
            raise ValueError(f"risk must be low/medium/high, got {self.risk!r}")
        amt = float(self.amount)
        if amt < 1000:
            raise ValueError("investment amount must be at least Rs.1,000")
        yrs = int(round(float(self.horizon_years)))
        if yrs not in (1, 3, 5):
            yrs = min((1, 3, 5), key=lambda y: abs(y - float(self.horizon_years)))
        tgt = float(self.target_return)
        if tgt > 1.0:       # user typed 12 meaning 12 %
            tgt = tgt / 100.0
        sectors = [str(s).strip() for s in (self.preferred_sectors or []) if str(s).strip()]
        return UserProfile(amt, yrs, r, tgt, sectors)

    def key(self) -> tuple:
        p = self.normalised()
        return (p.amount, p.horizon_years, p.risk, round(p.target_return, 4), tuple(sorted(s.lower() for s in p.preferred_sectors)))

    def describe(self) -> str:
        p = self.normalised()
        pref = ", ".join(p.preferred_sectors) if p.preferred_sectors else "none"
        return (f"Rs.{p.amount:,.0f} for {p.horizon_years} year(s), {p.risk} risk, "
                f"target {p.target_return:.1%} p.a., preferred sectors: {pref}")


@dataclass
class Evaluation:
    strategy: str
    weights: pd.Series
    stats: dict                  # analytic exp_return / volatility / sharpe / beta
    mc: MC.MCResult
    stress: pd.DataFrame
    breaches: list[str]

    @property
    def within_tolerance(self) -> bool:
        return not self.breaches


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #
class Engine:
    def __init__(self, md: D.MarketData | None = None, estimator: ml.ReturnEstimator | None = None):
        self.md = md or D.load()
        self.regime = ml.fit_regimes(self.md)
        self.anomaly = ml.detect_anomalies(self.md)
        self.estimator = estimator if estimator is not None else ml.load_return_estimator(self.md)
        self.rm = risk.build_risk_model(self.md)
        self.mu_table = ml.expected_returns(self.rm, self.estimator)
        self.mu = self.mu_table["expected"]
        self._board_cache: dict[tuple, dict[str, Evaluation]] = {}

    # ------------------------------------------------------------------ market
    def market_overview(self) -> dict:
        md, reg = self.md, self.regime
        m = md.market
        r = m.pct_change()
        vix = float(md.macro["vix"].iloc[-1])
        out = dict(
            as_of=str(md.last_date.date()),
            nifty_close=float(m.iloc[-1]),
            nifty_1d=float(r.iloc[-1]),
            nifty_1m=float(m.iloc[-1] / m.iloc[-22] - 1),
            nifty_1y=float(m.iloc[-1] / m.iloc[-253] - 1),
            nifty_drawdown_from_peak=float(m.iloc[-1] / m.cummax().iloc[-1] - 1),
            nifty_vol_1m=float(r.iloc[-21:].std() * np.sqrt(C.TRADING_DAYS)),
            india_vix=vix,
            brent=float(md.macro["brent"].iloc[-1]),
            usdinr=float(md.macro["usdinr"].iloc[-1]),
            regime=reg.current_name,
            regime_probabilities={n: float(p) for n, p in zip(reg.names, reg.current_probs)},
            anomaly_today=self.anomaly.today_is_anomalous,
            anomaly_percentile=self.anomaly.today_score_percentile,
            unusual_stock_moves=[
                dict(symbol=D.short(s), ret=float(row.ret_today), z=float(row.z_score))
                for s, row in self.anomaly.asset_alerts.iterrows()
            ],
            risk_free=C.RISK_FREE,
            market_expected_return=self.rm.market_return,
            ml_model=self.estimator.model_name,
            ml_skill_weight=self.estimator.skill_weight,
        )
        return out

    def asset_report(self, symbol: str) -> dict:
        sym = self.resolve_symbol(symbol)
        if sym is None:
            raise KeyError(f"unknown asset {symbol!r}")
        c = self.rm.capm.loc[sym]
        px = self.md.prices[sym].dropna()
        r = px.pct_change()
        rep = D.meta(sym)
        rep.update(
            last_price=float(px.iloc[-1]),
            ret_1m=float(px.iloc[-1] / px.iloc[-22] - 1), ret_6m=float(px.iloc[-1] / px.iloc[-127] - 1),
            ret_1y=float(px.iloc[-1] / px.iloc[-253] - 1),
            beta=float(c.beta), capm_expected_return=float(c.capm_return),
            hist_return_5y=float(c.hist_return), volatility=float(c.vol), max_drawdown=float(c.mdd),
            var95_1d=float(c.var95_1d), cvar95_1d=float(c.cvar95_1d), sharpe_hist=float(c.sharpe_hist),
            ml_forecast_21d=float(self.estimator.ml_forecast_21d.get(sym, np.nan)),
            final_expected_return=float(self.mu[sym]),
            rsi14=float(__import__("ifit.features", fromlist=["rsi"]).rsi(px).iloc[-1]),
            above_200dma=bool(px.iloc[-1] > px.rolling(200).mean().iloc[-1]),
            ret_today=float(r.iloc[-1]),
        )
        return rep

    def resolve_symbol(self, text: str) -> str | None:
        t = str(text).strip().upper().replace(" ", "")
        for s in C.UNIVERSE:
            if t == s.upper() or t == s.upper().replace(".NS", ""):
                return s
        for s, (name, *_rest) in C.UNIVERSE.items():
            if t and t in name.upper().replace(" ", ""):
                return s
        return None

    # --------------------------------------------------------------- strategies
    def bounds(self, p: UserProfile) -> O.Bounds:
        return O.build_bounds(self.rm.symbols, p.risk, p.preferred_sectors)

    def _stress_matrix(self, w_ref: pd.Series | None = None) -> np.ndarray:
        sectors = sorted({C.UNIVERSE[s][1] for s in self.rm.symbols if C.UNIVERSE[s][2] == "stock"})
        cols = []
        base = risk.asset_shocks(self.rm, self.md, "Banking")
        cols.extend(base.values.T)
        for sec in sectors:      # crash of every sector, so the portfolio is not exposed to any one of them
            cols.append(risk.asset_shocks(self.rm, self.md, sec).filter(like="sector crash").iloc[:, 0].values)
        return np.array(cols)

    def strategy_weights(self, p: UserProfile) -> dict[str, pd.Series]:
        p = p.normalised()
        b = self.bounds(p)
        mu, cov = self.mu, self.rm.cov
        out: dict[str, pd.Series] = {}
        out["Max Return"] = O.max_return(mu, b)
        out["Min Risk"] = O.min_variance(mu, cov, b)
        out["Max Sharpe"] = O.max_sharpe(mu, cov, b)
        out["Goal-Based"] = self._goal_based(p, b)
        out["Crash-Resistant"] = self._crash_resistant(p, b)
        return out

    def _goal_based(self, p: UserProfile, b: O.Bounds) -> pd.Series:
        front = O.efficient_frontier(self.mu, self.rm.cov, b, n_points=22)
        best, best_key = None, None
        probs = []
        for w in front:
            st = risk.portfolio_stats(w, self.mu, self.rm.cov, self.rm.beta)
            pr = MC.quick_prob_target(st["exp_return"], st["volatility"], st["beta"], self.regime,
                                      p.horizon_years, p.target_return)
            probs.append((pr, st["volatility"], w))
        top = max(x[0] for x in probs)
        # among portfolios within 1pp of the best probability take the least volatile one
        cand = [x for x in probs if x[0] >= top - 0.01]
        return min(cand, key=lambda x: x[1])[2]

    def _crash_resistant(self, p: UserProfile, b: O.Bounds) -> pd.Series:
        syms = b.symbols
        rets = self.rm.rets[syms].values
        scen = rets - rets.mean(axis=0) + self.mu.loc[syms].values / C.TRADING_DAYS
        stress = np.repeat(self._stress_matrix()[:, [self.rm.symbols.index(s) for s in syms]], 3, axis=0)
        R = np.vstack([scen, stress])
        return O.min_cvar(R, b, self.mu, min_return=C.RISK_FREE + 0.01)

    # -------------------------------------------------------------- evaluation
    def evaluate(self, name: str, w: pd.Series, p: UserProfile, n_paths: int = C.MC_PATHS) -> Evaluation:
        p = p.normalised()
        st = risk.portfolio_stats(w, self.mu, self.rm.cov, self.rm.beta)
        mc = MC.run_mc(st["exp_return"], st["volatility"], st["beta"], self.regime, p.horizon_years,
                       p.amount, p.target_return, n_paths=n_paths)
        prof = C.RISK_PROFILES[p.risk]
        stress = risk.stress_test(w, self.rm, self.md, p.amount, prof["max_stress_loss"])
        breaches = []
        if st["volatility"] > prof["max_annual_vol"] + 1e-9:
            breaches.append(f"volatility {st['volatility']:.1%} > {prof['max_annual_vol']:.0%} limit")
        synth = stress[~stress.scenario.str.startswith("Replay")]
        worst = float(-synth.portfolio_return.min())
        if worst > prof["max_stress_loss"]:
            breaches.append(f"worst stress loss {worst:.1%} > {prof['max_stress_loss']:.0%} limit")
        if mc.stats["var95_1y"] > prof["max_var95_1y"]:
            breaches.append(f"1-year VaR95 {mc.stats['var95_1y']:.1%} > {prof['max_var95_1y']:.0%} limit")
        return Evaluation(name, w, st, mc, stress, breaches)

    def run_all(self, p: UserProfile, use_cache: bool = True) -> dict[str, Evaluation]:
        p = p.normalised()
        k = p.key()
        if use_cache and k in self._board_cache:
            return self._board_cache[k]
        ws = self.strategy_weights(p)
        board = {n: self.evaluate(n, w, p) for n, w in ws.items()}
        self._board_cache[k] = board
        return board

    def recommend(self, board: dict[str, Evaluation], p: UserProfile) -> tuple[str, str]:
        """Transparent decision rule: among strategies inside the user's risk limits pick the one
        with the highest probability of reaching the target (ties within 2pp -> higher Sharpe)."""
        ok = {n: e for n, e in board.items() if e.within_tolerance}
        if ok:
            top = max(e.mc.stats["prob_target"] for e in ok.values())
            near = {n: e for n, e in ok.items() if e.mc.stats["prob_target"] >= top - 0.02}
            name = max(near, key=lambda n: near[n].stats["sharpe"])
            why = (f"{name} stays within your {p.normalised().risk}-risk limits and has the best chance "
                   f"({board[name].mc.stats['prob_target']:.0%}) of reaching the {p.normalised().target_return:.0%} target.")
        else:
            name = min(board, key=lambda n: board[n].stats["volatility"])
            why = (f"No strategy fully fits your {p.normalised().risk}-risk limits; {name} is the closest "
                   f"(lowest volatility {board[name].stats['volatility']:.1%}).")
        return name, why

    # ------------------------------------------------------------- the plan
    def build_plan(self, w: pd.Series, p: UserProfile) -> pd.DataFrame:
        """Convert weights to a whole-share order list using the latest close ("tomorrow's plan")."""
        p = p.normalised()
        w = w[w > 0].sort_values(ascending=False)
        px = self.md.last_prices()
        rows = []
        for s, wt in w.items():
            name, sector, cls = C.UNIVERSE[s]
            rows.append(dict(symbol=s, ticker=D.short(s), name=name, sector=sector, asset_class=cls,
                             weight=float(wt), target_amount=float(wt * p.amount), price=float(px[s])))
        df = pd.DataFrame(rows)
        # keep room for trading costs
        budget = p.amount / (1 + C.BROKERAGE_RATE + C.SLIPPAGE_RATE)
        df["shares"] = np.floor(df.target_amount / (1 + C.BROKERAGE_RATE + C.SLIPPAGE_RATE) / df.price).astype(int)
        spent = float((df.shares * df.price).sum())
        left = budget - spent
        # hand out the leftover cash one share at a time to the most under-allocated asset
        for _ in range(500):
            gap = (df.target_amount / (1 + C.BROKERAGE_RATE + C.SLIPPAGE_RATE) - df.shares * df.price)
            afford = df.price <= left
            if not afford.any():
                break
            i = (gap.where(afford)).idxmax()
            if gap[i] < df.price[i] * 0.5:
                break
            df.loc[i, "shares"] += 1
            left -= df.price[i]
        df["invested"] = df.shares * df.price
        df["actual_weight"] = df.invested / p.amount
        df.attrs["cash_left"] = float(p.amount - df.invested.sum() * (1 + C.BROKERAGE_RATE + C.SLIPPAGE_RATE))
        return df

    # -------------------------------------------------------- extra analyses
    def shock_monte_carlo(self, w: pd.Series, p: UserProfile, n_paths: int = 4000) -> pd.DataFrame:
        """Monte Carlo conditional on a day-0 shock (market -2/-5/-10 %, sector crash, rate, oil)."""
        p = p.normalised()
        st = risk.portfolio_stats(w, self.mu, self.rm.cov, self.rm.beta)
        sec_w: dict[str, float] = {}
        for s, x in w.items():
            if C.UNIVERSE[s][2] == "stock":
                sec_w[C.UNIVERSE[s][1]] = sec_w.get(C.UNIVERSE[s][1], 0) + x
        sector = max(sec_w, key=sec_w.get) if sec_w else "Banking"
        shocks = risk.asset_shocks(self.rm, self.md, sector)
        wv = w.reindex(self.rm.symbols).fillna(0.0)
        rows = [dict(scenario="No shock (base case)", day0_impact=0.0,
                     **self._mc_row(st, p, 0.0, n_paths))]
        for sc in shocks.columns:
            if sc.startswith("Replay"):
                continue
            imp = float((wv * shocks[sc]).sum())
            rows.append(dict(scenario=sc, day0_impact=imp, **self._mc_row(st, p, imp, n_paths)))
        return pd.DataFrame(rows)

    def _mc_row(self, st: dict, p: UserProfile, shock: float, n_paths: int) -> dict:
        res = MC.run_mc(st["exp_return"], st["volatility"], st["beta"], self.regime, p.horizon_years,
                        p.amount, p.target_return, n_paths=n_paths, shock=shock, seed=321)
        s = res.stats
        return dict(median_final=s["median_final"], median_cagr=s["exp_return_median"],
                    prob_positive=s["prob_positive"], prob_target=s["prob_target"],
                    worst_case_p5=s["worst_case_p5"], prob_loss_gt_10=s["prob_loss_gt_10"])

    def timing(self, w: pd.Series, p: UserProfile) -> pd.DataFrame:
        p = p.normalised()
        st = risk.portfolio_stats(w, self.mu, self.rm.cov, self.rm.beta)
        return MC.timing_comparison(st["exp_return"], st["volatility"], st["beta"], self.regime,
                                    max(p.horizon_years, 1), p.amount)

    def frontier(self, p: UserProfile, n_points: int = 25) -> dict:
        p = p.normalised()
        b = self.bounds(p)
        pts = O.efficient_frontier(self.mu, self.rm.cov, b, n_points)
        fr = pd.DataFrame([risk.portfolio_stats(w, self.mu, self.rm.cov) for w in pts])
        cloud = O.random_portfolios(self.mu, self.rm.cov, b)
        elig = [s for s, u in zip(b.symbols, b.ub) if u > 0]
        assets = pd.DataFrame({"ret": self.mu[elig], "vol": np.sqrt(np.diag(self.rm.cov.loc[elig, elig]))}, index=elig)
        return dict(frontier=fr, cloud=cloud, assets=assets)

    # ---------------------------------------------------------------- backtest
    def backtest(self, p: UserProfile, years: int = 3, rebalance_days: int = 63) -> dict:
        """Walk-forward test: choose weights using only data up to the start date, then hold
        (rebalancing quarterly) until today. ML is excluded (no look-ahead), prior = CAPM+history."""
        p = p.normalised()
        md = self.md
        end = md.last_date
        start = md.prices.index[md.prices.index.get_indexer([end - pd.DateOffset(years=years)], method="nearest")[0]]
        rm0 = risk.build_risk_model(md, asof=start)
        mu0 = ml.expected_returns(rm0, None)["expected"]
        b = O.build_bounds(rm0.symbols, p.risk, p.preferred_sectors)
        ws = {
            "Max Return": O.max_return(mu0, b),
            "Min Risk": O.min_variance(mu0, rm0.cov, b),
            "Max Sharpe": O.max_sharpe(mu0, rm0.cov, b),
        }
        front = O.efficient_frontier(mu0, rm0.cov, b, 18)
        goal = None
        for w in front:
            if float(w @ mu0.loc[w.index]) >= p.target_return:
                goal = w
                break
        ws["Goal-Based"] = goal if goal is not None else front[-1]
        rets0 = rm0.rets[rm0.symbols].values
        scen = rets0 - rets0.mean(axis=0) + mu0.loc[rm0.symbols].values / C.TRADING_DAYS
        ws["Crash-Resistant"] = O.min_cvar(scen, b, mu0, C.RISK_FREE + 0.01)

        r = md.prices[rm0.symbols].loc[start:].pct_change().dropna(how="all").fillna(0.0)
        curves = {}
        for name, w in ws.items():
            val, hold, out = 1.0, w.reindex(rm0.symbols).fillna(0.0).values, []
            for i, (_, row) in enumerate(r.iterrows()):
                if i % rebalance_days == 0:
                    hold = val * w.reindex(rm0.symbols).fillna(0.0).values
                hold = hold * (1 + row.values)
                val = hold.sum()
                out.append(val)
            curves[name] = pd.Series(out, index=r.index)
        mk = md.market.loc[start:]
        curves["NIFTY 50 (benchmark)"] = (mk / mk.iloc[0]).reindex(r.index).ffill()
        eq = (1 + r[[s for s in rm0.symbols if C.UNIVERSE[s][2] == "stock"]].mean(axis=1)).cumprod()
        curves["Equal-weight stocks"] = eq
        curve_df = pd.DataFrame(curves)
        rows = []
        for name, s in curve_df.items():
            dr = s.pct_change().dropna()
            n_y = len(s) / C.TRADING_DAYS
            cagr = float(s.iloc[-1] ** (1 / n_y) - 1)
            vol = float(dr.std() * np.sqrt(C.TRADING_DAYS))
            rows.append(dict(strategy=name, total_return=float(s.iloc[-1] - 1), cagr=cagr, volatility=vol,
                             sharpe=risk.sharpe_ratio(cagr, vol), max_drawdown=risk.max_drawdown(s.values),
                             final_value=float(s.iloc[-1] * p.amount)))
        return dict(start=str(start.date()), end=str(end.date()), years=years,
                    table=pd.DataFrame(rows), curves=curve_df, weights=ws)
