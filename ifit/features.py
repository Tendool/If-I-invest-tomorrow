"""Module 2 - Feature engineering (returns, moving averages, volatility, beta, indicators)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .data import MarketData

FWD_DAYS = 21   # prediction horizon for the ML return model (~1 trading month)


def rsi(px: pd.Series, n: int = 14) -> pd.Series:
    d = px.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def macd_hist(px: pd.Series) -> pd.Series:
    macd = px.ewm(span=12, adjust=False).mean() - px.ewm(span=26, adjust=False).mean()
    return (macd - macd.ewm(span=9, adjust=False).mean()) / px


def asset_features(px: pd.Series, mkt: pd.Series) -> pd.DataFrame:
    """Technical / statistical features for a single asset (all strictly backward looking)."""
    r = px.pct_change()
    mr = mkt.pct_change()
    f = pd.DataFrame(index=px.index)
    for n in (1, 5, 21, 63, 126, 252):
        f[f"ret_{n}d"] = px.pct_change(n)
    f["vol_21d"] = r.rolling(21).std() * np.sqrt(C.TRADING_DAYS)
    f["vol_63d"] = r.rolling(63).std() * np.sqrt(C.TRADING_DAYS)
    f["vol_ratio"] = f["vol_21d"] / f["vol_63d"]
    f["px_sma20"] = px / px.rolling(20).mean() - 1
    f["px_sma50"] = px / px.rolling(50).mean() - 1
    f["sma50_sma200"] = px.rolling(50).mean() / px.rolling(200).mean() - 1
    f["rsi14"] = rsi(px)
    f["macd_hist"] = macd_hist(px)
    f["dd_252"] = px / px.rolling(252, min_periods=60).max() - 1
    cov = r.rolling(63).cov(mr)
    f["beta_63d"] = cov / mr.rolling(63).var()
    f["corr_mkt_63d"] = r.rolling(63).corr(mr)
    f["skew_63d"] = r.rolling(63).skew()
    return f


def market_features(md: MarketData) -> pd.DataFrame:
    """Market-wide state variables (used for regime clustering, anomaly detection and as ML inputs)."""
    m = md.market
    r = m.pct_change()
    f = pd.DataFrame(index=m.index)
    f["mkt_ret_21d"] = m.pct_change(21)
    f["mkt_ret_63d"] = m.pct_change(63)
    f["mkt_vol_21d"] = r.rolling(21).std() * np.sqrt(C.TRADING_DAYS)
    f["mkt_dd"] = m / m.cummax() - 1
    f["mkt_ma_gap"] = m / m.rolling(200).mean() - 1
    f["vix"] = md.macro["vix"]
    f["vix_chg_21d"] = md.macro["vix"].pct_change(21)
    f["brent_ret_21d"] = md.macro["brent"].pct_change(21)
    f["usdinr_ret_21d"] = md.macro["usdinr"].pct_change(21)
    f["us10y_chg_21d"] = md.macro["us10y"].diff(21)
    return f


REGIME_COLS = ["mkt_ret_21d", "mkt_ret_63d", "mkt_vol_21d", "mkt_dd", "vix"]


def regime_state(market: pd.Series, vix: pd.Series) -> pd.DataFrame:
    """The regime-model inputs (same definitions as in market_features) from a market level and a VIX series."""
    r = market.pct_change()
    return pd.DataFrame({"mkt_ret_21d": market.pct_change(21), "mkt_ret_63d": market.pct_change(63),
                         "mkt_vol_21d": r.rolling(21).std() * np.sqrt(C.TRADING_DAYS), "mkt_dd": market / market.cummax() - 1,
                         "vix": vix}, index=market.index)
MARKET_ML_COLS = ["mkt_ret_21d", "mkt_vol_21d", "mkt_dd", "vix", "vix_chg_21d",
                  "brent_ret_21d", "usdinr_ret_21d", "us10y_chg_21d"]


def build_panel(md: MarketData, with_target: bool = True) -> pd.DataFrame:
    """Long panel (date, symbol) with features and the forward 21-day return target."""
    mf = market_features(md)
    frames = []
    for sym in md.prices.columns:
        px = md.prices[sym].dropna()
        f = asset_features(px, md.market.reindex(px.index).ffill())
        f = f.join(mf[MARKET_ML_COLS], how="left")
        if with_target:
            f["target"] = px.shift(-FWD_DAYS) / px - 1
        f["symbol"] = sym
        frames.append(f)
    panel = pd.concat(frames)
    panel.index.name = "date"
    panel = panel.reset_index().set_index(["date", "symbol"]).sort_index()
    return panel.replace([np.inf, -np.inf], np.nan)


def feature_columns(panel: pd.DataFrame) -> list[str]:
    return [c for c in panel.columns if c != "target"]
