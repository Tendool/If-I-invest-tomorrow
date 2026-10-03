"""Custom investment simulator: "I put X (and Y a month) into these assets - what could it become?"

Runs the same fat-tailed, regime-switching Monte Carlo as the planner on an arbitrary user-chosen mix and
reports a year-by-year projection, a monthly fan for charting, and per-asset contributions.
Contributions (the optional monthly SIP) are added at the end of each month.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from . import data as D
from . import montecarlo as MC
from . import risk

MAX_YEARS = 10
MAX_PATHS = 8000


class SimulationError(ValueError):
    pass


def resolve_holdings(engine, holdings: list[dict]) -> pd.Series:
    """[{asset, weight}] -> normalised weight Series indexed by symbol. Weights are relative (any positive scale)."""
    w: dict[str, float] = {}
    for h in holdings or []:
        sym = engine.resolve_symbol(str(h.get("asset", h.get("symbol", ""))))
        if sym is None:
            raise SimulationError(f"unknown asset {h.get('asset', h.get('symbol'))!r}")
        wt = float(h.get("weight", 0) or 0)
        if wt < 0:
            raise SimulationError("weights cannot be negative")
        w[sym] = w.get(sym, 0.0) + wt
    w = {k: v for k, v in w.items() if v > 0}
    if not w:
        raise SimulationError("choose at least one asset with a positive weight")
    s = pd.Series(w)
    return (s / s.sum()).reindex(engine.rm.symbols).fillna(0.0)


def _pct_table(W: np.ndarray) -> dict:
    q = np.quantile(W, [0.05, 0.25, 0.5, 0.75, 0.95], axis=0)
    return dict(p5=q[0], p25=q[1], p50=q[2], p75=q[3], p95=q[4], mean=W.mean(axis=0))


def simulate(engine, holdings: list[dict], amount: float, years: int, monthly: float = 0.0,
             n_paths: int = 6000, seed: int = 17) -> dict:
    amount, monthly = float(amount), float(monthly or 0.0)
    years = int(round(float(years)))
    if amount < 0 or (amount == 0 and monthly <= 0):
        raise SimulationError("enter an amount (or a monthly contribution) greater than zero")
    if monthly < 0:
        raise SimulationError("monthly contribution cannot be negative")
    if not 1 <= years <= MAX_YEARS:
        raise SimulationError(f"horizon must be between 1 and {MAX_YEARS} years")
    n_paths = int(min(n_paths, MAX_PATHS))

    w = resolve_holdings(engine, holdings)
    st = risk.portfolio_stats(w, engine.mu, engine.rm.cov, engine.rm.beta)
    near = engine.near_term_vol(w)

    # --- simulate unit growth paths (daily), then read them on a monthly grid
    paths = MC.simulate_paths(st["exp_return"], st["volatility"], st["beta"], engine.regime, years,
                              n_paths=n_paths, steps_per_year=C.TRADING_DAYS, seed=seed)
    months = years * 12
    idx = [min(21 * k, paths.shape[1] - 1) for k in range(months + 1)]
    P = paths[:, idx].astype(np.float64)                                   # (n, months+1), P[:,0] = 1

    contrib = np.zeros(months + 1)
    contrib[0] = amount
    contrib[1:] = monthly                                                  # end-of-month SIP
    # wealth_m = P_m * sum_{i<=m} c_i / P_i   (each contribution grows with the portfolio from its date)
    W = P * np.cumsum(contrib[None, :] / P, axis=1)
    invested = np.cumsum(contrib)

    pt = _pct_table(W)
    rf, mkt = C.RISK_FREE, engine.rm.market_return
    t = np.arange(months + 1) / 12.0

    def deterministic(rate: float) -> np.ndarray:
        g = (1 + rate) ** t
        return amount * g + monthly * np.array([sum((1 + rate) ** ((m - i) / 12.0) for i in range(1, m + 1)) for m in range(months + 1)])

    fd, nifty = deterministic(rf), deterministic(mkt)

    fan = [dict(month=int(m), year=m / 12.0, invested=float(invested[m]), p5=float(pt["p5"][m]), p25=float(pt["p25"][m]),
                p50=float(pt["p50"][m]), p75=float(pt["p75"][m]), p95=float(pt["p95"][m]),
                fd=float(fd[m]), nifty=float(nifty[m])) for m in range(months + 1)]

    table = []
    for y in range(1, years + 1):
        m = 12 * y
        inv = float(invested[m])
        med = float(pt["p50"][m])
        table.append(dict(
            year=y, invested=inv, p5=float(pt["p5"][m]), p25=float(pt["p25"][m]), median=med, p75=float(pt["p75"][m]),
            p95=float(pt["p95"][m]), expected=float(pt["mean"][m]),
            median_gain=med - inv, median_return=(med / inv - 1) if inv > 0 else 0.0,
            prob_profit=float((W[:, m] > inv).mean()), fd=float(fd[m]), nifty=float(nifty[m]),
            beats_fd=float((W[:, m] > fd[m]).mean())))

    final = W[:, -1]
    hist_edges = np.linspace(np.percentile(final, 0.5), np.percentile(final, 99.5), 41)
    counts, edges = np.histogram(np.clip(final, hist_edges[0], hist_edges[-1]), bins=hist_edges)
    hist = [dict(x=float((edges[i] + edges[i + 1]) / 2), pct=float(counts[i] / len(final) * 100)) for i in range(len(counts))]

    # money-weighted annual return of the median outcome (IRR) when contributions are made
    med_final, tot_inv = float(np.median(final)), float(invested[-1])
    if monthly > 0:
        lo, hi = -0.9, 1.5
        for _ in range(60):
            r = (lo + hi) / 2
            fv = amount * (1 + r) ** years + monthly * sum((1 + r) ** ((months - i) / 12.0) for i in range(1, months + 1))
            lo, hi = (r, hi) if fv < med_final else (lo, r)
        median_annual = (lo + hi) / 2
    else:
        median_annual = (med_final / amount) ** (1 / years) - 1

    prices = engine.md.last_prices()
    breakdown = []
    for sym, wt in w[w > 0].sort_values(ascending=False).items():
        name, sector, cls = C.UNIVERSE[sym]
        mu_i = float(engine.mu[sym])
        breakdown.append(dict(
            symbol=sym, ticker=D.short(sym), name=name, sector=sector, asset_class=cls, weight=float(wt),
            amount=float(wt * amount), monthly=float(wt * monthly), price=float(prices[sym]),
            expected_return=mu_i, volatility=float(engine.rm.capm.loc[sym, "vol"]),
            contribution=float(wt * mu_i), beta=float(engine.rm.beta[sym]),
            projected=float(wt * amount * (1 + mu_i) ** years + wt * monthly * sum((1 + mu_i) ** ((months - i) / 12.0) for i in range(1, months + 1)))))

    return dict(
        inputs=dict(amount=amount, monthly=monthly, years=years, n_paths=n_paths),
        portfolio=dict(expected_return=float(st["exp_return"]), volatility=float(st["volatility"]),
                       next_month_volatility=float(near), beta=float(st["beta"]), sharpe=float(st["sharpe"]),
                       regime=engine.regime.current_name),
        summary=dict(
            total_invested=tot_inv, expected_final=float(final.mean()), median_final=med_final,
            p5_final=float(np.quantile(final, 0.05)), p95_final=float(np.quantile(final, 0.95)),
            expected_gain=float(final.mean() - tot_inv), median_gain=med_final - tot_inv,
            median_annual_return=float(median_annual), prob_profit=float((final > tot_inv).mean()),
            prob_beat_fd=float((final > fd[-1]).mean()), prob_beat_nifty=float((final > nifty[-1]).mean()),
            prob_loss_10=float((final < 0.9 * tot_inv).mean()), fd_final=float(fd[-1]), nifty_final=float(nifty[-1]),
            fd_rate=rf, nifty_rate=mkt),
        fan=fan, table=table, hist=hist, breakdown=breakdown)


def presets(engine) -> list[dict]:
    """Starting points for the 'where to invest' picker."""
    def mk(pid, label, desc, parts):
        hs = []
        for sym, wt in parts:
            hs.append(dict(symbol=sym, ticker=D.short(sym), name=C.UNIVERSE[sym][0], weight=wt))
        return dict(id=pid, label=label, description=desc, holdings=hs)

    out = []
    try:
        board = engine.run_all(engine.profile_default())
        name, _ = engine.recommend(board, engine.profile_default())
        wts = board[name].weights
        parts = [(s, round(float(x) * 100, 1)) for s, x in wts[wts > 0].sort_values(ascending=False).items()]
        out.append(mk("recommended", f"Recommended plan ({name})", "The optimiser's pick for a medium-risk, 3-year, 12% profile.", parts))
    except Exception:
        pass
    out += [
        mk("nifty", "NIFTY 50 index", "The whole market in one fund.", [("NIFTYBEES.NS", 100)]),
        mk("balanced", "Balanced mix", "40% index, 25% bonds, 20% gold, 15% liquid.",
           [("NIFTYBEES.NS", 40), ("LTGILTBEES.NS", 25), ("GOLDBEES.NS", 20), ("LIQUIDBEES.NS", 15)]),
        mk("gold", "Gold", "Gold ETF only.", [("GOLDBEES.NS", 100)]),
        mk("it", "IT leaders", "TCS, Infosys and HCL Tech, equal weight.", [("TCS.NS", 34), ("INFY.NS", 33), ("HCLTECH.NS", 33)]),
        mk("banks", "Banking", "HDFC Bank, ICICI Bank, SBI and Kotak, equal weight.",
           [("HDFCBANK.NS", 25), ("ICICIBANK.NS", 25), ("SBIN.NS", 25), ("KOTAKBANK.NS", 25)]),
        mk("safe", "Capital preservation", "Government bonds and liquid fund.", [("LTGILTBEES.NS", 50), ("LIQUIDBEES.NS", 50)]),
    ]
    return out
