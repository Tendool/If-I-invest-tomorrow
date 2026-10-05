"""Round 6: new ideas, selected on the 2017-20 walk-forward validation and scored once on 2021-26.

    python scripts/model_search_v5.py vol        # implied-systematic and seasonal volatility features, residual boosting
    python scripts/model_search_v5.py returns    # documented factors (no fitting) and LightGBM ranking
    python scripts/model_search_v5.py mc         # volatility uncertainty in the Monte Carlo, size measured before 2018

Same protocol as round 4 (scripts/model_search_v4.py): every choice is made on 2017-20; 2021-26 is only reported.
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
from sklearn.linear_model import Ridge  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from ifit import config as C, data, features as F, ml  # noqa: E402
from model_search_v4 import ANN, TEST_YEARS, VAL_YEARS, fold, r2, risky, within_r2  # noqa: E402

BLEND_GRID = np.arange(0, 0.55, 0.05)


# ================================================================================ volatility
RESULTS_MONTHS = {1, 2, 4, 5, 7, 8, 10, 11}        # Indian quarterly-results seasons (approx.)


def extra_vol_features(md, panel):
    """New point-in-time features. Every input uses data up to the forecast date only."""
    r = md.returns
    mr = md.market.pct_change().reindex(r.index)
    var_m = mr.rolling(63).var()
    beta = r.rolling(63).cov(mr).div(var_m, axis=0).clip(-1, 3)
    idio_var = (r.rolling(63).var() - beta ** 2 * var_m.values[:, None]).clip(lower=1e-8) * C.TRADING_DAYS
    vix2 = (md.macro["vix"].reindex(r.index) / 100) ** 2
    implied = np.sqrt((beta ** 2).mul(vix2, axis=0) + idio_var)            # beta^2 * implied market var + idiosyncratic var
    seas = np.log((r.rolling(21).std().shift(231) * ANN).clip(lower=0.01))  # realised vol in the same 21-day window last year
    new = {
        "impl_sys": np.log(implied.clip(lower=0.01)),
        "log_beta_vix": np.log((beta.abs() * md.macro["vix"].reindex(r.index).values[:, None] / 100).clip(lower=0.01)),
        "log_idio": np.log(np.sqrt(idio_var).clip(lower=0.01)),
        "rv_seas": seas,
    }
    out = panel.copy()
    for k, v in new.items():
        out[k] = v.stack().reindex(out.index)
    out["rv_seas_vs_252"] = out["rv_seas"] - out["rv_252"]
    out["impl_vs_rv21"] = out["impl_sys"] - out["rv_21"]
    # calendar: share of the next 21 trading days falling in a results season (known in advance), stocks only
    dates = out.index.get_level_values(0)
    cal = pd.Series(r.index, index=r.index)
    fut = pd.DataFrame({k: cal.shift(-k) for k in range(1, 22)})
    share = fut.apply(lambda c: c.dt.month.isin(RESULTS_MONTHS)).mean(axis=1)
    is_stock = np.array([C.UNIVERSE[s][2] == "stock" for s in out.index.get_level_values(1)], dtype=float)
    out["results_season"] = share.reindex(dates).values * is_stock
    return out.replace([np.inf, -np.inf], np.nan)


def _ridge():
    return make_pipeline(StandardScaler(), Ridge(alpha=ml.VOL_ALPHA))


def _lgbm():
    import lightgbm as lgb
    return lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=200, subsample=0.7, subsample_freq=1,
                             colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, random_state=7)


def run_vol():
    md = risky(data.load())
    p0 = ml.vol_panel(md)
    base = ml.vol_features(p0)
    panel = extra_vol_features(md, p0)
    sysf = ["impl_sys", "log_beta_vix", "log_idio", "impl_vs_rv21"]
    seasf = ["rv_seas", "rv_seas_vs_252", "results_season"]
    cands = {
        "A production features": (base, "ridge"),
        "B + implied systematic vol": (base + sysf, "ridge"),
        "C + seasonal": (base + seasf, "ridge"),
        "D + implied systematic + seasonal": (base + sysf + seasf, "ridge"),
        "E D + boosted trees on Ridge residuals": (base + sysf + seasf, "ridge+lgbm"),
        "F boosted trees alone (D features)": (base + sysf + seasf, "lgbm"),
    }
    preds = {k: {"val": [], "test": []} for k in cands}
    for yr in VAL_YEARS + TEST_YEARS:
        part = "val" if yr in VAL_YEARS else "test"
        for name, (cols, kind) in cands.items():
            tr, te = fold(panel.dropna(subset=cols + ["y"]), yr)
            if len(tr) < 1500 or te.empty:
                continue
            trs = tr.iloc[::3]
            if kind == "ridge":
                p = _ridge().fit(trs[cols].values, trs["y"].values).predict(te[cols].values)
            elif kind == "lgbm":
                p = _lgbm().fit(trs[cols].values, trs["y"].values).predict(te[cols].values)
            else:
                rg = _ridge().fit(trs[cols].values, trs["y"].values)
                resid = trs["y"].values - rg.predict(trs[cols].values)
                gb = _lgbm().fit(trs[cols].values, resid)
                p = rg.predict(te[cols].values) + gb.predict(te[cols].values)
            preds[name][part].append(pd.DataFrame({"y": te["y"], "p": p, "n63": te["rv_63"]}, index=te.index))
        print("fold", yr, flush=True)

    res = {}
    for name in cands:
        v, t = pd.concat(preds[name]["val"]), pd.concat(preds[name]["test"])
        w = max(BLEND_GRID, key=lambda x: r2(v.y, (1 - x) * v.p + x * v.n63))          # blend with last quarter, chosen on validation
        vb, tb = (1 - w) * v.p + w * v.n63, (1 - w) * t.p + w * t.n63
        res[name] = dict(blend=float(w), val_r2=r2(v.y, vb), test_r2=r2(t.y, tb), test_within=within_r2(pd.DataFrame({"y": t.y, "p": tb})),
                         test_err=float(np.mean(np.abs(np.exp(tb - t.y) - 1))), test_rows=int(len(t)),
                         test_by_year={int(y): r2(g.y, g.p) for y, g in pd.DataFrame({"y": t.y, "p": tb}).groupby(t.index.get_level_values(0).year)})
        r = res[name]
        print(f"{name:44s} w={w:.2f}  val R2 {r['val_r2']:.4f} | test R2 {r['test_r2']:.4f} within {r['test_within']:.4f} err {r['test_err'] * 100:.1f}%", flush=True)
    chosen = max(res, key=lambda k: res[k]["val_r2"])
    print("chosen on 2017-20 validation:", chosen)
    (C.REPORTS_DIR / "model_search_v5_vol.json").write_text(json.dumps(dict(results=res, chosen=chosen), indent=1), encoding="utf-8")


# ================================================================================ returns
def run_returns():
    from eval_models import build_return_panel, daily_ic, ic_stats
    md = risky(data.load())
    panel, sets = build_return_panel(md)
    g = panel.groupby(level=0)
    rk = lambda s: s.groupby(level=0).rank(pct=True) - 0.5
    # documented factors, no parameters fitted (signs fixed by the literature)
    panel["f_reversal"] = -rk(panel["ret_21d"])
    panel["f_momentum"] = rk(panel["ret_252d"] - panel["ret_21d"])
    panel["f_lowvol"] = -rk(panel["vol_63d"])
    panel["f_composite"] = (panel["f_reversal"] + panel["f_momentum"] + panel["f_lowvol"]) / 3
    panel["f_rev_mom"] = (panel["f_reversal"] + panel["f_momentum"]) / 2
    d = panel.dropna(subset=["y_rel"])
    dates = d.index.get_level_values(0)
    val_mask = (dates >= "2017-01-01") & (dates <= "2020-12-31")
    test_mask = dates >= "2021-01-01"
    res = {}

    def report(name, val_df, test_df, extra=None):
        vi, ti = daily_ic(val_df), daily_ic(test_df)
        st = ic_stats(ti)
        vst = ic_stats(vi)
        res[name] = dict(val_ic=float(vi.mean()), val_t=vst["t_nonoverlap"], **{"test_" + k: v for k, v in st.items()}, **(extra or {}))
        print(f"{name:48s} val IC {vi.mean():+.4f} (tIND {vst['t_nonoverlap']:+.2f}) | test IC {st['mean']:+.4f} tNW {st['t_newey_west']:+.2f} tIND {st['t_nonoverlap']:+.2f}", flush=True)

    for f in ("f_reversal", "f_momentum", "f_lowvol", "f_composite", "f_rev_mom"):
        x = d.dropna(subset=[f])
        dd = x.index.get_level_values(0)
        mk = lambda m: pd.DataFrame({"y": x["y_rel"][m].values, "p": x[f][m].values}, index=x.index[m])
        report(f"factor: {f[2:]}", mk((dd >= "2017-01-01") & (dd <= "2020-12-31")), mk(dd >= "2021-01-01"))

    # production Ridge on the same folds, for reference
    cols = sets["base"]
    dr = d.dropna(subset=cols)
    parts = {"val": [], "test": []}
    for yr in VAL_YEARS + TEST_YEARS:
        tr, te = fold(dr, yr)
        m = make_pipeline(StandardScaler(), Ridge(alpha=300000)).fit(tr[cols].values[::3], tr["y_rel"].values[::3])
        parts["val" if yr in VAL_YEARS else "test"].append(pd.DataFrame({"y": te["y_rel"].values, "p": m.predict(te[cols].values)}, index=te.index))
    report("Ridge (production)", pd.concat(parts["val"]), pd.concat(parts["test"]))

    # LightGBM learning-to-rank on cross-sectional quintiles, conservative fixed settings
    import lightgbm as lgb
    cols = sets["base + RS + cross-sectional ranks"]
    dl = d.dropna(subset=cols).copy()
    dl["label"] = dl.groupby(level=0)["y_rel"].transform(lambda s: pd.qcut(s.rank(method="first"), 5, labels=False))
    parts = {"val": [], "test": []}
    for yr in VAL_YEARS + TEST_YEARS:
        tr, te = fold(dl, yr)
        tr = tr[tr.index.get_level_values(0).isin(tr.index.get_level_values(0).unique()[::3])]      # every 3rd date (less overlap)
        grp = tr.groupby(level=0).size().values
        m = lgb.LGBMRanker(n_estimators=200, learning_rate=0.03, num_leaves=7, min_child_samples=100, subsample=0.7, subsample_freq=1,
                           colsample_bytree=0.6, reg_lambda=10.0, verbose=-1, random_state=7)
        m.fit(tr[cols].values, tr["label"].values, group=grp)
        parts["val" if yr in VAL_YEARS else "test"].append(pd.DataFrame({"y": te["y_rel"].values, "p": m.predict(te[cols].values)}, index=te.index))
        print("ranker fold", yr, flush=True)
    report("LightGBM ranker (rank features)", pd.concat(parts["val"]), pd.concat(parts["test"]))

    eligible = {k: v for k, v in res.items() if v["val_ic"] > 0}
    chosen = max(eligible, key=lambda k: eligible[k]["val_ic"]) if eligible else None
    print("chosen on 2017-20 validation (needs val IC > 0):", chosen)
    (C.REPORTS_DIR / "model_search_v5_returns.json").write_text(json.dumps(dict(results=res, chosen=chosen), indent=1), encoding="utf-8")


# ================================================================================ Monte Carlo
def vol_uncertainty_pre2018(md) -> float:
    """sd of log(next-year realised vol / trailing-year vol), pooled over risky assets, outcomes known before 2018."""
    r = md.returns[[c for c in md.prices.columns if C.UNIVERSE[c][2] != "cash"]]
    trail = r.rolling(252, min_periods=200).std()
    nxt = trail.shift(-252)
    lr = np.log(nxt / trail).loc[:pd.Timestamp("2016-12-31")]           # window ends before 2018
    vals = lr.iloc[::21].stack().dropna()                                  # monthly samples (less overlap)
    return float(vals.std())


def run_mc(n_paths=4000):
    from calibration import HORIZON, PORTFOLIOS, truncate
    from ifit import montecarlo as MC, risk
    md = data.load()
    s_vol = vol_uncertainty_pre2018(md)
    print(f"volatility uncertainty measured on pre-2018 data: sd(log vol ratio) = {s_vol:.3f}")
    idx = md.prices.index
    rows = []
    for q in pd.date_range("2019-03-31", "2025-09-30", freq="QE"):
        pos = idx.searchsorted(q, side="right") - 1
        if pos + HORIZON >= len(idx):
            continue
        t = idx[pos]
        md_t = truncate(md, t)
        rm = risk.build_risk_model(md_t)
        mu = ml.expected_returns(rm, None)["expected"]
        regime = ml.fit_regimes(md_t)
        for name, wd in PORTFOLIOS.items():
            w = pd.Series(wd).reindex(rm.symbols).fillna(0.0)
            if w.sum() < 0.999:
                continue
            st = risk.portfolio_stats(w, mu, rm.cov, rm.beta)
            rets = md.prices.pct_change().iloc[pos + 1: pos + 1 + HORIZON]
            real = float((1 + (rets * w.reindex(rets.columns).fillna(0.0)).sum(axis=1)).prod() - 1)
            row = dict(date=str(t.date()), portfolio=name, realised=real)
            for lab, sv in (("prod", 0.0), ("volunc", s_vol)):
                C.MC_VOL_UNCERTAINTY = sv
                sim = MC.simulate_paths(st["exp_return"], st["volatility"], st["beta"], regime, 1, n_paths=n_paths, steps_per_year=252, seed=11)[:, -1].astype(float) - 1
                row["pit_" + lab] = float((sim < real).mean())
            rows.append(row)
        print("done", t.date(), flush=True)
    C.MC_VOL_UNCERTAINTY = 0.0
    df = pd.DataFrame(rows)
    levels = (0.5, 0.75, 0.9, 0.95, 0.99)
    res = dict(vol_uncertainty_sd=s_vol)
    for lab in ("prod", "volunc"):
        p = df["pit_" + lab].values
        cov = {str(int(q * 100)): float(((p >= (1 - q) / 2) & (p <= 1 - (1 - q) / 2)).mean()) for q in levels}
        cov["mean_abs_gap"] = float(np.mean([abs(cov[str(int(q * 100))] - q) for q in levels]))
        res[lab] = cov
        print(f"{lab:8s} " + "  ".join(f"{int(q * 100)}%:{cov[str(int(q * 100))]:.0%}" for q in levels) + f"   mean gap {cov['mean_abs_gap']:.3f}   n={len(p)}")
    (C.REPORTS_DIR / "model_search_v5_mc.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"vol": run_vol, "returns": run_returns, "mc": run_mc}[sys.argv[1]]()
