"""Round 3: squeeze the volatility model and re-test the 63-day return lead with a correct (non-overlapping) significance test.

    python scripts/model_search_v3.py vol
    python scripts/model_search_v3.py returns

Protocol is unchanged: configurations are chosen on 2019-20 validation, then scored once on the 2021-26 walk-forward.
"""
import dataclasses
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
from scipy import stats  # noqa: E402
from sklearn.linear_model import Ridge  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from ifit import config as C, data, ml  # noqa: E402
import model_search_v2 as V2  # noqa: E402

YEARS = V2.TEST_YEARS


def risky(md):
    keep = [c for c in md.prices.columns if C.UNIVERSE[c][2] != "cash"]
    return dataclasses.replace(md, prices=md.prices[keep], volume=md.volume[keep])


def r2(y, p):
    return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def within_r2(df):
    g = df.groupby(level=1)
    wy = df["y"] - g["y"].transform("mean")
    wp = df["p"] - g["p"].transform("mean")
    return float(1 - ((wy - wp) ** 2).sum() / (wy ** 2).sum())


def score(df):
    return dict(r2=r2(df["y"], df["p"]), within=within_r2(df), err=float(np.mean(np.abs(np.exp(df["p"] - df["y"]) - 1))))


# --------------------------------------------------------------------------- volatility
def extra_features(panel, md):
    p = panel.copy()
    r = md.returns
    # long-run level of each asset (3y mean of its own 21d log vol) and distance of today from it (mean reversion target)
    lr = (np.log((r.rolling(21).std() * np.sqrt(252)).clip(lower=0.01))).rolling(756, min_periods=252).mean()
    p["lr_level"] = lr.stack().reindex(p.index)
    p["rv21_vs_lr"] = p["rv_21"] - p["lr_level"]
    p["rv63_vs_lr"] = p["rv_63"] - p["lr_level"]
    # market-wide level of the same thing
    p["cs_lr"] = p.groupby(level=0)["lr_level"].transform("mean")
    # asset sensitivity to market vol: rolling beta of its 21d log vol changes is costly; use rv21 x market rv21 interaction
    p["rv21_x_m21"] = p["rv_21"] * p["m_rv_21"]
    p["vix_x_beta"] = p["vix"] * p["rv_63"]
    p["m_rv5_over_63"] = p["m_rv_5"] - p["m_rv_63"]
    return p.replace([np.inf, -np.inf], np.nan)


def fit_predict(kind, trn, te, feats, prm):
    X, y = trn[feats].values, trn["y"].values
    if kind == "ridge":
        w = None
        if prm.get("halflife"):
            age = (trn.index.get_level_values(0).max() - trn.index.get_level_values(0)).days.values
            w = 0.5 ** (age / (prm["halflife"] * 365))
        m = make_pipeline(StandardScaler(), Ridge(alpha=prm["alpha"]))
        m.fit(X[:: prm.get("step", 3)], y[:: prm.get("step", 3)], ridge__sample_weight=None if w is None else w[:: prm.get("step", 3)])
        return m.predict(te[feats].values)
    if kind == "ridge+lgb":
        m = make_pipeline(StandardScaler(), Ridge(alpha=prm["alpha"])).fit(X[::3], y[::3])
        res = y - m.predict(X)
        g = lgb.LGBMRegressor(n_estimators=prm["n"], num_leaves=prm["leaves"], learning_rate=0.02, subsample=0.7, subsample_freq=1,
                              colsample_bytree=0.7, min_child_samples=400, reg_lambda=50.0, random_state=7, verbose=-1, n_jobs=-1)
        g.fit(X[::3], res[::3])
        return m.predict(te[feats].values) + prm.get("shrink", 1.0) * g.predict(te[feats].values)
    raise KeyError(kind)


def run_vol():
    md = risky(data.load())
    base = ml.vol_panel(md)
    full = extra_features(base, md)
    f_base = ml.vol_features(base)
    f_full = [c for c in full.columns if c != "y"]
    cands = {
        "A  production (Ridge 3000, every 3rd row)": ("ridge", f_base, dict(alpha=3000)),
        "B  Ridge, every row": ("ridge", f_base, dict(alpha=3000, step=1)),
        "C  + long-run level / mean-reversion features": ("ridge", f_full, dict(alpha=3000)),
        "D  C with alpha 300": ("ridge", f_full, dict(alpha=300)),
        "E  C with alpha 30000": ("ridge", f_full, dict(alpha=30000)),
        "F  C with time-decay weights (3y half-life)": ("ridge", f_full, dict(alpha=3000, halflife=3)),
        "G  C with time-decay weights (6y half-life)": ("ridge", f_full, dict(alpha=3000, halflife=6)),
        "H  Ridge + LightGBM on residuals (shrink 1.0)": ("ridge+lgb", f_full, dict(alpha=3000, n=200, leaves=7, shrink=1.0)),
        "I  Ridge + LightGBM on residuals (shrink 0.5)": ("ridge+lgb", f_full, dict(alpha=3000, n=200, leaves=7, shrink=0.5)),
    }
    dates = full.index.get_level_values(0)
    purge = pd.Timedelta(days=31)
    out = {}
    for name, (kind, feats, prm) in cands.items():
        d = full.dropna(subset=feats + ["y"])
        dd = d.index.get_level_values(0)
        # inner validation: train < 2019, validate 2019-20
        tr, va = d[dd < pd.Timestamp("2019-01-01") - purge], d[(dd >= "2019-01-01") & (dd <= "2020-12-31")]
        inner = score(pd.DataFrame({"y": va["y"], "p": fit_predict(kind, tr, va, feats, prm)}, index=va.index))
        parts = []
        for yr in YEARS:
            a, b = pd.Timestamp(f"{yr}-01-01"), pd.Timestamp(f"{yr}-12-31")
            trn, te = d[dd < a - purge], d[(dd >= a) & (dd <= b)]
            if te.empty:
                continue
            parts.append(pd.DataFrame({"y": te["y"], "p": fit_predict(kind, trn, te, feats, prm)}, index=te.index))
        oos = score(pd.concat(parts))
        out[name] = dict(inner=inner, oos=oos)
        print(f"{name:52s} inner R2 {inner['r2']:.4f}  | OOS R2 {oos['r2']:.4f}  within {oos['within']:.4f}  err {oos['err'] * 100:.1f}%", flush=True)
    (C.REPORTS_DIR / "model_search_v3_vol.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


# --------------------------------------------------------------------------- returns
def run_returns():
    md = risky(data.load())
    horizon = 63
    panel, base_cols, _ = V2.ret_panel(md, horizon)
    d = panel.dropna(subset=base_cols + ["excess"])
    tr, va = V2.inner(d, horizon)
    best = None
    for a in (100, 1000, 10000, 100000, 1000000):
        m = make_pipeline(StandardScaler(), Ridge(alpha=a)).fit(tr[base_cols].values[::3], tr["excess"].values[::3])
        ic = V2.rel_scores(pd.DataFrame({"y": va["excess"].values, "p": m.predict(va[base_cols].values)}, index=va.index))["ic"]
        print(f"  inner alpha {a:>8}: IC {ic:+.4f}")
        if best is None or ic > best[1]:
            best = (a, ic)
    a = best[0]
    parts = []
    for yr, trn, te in V2.split(d, YEARS, horizon):
        m = make_pipeline(StandardScaler(), Ridge(alpha=a)).fit(trn[base_cols].values[::3], trn["excess"].values[::3])
        parts.append(pd.DataFrame({"y": te["excess"].values, "p": m.predict(te[base_cols].values)}, index=te.index))
    df = pd.concat(parts)
    ic = df.groupby(level=0).apply(lambda g: stats.spearmanr(g["y"], g["p"])[0] if len(g) > 8 else np.nan).dropna()
    print(f"\nchosen alpha {a}; daily-IC mean {ic.mean():+.4f} over {len(ic)} days")
    # non-overlapping: one cross-section every 63 trading days (independent forward windows)
    for off in (0, 21, 42):
        s = ic.iloc[off::63]
        t = s.mean() / (s.std() / np.sqrt(len(s)))
        print(f"  non-overlapping (offset {off:2d}): n={len(s):2d}  mean IC {s.mean():+.4f}  t {t:+.2f}  share>0 {(s > 0).mean():.0%}")
    by_year = ic.groupby(ic.index.year).mean()
    print("  IC by year:", {int(k): round(float(v), 3) for k, v in by_year.items()})
    # tradeable check: top-minus-bottom quintile 63d spread, non-overlapping
    q = df.copy()
    q["rk"] = q.groupby(level=0)["p"].rank(pct=True)
    sp = (q[q.rk >= 0.8]["y"].groupby(level=0).mean() - q[q.rk <= 0.2]["y"].groupby(level=0).mean()).dropna()
    s = sp.iloc[::63]
    print(f"  quintile spread (63d, non-overlapping): mean {s.mean():+.2%}  t {s.mean() / (s.std() / np.sqrt(len(s))):+.2f}  n={len(s)}")
    # which features drive it
    m = make_pipeline(StandardScaler(), Ridge(alpha=a)).fit(d[base_cols].values[::3], d["excess"].values[::3])
    coef = pd.Series(m[-1].coef_, index=base_cols).sort_values(key=abs, ascending=False).head(8)
    print("  top coefficients:", {k: round(float(v), 4) for k, v in coef.items()})


if __name__ == "__main__":
    {"vol": run_vol, "returns": run_returns}[sys.argv[1]]()
