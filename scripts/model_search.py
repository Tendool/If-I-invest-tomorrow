"""Model search: which forecasting models are genuinely better, evaluated out-of-sample?

    python scripts/model_search.py

Two tasks, each tuned on an inner validation period (train < 2019, validate 2019-2020) and then
scored on the SAME untouched expanding-window walk-forward as ml.walk_forward (test years 2021-2026,
targets purged):

  A. RELATIVE RETURN  - forward 21d return minus the cross-sectional mean ("beats the average asset?")
  B. VOLATILITY       - log of forward 21d realised volatility (drives VaR, drawdown, Monte Carlo)

Writes reports/model_search.json and reports/model_search.md.
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
from scipy import stats  # noqa: E402
from sklearn.ensemble import RandomForestRegressor  # noqa: E402
from sklearn.linear_model import Ridge  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
import xgboost as xgb  # noqa: E402

from ifit import config as C, data, features as F  # noqa: E402

TEST_YEARS = (2021, 2022, 2023, 2024, 2025, 2026)
PURGE = pd.Timedelta(days=int(F.FWD_DAYS * 1.5))


# ----------------------------------------------------------------------------- data
def build(md):
    panel = F.build_panel(md)                      # (date, symbol) x features + raw target
    r = md.returns
    fvol = r.rolling(F.FWD_DAYS).std().shift(-F.FWD_DAYS) * np.sqrt(C.TRADING_DAYS)   # forward realised vol
    v252 = r.rolling(252).std() * np.sqrt(C.TRADING_DAYS)
    v5 = r.rolling(5).std() * np.sqrt(C.TRADING_DAYS)
    st = lambda df, n: df.stack().rename(n)         # noqa: E731
    extra = pd.concat([st(fvol, "fvol"), st(v252, "vol_252d"), st(v5, "vol_5d")], axis=1)
    extra.index.names = ["date", "symbol"]
    panel = panel.join(extra)
    panel["excess"] = panel["target"] - panel.groupby(level=0)["target"].transform("mean")
    for c in ("vol_5d", "vol_21d", "vol_63d", "vol_252d", "fvol"):
        panel["log_" + c] = np.log(panel[c].clip(lower=0.01))
    panel["cs_rank_ret21"] = panel.groupby(level=0)["ret_21d"].rank(pct=True)
    panel["cs_rank_ret126"] = panel.groupby(level=0)["ret_126d"].rank(pct=True)
    panel["cs_rank_vol"] = panel.groupby(level=0)["vol_63d"].rank(pct=True)
    return panel.replace([np.inf, -np.inf], np.nan)


def folds(panel, years):
    dates = panel.index.get_level_values(0)
    for yr in years:
        start, end = pd.Timestamp(f"{yr}-01-01"), pd.Timestamp(f"{yr}-12-31")
        yield yr, panel[dates < start - PURGE], panel[(dates >= start) & (dates <= end)]


# --------------------------------------------------------------------------- models
def make(name, params):
    if name == "Ridge":
        return make_pipeline(StandardScaler(), Ridge(**params))
    if name == "Random Forest":
        return RandomForestRegressor(n_jobs=-1, random_state=7, **params)
    if name == "XGBoost":
        return xgb.XGBRegressor(n_jobs=-1, random_state=7, verbosity=0, **params)
    raise KeyError(name)


GRIDS = {
    "Ridge": [dict(alpha=a) for a in (1, 30, 300, 3000)],
    "Random Forest": [dict(n_estimators=150, max_depth=d, min_samples_leaf=l, max_features=0.5) for d in (4, 6, 8) for l in (100, 400)],
    "XGBoost": [dict(n_estimators=n, max_depth=d, learning_rate=0.03, subsample=0.7, colsample_bytree=0.7,
                     min_child_weight=m, reg_lambda=10.0) for n in (150, 400) for d in (2, 3, 4) for m in (50, 200)],
}


# -------------------------------------------------------------------------- metrics
def ic_by_date(df):
    return df.groupby(level=0).apply(lambda g: stats.spearmanr(g["y"], g["p"])[0] if len(g) > 8 else np.nan).dropna()


def rel_metrics(df):
    ic = ic_by_date(df)
    q = df.copy()
    q["rk"] = q.groupby(level=0)["p"].rank(pct=True)
    top, bot = q[q.rk >= 0.8]["y"].groupby(level=0).mean(), q[q.rk <= 0.2]["y"].groupby(level=0).mean()
    spread = (top - bot).dropna()
    return dict(ic=float(ic.mean()), icir=float(ic.mean() / ic.std()), ic_pos=float((ic > 0).mean()),
                hit=float((np.sign(df.y) == np.sign(df.p)).mean()),
                top_hit=float((q[q.rk >= 0.8]["y"] > 0).mean()),
                spread_21d=float(spread.mean()), spread_t=float(spread.mean() / (spread.std() / np.sqrt(len(spread) / 21))))


def vol_metrics(df, logscale=True):
    y, p = df["y"].values, df["p"].values
    ss = ((y - y.mean()) ** 2).sum()
    return dict(r2=float(1 - ((y - p) ** 2).sum() / ss), corr=float(np.corrcoef(y, p)[0, 1]),
                mape=float(np.mean(np.abs(np.exp(p) / np.exp(y) - 1))))


def run_task(panel, task, feats, target, metric_fn, score_key, baselines, models=("Ridge", "Random Forest", "XGBoost")):
    data_ = panel.dropna(subset=feats + [target])
    # ---- inner validation: choose hyper-parameters using only pre-2021 data
    chosen = {}
    tr, va = next(((a, b) for yr, a, b in folds(data_, [2019])))
    va = data_[(data_.index.get_level_values(0) >= "2019-01-01") & (data_.index.get_level_values(0) <= "2020-12-31")]
    for name in models:
        best, best_s = None, -1e9
        for prm in GRIDS[name]:
            m = make(name, prm).fit(tr[feats].values[::3], tr[target].values[::3])
            s = metric_fn(pd.DataFrame({"y": va[target].values, "p": m.predict(va[feats].values)}, index=va.index))[score_key]
            if s > best_s:
                best, best_s = prm, s
        chosen[name] = best
        print(f"  [{task}] tuned {name}: {score_key}={best_s:.4f} {best}")
    # ---- walk-forward on the untouched test years
    oos = {n: [] for n in models}
    for yr, tr, te in folds(data_, TEST_YEARS):
        if len(te) < 100:
            continue
        for n in models:
            m = make(n, chosen[n]).fit(tr[feats].values[::3], tr[target].values[::3])
            oos[n].append(pd.DataFrame({"y": te[target].values, "p": m.predict(te[feats].values)}, index=te.index))
    res, preds = {}, {}
    for n in models:
        preds[n] = pd.concat(oos[n])
    # ensemble = mean of model predictions (rank-average for relative task)
    ens = preds[models[0]].copy()
    stack = np.column_stack([preds[n]["p"].values for n in models])
    ens["p"] = stack.mean(axis=1)
    preds["Ensemble (mean)"] = ens
    for n, d in preds.items():
        res[n] = metric_fn(d)
    for n, fn in baselines.items():
        d = preds[models[0]][["y"]].copy()
        d["p"] = fn(data_.loc[d.index])
        res[n] = metric_fn(d)
    return res, chosen


def main():
    md = data.load()
    panel = build(md)
    base = [c for c in F.feature_columns(panel) if c not in ("excess", "fvol", "vol_252d", "vol_5d") and not c.startswith("log_") and not c.startswith("cs_")]
    rel_feats = base + ["cs_rank_ret21", "cs_rank_ret126", "cs_rank_vol"]
    vol_feats = ["log_vol_5d", "log_vol_21d", "log_vol_63d", "log_vol_252d", "vix", "vix_chg_21d", "mkt_vol_21d", "mkt_dd",
                 "ret_21d", "ret_63d", "dd_252", "beta_63d", "vol_ratio", "skew_63d"]
    out = {}

    print("A. relative return (excess over cross-sectional mean)")
    resA, chA = run_task(
        panel, "relative", rel_feats, "excess", rel_metrics, "ic",
        baselines={"Momentum baseline (12m rank)": lambda d: d["ret_252d"].values,
                   "Reversal baseline (1m rank)": lambda d: -d["ret_21d"].values,
                   "Low-vol baseline": lambda d: -d["vol_63d"].values})
    out["relative_return"] = dict(results=resA, params=chA)

    print("B. volatility (log forward 21d realised vol)")
    resB, chB = run_task(
        panel, "vol", vol_feats, "log_fvol", vol_metrics, "r2",
        baselines={"Trailing 21d vol (naive)": lambda d: d["log_vol_21d"].values,
                   "Trailing 63d vol (naive)": lambda d: d["log_vol_63d"].values})
    out["volatility"] = dict(results=resB, params=chB)

    (C.REPORTS_DIR / "model_search.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")

    lines = ["# Model search (walk-forward 2021-2026, hyper-parameters tuned on 2019-2020 only)\n",
             "## A. Relative return: does the model rank assets correctly over the next 21 days?\n",
             "| Model | IC | ICIR | Days IC>0 | Direction hit | Top-quintile beats avg | Top-minus-bottom 21d | t-stat |", "|---|---|---|---|---|---|---|---|"]
    for n, m in resA.items():
        lines.append(f"| {n} | {m['ic']:.3f} | {m['icir']:.2f} | {m['ic_pos']:.0%} | {m['hit']:.1%} | {m['top_hit']:.1%} | {m['spread_21d']:+.2%} | {m['spread_t']:.1f} |")
    lines += ["\n## B. Volatility: forecast of next-21-day realised volatility (log scale)\n",
              "| Model | R2 | Correlation | Mean abs % error |", "|---|---|---|---|"]
    for n, m in resB.items():
        lines.append(f"| {n} | {m['r2']:.3f} | {m['corr']:.3f} | {m['mape']:.1%} |")
    (C.REPORTS_DIR / "model_search.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
