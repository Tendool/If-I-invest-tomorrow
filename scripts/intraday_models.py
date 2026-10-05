"""Intraday volatility models from free Yahoo Finance intraday bars (NSE, 30 stocks and ETFs; cash and the illiquid gilt ETF excluded).

    python scripts/intraday_models.py download   # 5-minute bars (last ~60 days) and 60-minute bars (last ~2 years) -> data/intraday/
    python scripts/intraday_models.py hour       # next-HOUR realised volatility, measured from 5-minute returns
    python scripts/intraday_models.py day        # next-DAY realised volatility, measured from hourly returns

Both are walk-forward: models are refit on everything before each test day and scored on later days only. R2 is on log
realised volatility, pooled over assets (plus a within-asset version), against naive baselines on identical rows.
"""
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.linear_model import Ridge  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from ifit import config as C, data  # noqa: E402

DIR = ROOT / "data" / "intraday"
TARGET = "lpk" if "--range" in sys.argv else "lrv"           # lrv: from close-to-close returns; lpk: Parkinson (high-low) - a more precise measurement
SFX = "_range" if TARGET == "lpk" else ""
SYMS = [s for s, v in C.UNIVERSE.items() if v[2] not in ("cash", "bond")] + [C.MARKET_SYMBOL]


def download():
    import yfinance as yf
    DIR.mkdir(parents=True, exist_ok=True)
    for iv, per in (("5m", "60d"), ("60m", "730d")):
        for s in SYMS:
            try:
                df = yf.Ticker(s).history(period=per, interval=iv)
                df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)
                df[["Open", "High", "Low", "Close", "Volume"]].to_csv(DIR / f"{iv}_{data._fname(s)}.csv")
                print(f"{iv:4s} {s:15s} {len(df):5d} bars {df.index[0]} -> {df.index[-1]}", flush=True)
            except Exception as e:
                print(f"{iv:4s} {s:15s} FAILED {e}", flush=True)


def bars(iv, s):
    p = DIR / f"{iv}_{data._fname(s)}.csv"
    return pd.read_csv(p, index_col=0, parse_dates=True) if p.exists() else None


def r2(y, p):
    y, p = np.asarray(y), np.asarray(p)
    return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def within_r2(df, col):
    g = df.groupby("sym")
    wy, wp = df.y - g.y.transform("mean"), df[col] - g[col].transform("mean")
    return float(1 - ((wy - wp) ** 2).sum() / (wy ** 2).sum())


def report(df, cols, title, path):
    out = {}
    for c in cols:
        out[c] = dict(r2=r2(df.y, df[c]), within_asset_r2=within_r2(df, c), corr=float(np.corrcoef(df.y, df[c])[0, 1]),
                      err=float(np.mean(np.abs(np.exp(df[c] - df.y) - 1))))
    print(f"\n{title}  ({len(df):,} forecasts, {df.sym.nunique()} assets, {df.day.nunique()} test days)")
    for c, m in sorted(out.items(), key=lambda kv: -kv[1]["r2"]):
        print(f"  {c:44s} R2 {m['r2']:.3f}  within-asset {m['within_asset_r2']:.3f}  corr {m['corr']:.3f}  avg err {m['err'] * 100:.1f}%")
    json.dump(dict(rows=len(df), assets=int(df.sym.nunique()), test_days=int(df.day.nunique()), results=out), open(path, "w"), indent=1)
    return out


def walk_forward(panel, feats, first_test_frac=0.5, step_days=5, alpha=10.0):
    """Expanding window: refit every `step_days` test days on all rows strictly before the first day of the block."""
    days = np.array(sorted(panel.day.unique()))
    start = int(len(days) * first_test_frac)
    preds = []
    for i in range(start, len(days), step_days):
        block = days[i: i + step_days]
        tr = panel[panel.day < block[0]].dropna(subset=feats + ["y"])
        te = panel[panel.day.isin(block)].dropna(subset=feats + ["y"])
        if te.empty:
            continue
        m = make_pipeline(StandardScaler(), Ridge(alpha=alpha)).fit(tr[feats].values, tr.y.values)
        preds.append(te.assign(model=m.predict(te[feats].values)))
    return pd.concat(preds)


# ================================================================================ next hour (from 5-minute bars)
def hour_panel():
    rows = []
    mkt = None
    for s in SYMS:
        b = bars("5m", s)
        if b is None:
            continue
        b = b[(b.index.time >= pd.Timestamp("09:15").time()) & (b.index.time < pd.Timestamp("15:15").time())]   # six full hours
        b["day"] = b.index.normalize()
        b["slot"] = ((b.index.hour * 60 + b.index.minute) - (9 * 60 + 15)) // 60                                # 0..5
        lr = np.log(b.Close).groupby(b.day).diff()                                                           # 5-min returns within the day only
        b["r2_5m"] = lr ** 2
        b["pk_5m"] = np.log(b.High / b.Low).clip(lower=0) ** 2 / (4 * np.log(2))    # Parkinson variance of each 5-min bar
        h = b.groupby(["day", "slot"]).agg(rv=("r2_5m", "sum"), pk=("pk_5m", "sum"), n=("r2_5m", "count"), hi=("High", "max"), lo=("Low", "min"),
                                            vol=("Volume", "sum"), close=("Close", "last"), open=("Open", "first"))
        h = h[h.n >= 10]
        h["lrv"] = np.log(np.sqrt(h.rv.clip(lower=1e-10)))
        h["lpk"] = np.log(np.sqrt(h.pk.clip(lower=1e-10)))
        h["lrange"] = np.log(np.log(h.hi / h.lo).clip(lower=1e-5))
        h = h.reset_index()
        h["sym"] = s
        rows.append(h)
    p = pd.concat(rows).sort_values(["sym", "day", "slot"]).reset_index(drop=True)
    g = p.groupby("sym")
    p["y"] = g[TARGET].shift(-1)                               # target: log volatility of the NEXT hour
    p["next_slot"] = g.slot.shift(-1)
    p["next_day"] = g.day.shift(-1)
    p["lrv_1"] = p[TARGET]                                     # last hour
    p["lpk_1"], p["lrv_close_1"] = p.lpk, p.lrv
    p["lrv_mean6"] = g[TARGET].transform(lambda x: x.rolling(6, min_periods=3).mean())       # ~ last day
    p["lrv_mean30"] = g[TARGET].transform(lambda x: x.rolling(30, min_periods=12).mean())    # ~ last week
    p["lrange_1"] = p.lrange
    p["lvol_ratio"] = np.log((p.vol + 1) / (g.vol.transform(lambda x: x.rolling(30, min_periods=12).mean()) + 1))
    p["new_day"] = (p.next_day != p.day).astype(float)        # next hour is tomorrow's opening hour
    # same slot yesterday for the target hour (6 hours back from the target = 5 back from now)
    p["lrv_same_slot_yday"] = g[TARGET].shift(5)
    for k in range(6):
        p[f"slot_{k}"] = (p.next_slot == k).astype(float)
    # market-wide: NIFTY's last-hour log RV at the same time
    m = p[p.sym == C.MARKET_SYMBOL][["day", "slot", TARGET]].rename(columns={TARGET: "mkt_lrv_1"})
    p = p.merge(m, on=["day", "slot"], how="left")
    p = p[p.sym != C.MARKET_SYMBOL]
    p["day"] = p.next_day                                      # a forecast belongs to the day of its target hour
    return p.dropna(subset=["y", "next_slot"])


def run_hour():
    p = hour_panel()
    feats = ["lrv_1", "lpk_1", "lrv_close_1", "lrv_mean6", "lrv_mean30", "lrange_1", "lvol_ratio", "lrv_same_slot_yday", "new_day", "mkt_lrv_1"] + [f"slot_{k}" for k in range(1, 6)]
    df = walk_forward(p, feats, first_test_frac=0.5, step_days=3)
    # baselines on the same rows: last hour; average of the last ~day; average of this time-of-day over the training past (per asset)
    df["naive: same as last hour"] = df.lrv_1
    df["naive: average of the last 6 hours"] = df.lrv_mean6
    tod = p.groupby(["sym", "next_slot"]).y.transform(lambda x: x.shift(1).expanding(min_periods=5).mean())   # past-only time-of-day mean
    df["naive: usual level for this hour of the day"] = tod.reindex(df.index)
    df = df.dropna(subset=["naive: usual level for this hour of the day"])
    df = df.rename(columns={"model": "Ridge (HAR + time-of-day + range + market)"})
    report(df, ["Ridge (HAR + time-of-day + range + market)", "naive: same as last hour", "naive: average of the last 6 hours",
                "naive: usual level for this hour of the day"], f"NEXT-HOUR volatility (5-minute bars, measured by {'high-low range' if SFX else 'close-to-close returns'})", C.REPORTS_DIR / f"intraday_hour{SFX}.json")


# ================================================================================ next day (from hourly bars)
def day_panel():
    rows = []
    for s in SYMS:
        b = bars("60m", s)
        if b is None:
            continue
        b["day"] = b.index.normalize()
        lr = np.log(b.Close).groupby(b.day).diff()            # within-day hourly returns
        pk = np.log(b.High / b.Low).clip(lower=0) ** 2 / (4 * np.log(2))
        d = pd.DataFrame({"rv": (lr ** 2).groupby(b.day).sum(), "pk": pk.groupby(b.day).sum(), "n": lr.groupby(b.day).count(),
                          "hi": b.High.groupby(b.day).max(), "lo": b.Low.groupby(b.day).min(),
                          "open": b.Open.groupby(b.day).first(), "close": b.Close.groupby(b.day).last(), "vol": b.Volume.groupby(b.day).sum()})
        d = d[d.n >= 4]
        d["lrv"] = np.log(np.sqrt(d.rv.clip(lower=1e-10)))
        d["lpk"] = np.log(np.sqrt(d.pk.clip(lower=1e-10)))
        d["gap"] = np.log(d.open / d.close.shift(1)).abs()
        d["lrange"] = np.log(np.log(d.hi / d.lo).clip(lower=1e-5))
        d["sym"] = s
        rows.append(d.reset_index().rename(columns={"index": "day"}))
    p = pd.concat(rows).sort_values(["sym", "day"]).reset_index(drop=True)
    g = p.groupby("sym")
    p["y"] = g[TARGET].shift(-1)
    p["target_day"] = g.day.shift(-1)
    p["lrv_1"] = p[TARGET]
    p["lpk_1"], p["lrv_close_1"] = p.lpk, p.lrv
    p["lrv_5"] = g[TARGET].transform(lambda x: x.rolling(5).mean())
    p["lrv_22"] = g[TARGET].transform(lambda x: x.rolling(22).mean())
    p["lrv_66"] = g[TARGET].transform(lambda x: x.rolling(66, min_periods=30).mean())
    p["lrange_1"] = p.lrange
    p["lrange_5"] = g.lrange.transform(lambda x: x.rolling(5).mean())
    p["lgap"] = np.log(p.gap.clip(lower=1e-5))
    p["lvol_ratio"] = np.log((p.vol + 1) / (g.vol.transform(lambda x: x.rolling(22).mean()) + 1))
    m = p[p.sym == C.MARKET_SYMBOL][["day", TARGET, "lrange"]].rename(columns={TARGET: "mkt_lrv_1", "lrange": "mkt_lrange_1"})
    p = p.merge(m, on="day", how="left")
    md = data.load()
    vix = np.log(md.macro["vix"])
    p["lvix"] = vix.reindex(p.day).values
    p["dow"] = pd.to_datetime(p.target_day).dt.dayofweek
    for k in range(1, 5):
        p[f"dow_{k}"] = (p.dow == k).astype(float)
    p = p[p.sym != C.MARKET_SYMBOL]
    p["day"] = p.target_day
    return p.dropna(subset=["y"])


def run_day():
    p = day_panel()
    feats = ["lrv_1", "lpk_1", "lrv_close_1", "lrv_5", "lrv_22", "lrv_66", "lrange_1", "lrange_5", "lgap", "lvol_ratio", "mkt_lrv_1", "mkt_lrange_1", "lvix"] + [f"dow_{k}" for k in range(1, 5)]
    df = walk_forward(p, feats, first_test_frac=0.4, step_days=10)
    df["naive: same as yesterday"] = df.lrv_1
    df["naive: average of the last 5 days"] = df.lrv_5
    df["naive: average of the last 22 days"] = df.lrv_22
    df = df.rename(columns={"model": "Ridge (HAR + range + gap + market + VIX)"})
    report(df, ["Ridge (HAR + range + gap + market + VIX)", "naive: same as yesterday", "naive: average of the last 5 days", "naive: average of the last 22 days"],
           f"NEXT-DAY volatility (hourly bars, measured by {'high-low range' if SFX else 'close-to-close returns'})", C.REPORTS_DIR / f"intraday_day{SFX}.json")


if __name__ == "__main__":
    {"download": download, "hour": run_hour, "day": run_day}[sys.argv[1]]()
