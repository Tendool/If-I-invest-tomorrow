"""Earnings-based features (quarterly results of the NSE stocks), all point in time.

Source: data/earnings/<SYMBOL>.csv from scripts/download_earnings.py (Yahoo Finance: date, EPS estimate, reported EPS, surprise).
A result counts from the first trading day *after* its announcement date, whatever the hour, so no feature can see a result
before the market could. Future (scheduled) announcements in the files are never used directly: the next results date is
projected from past dates only.

Return features (post-earnings announcement drift; Ball & Brown 1968, Bernard & Thomas 1989):
  surprise        - EPS surprise % of the latest result, while it is at most 63 trading days old
  ear             - the stock's market-adjusted return over the 3 trading days after the latest result (same 63-day window)
Volatility features:
  earn_in_window  - share of the next 21 trading days that falls within +-3 days of the projected next result
  earn_jump       - how much more the stock moves on result days than on other days (log ratio, past results only)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .data import MarketData

EARN_DIR = C.DATA_RAW.parent / "earnings"
CARRY = 63            # trading days a result stays "fresh"


def _file(sym: str):
    return EARN_DIR / f"{sym.replace('&', 'and')}.csv"


def download(verbose: bool = True) -> int:
    """Fetch quarterly results (date, EPS estimate, reported EPS, surprise) for every stock from Yahoo Finance."""
    import time
    import yfinance as yf
    EARN_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for s, (_, _, cls) in C.UNIVERSE.items():
        if cls != "stock":
            continue
        df = None
        for _ in range(3):
            try:
                df = yf.Ticker(s).get_earnings_dates(limit=100)
                break
            except Exception:                           # pragma: no cover - network
                time.sleep(3)
        if df is None or df.empty:
            if verbose:
                print(s, "no earnings data")
            continue
        ts = df.index.tz_convert("Asia/Kolkata")
        out = pd.DataFrame({"announced_ist": ts.tz_localize(None), "eps_estimate": df["EPS Estimate"].values,
                            "eps_reported": df["Reported EPS"].values, "surprise_pct": df["Surprise(%)"].values})
        out.sort_values("announced_ist").drop_duplicates("announced_ist").to_csv(_file(s), index=False)
        n += 1
        if verbose:
            print(f"{s:16s} {len(out):3d} results")
        time.sleep(0.5)
    return n


def load_events(md: MarketData) -> dict[str, pd.DataFrame]:
    """Per stock: announcement date, the trading-day position from which it is known, and the surprise."""
    idx = md.prices.index
    out = {}
    for s in md.prices.columns:
        if C.UNIVERSE[s][2] != "stock" or not _file(s).exists():
            continue
        e = pd.read_csv(_file(s), parse_dates=["announced_ist"])
        e = e[e["eps_reported"].notna() | e["surprise_pct"].notna()].copy()           # only results that actually happened
        e["day"] = e["announced_ist"].dt.normalize()
        e["pos_known"] = idx.searchsorted(e["day"], side="right")                     # first trading day after the announcement date
        e = e[e["pos_known"] < len(idx)]
        out[s] = e.reset_index(drop=True)
    return out


def return_features(md: MarketData) -> pd.DataFrame:
    """(date, symbol) surprise and earnings-announcement return, NaN where no fresh result (and for non-stocks)."""
    idx = md.prices.index
    r = md.prices.pct_change(fill_method=None)
    mr = md.market.pct_change(fill_method=None).reindex(idx)
    sur = pd.DataFrame(np.nan, index=idx, columns=md.prices.columns)
    ear = pd.DataFrame(np.nan, index=idx, columns=md.prices.columns)
    for s, e in load_events(md).items():
        ab = (r[s] - mr).values
        for _, row in e.iterrows():
            k = int(row["pos_known"])
            if not np.isnan(row["surprise_pct"]):
                sur.iloc[k:k + CARRY, sur.columns.get_loc(s)] = float(np.clip(row["surprise_pct"], -100, 100))
            # reaction: the announcement day itself if it was a trading day, else the next one, plus two more days
            d0 = idx.searchsorted(row["day"], side="left")
            if d0 + 3 < len(idx):
                val = float(np.nansum(ab[d0:d0 + 3]))
                ear.iloc[d0 + 3:d0 + 3 + CARRY, ear.columns.get_loc(s)] = val
    out = pd.concat([sur.stack(future_stack=True).rename("surprise"), ear.stack(future_stack=True).rename("ear")], axis=1)
    out.index.names = ["date", "symbol"]
    return out


def vol_features(md: MarketData) -> pd.DataFrame:
    """(date, symbol) projected-results window and the stock's typical result-day jump; 0 for non-stocks."""
    idx = md.prices.index
    n = len(idx)
    r = md.prices.pct_change(fill_method=None)
    inwin = pd.DataFrame(0.0, index=idx, columns=md.prices.columns)
    jump = pd.DataFrame(0.0, index=idx, columns=md.prices.columns)
    for s, e in load_events(md).items():
        days = e["day"].values
        d0s = idx.searchsorted(e["day"], side="left")
        absr = r[s].abs()
        base = absr.rolling(756, min_periods=126).mean().values
        col = inwin.columns.get_loc(s)
        jcol = jump.columns.get_loc(s)
        # result-day moves known so far (each result enters after its 2-day reaction)
        react = np.full(n, np.nan)
        for d0 in d0s:
            if d0 + 2 < n:
                react[d0 + 2] = np.nanmean(absr.values[d0:d0 + 2]) / base[d0] if base[d0] and not np.isnan(base[d0]) else np.nan
        ratio = pd.Series(react).expanding(min_periods=4).apply(lambda x: np.nanmean(x[~np.isnan(x)][-8:]), raw=True)
        jump.iloc[:, jcol] = np.log(ratio.ffill().clip(lower=0.5, upper=6.0)).fillna(0.0).values
        # projected next result: last known result + the median gap of past results (dates before t only)
        known = e["pos_known"].values
        dnum = days.astype("datetime64[D]").astype(np.int64)            # whole days, integer arithmetic
        tnum = idx.values.astype("datetime64[D]").astype(np.int64)
        for t in range(n):
            past = dnum[known <= t]
            if len(past) < 3:
                continue
            nxt = past[-1] + float(np.median(np.diff(past[-9:])))
            lo, hi = nxt - 3, nxt + 3
            start, end = tnum[t] + 1, tnum[t] + 30                          # next 21 trading days ~ the next 30 calendar days
            ov = min(end, hi) - max(start, lo) + 1
            inwin.iat[t, col] = max(ov, 0) / 30.0
    out = pd.concat([inwin.stack(future_stack=True).rename("earn_in_window"), jump.stack(future_stack=True).rename("earn_jump")], axis=1)
    out["earn_window_x_jump"] = out["earn_in_window"] * out["earn_jump"]
    out.index.names = ["date", "symbol"]
    return out
