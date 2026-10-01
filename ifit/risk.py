"""Module 4 - Risk & financial engineering.

CAPM, covariance estimation, Sharpe, VaR / CVaR, maximum drawdown and the stress tests.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.covariance import LedoitWolf

from . import config as C
from .data import MarketData

TD = C.TRADING_DAYS


# --------------------------------------------------------------------------- #
# Basic statistics
# --------------------------------------------------------------------------- #
def annualised_return(r: pd.Series) -> float:
    r = r.dropna()
    return float((1 + r).prod() ** (TD / len(r)) - 1) if len(r) else np.nan


def annualised_vol(r: pd.Series) -> float:
    return float(r.dropna().std() * np.sqrt(TD))


def sharpe_ratio(mu: float, vol: float, rf: float = C.RISK_FREE) -> float:
    return float((mu - rf) / vol) if vol > 1e-12 else 0.0


def max_drawdown(values: pd.Series | np.ndarray) -> float:
    v = np.asarray(values, dtype=float)
    peak = np.maximum.accumulate(v)
    return float(np.min(v / peak - 1))


def historical_var(r: pd.Series | np.ndarray, alpha: float = 0.95) -> float:
    """Loss (positive number) not exceeded with probability alpha."""
    return float(-np.quantile(np.asarray(r, dtype=float), 1 - alpha))


def historical_cvar(r: pd.Series | np.ndarray, alpha: float = 0.95) -> float:
    x = np.asarray(r, dtype=float)
    q = np.quantile(x, 1 - alpha)
    tail = x[x <= q]
    return float(-tail.mean()) if len(tail) else float(-q)


def parametric_var(mu: float, sigma: float, alpha: float = 0.95) -> float:
    return float(-(mu + sigma * stats.norm.ppf(1 - alpha)))


# --------------------------------------------------------------------------- #
# Risk model: CAPM + covariance + factor sensitivities
# --------------------------------------------------------------------------- #
@dataclass
class RiskModel:
    symbols: list[str]
    capm: pd.DataFrame          # beta, alpha, r2, capm_return, hist_return, vol, sharpe ...
    cov: pd.DataFrame           # annualised covariance (Ledoit-Wolf shrinkage)
    corr: pd.DataFrame
    rets: pd.DataFrame          # daily returns used (look-back window)
    market_return: float        # CAPM market expected return
    erp: float
    oil_beta: pd.Series         # asset sensitivity to Brent (controlling for market)
    nifty_oil_beta: float       # market's sensitivity to Brent
    asof: pd.Timestamp

    @property
    def beta(self) -> pd.Series:
        return self.capm["beta"]


def build_risk_model(md: MarketData, asof: pd.Timestamp | None = None,
                     lookback_years: int = C.COV_LOOKBACK_YEARS) -> RiskModel:
    prices = md.prices
    mkt = md.market
    if asof is not None:
        prices = prices.loc[:asof]
        mkt = mkt.loc[:asof]
    end = prices.index[-1]
    start = end - pd.DateOffset(years=lookback_years)
    rets = prices.loc[start:].pct_change().dropna(how="all")
    rets = rets.dropna(axis=1, thresh=int(0.8 * len(rets)))   # need a decent history
    rets = rets.fillna(0.0)
    mret = mkt.pct_change().reindex(rets.index).fillna(0.0)
    brent = md.macro["brent"].reindex(prices.index).pct_change().reindex(rets.index).fillna(0.0)
    rf_d = C.RISK_FREE / TD

    # --- single-index (CAPM) regression on excess returns
    X = (mret - rf_d).values
    rows = {}
    for s in rets.columns:
        y = (rets[s] - rf_d).values
        slope, intercept, r_val, _, _ = stats.linregress(X, y)
        rows[s] = dict(beta=slope, alpha_ann=intercept * TD, r2=r_val ** 2)
    capm = pd.DataFrame(rows).T

    # --- market expected return (blend of history and prior ERP)
    n_years = len(mret) / TD
    hist_mkt = (1 + mret).prod() ** (1 / n_years) - 1 + 0.013      # + ~1.3 % dividend yield
    erp = float(np.clip(0.5 * (hist_mkt - C.RISK_FREE) + 0.5 * C.EQUITY_RISK_PREMIUM_PRIOR, 0.03, 0.08))
    market_return = C.RISK_FREE + erp
    capm["capm_return"] = C.RISK_FREE + capm["beta"] * erp

    # --- history & risk
    capm["hist_return"] = [annualised_return(rets[s]) for s in capm.index]
    capm["vol"] = [annualised_vol(rets[s]) for s in capm.index]
    capm["mdd"] = [max_drawdown((1 + rets[s]).cumprod()) for s in capm.index]
    capm["var95_1d"] = [historical_var(rets[s], 0.95) for s in capm.index]
    capm["cvar95_1d"] = [historical_cvar(rets[s], 0.95) for s in capm.index]
    capm["sharpe_hist"] = [sharpe_ratio(capm.loc[s, "hist_return"], capm.loc[s, "vol"]) for s in capm.index]

    # --- covariance: Ledoit-Wolf shrinkage on daily returns
    lw = LedoitWolf().fit(rets.values)
    cov = pd.DataFrame(lw.covariance_ * TD, index=rets.columns, columns=rets.columns)
    d = np.sqrt(np.diag(cov.values))
    corr = pd.DataFrame(cov.values / np.outer(d, d), index=rets.columns, columns=rets.columns)

    # --- oil sensitivity: r_i = a + b_m r_m + b_o r_oil
    Z = np.column_stack([np.ones(len(rets)), mret.values, brent.values])
    oil_b = {}
    for s in rets.columns:
        coef, *_ = np.linalg.lstsq(Z, rets[s].values, rcond=None)
        oil_b[s] = coef[2]
    nifty_oil = float(stats.linregress(brent.values, mret.values).slope)

    return RiskModel(symbols=list(rets.columns), capm=capm, cov=cov, corr=corr, rets=rets,
                     market_return=market_return, erp=erp, oil_beta=pd.Series(oil_b),
                     nifty_oil_beta=nifty_oil, asof=pd.Timestamp(end))


# --------------------------------------------------------------------------- #
# Portfolio-level helpers
# --------------------------------------------------------------------------- #
def portfolio_stats(w: pd.Series, mu: pd.Series, cov: pd.DataFrame, beta: pd.Series | None = None) -> dict:
    w = w.reindex(cov.index).fillna(0.0)
    m = float(w @ mu.reindex(cov.index))
    v = float(np.sqrt(w.values @ cov.values @ w.values))
    out = dict(exp_return=m, volatility=v, sharpe=sharpe_ratio(m, v))
    if beta is not None:
        out["beta"] = float(w @ beta.reindex(cov.index).fillna(0.0))
    return out


def historical_portfolio_returns(w: pd.Series, rets: pd.DataFrame) -> pd.Series:
    return (rets * w.reindex(rets.columns).fillna(0.0)).sum(axis=1)


# --------------------------------------------------------------------------- #
# Stress testing
# --------------------------------------------------------------------------- #
def asset_shocks(rm: RiskModel, md: MarketData, sectors_crash: str | None = None) -> pd.DataFrame:
    """Per-asset return under each stress scenario (columns = scenarios, index = assets)."""
    syms = rm.symbols
    beta = rm.beta.reindex(syms)
    sector = pd.Series({s: C.UNIVERSE[s][1] for s in syms})
    cls = pd.Series({s: C.UNIVERSE[s][2] for s in syms})
    cols: dict[str, pd.Series] = {}

    for sh in C.MARKET_SHOCKS:
        cols[f"Market {sh:+.0%} shock"] = beta * sh

    if sectors_crash:
        hit = (sector == sectors_crash) & (cls != "cash")
        contagion = beta * (-0.01)
        cols[f"{sectors_crash} sector crash ({C.SECTOR_CRASH:+.0%})"] = pd.Series(
            np.where(hit, C.SECTOR_CRASH, contagion), index=syms)

    # interest-rate shock: sector sensitivities for equities / gold, duration for bonds
    sens = sector.map(C.SECTOR_RATE_SENSITIVITY).fillna(-0.03) * (C.RATE_SHOCK_BPS / 100)
    sens = sens.where(cls != "bond", -C.BOND_DURATION * C.RATE_SHOCK_BPS / 1e4)
    sens = sens.where(cls != "cash", 0.0)
    cols[f"Interest-rate shock (+{C.RATE_SHOCK_BPS}bps)"] = sens

    # oil shock: market reaction (through nifty~brent beta) + stock-specific oil beta
    mkt_react = rm.nifty_oil_beta * C.OIL_SHOCK
    oil = beta * mkt_react + rm.oil_beta.reindex(syms) * C.OIL_SHOCK
    cols[f"Oil-price shock ({C.OIL_SHOCK:+.0%} Brent)"] = oil

    # historical crash replays
    px = md.prices
    for name, (a, b) in C.HISTORICAL_CRASHES.items():
        sub = px.loc[a:b]
        mk = md.market.loc[a:b]
        mret = mk.iloc[-1] / mk.iloc[0] - 1
        vals = {}
        for s in syms:
            col = sub[s].dropna()
            if len(col) > 0.8 * len(sub) and col.index[0] <= sub.index[3]:
                vals[s] = col.iloc[-1] / col.iloc[0] - 1
            else:
                vals[s] = beta[s] * mret      # asset did not exist: fall back on its beta
        cols[f"Replay: {name}"] = pd.Series(vals)
    return pd.DataFrame(cols)


def stress_test(w: pd.Series, rm: RiskModel, md: MarketData, amount: float,
                max_loss: float, sector: str | None = None) -> pd.DataFrame:
    w = w.reindex(rm.symbols).fillna(0.0)
    if sector is None:
        sec_w = {}
        for s, x in w.items():
            if C.UNIVERSE[s][2] == "stock":
                sec_w[C.UNIVERSE[s][1]] = sec_w.get(C.UNIVERSE[s][1], 0) + x
        sector = max(sec_w, key=sec_w.get) if sec_w else "Banking"
    shocks = asset_shocks(rm, md, sector)
    rows = []
    for sc in shocks.columns:
        contrib = w * shocks[sc]
        pr = float(contrib.sum())
        worst = contrib.sort_values().head(2)
        rows.append(dict(
            scenario=sc, portfolio_return=pr, pnl=pr * amount,
            survives=bool(-pr <= max_loss),
            top_hits=", ".join(f"{s.replace('.NS','')} ({v*100:.1f}%)" for s, v in worst.items() if v < 0),
        ))
    return pd.DataFrame(rows)
