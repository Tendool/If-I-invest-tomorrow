"""Round 8: nested walk-forward selection and forecast combination.

Every candidate produces walk-forward predictions for each year 2017-2026, trained only on data before that year. For each
test year Y the *choice* (best single candidate, top-3 average, or non-negative stacking weights) is learned from the
candidates' predictions in the years before Y only (expanding window from 2017). The 2021-26 score of these procedures is
therefore honest however many candidates are included, and it is compared with the fixed production model.

    python scripts/model_search_v7.py vol
    python scripts/model_search_v7.py returns
"""
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.optimize import nnls  # noqa: E402
from sklearn.linear_model import HuberRegressor, Ridge  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from ifit import config as C, data, ml  # noqa: E402
from model_search_v4 import fold, r2, risky, within_r2  # noqa: E402

YEARS = tuple(range(2017, 2027))
TEST = tuple(range(2021, 2027))


def by_year(df):
    return df.index.get_level_values(0).year


# ================================================================================ volatility
def run_vol():
    import lightgbm as lgb
    from model_search_v5 import extra_vol_features
    md = risky(data.load())
    p0 = ml.vol_panel(md)
    prod = ml.vol_features(p0)
    panel = extra_vol_features(md, p0)
    extra = prod + ["impl_sys", "log_beta_vix", "log_idio", "impl_vs_rv21"]
    panel["log_vix"] = np.log(panel["vix"].clip(lower=0.05))
    extra2 = extra + ["log_vix"]

    def ridge(a):
        return lambda: make_pipeline(StandardScaler(), Ridge(alpha=a))

    def lgbm(n, leaves):
        return lambda: lgb.LGBMRegressor(n_estimators=n, learning_rate=0.03, num_leaves=leaves, min_child_samples=200, subsample=0.7, subsample_freq=1,
                                         colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, random_state=7)

    cands = {
        "ridge a3000 (production features)": (prod, ridge(3000)),
        "ridge a300": (prod, ridge(300)),
        "ridge a30000": (prod, ridge(30000)),
        "ridge a3000 + implied/log-VIX features": (extra2, ridge(3000)),
        "huber (production features)": (prod, lambda: make_pipeline(StandardScaler(), HuberRegressor(alpha=1000.0, epsilon=1.35, max_iter=300))),
        "lightgbm 400x15": (prod, lgbm(400, 15)),
        "lightgbm 400x15 + implied/log-VIX": (extra2, lgbm(400, 15)),
        "lightgbm 800x31": (prod, lgbm(800, 31)),
    }
    need = sorted(set(extra2 + ["y", "rv_63", "rv_21"]))
    d = panel.dropna(subset=need)
    preds = pd.DataFrame(index=d[by_year(d) >= YEARS[0]].index)
    preds["y"] = d["y"].reindex(preds.index)
    preds["naive_63"] = d["rv_63"].reindex(preds.index)
    preds["naive_21"] = d["rv_21"].reindex(preds.index)
    preds["naive_ewma"] = d["ewma_0.94"].reindex(preds.index)
    for name, (cols, mk) in cands.items():
        out = []
        for yr in YEARS:
            tr, te = fold(d, yr)
            trs = tr.iloc[::3]
            m = mk().fit(trs[cols].values, trs["y"].values)
            out.append(pd.Series(m.predict(te[cols].values), index=te.index))
        preds[name] = pd.concat(out).reindex(preds.index)
        print("candidate done:", name, flush=True)
    preds.to_pickle(C.REPORTS_DIR / "_v7_vol_preds.pkl")
    names = [c for c in preds.columns if c != "y"]
    # production = round-7 model: ridge a3000 production features, 85/15 blend with last quarter
    preds["PRODUCTION (fixed)"] = 0.85 * preds["ridge a3000 (production features)"] + 0.15 * preds["naive_63"]

    yrs = by_year(preds)
    procs = {"best single (nested)": [], "top-3 average (nested)": [], "stacking, non-negative weights (nested)": []}
    choices = []
    for Y in TEST:
        past, cur = preds[(yrs >= YEARS[0]) & (yrs < Y)], preds[yrs == Y]
        sc = {n: r2(past["y"], past[n]) for n in names}
        rank = sorted(sc, key=sc.get, reverse=True)
        procs["best single (nested)"].append(cur[rank[0]])
        procs["top-3 average (nested)"].append(cur[rank[:3]].mean(axis=1))
        A = past[names].values
        w, _ = nnls(np.column_stack([A, np.ones(len(A))]), past["y"].values)        # intercept as a non-negative constant column
        wn, b = w[:-1], w[-1]
        procs["stacking, non-negative weights (nested)"].append(pd.Series(cur[names].values @ wn + b, index=cur.index))
        choices.append(dict(year=Y, best=rank[0], top3=rank[:3], stack={n: round(float(x), 3) for n, x in zip(names, wn) if x > 1e-3}, intercept=round(float(b), 3)))
        print(Y, "best:", rank[0], "| stack:", choices[-1]["stack"], flush=True)
    test = preds[yrs >= TEST[0]]
    res = {}
    for n in ["PRODUCTION (fixed)"] + names:
        res[n] = dict(r2=r2(test["y"], test[n]), within=within_r2(pd.DataFrame({"y": test["y"], "p": test[n]})), err=float(np.mean(np.abs(np.exp(test[n] - test["y"]) - 1))))
    for n, parts in procs.items():
        s = pd.concat(parts).reindex(test.index)
        res[n] = dict(r2=r2(test["y"], s), within=within_r2(pd.DataFrame({"y": test["y"], "p": s})), err=float(np.mean(np.abs(np.exp(s - test["y"]) - 1))),
                      by_year={int(y): r2(g["y"], g["p"]) for y, g in pd.DataFrame({"y": test["y"], "p": s}).groupby(by_year(test))})
    prod_by = {int(y): r2(g["y"], g["p"]) for y, g in pd.DataFrame({"y": test["y"], "p": test["PRODUCTION (fixed)"]}).groupby(by_year(test))}
    res["PRODUCTION (fixed)"]["by_year"] = prod_by
    for n, v in res.items():
        print(f"{n:44s} test R2 {v['r2']:.4f}  within {v['within']:.4f}  err {v['err'] * 100:.1f}%", flush=True)
    (C.REPORTS_DIR / "model_search_v7_vol.json").write_text(json.dumps(dict(results=res, choices=choices), indent=1), encoding="utf-8")


# ================================================================================ returns
def run_returns():
    from eval_models import build_return_panel, daily_ic, ic_stats
    from model_search_v6 import add_factors
    md = risky(data.load())
    panel, _ = build_return_panel(md)
    d = add_factors(md, panel).dropna(subset=["y_rel"])
    base = ["f_reversal", "f_momentum", "f_res_rev", "f_res_mom", "f_high52", "f_seas"]
    d["c_rev_mom"] = d[["f_reversal", "f_momentum"]].mean(axis=1, skipna=False)
    d["c_res"] = d[["f_res_rev", "f_res_mom"]].mean(axis=1, skipna=False)                 # production (round 7)
    d["c_rev_mom_seas"] = d[["f_reversal", "f_momentum", "f_seas"]].mean(axis=1, skipna=False)
    cands = base + ["c_rev_mom", "c_res", "c_rev_mom_seas"]
    d = d[by_year(d) >= YEARS[0]].dropna(subset=cands)
    yrs = by_year(d)
    ic = {c: daily_ic(pd.DataFrame({"y": d["y_rel"], "p": d[c]})) for c in cands}
    icy = pd.DataFrame(ic)                                                              # daily IC per candidate
    procs = {"best single (nested)": [], "top-3 average (nested)": [], "IC-weighted factor mix (nested)": []}
    for Y in TEST:
        past = icy[(icy.index.year >= YEARS[0]) & (icy.index.year < Y)]
        cur = d[yrs == Y]
        m = past.mean()
        rank = m.sort_values(ascending=False).index.tolist()
        procs["best single (nested)"].append(cur[rank[0]])
        procs["top-3 average (nested)"].append(cur[rank[:3]].mean(axis=1))
        wb = m[base].clip(lower=0)
        wb = wb / wb.sum() if wb.sum() > 0 else wb
        procs["IC-weighted factor mix (nested)"].append((cur[base] * wb).sum(axis=1))
        print(Y, "best:", rank[0], "| weights:", {k: round(v, 2) for k, v in wb.items() if v > 0}, flush=True)
    test = d[yrs >= TEST[0]]
    res = {}
    for c in ["c_res"] + [x for x in cands if x != "c_res"]:
        st = ic_stats(daily_ic(pd.DataFrame({"y": test["y_rel"], "p": test[c]})))
        res[("PRODUCTION (fixed): " if c == "c_res" else "") + c] = dict(ic=st["mean"], t=st["t_nonoverlap"], pct_pos=st["pct_pos"])
    for n, parts in procs.items():
        s = pd.concat(parts).reindex(test.index)
        st = ic_stats(daily_ic(pd.DataFrame({"y": test["y_rel"], "p": s})))
        res[n] = dict(ic=st["mean"], t=st["t_nonoverlap"], pct_pos=st["pct_pos"])
    for n, v in res.items():
        print(f"{n:40s} test IC {v['ic']:+.4f}  t {v['t']:+.2f}  days>0 {v['pct_pos']:.0%}", flush=True)
    (C.REPORTS_DIR / "model_search_v7_returns.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"vol": run_vol, "returns": run_returns}[sys.argv[1]]()
