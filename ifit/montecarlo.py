"""Module 6 - Monte Carlo simulation.

Portfolio value paths are simulated with

* Student-t innovations (fat tails),
* a 3-state Markov regime process (Bull/Calm, Neutral, Bear/Volatile) estimated from NIFTY data,
  which scales volatility and shifts drift (volatility clustering),
* an optional day-0 shock (market -2/-5/-10 %, sector crash ...), after which the market is
  assumed to be in the Bear/Volatile regime.

For a constant-mix portfolio of jointly Student-t assets the portfolio return is itself
Student-t, so simulating at portfolio level is exact for the linear combination while being
orders of magnitude cheaper than simulating every asset.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config as C
from .ml import RegimeModel


# --------------------------------------------------------------------------- #
# Path simulation
# --------------------------------------------------------------------------- #
def _stationary(T: np.ndarray) -> np.ndarray:
    vals, vecs = np.linalg.eig(T.T)
    v = np.real(vecs[:, np.argmax(np.real(vals))])
    v = np.abs(v)
    return v / v.sum()


def simulate_paths(mu_p: float, sigma_p: float, beta_p: float, regime: RegimeModel | None,
                   years: float, n_paths: int = C.MC_PATHS, steps_per_year: int = 252,
                   shock: float = 0.0, seed: int = 123, dof: int = C.MC_T_DOF, extra_drift_se: float = 0.0) -> np.ndarray:
    """Return growth factors V_t/V_0, shape (n_paths, steps+1), float32.

    extra_drift_se: additional standard error of the expected return (e.g. model uncertainty), added in quadrature."""
    rng = np.random.default_rng(seed)
    spy = steps_per_year
    steps = max(int(round(years * spy)), 1)
    dt = 1.0 / spy

    if regime is not None:
        k = regime.transition.shape[0]
        T = np.linalg.matrix_power(regime.transition, max(int(round(C.TRADING_DAYS / spy)), 1))
        pi = _stationary(regime.transition)
        raw_mult = regime.mkt_vol_daily / np.sqrt((pi * regime.mkt_vol_daily ** 2).sum())
        mult = np.clip(raw_mult, 0.5, 3.0)
        tilt_ann = beta_p * (regime.mkt_mean_daily - (pi * regime.mkt_mean_daily).sum()) * C.TRADING_DAYS
        tilt_ann = np.clip(tilt_ann, -0.25, 0.25)
        start_p = regime.current_probs / regime.current_probs.sum()
        reg = rng.choice(k, size=n_paths, p=start_p)
        if shock <= -0.02:
            reg = np.full(n_paths, k - 1)          # a crash day puts the market in the bear state
        cum = T.cumsum(axis=1)
    else:
        mult = np.ones(1)
        tilt_ann = np.zeros(1)
        reg = np.zeros(n_paths, dtype=int)
        cum = np.ones((1, 1))

    eps = rng.standard_t(dof, size=(n_paths, steps)).astype(np.float32) / np.sqrt(dof / (dof - 2.0))
    # Parameter uncertainty: the expected return is estimated from ~COV_LOOKBACK_YEARS of history, so its standard
    # error is sigma / sqrt(years). Each path draws its own drift error (mean-preserving); widens long horizons honestly.
    # Calibration backtest (scripts/model_search_v4.py mc): mean coverage gap 0.078 -> 0.051.
    drift_err = np.zeros(n_paths, dtype=np.float32)
    se = np.sqrt((sigma_p ** 2 / C.COV_LOOKBACK_YEARS if C.MC_PARAM_UNCERTAINTY else 0.0) + extra_drift_se ** 2)
    if se > 0:
        drift_err = rng.normal(-0.5 * se ** 2 * years, se, n_paths).astype(np.float32)
    logv = np.zeros((n_paths, steps + 1), dtype=np.float32)
    u = rng.random((n_paths, steps)).astype(np.float32)
    # Volatility uncertainty: each path draws its own volatility level (mean-preserving log-normal multiplier), sized by how much
    # next-year volatility differs from trailing volatility. Drawn last, so the other random streams are unchanged.
    vmult = np.ones(n_paths, dtype=np.float32)
    if C.MC_VOL_UNCERTAINTY > 0:
        s = C.MC_VOL_UNCERTAINTY
        vmult = np.exp(rng.normal(-0.5 * s ** 2, s, n_paths)).astype(np.float32)
    sig_step = sigma_p * np.sqrt(dt) * vmult
    for t in range(steps):
        sig = sig_step * mult[reg]
        # ln(1+mu): mu is an *annual effective* expected return, so E[V_T] = (1+mu)^T
        drift = np.log1p(np.clip(mu_p + tilt_ann[reg], -0.9, None)) * dt - 0.5 * sig ** 2
        logv[:, t + 1] = logv[:, t] + drift + drift_err * dt + sig * eps[:, t]
        if cum.shape[0] > 1:
            reg = (u[:, t][:, None] > cum[reg]).sum(axis=1).clip(max=cum.shape[0] - 1)
    v = np.exp(logv)
    if shock:
        v *= np.float32(1.0 + shock)
    return v


# --------------------------------------------------------------------------- #
# Result container + summary statistics
# --------------------------------------------------------------------------- #
@dataclass
class MCResult:
    years: float
    amount: float
    target: float | None
    n_paths: int
    stats: dict
    fan: pd.DataFrame                 # percentile bands over time (in currency)
    hist_edges: np.ndarray
    hist_counts: np.ndarray
    sample_paths: np.ndarray          # (30, grid) currency values
    terminal: np.ndarray = field(repr=False, default=None)
    grid_years: np.ndarray = field(repr=False, default=None)


def summarise(v: np.ndarray, years: float, amount: float, target: float | None,
              steps_per_year: int = 252, rf: float = C.RISK_FREE) -> MCResult:
    n, m = v.shape
    steps = m - 1
    term = v[:, -1].astype(np.float64)
    cagr = term ** (1.0 / years) - 1
    peak = np.maximum.accumulate(v, axis=1)
    mdd = (v / peak - 1).min(axis=1)
    lr = np.diff(np.log(np.maximum(v, 1e-9)), axis=1)
    if lr.shape[1] > 1:
        ann_vol = float(lr.std(axis=1).mean() * np.sqrt(steps_per_year))
    else:
        ann_vol = float(lr.std())

    one_y = min(steps_per_year, steps)
    ret_1y = v[:, one_y].astype(np.float64) - 1
    total = term - 1

    stats = dict(
        exp_return_mean=float(cagr.mean()),               # mean of annualised (CAGR) outcomes
        exp_return_median=float(np.median(cagr)),
        exp_volatility=ann_vol,
        prob_positive=float((term > 1).mean()),
        prob_beat_riskfree=float((cagr > rf).mean()),
        prob_target=float((cagr >= target).mean()) if target is not None else None,
        prob_loss_gt_10=float((total < -0.10).mean()),
        expected_final=float(term.mean() * amount),
        median_final=float(np.median(term) * amount),
        best_case_p95=float(np.quantile(term, 0.95) * amount),
        worst_case_p5=float(np.quantile(term, 0.05) * amount),
        absolute_best=float(term.max() * amount),
        absolute_worst=float(term.min() * amount),
        var95_horizon=float(max(-np.quantile(total, 0.05), 0.0)),
        cvar95_horizon=float(max(-total[total <= np.quantile(total, 0.05)].mean(), 0.0)),
        var95_1y=float(max(-np.quantile(ret_1y, 0.05), 0.0)),
        cvar95_1y=float(max(-ret_1y[ret_1y <= np.quantile(ret_1y, 0.05)].mean(), 0.0)),
        prob_loss_1y=float((ret_1y < 0).mean()),
        exp_max_drawdown=float(-mdd.mean()),
        p95_max_drawdown=float(-np.quantile(mdd, 0.05)),
        median_max_drawdown=float(-np.median(mdd)),
    )
    # fan chart on a ~60-point grid
    idx = np.unique(np.linspace(0, steps, min(61, steps + 1)).astype(int))
    q = np.quantile(v[:, idx], [0.05, 0.25, 0.5, 0.75, 0.95], axis=0) * amount
    fan = pd.DataFrame(q.T, columns=["p5", "p25", "p50", "p75", "p95"])
    fan.insert(0, "year", idx / steps_per_year)
    counts, edges = np.histogram(term * amount, bins=45)
    return MCResult(years=years, amount=amount, target=target, n_paths=n, stats=stats, fan=fan,
                    hist_edges=edges, hist_counts=counts,
                    sample_paths=(v[:30][:, idx] * amount), terminal=term * amount,
                    grid_years=idx / steps_per_year)


def run_mc(mu_p: float, sigma_p: float, beta_p: float, regime: RegimeModel | None, years: float,
           amount: float, target: float | None, n_paths: int = C.MC_PATHS, shock: float = 0.0,
           seed: int = 123, steps_per_year: int = 252) -> MCResult:
    v = simulate_paths(mu_p, sigma_p, beta_p, regime, years, n_paths, steps_per_year, shock, seed)
    return summarise(v, years, amount, target, steps_per_year)


def quick_prob_target(mu_p: float, sigma_p: float, beta_p: float, regime: RegimeModel | None,
                      years: float, target: float, n_paths: int = 3000, seed: int = 5) -> float:
    """Fast P(CAGR >= target) used when searching the efficient frontier (weekly steps)."""
    v = simulate_paths(mu_p, sigma_p, beta_p, regime, years, n_paths, 52, 0.0, seed)
    cagr = v[:, -1].astype(np.float64) ** (1 / years) - 1
    return float((cagr >= target).mean())


# --------------------------------------------------------------------------- #
# Invest now vs wait vs SIP
# --------------------------------------------------------------------------- #
def timing_comparison(mu_p: float, sigma_p: float, beta_p: float, regime: RegimeModel | None,
                      years: float, amount: float, n_paths: int = 6000, seed: int = 99,
                      rf: float = C.RISK_FREE) -> pd.DataFrame:
    """Compare lump-sum now, waiting k months, and a monthly SIP, on identical simulated paths.

    Money not yet invested sits in cash earning ``rf``. All variants are measured at the same
    horizon, so the comparison is on final wealth.
    """
    v = simulate_paths(mu_p, sigma_p, beta_p, regime, years, n_paths, 252, 0.0, seed).astype(np.float64)
    months = int(round(years * 12))
    P = v[:, [min(21 * k, v.shape[1] - 1) for k in range(months + 1)]]      # monthly grid
    cash = (1 + rf) ** (np.arange(months + 1) / 12.0)
    PT = P[:, -1]

    finals: dict[str, np.ndarray] = {"Invest now (lump sum)": amount * PT}
    for k in (1, 3, 6):
        if k < months:
            finals[f"Wait {k} month{'s' if k > 1 else ''}, then invest"] = amount * cash[k] * PT / P[:, k]
    for m in (6, 12):
        if m <= months:
            acc = np.zeros(n_paths)
            for i in range(m):
                acc += (amount / m) * cash[i] * PT / P[:, i]
            finals[f"SIP over {m} months"] = acc

    base = finals["Invest now (lump sum)"]
    rows = []
    for name, f in finals.items():
        rows.append(dict(
            strategy=name,
            expected_final=float(f.mean()), median_final=float(np.median(f)),
            p5_final=float(np.quantile(f, 0.05)), p95_final=float(np.quantile(f, 0.95)),
            prob_beats_lump_sum=float((f > base).mean()) if name != "Invest now (lump sum)" else np.nan,
            prob_profit=float((f > amount).mean()),
            median_cagr=float((np.median(f) / amount) ** (1 / years) - 1),
        ))
    return pd.DataFrame(rows)
