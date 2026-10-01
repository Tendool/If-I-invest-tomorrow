"""Module 5 - Portfolio optimisation (Markowitz mean-variance, efficient frontier, CVaR).

All optimisers share one constraint set built from the user's risk tolerance and
sector preferences: long-only, fully invested, per-asset caps by asset class.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import linprog, minimize

from . import config as C


@dataclass
class Bounds:
    symbols: list[str]
    lb: np.ndarray
    ub: np.ndarray

    @property
    def n(self) -> int:
        return len(self.symbols)


def build_bounds(symbols: list[str], risk: str, preferred: list[str] | None = None) -> Bounds:
    """Per-asset weight bounds from the risk profile and the user's preferred sectors / assets."""
    prof = C.RISK_PROFILES[risk]
    pref = {p.strip().lower() for p in (preferred or []) if p and p.strip()}
    stock_sectors = {C.UNIVERSE[s][1].lower() for s in symbols if C.UNIVERSE[s][2] == "stock"}
    sector_filter = pref & stock_sectors            # restrict single stocks to preferred sectors
    cap_by_class = dict(stock=prof["stock_cap"], etf=prof["etf_cap"], gold=prof["gold_cap"],
                        bond=prof["bond_cap"], cash=prof["cash_cap"])
    lb = np.zeros(len(symbols))
    ub = np.zeros(len(symbols))
    for i, s in enumerate(symbols):
        _, sector, cls = C.UNIVERSE[s]
        cap = cap_by_class[cls]
        if cls == "stock" and sector_filter and sector.lower() not in sector_filter:
            cap = 0.0
        ub[i] = cap
        # explicit preference for gold / bonds => minimum allocation to that class
        if cls in ("gold", "bond") and (sector.lower() in pref or cls in pref):
            lb[i] = min(C.MIN_PREFERRED_CLASS_WEIGHT, cap)
    # feasibility safeguard: if caps cannot reach 100 %, relax them proportionally
    if ub.sum() < 1.0:
        ub = ub * (1.05 / ub.sum())
    return Bounds(list(symbols), lb, np.minimum(ub, 1.0))


def clean_weights(w: np.ndarray, b: Bounds, thr: float = C.MIN_WEIGHT_THRESHOLD) -> pd.Series:
    """Drop dust positions, renormalise and re-impose the caps."""
    w = np.clip(np.asarray(w, dtype=float), 0, None)
    w[w < thr] = 0.0
    if w.sum() <= 0:
        w = np.ones(b.n)
    w = w / w.sum()
    for _ in range(50):
        over = w > b.ub + 1e-9
        if not over.any():
            break
        excess = (w[over] - b.ub[over]).sum()
        w[over] = b.ub[over]
        room = np.where((~over) & (w > 0), b.ub - w, 0.0)
        if room.sum() <= 1e-12:
            room = np.where(~over, b.ub - w, 0.0)
        if room.sum() <= 1e-12:
            break
        w = w + excess * room / room.sum()
    w = w / w.sum()
    return pd.Series(w, index=b.symbols)


def _feasible_start(b: Bounds) -> np.ndarray:
    w = b.lb.copy()
    rest = 1 - w.sum()
    room = b.ub - w
    return w + rest * room / room.sum()


def _solve(obj, b: Bounds, mu: np.ndarray, cov: np.ndarray, extra_cons=(), x0=None) -> np.ndarray:
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0, "jac": lambda w: np.ones_like(w)}, *extra_cons]
    x0 = _feasible_start(b) if x0 is None else x0
    res = minimize(obj, x0, method="SLSQP", bounds=list(zip(b.lb, b.ub)), constraints=cons,
                   options=dict(maxiter=400, ftol=1e-10))
    return res.x


def min_variance(mu: pd.Series, cov: pd.DataFrame, b: Bounds) -> pd.Series:
    S = cov.loc[b.symbols, b.symbols].values
    w = _solve(lambda w: w @ S @ w, b, mu.values, S)
    return clean_weights(w, b)


def max_sharpe(mu: pd.Series, cov: pd.DataFrame, b: Bounds, rf: float = C.RISK_FREE) -> pd.Series:
    m = mu.loc[b.symbols].values
    S = cov.loc[b.symbols, b.symbols].values

    def neg_sharpe(w):
        return -(w @ m - rf) / np.sqrt(w @ S @ w + 1e-12)

    best, best_val = None, np.inf
    starts = [_feasible_start(b), min_variance(mu, cov, b).reindex(b.symbols).values]
    for x0 in starts:
        w = _solve(neg_sharpe, b, m, S, x0=np.clip(x0, b.lb, b.ub))
        v = neg_sharpe(w)
        if v < best_val:
            best, best_val = w, v
    return clean_weights(best, b)


def max_return(mu: pd.Series, b: Bounds) -> pd.Series:
    """LP: maximise expected return subject to the same caps (concentrates in the best assets)."""
    m = mu.loc[b.symbols].values
    res = linprog(-m, A_eq=np.ones((1, b.n)), b_eq=[1.0], bounds=list(zip(b.lb, b.ub)), method="highs")
    return clean_weights(res.x, b)


def target_return_min_var(mu: pd.Series, cov: pd.DataFrame, b: Bounds, target: float) -> pd.Series | None:
    m = mu.loc[b.symbols].values
    S = cov.loc[b.symbols, b.symbols].values
    cons = [{"type": "ineq", "fun": lambda w: w @ m - target, "jac": lambda w: m}]
    w = _solve(lambda w: w @ S @ w, b, m, S, extra_cons=cons)
    if w @ m < target - 5e-4:
        return None
    return clean_weights(w, b)


def min_cvar(scenarios: np.ndarray, b: Bounds, mu: pd.Series, min_return: float,
             beta: float = 0.95) -> pd.Series:
    """Rockafellar-Uryasev LP: minimise CVaR_beta of portfolio loss over a scenario matrix
    (rows = scenarios, columns = assets in ``b.symbols`` order)."""
    T, n = scenarios.shape
    m = mu.loc[b.symbols].values
    c = np.concatenate([np.zeros(n), [1.0], np.full(T, 1.0 / ((1 - beta) * T))])
    # u_t >= -r_t.w - alpha   ->   -r_t.w - alpha - u_t <= 0
    A_ub = np.hstack([-scenarios, -np.ones((T, 1)), -np.eye(T)])
    b_ub = np.zeros(T)
    # expected return floor: -m.w <= -min_return
    A_ub = np.vstack([A_ub, np.concatenate([-m, [0.0], np.zeros(T)])])
    b_ub = np.append(b_ub, -min_return)
    A_eq = np.concatenate([np.ones(n), [0.0], np.zeros(T)])[None, :]
    bounds = list(zip(b.lb, b.ub)) + [(None, None)] + [(0, None)] * T
    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=[1.0], bounds=bounds, method="highs")
    if res.status != 0:        # return floor infeasible -> drop it
        res = linprog(c, A_ub=A_ub[:-1], b_ub=b_ub[:-1], A_eq=A_eq, b_eq=[1.0], bounds=bounds, method="highs")
    return clean_weights(res.x[:n], b)


def efficient_frontier(mu: pd.Series, cov: pd.DataFrame, b: Bounds, n_points: int = 25) -> list[pd.Series]:
    """Portfolios on the efficient frontier between the min-variance and max-return portfolios."""
    lo = float(min_variance(mu, cov, b) @ mu.loc[b.symbols])
    hi = float(max_return(mu, b) @ mu.loc[b.symbols])
    out = []
    for t in np.linspace(lo, hi, n_points):
        w = target_return_min_var(mu, cov, b, float(t))
        if w is not None:
            out.append(w)
    return out


def random_portfolios(mu: pd.Series, cov: pd.DataFrame, b: Bounds, n: int = 3000, seed: int = 11) -> pd.DataFrame:
    """Random feasible portfolios (for the risk-return cloud behind the efficient frontier)."""
    rng = np.random.default_rng(seed)
    elig = np.where(b.ub > 0)[0]
    m = mu.loc[b.symbols].values
    S = cov.loc[b.symbols, b.symbols].values
    rows = []
    for _ in range(n):
        k = rng.integers(3, min(12, len(elig)) + 1)
        idx = rng.choice(elig, size=k, replace=False)
        w = np.zeros(b.n)
        w[idx] = rng.dirichlet(np.ones(k))
        w = np.clip(w, b.lb, b.ub)
        if w.sum() <= 0:
            continue
        w /= w.sum()
        rows.append((float(w @ m), float(np.sqrt(w @ S @ w))))
    df = pd.DataFrame(rows, columns=["ret", "vol"])
    df["sharpe"] = (df["ret"] - C.RISK_FREE) / df["vol"]
    return df
