"""Tune the hour / day / week volatility models (they were built in one pass). Target measurement is fixed (high-low range);
each candidate is chosen on a validation period that precedes the test period, and scored on the SAME test rows as before.

    python scripts/short_horizon_search.py hour|day|week
"""
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
warnings.filterwarnings("ignore")

import lightgbm as lgb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.linear_model import Ridge  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from ifit import config as C, data, ml  # noqa: E402

import intraday_models as IM  # noqa: E402

IM.TARGET = "lpk"


def r2(y, p):
    y, p = np.asarray(y), np.asarray(p)
    return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def within(df, col, key):
    g = df.groupby(key)
    wy, wp = df.y - g.y.transform("mean"), df[col] - g[col].transform("mean")
    return float(1 - ((wy - wp) ** 2).sum() / (wy ** 2).sum())


def fit_predict(kind, tr, te, feats):
    X, y = tr[feats].values, tr.y.values
    if kind.startswith("ridge"):
        a = float(kind.split(":")[1])
        return make_pipeline(StandardScaler(), Ridge(alpha=a)).fit(X, y).predict(te[feats].values)
    if kind == "lgbm":
        m = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=100, subsample=0.8, subsample_freq=1,
                              colsample_bytree=0.8, reg_lambda=10.0, random_state=7, verbose=-1, n_jobs=-1)
        return m.fit(np.nan_to_num(X), y).predict(np.nan_to_num(te[feats].values))
    if kind == "avg":
        return 0.5 * fit_predict("ridge:10", tr, te, feats) + 0.5 * fit_predict("lgbm", tr, te, feats)
    raise KeyError(kind)


def walk(panel, feats, kind, days, step, purge_days=0):
    """Expanding walk-forward over the given test days (refit every `step` days on all earlier rows)."""
    out = []
    for i in range(0, len(days), step):
        blk = days[i: i + step]
        tr = panel[panel.day < pd.Timestamp(blk[0]) - pd.Timedelta(days=purge_days)].dropna(subset=feats + ["y"])
        te = panel[panel.day.isin(blk)].dropna(subset=feats + ["y"])
        if te.empty or len(tr) < 500:
            continue
        out.append(te.assign(pred=fit_predict(kind, tr, te, feats)))
    return pd.concat(out)


def search(panel, feature_sets, kinds, val_days, test_days, step, key, baseline_col, label, purge_days=0):
    res = {}
    for fs_name, feats in feature_sets.items():
        for kind in kinds:
            v = walk(panel, feats, kind, val_days, step, purge_days)
            t = walk(panel, feats, kind, test_days, step, purge_days)
            res[f"{fs_name} | {kind}"] = dict(val_r2=r2(v.y, v.pred), test_r2=r2(t.y, t.pred), test_within=within(t, "pred", key),
                                              test_err=float(np.mean(np.abs(np.exp(t.pred - t.y) - 1))), n=len(t))
            m = res[f"{fs_name} | {kind}"]
            print(f"  {fs_name + ' | ' + kind:48s} val R2 {m['val_r2']:.3f} | test R2 {m['test_r2']:.3f} within {m['test_within']:.3f} err {m['test_err'] * 100:.1f}%  n={m['n']}", flush=True)
    chosen = max(res, key=lambda k: res[k]["val_r2"])
    print(f"{label}: chosen on validation -> {chosen}: test R2 {res[chosen]['test_r2']:.3f}, within {res[chosen]['test_within']:.3f}, err {res[chosen]['test_err'] * 100:.1f}%")
    return dict(results=res, chosen=chosen)


# ================================================================================ hour
def run_hour():
    p = IM.hour_panel()
    p = p.sort_values(["sym", "day", "next_slot"])
    # past-only per-asset time-of-day level of the target hour, and slot-specific persistence
    p["tod_level"] = p.groupby(["sym", "next_slot"]).y.transform(lambda x: x.shift(1).expanding(min_periods=3).mean())
    p["mkt_tod_level"] = p.groupby("next_slot").y.transform(lambda x: x.shift(1).expanding(min_periods=30).mean())
    for k in range(6):
        p[f"lrv1_x_slot{k}"] = p.lrv_1 * (p.next_slot == k)
    p["dow"] = pd.to_datetime(p.day).dt.dayofweek
    for k in range(1, 5):
        p[f"dow_{k}"] = (p.dow == k).astype(float)
    base = ["lrv_1", "lpk_1", "lrv_close_1", "lrv_mean6", "lrv_mean30", "lrange_1", "lvol_ratio", "lrv_same_slot_yday", "new_day", "mkt_lrv_1"] + [f"slot_{k}" for k in range(1, 6)]
    fs = {"production features": base, "+ time-of-day levels": base + ["tod_level", "mkt_tod_level"],
          "+ time-of-day levels + slot persistence + weekday": base + ["tod_level", "mkt_tod_level"] + [f"lrv1_x_slot{k}" for k in range(6)] + [f"dow_{k}" for k in range(1, 5)]}
    days = np.array(sorted(p.day.unique()))
    half = int(len(days) * 0.5)
    val_days, test_days = days[int(len(days) * 0.25): half], days[half:]          # same test days as the published model
    out = search(p, fs, ["ridge:10", "ridge:300", "lgbm", "avg"], val_days, test_days, 3, "sym", None, "NEXT HOUR")
    (C.REPORTS_DIR / "short_search_hour.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


# ================================================================================ day
def run_day():
    p = IM.day_panel()
    # long-history daily features for the same asset and date (12 years of daily OHLC), as of the forecast day
    md = data.load()
    keep = [c for c in md.prices.columns if C.UNIVERSE[c][2] not in ("cash", "bond")]
    import dataclasses
    vp = ml.vol_panel(dataclasses.replace(md, prices=md.prices[keep], volume=md.volume[keep]))
    longf = ["park_5", "park_21", "park_63", "gk_5", "gk_21", "rv_63", "rv_252", "ewma_0.94", "lr_level", "rv21_vs_lr", "semi_dn_21", "vix_chg_5", "m_rv_21"]
    vp = vp[longf].reset_index().rename(columns={"date": "fday", "symbol": "sym"})
    # the forecast is made at the close of the previous trading day (day_panel relabels each row with its target day)
    p["fday"] = p.groupby("sym").day.shift(1)        # day labels were moved to the target day; the forecast day is the previous row's target
    p = p.merge(vp, on=["fday", "sym"], how="left")
    p["park_1"] = p.lrange_1
    base = ["lrv_1", "lpk_1", "lrv_close_1", "lrv_5", "lrv_22", "lrv_66", "lrange_1", "lrange_5", "lgap", "lvol_ratio", "mkt_lrv_1", "mkt_lrange_1", "lvix"] + [f"dow_{k}" for k in range(1, 5)]
    fs = {"production features": base, "+ 12-year daily-bar features": base + longf}
    days = np.array(sorted(p.day.dropna().unique()))
    val_days, test_days = days[int(len(days) * 0.2): int(len(days) * 0.4)], days[int(len(days) * 0.4):]
    out = search(p, fs, ["ridge:10", "ridge:300", "lgbm", "avg"], val_days, test_days, 10, "sym", None, "NEXT DAY")
    (C.REPORTS_DIR / "short_search_day.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


# ================================================================================ week
def run_week():
    import dataclasses
    md = data.load()
    keep = [c for c in md.prices.columns if C.UNIVERSE[c][2] not in ("cash", "bond")]
    md = dataclasses.replace(md, prices=md.prices[keep], volume=md.volume[keep])
    panel = ml.vol_panel(md)
    feats = ml.vol_features(panel)
    o = ml._load_ohlc(md)
    pk = np.log(o["high"] / o["low"]).clip(0, 0.25) ** 2 / (4 * np.log(2))
    y = np.log(np.sqrt(pk.rolling(5).mean().shift(-5) * C.TRADING_DAYS).clip(lower=0.01))
    d = panel[feats].copy()
    d["y"] = y.stack().reindex(d.index)
    d["park_1"] = np.log(np.sqrt(pk * C.TRADING_DAYS).clip(lower=0.01)).stack().reindex(d.index)
    d["park_10"] = np.log(np.sqrt(pk.rolling(10).mean() * C.TRADING_DAYS).clip(lower=0.01)).stack().reindex(d.index)
    d["dow"] = d.index.get_level_values(0).dayofweek
    for k in range(1, 5):
        d[f"dow_{k}"] = (d.dow == k).astype(float)
    d = d.dropna(subset=feats + ["y", "park_1", "park_10"]).iloc[::2]                # every other day keeps it fast; same rows for all candidates
    d = d.reset_index().rename(columns={"date": "day", "symbol": "sym"})
    fs = {"production features": feats, "+ yesterday's and 2-week range + weekday": feats + ["park_1", "park_10"] + [f"dow_{k}" for k in range(1, 5)]}
    days = pd.DatetimeIndex(sorted(d.day.unique()))
    val_days = days[(days >= "2017-01-01") & (days < "2021-01-01")]
    test_days = days[days >= "2021-01-01"]
    out = search(d, fs, ["ridge:300", "ridge:30000", "lgbm", "avg"], val_days, test_days, 126, "sym", None, "NEXT WEEK", purge_days=8)
    (C.REPORTS_DIR / "short_search_week.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"hour": run_hour, "day": run_day, "week": run_week}[sys.argv[1]]()
