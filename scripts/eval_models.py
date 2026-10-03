"""Model-level evaluation: return-signal targets/features with full IC statistics, year-by-year and rolling robustness,
and the volatility model against alternative learners / targets.

    python scripts/eval_models.py returns
    python scripts/eval_models.py vol

Protocol: every setting is chosen on the 2019-20 validation window and scored once on the 2021-26 expanding-window
walk-forward (targets purged by 1.5x horizon). Cash (a flat accrual) is excluded from every score.
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
from scipy import stats  # noqa: E402
from sklearn.linear_model import ElasticNet, HuberRegressor, Ridge  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from ifit import config as C, data, features as F, ml  # noqa: E402

YEARS = (2021, 2022, 2023, 2024, 2025, 2026)
PURGE = pd.Timedelta(days=int(F.FWD_DAYS * 1.5))


def risky(md):
    keep = [c for c in md.prices.columns if C.UNIVERSE[c][2] != "cash"]
    return dataclasses.replace(md, prices=md.prices[keep], volume=md.volume[keep])


def splits(panel):
    d = panel.index.get_level_values(0)
    for yr in YEARS:
        a, b = pd.Timestamp(f"{yr}-01-01"), pd.Timestamp(f"{yr}-12-31")
        yield yr, panel[d < a - PURGE], panel[(d >= a) & (d <= b)]


def inner_split(panel):
    d = panel.index.get_level_values(0)
    return panel[d < pd.Timestamp("2019-01-01") - PURGE], panel[(d >= "2019-01-01") & (d <= "2020-12-31")]


# ================================================================================ IC statistics
def daily_ic(df):
    return df.groupby(level=0).apply(lambda g: stats.spearmanr(g["y"], g["p"])[0] if len(g) > 8 else np.nan).dropna()


def newey_west_t(x, lag=20):
    x = np.asarray(x, float)
    n, m = len(x), x.mean()
    u = x - m
    s = (u ** 2).sum() / n
    for k in range(1, lag + 1):
        s += 2 * (1 - k / (lag + 1)) * (u[k:] * u[:-k]).sum() / n
    return float(m / np.sqrt(s / n))


def ic_stats(ic):
    nonover = ic.iloc[::F.FWD_DAYS]
    return dict(mean=float(ic.mean()), median=float(ic.median()), sd=float(ic.std()), ir=float(ic.mean() / ic.std()),
                pct_pos=float((ic > 0).mean()), t_newey_west=newey_west_t(ic.values),
                t_nonoverlap=float(nonover.mean() / (nonover.std() / np.sqrt(len(nonover)))), n_days=int(len(ic)), n_independent=int(len(nonover)))


# ================================================================================ returns
def build_return_panel(md):
    panel = F.build_panel(md)                                  # production features + raw forward-21d "target"
    r = md.prices.pct_change()
    sector = pd.Series({s: C.UNIVERSE[s][1] if C.UNIVERSE[s][2] == "stock" else C.UNIVERSE[s][2] for s in md.prices.columns})
    g = panel.groupby(level=0)
    fwd = panel["target"]
    panel["y_rel"] = fwd - g["target"].transform("mean")                                  # production target
    mk = md.market.pct_change(F.FWD_DAYS).shift(-F.FWD_DAYS)
    panel["y_bench"] = fwd - mk.reindex(panel.index.get_level_values(0)).values           # excess vs NIFTY
    sec = sector.reindex(panel.index.get_level_values(1)).values
    panel["_sec"] = sec
    panel["y_sector"] = fwd - panel.groupby([panel.index.get_level_values(0), "_sec"])["target"].transform("mean")   # sector-neutral
    panel["y_voladj"] = panel["y_rel"] / panel["vol_63d"].clip(lower=0.05)               # volatility-adjusted
    panel["y_rank"] = g["y_rel"].rank(pct=True) - 0.5                                    # cross-sectional rank
    # relative-strength features
    for k in (21, 63):
        c = f"ret_{k}d"
        panel[f"rs_idx_{k}"] = panel[c] - panel.groupby(level=0)[c].transform("median")
        panel[f"rs_sec_{k}"] = panel[c] - panel.groupby([panel.index.get_level_values(0), "_sec"])[c].transform("mean")
    base = F.feature_columns(panel)
    base = [c for c in base if c not in ("y_rel", "y_bench", "y_sector", "y_voladj", "y_rank", "_sec") and not c.startswith(("rs_", "cs_"))]
    rs = ["rs_idx_21", "rs_idx_63", "rs_sec_21", "rs_sec_63"]
    for c in base + rs:
        panel["cs_" + c] = panel.groupby(level=0)[c].rank(pct=True) - 0.5
    sets = {"base": base, "base + relative strength": base + rs, "base + RS + cross-sectional ranks": base + rs + ["cs_" + c for c in base + rs]}
    return panel.replace([np.inf, -np.inf], np.nan), sets


def run_returns():
    md = risky(data.load())
    panel, sets = build_return_panel(md)
    targets = {"relative return (production)": "y_rel", "excess vs NIFTY": "y_bench", "sector-neutral": "y_sector",
               "volatility-adjusted": "y_voladj", "cross-sectional rank": "y_rank"}
    results, keep = {}, {}
    for sname, cols in sets.items():
        for tname, tcol in targets.items():
            d = panel.dropna(subset=cols + [tcol, "y_rel"])
            tr, va = inner_split(d)
            best = (None, -9)
            for a in (300, 3000, 30000, 300000):
                m = make_pipeline(StandardScaler(), Ridge(alpha=a)).fit(tr[cols].values[::3], tr[tcol].values[::3])
                ic = daily_ic(pd.DataFrame({"y": va["y_rel"].values, "p": m.predict(va[cols].values)}, index=va.index)).mean()
                if ic > best[1]:
                    best = (a, ic)
            parts = []
            for yr, trn, te in splits(d):
                m = make_pipeline(StandardScaler(), Ridge(alpha=best[0])).fit(trn[cols].values[::3], trn[tcol].values[::3])
                parts.append(pd.DataFrame({"y": te["y_rel"].values, "p": m.predict(te[cols].values)}, index=te.index))
            df = pd.concat(parts)
            ic = daily_ic(df)
            key = f"{sname} | {tname}"
            results[key] = dict(alpha=best[0], inner_ic=float(best[1]), **ic_stats(ic),
                                rmse=float(np.sqrt(((df.y - df.p) ** 2).mean())), dir_acc=float((np.sign(df.y) == np.sign(df.p)).mean()))
            keep[key] = (df, ic)
            r = results[key]
            print(f"{key:78s} a={best[0]:>6} innerIC {best[1]:+.3f} | IC {r['mean']:+.4f} med {r['median']:+.4f} sd {r['sd']:.3f} IR {r['ir']:+.3f} "
                  f"pos {r['pct_pos']:.0%} tNW {r['t_newey_west']:+.2f} tIND {r['t_nonoverlap']:+.2f}", flush=True)
    # production configuration = base features, production target
    prod_key = "base | relative return (production)"
    df, ic = keep[prod_key]
    base_rmse = float(np.sqrt(((df.y - df.groupby(level=0)["y"].transform("mean").mean()) ** 2).mean()))
    by_year = {}
    for yr in YEARS:
        sub = df[df.index.get_level_values(0).year == yr]
        i = ic[ic.index.year == yr]
        by_year[yr] = dict(ic=float(i.mean()), ic_t_nw=newey_west_t(i.values) if len(i) > 30 else None, rmse=float(np.sqrt(((sub.y - sub.p) ** 2).mean())),
                           rmse_mean_baseline=float(np.sqrt(((sub.y - sub.y.mean()) ** 2).mean())), dir_acc=float((np.sign(sub.y) == np.sign(sub.p)).mean()), n=int(len(sub)))
    rolling = {}
    for lab, w in (("3-month", 63), ("6-month", 126), ("12-month", 252)):
        rm = ic.rolling(w).mean().dropna()
        rolling[lab] = dict(min=float(rm.min()), median=float(rm.median()), max=float(rm.max()), share_positive=float((rm > 0).mean()))
    best_key = max(results, key=lambda k: results[k]["inner_ic"])
    out = dict(configs=results, production=prod_key, by_year=by_year, rolling=rolling, selected_on_validation=best_key,
               selected_on_validation_oos_ic=results[best_key]["mean"])
    (C.REPORTS_DIR / "eval_returns.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\nby year:", json.dumps({k: {a: (round(b, 4) if isinstance(b, float) else b) for a, b in v.items()} for k, v in by_year.items()}, indent=0))
    print("rolling:", json.dumps(rolling))
    print("selected on validation:", best_key, "-> OOS IC", round(results[best_key]["mean"], 4))


# ================================================================================ volatility
def run_vol():
    md = risky(data.load())
    panel = ml.vol_panel(md)
    feats = ml.vol_features(panel)
    # alternative targets: forward 21d Parkinson vol, forward 63d close-to-close vol
    o = ml._load_ohlc(md)
    hl = np.log(o["high"] / o["low"]).clip(0, 0.25)
    park = hl ** 2 / (4 * np.log(2))
    fp = np.log(np.sqrt(park.rolling(21).mean().shift(-21) * C.TRADING_DAYS).clip(lower=0.01))
    f63 = np.log((md.returns.rolling(63).std().shift(-63) * np.sqrt(C.TRADING_DAYS)).clip(lower=0.01))
    panel["y_park"] = fp.stack().reindex(panel.index)
    panel["y_63"] = f63.stack().reindex(panel.index)
    d = panel.dropna(subset=feats + ["y", "y_park", "y_63"])

    models = {
        "Ridge (production)": ("y", lambda: make_pipeline(StandardScaler(), Ridge(alpha=3000.0))),
        "Elastic Net": ("y", None),
        "Huber regression": ("y", lambda: make_pipeline(StandardScaler(), HuberRegressor(alpha=1000.0, epsilon=1.35, max_iter=200))),
        "Ridge, target = forward Parkinson vol": ("y_park", lambda: make_pipeline(StandardScaler(), Ridge(alpha=3000.0))),
        "Ridge, target = forward 63-day vol": ("y_63", lambda: make_pipeline(StandardScaler(), Ridge(alpha=3000.0))),
    }
    tr, va = inner_split(d)
    best_en = (None, -9)
    for a in (0.001, 0.003, 0.01):
        for l1 in (0.1, 0.5):
            m = make_pipeline(StandardScaler(), ElasticNet(alpha=a, l1_ratio=l1, max_iter=5000)).fit(tr[feats].values[::3], tr["y"].values[::3])
            p = m.predict(va[feats].values)
            sc = 1 - ((va["y"] - p) ** 2).sum() / ((va["y"] - va["y"].mean()) ** 2).sum()
            if sc > best_en[1]:
                best_en = ((a, l1), sc)
    print("Elastic Net chosen on validation:", best_en)
    models["Elastic Net"] = ("y", lambda: make_pipeline(StandardScaler(), ElasticNet(alpha=best_en[0][0], l1_ratio=best_en[0][1], max_iter=5000)))

    def r2(y, p):
        return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())

    out, preds = {}, {}
    for name, (tcol, mk) in models.items():
        parts = []
        for yr, trn, te in splits(d):
            m = mk().fit(trn[feats].values[::3], trn[tcol].values[::3])
            parts.append(pd.DataFrame({"y": te["y"].values, "p": m.predict(te[feats].values)}, index=te.index))
        df = pd.concat(parts)
        preds[name] = df
        g = df.groupby(level=1)
        wy, wp = df["y"] - g["y"].transform("mean"), df["p"] - g["p"].transform("mean")
        out[name] = dict(r2=r2(df.y, df.p), within_asset_r2=float(1 - ((wy - wp) ** 2).sum() / (wy ** 2).sum()),
                         err=float(np.mean(np.abs(np.exp(df.p - df.y) - 1))), corr=float(np.corrcoef(df.y, df.p)[0, 1]))
        print(f"{name:42s} R2 {out[name]['r2']:.4f}  within {out[name]['within_asset_r2']:.4f}  err {out[name]['err'] * 100:.1f}%  corr {out[name]['corr']:.3f}", flush=True)
    # Ridge R2 by year / by asset class; naive by year
    df = preds["Ridge (production)"]
    te_all = d[d.index.get_level_values(0) >= "2021-01-01"]
    by_year = {}
    for yr in YEARS:
        s = df[df.index.get_level_values(0).year == yr]
        t = te_all[te_all.index.get_level_values(0).year == yr]
        by_year[yr] = dict(r2=r2(s.y, s.p), naive_63d_r2=r2(t["y"], t["rv_63"]), naive_21d_r2=r2(t["y"], t["rv_21"]),
                           err=float(np.mean(np.abs(np.exp(s.p - s.y) - 1))), n=int(len(s)))
    cls = pd.Series({s: C.UNIVERSE[s][2] for s in md.prices.columns})
    by_class = {}
    for c in cls.unique():
        s = df[df.index.get_level_values(1).isin(cls[cls == c].index)]
        by_class[c] = dict(r2=r2(s.y, s.p), err=float(np.mean(np.abs(np.exp(s.p - s.y) - 1))), n=int(len(s)))
    res = dict(models=out, by_year=by_year, by_class=by_class, elastic_net_choice=dict(alpha=best_en[0][0], l1_ratio=best_en[0][1]))
    (C.REPORTS_DIR / "eval_vol.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("by year:", {k: {a: round(b, 3) if isinstance(b, float) else b for a, b in v.items()} for k, v in by_year.items()})
    print("by class:", {k: {a: round(b, 3) if isinstance(b, float) else b for a, b in v.items()} for k, v in by_class.items()})


if __name__ == "__main__":
    {"returns": run_returns, "vol": run_vol}[sys.argv[1]]()
