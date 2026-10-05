"""Next-WEEK (5 trading days) volatility model from 12 years of daily data.

    python scripts/weekly_model.py

Features: the production volatility features (realised, Parkinson / Garman-Klass / Rogers-Satchell, EWMA, market, VIX, ...).
Target, two measurements of the same thing:
  * close-to-close: RMS of the next 5 daily returns (only 5 numbers -> noisy)
  * high-low range: mean Parkinson variance of the next 5 daily bars (a more precise measurement)
Ridge penalty chosen on a 2017-20 walk-forward validation; scored on 2021-26 (yearly expanding folds, 8-day purge) against
'same as last week / month / quarter' on identical rows. Cash and the illiquid gilt ETF excluded.
"""
import dataclasses
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

from ifit import config as C, data, ml  # noqa: E402

H = 5
VAL, TEST = (2017, 2018, 2019, 2020), (2021, 2022, 2023, 2024, 2025, 2026)
PURGE = pd.Timedelta(days=8)
ANN = C.TRADING_DAYS


def r2(y, p):
    return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def within(df, c):
    g = df.groupby(level=1)
    wy, wp = df.y - g.y.transform("mean"), df[c] - g[c].transform("mean")
    return float(1 - ((wy - wp) ** 2).sum() / (wy ** 2).sum())


def fwd_mean(x: pd.DataFrame, h: int) -> pd.DataFrame:
    """mean of x over t+1..t+h"""
    return x.rolling(h).mean().shift(-h)


def main():
    md = data.load()
    keep = [c for c in md.prices.columns if C.UNIVERSE[c][2] not in ("cash", "bond")]
    md = dataclasses.replace(md, prices=md.prices[keep], volume=md.volume[keep])
    panel = ml.vol_panel(md)
    feats = ml.vol_features(panel)
    r = md.returns
    o = ml._load_ohlc(md)
    pk = np.log(o["high"] / o["low"]).clip(0, 0.25) ** 2 / (4 * np.log(2))
    tgt = {"close-to-close": np.log(np.sqrt(fwd_mean(r ** 2, H) * ANN).clip(lower=0.01)),
           "high-low range": np.log(np.sqrt(fwd_mean(pk, H) * ANN).clip(lower=0.01))}
    naive_src = {"close-to-close": {"same as last week": np.log(np.sqrt((r ** 2).rolling(H).mean() * ANN).clip(lower=0.01)),
                                    "same as last month": panel["rv_21"], "same as last quarter": panel["rv_63"]},
                 "high-low range": {"same as last week": panel["park_5"], "same as last month": panel["park_21"], "same as last quarter": panel["park_63"]}}
    out = {}
    # short-horizon additions (round 6, chosen on 2017-20 validation): yesterday's and the 2-week range, weekday
    extra = {"park_1": np.log(np.sqrt(pk * ANN).clip(lower=0.01)), "park_10": np.log(np.sqrt(pk.rolling(10).mean() * ANN).clip(lower=0.01))}
    feats = feats + list(extra) + [f"dow_{k}" for k in range(1, 5)]
    for tname, y in tgt.items():
        d = panel[[f for f in feats if f in panel.columns]].copy()
        for k, v in extra.items():
            d[k] = v.stack().reindex(d.index)
        for k in range(1, 5):
            d[f"dow_{k}"] = (d.index.get_level_values(0).dayofweek == k).astype(float)
        d["y"] = y.stack().reindex(d.index)
        for nm, src in naive_src[tname].items():
            d["n: " + nm] = (src.stack() if isinstance(src, pd.DataFrame) else src).reindex(d.index)
        d = d.dropna()
        dates = d.index.get_level_values(0)

        def run(alpha, years):
            parts = []
            for yr in years:
                a, b = pd.Timestamp(f"{yr}-01-01"), pd.Timestamp(f"{yr}-12-31")
                tr, te = d[dates < a - PURGE], d[(dates >= a) & (dates <= b)]
                m = make_pipeline(StandardScaler(), Ridge(alpha=alpha)).fit(tr[feats].values[::2], tr.y.values[::2])
                parts.append(te.assign(model=m.predict(te[feats].values)))
            return pd.concat(parts)

        alpha = max((30, 300, 3000, 30000), key=lambda a: r2(*(lambda v: (v.y, v.model))(run(a, VAL))))
        va, te = run(alpha, VAL), run(alpha, TEST)
        print(f"  [{tname}] mean bias (pred - actual): validation {float((va.model - va.y).mean()):+.3f}, test {float((te.model - te.y).mean()):+.3f}")
        # blend with 'same as last month', weight chosen on 2017-20 validation (as for the monthly model)
        nb = "n: same as last month"
        w = max(np.arange(0, 0.75, 0.05), key=lambda w: r2(va.y, (1 - w) * va.model + w * va[nb]))
        print(f"  [{tname}] blend weight on last month chosen on validation: {w:.2f}  (validation R2 {r2(va.y, va.model):.3f} -> {r2(va.y, (1 - w) * va.model + w * va[nb]):.3f})")
        te["model"] = (1 - w) * te.model + w * te[nb]
        res = {}
        for c in ["model"] + [k for k in te.columns if k.startswith("n: ")]:
            res[f"Ridge (+{w:.0%} last month)" if c == "model" else c[3:]] = dict(r2=r2(te.y, te[c]), within_asset_r2=within(te, c),
                                                           corr=float(np.corrcoef(te.y, te[c])[0, 1]), err=float(np.mean(np.abs(np.exp(te[c] - te.y) - 1))))
        by_year = {int(yr): dict(model=r2(g.y, g.model), best_naive=max(r2(g.y, g[k]) for k in g.columns if k.startswith("n: ")))
                   for yr, g in te.groupby(te.index.get_level_values(0).year)}
        out[tname] = dict(alpha=alpha, blend_weight=float(w), rows=len(te), results=res, by_year=by_year)
        print(f"\nNEXT-WEEK volatility, measured by {tname}  (alpha {alpha} chosen on 2017-20; {len(te):,} forecasts 2021-26)")
        for k, m in sorted(res.items(), key=lambda kv: -kv[1]["r2"]):
            print(f"  {k:22s} R2 {m['r2']:.3f}  within-asset {m['within_asset_r2']:.3f}  corr {m['corr']:.3f}  avg err {m['err'] * 100:.1f}%")
        print("  by year (model / best naive):", {y: f"{v['model']:.2f}/{v['best_naive']:.2f}" for y, v in by_year.items()})
    (C.REPORTS_DIR / "weekly_model.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
