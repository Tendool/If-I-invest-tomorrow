"""Module 1 - Data acquisition & preprocessing.

Downloads daily OHLCV for the investable universe, the benchmark and macro series from
Yahoo Finance, cleans them and stores a tidy, aligned panel under ``data/``.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config as C

FIELDS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]


# --------------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------------- #
def _download_one(symbol: str, years: int, retries: int = 3, period: str | None = None) -> pd.DataFrame:
    import yfinance as yf

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            df = yf.Ticker(symbol).history(period=period or f"{years}y", interval="1d", auto_adjust=False)
            if df is not None and len(df) > 20:
                df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
                df = df[~df.index.duplicated(keep="last")]
                cols = [c for c in FIELDS if c in df.columns]
                return df[cols]
        except Exception as e:  # network / rate-limit hiccup
            last_err = e
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"could not download {symbol}: {last_err}")


def download_all(years: int = C.HISTORY_YEARS, verbose: bool = True) -> dict[str, str]:
    """Download every symbol and write ``data/raw/<symbol>.csv``. Returns {symbol: status}."""
    symbols = list(C.UNIVERSE) + [C.MARKET_SYMBOL] + list(C.MACRO)
    status: dict[str, str] = {}
    for s in symbols:
        try:
            df = _download_one(s, years)
            df.to_csv(C.DATA_RAW / f"{_fname(s)}.csv")
            status[s] = f"ok rows={len(df)} {df.index[0].date()} -> {df.index[-1].date()}"
        except Exception as e:
            status[s] = f"FAILED {e}"
        if verbose:
            print(f"{s:16s} {status[s]}")
    for s in C.REGIME_LONG_SYMBOLS:                      # full history, for the regime model only
        try:
            df = _download_one(s, years, period="max")
            df.to_csv(C.DATA_RAW / f"long_{_fname(s)}.csv")
            status["long " + s] = f"ok rows={len(df)} {df.index[0].date()} -> {df.index[-1].date()}"
        except Exception as e:
            status["long " + s] = f"FAILED {e}"
        if verbose:
            print(f"{'long ' + s:16s} {status['long ' + s]}")
    return status


def _fname(symbol: str) -> str:
    return symbol.replace("^", "_").replace("=", "_").replace("&", "and")


def _read_raw(symbol: str) -> pd.DataFrame | None:
    p = C.DATA_RAW / f"{_fname(symbol)}.csv"
    if not p.exists():
        return None
    return pd.read_csv(p, index_col=0, parse_dates=True)


# --------------------------------------------------------------------------- #
# Cleaning
# --------------------------------------------------------------------------- #
@dataclass
class MarketData:
    """Cleaned, calendar-aligned market data."""
    prices: pd.DataFrame          # adjusted close, investable assets (columns = symbols)
    volume: pd.DataFrame
    market: pd.Series             # NIFTY 50 level
    macro: pd.DataFrame           # vix, brent, usdinr, us10y, banknifty
    report: dict                  # cleaning statistics
    regime_long: pd.DataFrame | None = None   # long NIFTY + VIX history (columns market, vix) for the regime model only

    @property
    def returns(self) -> pd.DataFrame:
        return self.prices.pct_change()

    @property
    def market_returns(self) -> pd.Series:
        return self.market.pct_change()

    @property
    def last_date(self) -> pd.Timestamp:
        return self.prices.index[-1]

    def last_prices(self) -> pd.Series:
        return self.prices.iloc[-1]


def _liquid_proxy(px: pd.Series, cal: pd.DatetimeIndex) -> pd.Series:
    """Cash proxy: accrue the (approx.) repo rate less a small spread, anchored to the last close."""
    hist = pd.Series({pd.Timestamp(d): r / 100 for d, r in C.REPO_RATE_HISTORY}).sort_index()
    repo = hist.reindex(cal.union(hist.index)).ffill().reindex(cal).bfill()
    acc = (1 + (repo - C.LIQUID_SPREAD) / C.TRADING_DAYS).cumprod()
    last = px.dropna().iloc[-1]
    return acc / acc.iloc[-1] * last


def clean(years_min_history: float = 3.0) -> MarketData:
    """Align to the NSE trading calendar, fill small gaps, drop bad ticks, validate history."""
    mkt_raw = _read_raw(C.MARKET_SYMBOL)
    if mkt_raw is None:
        raise FileNotFoundError("No raw data found. Run `python scripts/download_data.py` first.")
    cal = mkt_raw["Close"].dropna().index          # NSE trading days

    report = {"calendar_days": len(cal), "assets": {}, "dropped": []}
    adj, vol = {}, {}
    for sym in C.UNIVERSE:
        raw = _read_raw(sym)
        if raw is None:
            report["dropped"].append((sym, "missing file"))
            continue
        px = raw["Adj Close"] if "Adj Close" in raw else raw["Close"]
        px = px.reindex(cal)
        n_missing_before = int(px.isna().sum() - px.loc[: px.first_valid_index()].isna().sum()) if px.first_valid_index() is not None else len(px)
        px = px.where(px > 0)
        cls = C.UNIVERSE[sym][2]
        if cls == "cash":
            px = _liquid_proxy(px, cal)
        # bad ticks (wrong-scale prints such as the 19-20 Dec 2019 ETF glitch, or stale/illiquid
        # prints): a price far from its centred 11-day median is a data error.
        lo, hi = (0.96, 1.04) if cls == "bond" else (0.4, 2.5)
        med = px.rolling(11, center=True, min_periods=3).median()
        ratio = px / med
        bad = (ratio < lo) | (ratio > hi)
        n_bad = int(bad.sum())
        if n_bad:
            px = px.mask(bad)
        px = px.ffill(limit=5)
        n_years = px.dropna().shape[0] / C.TRADING_DAYS
        if n_years < years_min_history:
            report["dropped"].append((sym, f"only {n_years:.1f}y history"))
            continue
        adj[sym] = px
        v = raw["Volume"].reindex(cal) if "Volume" in raw else pd.Series(index=cal, dtype=float)
        vol[sym] = v.fillna(0)
        report["assets"][sym] = dict(years=round(n_years, 2), gaps_filled=n_missing_before, bad_ticks=n_bad)

    prices = pd.DataFrame(adj)
    # Common window: from the first date on which *all* assets trade (needed for covariance).
    first_common = prices.apply(lambda s: s.first_valid_index()).max()
    report["first_common_date"] = str(pd.Timestamp(first_common).date())
    volume = pd.DataFrame(vol).reindex(prices.index)

    market = mkt_raw["Close"].reindex(cal).ffill(limit=5)
    macro = pd.DataFrame(index=cal)
    names = {"^INDIAVIX": "vix", "BZ=F": "brent", "USDINR=X": "usdinr", "^TNX": "us10y", "^NSEBANK": "banknifty"}
    for sym, nm in names.items():
        raw = _read_raw(sym)
        if raw is not None:
            macro[nm] = raw["Close"].reindex(cal).ffill(limit=5)
    macro = macro.ffill()

    md = MarketData(prices=prices, volume=volume, market=market, macro=macro, report=report, regime_long=_regime_long(market))
    return md


def _regime_long(market: pd.Series) -> pd.DataFrame | None:
    """Long NIFTY / VIX history if downloaded and as recent as the main data; otherwise None (regime model falls back)."""
    parts = {}
    for sym, name in C.REGIME_LONG_SYMBOLS.items():
        p = C.DATA_RAW / f"long_{_fname(sym)}.csv"
        if not p.exists():
            return None
        parts[name] = pd.read_csv(p, index_col=0, parse_dates=True)["Close"]
    cal = parts["market"].dropna().index
    df = pd.DataFrame({k: v.reindex(cal).ffill(limit=5) for k, v in parts.items()})
    if df.index[-1] < market.dropna().index[-1]:
        return None
    return df


def build_dataset(save: bool = True) -> MarketData:
    md = clean()
    if save:
        md.prices.to_csv(C.DATA_PROC / "prices.csv")
        md.market.to_frame("NIFTY50").to_csv(C.DATA_PROC / "market.csv")
        md.macro.to_csv(C.DATA_PROC / "macro.csv")
        md.returns.to_csv(C.DATA_PROC / "returns.csv")
    return md


_CACHE: dict[str, MarketData] = {}


def load(refresh: bool = False) -> MarketData:
    """Cached loader of the cleaned data."""
    if refresh or "md" not in _CACHE:
        _CACHE["md"] = clean()
    return _CACHE["md"]


def meta(symbol: str) -> dict:
    name, sector, cls = C.UNIVERSE[symbol]
    return dict(symbol=symbol, name=name, sector=sector, asset_class=cls)


def short(symbol: str) -> str:
    """Ticker without the exchange suffix, for display."""
    return symbol.replace(".NS", "")
