"""Round 4: new ideas, selected on a 4-year walk-forward validation (folds 2017-2020) instead of the single noisy
2019-20 window, then scored once on 2021-26.

    python scripts/model_search_v4.py vol        # GARCH feature, long-run level, forecast combination
    python scripts/model_search_v4.py returns    # relative-strength features / targets, chosen on 2017-20
    python scripts/model_search_v4.py mc         # drift-uncertainty and online-recalibrated Monte Carlo
    python scripts/model_search_v4.py labels     # AUC of regime / anomaly scores for a coming 5% drawdown

Note: the switch to a 2017-20 validation was made after 2021-26 results had been seen; gains are tentative.
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

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import optimize, stats  # noqa: E402
from sklearn.linear_model import Ridge  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from ifit import config as C, data, features as F, ml  # noqa: E402

VAL_YEARS = (2017, 2018, 2019, 2020)
TEST_YEARS = (2021, 2022, 2023, 2024, 2025, 2026)
PURGE = pd.Timedelta(days=int(F.FWD_DAYS * 1.5))
ANN = np.sqrt(C.TRADING_DAYS)
OUT = {}


def risky(md):
    keep = [c for c in md.prices.columns if C.UNIVERSE[c][2] != "cash"]
    return dataclasses.replace(md, prices=md.prices[keep], volume=md.volume[keep])


def trunc(md, t):
    return dataclasses.replace(md, prices=md.prices.loc[:t], volume=md.volume.loc[:t], market=md.market.loc[:t], macro=md.macro.loc[:t])


def fold(panel, yr):
    d = panel.index.get_level_values(0)
    a, b = pd.Timestamp(f"{yr}-01-01"), pd.Timestamp(f"{yr}-12-31")
    return panel[d < a - PURGE], panel[(d >= a) & (d <= b)]


def r2(y, p):
    y, p = np.asarray(y), np.asarray(p)
    return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def within_r2(df):
    g = df.groupby(level=1)
    wy, wp = df["y"] - g["y"].transform("mean"), df["p"] - g["p"].transform("mean")
    return float(1 - ((wy - wp) ** 2).sum() / (wy ** 2).sum())


# ================================================================================ volatility
def garch_fit(r):
    """GARCH(1,1) by Gaussian quasi-MLE on demeaned daily returns. Returns (omega, alpha, beta)."""
    r = r - r.mean()
    v0 = r.var()

    def nll(x):
        w, a, b = np.exp(x[0]), 1 / (1 + np.exp(-x[1])), 1 / (1 + np.exp(-x[2]))
        if a + b >= 0.999:
            return 1e10
        h = np.empty(len(r))
        h[0] = v0
        for t in range(1, len(r)):
            h[t] = w + a * r[t - 1] ** 2 + b * h[t - 1]
        return 0.5 * np.sum(np.log(h) + r ** 2 / h)

    x0 = np.array([np.log(v0 * 0.05), np.log(0.08 / 0.92), np.log(0.88 / 0.12)])
    res = optimize.minimize(nll, x0, method="Nelder-Mead", options=dict(maxiter=600, xatol=1e-4, fatol=1e-3))
    w, a, b = np.exp(res.x[0]), 1 / (1 + np.exp(-res.x[1])), 1 / (1 + np.exp(-res.x[2]))
    return w, a, b


def garch_feature(r_full: pd.Series, params, h=21):
    """log annualised average variance over the next h days implied by GARCH, filtered with fixed params."""
    w, a, b = params
    r = (r_full - r_full.mean()).fillna(0.0).values
    hv = np.empty(len(r))
    hv[0] = np.nanvar(r)
    for t in range(1, len(r)):
        hv[t] = w + a * r[t - 1] ** 2 + b * hv[t - 1]
    hnext = w + a * r ** 2 + b * hv                    # variance for t+1 given info at t
    p = a + b
    lr = w / (1 - p)
    k = np.arange(h)
    avg = lr + (hnext[:, None] - lr) * (p ** k)[None, :]
    return pd.Series(np.log(np.sqrt(np.clip(avg.mean(axis=1), 1e-8, None) * C.TRADING_DAYS).clip(0.01)), index=r_full.index)


def add_pit_features(md, panel, yr):
    """Point-in-time features whose parameters come from data before `yr` (GARCH params, asset long-run level)."""
    a = pd.Timestamp(f"{yr}-01-01")
    r = md.returns
    g = {}
    for s in r.columns:
        hist = r[s].loc[:a - pd.Timedelta(days=1)].dropna()
        if len(hist) < 400:
            continue
        g[s] = garch_feature(r[s], garch_fit(hist.values[-1500:]))
    gf = pd.DataFrame(g)
    out = panel.copy()
    out["garch_21"] = gf.stack().reindex(out.index)
    lr = np.log((r.rolling(21).std() * ANN).clip(lower=0.01)).rolling(756, min_periods=252).mean()
    out["lr_level"] = lr.stack().reindex(out.index)
    out["rv21_vs_lr"] = out["rv_21"] - out["lr_level"]
    return out


def run_vol():
    md = risky(data.load())
    panel = ml.vol_panel(md)
    base = ml.vol_features(panel)
    cands = {
        "A production": base,
        "B + GARCH(1,1) forecast": base + ["garch_21"],
        "C + long-run level": base + ["lr_level", "rv21_vs_lr"],
        "D + GARCH + long-run level": base + ["garch_21", "lr_level", "rv21_vs_lr"],
    }
    preds = {k: {"val": [], "test": []} for k in cands}
    naive = {"val": [], "test": []}
    for yr in VAL_YEARS + TEST_YEARS:
        part = "val" if yr in VAL_YEARS else "test"
        pp = add_pit_features(md, panel, yr)
        for name, cols in cands.items():
            tr, te = fold(pp.dropna(subset=cols + ["y"]), yr)
            if len(tr) < 1500 or te.empty:
                continue
            m = make_pipeline(StandardScaler(), Ridge(alpha=ml.VOL_ALPHA)).fit(tr[cols].values[::3], tr["y"].values[::3])
            preds[name][part].append(pd.DataFrame({"y": te["y"], "p": m.predict(te[cols].values), "n63": te["rv_63"]}, index=te.index))
        print("fold", yr, flush=True)
    res = {}
    for name in cands:
        v, t = pd.concat(preds[name]["val"]), pd.concat(preds[name]["test"])
        res[name] = dict(val_r2=r2(v.y, v.p), test_r2=r2(t.y, t.p), test_within=within_r2(t), test_err=float(np.mean(np.abs(np.exp(t.p - t.y) - 1))), test_rows=len(t))
        # forecast combination with 'same as last quarter': weight chosen on validation
        best = max(np.arange(0, 0.55, 0.05), key=lambda w: r2(v.y, (1 - w) * v.p + w * v.n63))
        tc = (1 - best) * t.p + best * t.n63
        res[name + f" + combine with last quarter (w={best:.2f})"] = dict(val_r2=r2(v.y, (1 - best) * v.p + best * v.n63), test_r2=r2(t.y, tc),
                                                                        test_within=within_r2(pd.DataFrame({"y": t.y, "p": tc})),
                                                                        test_err=float(np.mean(np.abs(np.exp(tc - t.y) - 1))), test_rows=len(t))
    for k, v in res.items():
        print(f"{k:58s} val R2 {v['val_r2']:.4f} | test R2 {v['test_r2']:.4f} within {v['test_within']:.4f} err {v['test_err'] * 100:.1f}%  n={v['test_rows']}")
    chosen = max(res, key=lambda k: res[k]["val_r2"])
    print("chosen on 2017-20 validation:", chosen)
    (C.REPORTS_DIR / "model_search_v4_vol.json").write_text(json.dumps(dict(results=res, chosen=chosen), indent=1), encoding="utf-8")


# ================================================================================ returns
def run_returns():
    from eval_models import build_return_panel, daily_ic, ic_stats
    md = risky(data.load())
    panel, sets = build_return_panel(md)
    targets = {"relative return": "y_rel", "excess vs NIFTY": "y_bench", "cross-sectional rank": "y_rank"}
    res = {}
    for sname, cols in sets.items():
        for tname, tcol in targets.items():
            d = panel.dropna(subset=cols + [tcol, "y_rel"])
            out = {}
            for alpha in (3000, 30000, 300000):
                parts = {"val": [], "test": []}
                for yr in VAL_YEARS + TEST_YEARS:
                    tr, te = fold(d, yr)
                    if len(tr) < 3000 or te.empty:
                        continue
                    m = make_pipeline(StandardScaler(), Ridge(alpha=alpha)).fit(tr[cols].values[::3], tr[tcol].values[::3])
                    parts["val" if yr in VAL_YEARS else "test"].append(pd.DataFrame({"y": te["y_rel"].values, "p": m.predict(te[cols].values)}, index=te.index))
                out[alpha] = (daily_ic(pd.concat(parts["val"])), daily_ic(pd.concat(parts["test"])))
            a = max(out, key=lambda k: out[k][0].mean())
            vi, ti = out[a]
            st = ic_stats(ti)
            res[f"{sname} | {tname}"] = dict(alpha=a, val_ic=float(vi.mean()), val_t=float(vi.mean() / vi.std() * np.sqrt(len(vi) / F.FWD_DAYS)), **{"test_" + k: v for k, v in st.items()})
            r = res[f"{sname} | {tname}"]
            print(f"{sname + ' | ' + tname:62s} a={a:>6}  val IC {r['val_ic']:+.4f} (t~{r['val_t']:+.1f}) | test IC {r['test_mean']:+.4f} tNW {r['test_t_newey_west']:+.2f} tIND {r['test_t_nonoverlap']:+.2f}", flush=True)
    chosen = max(res, key=lambda k: res[k]["val_ic"])
    print("chosen on 2017-20 validation:", chosen, "-> test IC", round(res[chosen]["test_mean"], 4))
    (C.REPORTS_DIR / "model_search_v4_returns.json").write_text(json.dumps(dict(results=res, chosen=chosen), indent=1), encoding="utf-8")


# ================================================================================ Monte Carlo
def run_mc(n_paths=3000):
    from calibration import HORIZON, PORTFOLIOS
    from ifit import montecarlo as MC, risk
    md = data.load()
    idx = md.prices.index
    rows = []
    for q in pd.date_range("2016-03-31", "2025-09-30", freq="QE"):
        pos = idx.searchsorted(q, side="right") - 1
        if pos + HORIZON >= len(idx):
            continue
        t = idx[pos]
        md_t = trunc(md, t)
        rm = risk.build_risk_model(md_t)
        mu = ml.expected_returns(rm, None)["expected"]
        regime = ml.fit_regimes(md_t)
        yrs_hist = len(rm.rets) / C.TRADING_DAYS
        for name, wd in PORTFOLIOS.items():
            w = pd.Series(wd).reindex(rm.symbols).fillna(0.0)
            if w.sum() < 0.999:
                continue
            st = risk.portfolio_stats(w, mu, rm.cov, rm.beta)
            sim = MC.simulate_paths(st["exp_return"], st["volatility"], st["beta"], regime, 1, n_paths=n_paths, steps_per_year=252, seed=11, dof=5)[:, -1].astype(float)
            rng = np.random.default_rng(5)
            # parameter uncertainty: the expected return is estimated from ~yrs_hist years, standard error sigma/sqrt(T)
            se = st["volatility"] / np.sqrt(max(yrs_hist, 1.0))
            sim_pu = sim * np.exp(rng.normal(-0.5 * se ** 2, se, n_paths))
            rets = md.prices.pct_change().iloc[pos + 1: pos + 1 + HORIZON]
            real = 1 + float((1 + (rets * w.reindex(rets.columns).fillna(0.0)).sum(axis=1)).prod() - 1)
            outcome_date = idx[pos + HORIZON]
            ls, lpu = np.log(sim), np.log(sim_pu)
            rows.append(dict(date=t, outcome_date=outcome_date, portfolio=name, real=np.log(real),
                             m=ls.mean(), s=ls.std(), pit=float((sim < real).mean()), m_pu=lpu.mean(), s_pu=lpu.std(), pit_pu=float((sim_pu < real).mean())))
        print("done", t.date(), flush=True)
    df = pd.DataFrame(rows)
    # online recalibration: widen by the dispersion of past standardised errors whose outcomes were known at the time
    df["z_pu"] = (df.real - df.m_pu) / df.s_pu
    scale, bias = [], []
    for _, r in df.iterrows():
        past = df[df.outcome_date <= r.date]
        if len(past) >= 12:
            scale.append(float(np.clip(past.z_pu.std(), 1.0, 2.5)))
            bias.append(0.0)
        else:
            scale.append(1.0)
            bias.append(0.0)
    df["k"] = scale
    df["pit_recal"] = stats.t.cdf((df.real - df.m_pu) / (df.s_pu * df.k), df=8)
    ev = df[df.date >= "2019-01-01"]
    levels = (0.5, 0.75, 0.9, 0.95, 0.99)
    res = {}
    for lab, col in (("Current", "pit"), ("+ parameter uncertainty", "pit_pu"), ("+ parameter uncertainty + online recalibration", "pit_recal")):
        p = ev[col].values
        res[lab] = {str(int(q * 100)): float(((p >= (1 - q) / 2) & (p <= 1 - (1 - q) / 2)).mean()) for q in levels}
        res[lab]["mean_abs_gap"] = float(np.mean([abs(res[lab][str(int(q * 100))] - q) for q in levels]))
        print(f"{lab:50s} " + "  ".join(f"{int(q * 100)}%:{res[lab][str(int(q * 100))]:.0%}" for q in levels) + f"   mean gap {res[lab]['mean_abs_gap']:.3f}")
    print("recalibration factor at last origin:", round(df.k.iloc[-1], 2), "| n evaluated:", len(ev))
    (C.REPORTS_DIR / "model_search_v4_mc.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


# ================================================================================ regime / anomaly as risk warnings
def run_labels():
    from eval_risk import PITRegime, forward_market_stats
    from sklearn.ensemble import IsolationForest
    md = data.load()
    fwd = forward_market_stats(md)
    mf = F.market_features(md).dropna()
    rows = []
    for yr in VAL_YEARS + TEST_YEARS:
        a, b = pd.Timestamp(f"{yr}-01-01"), pd.Timestamp(f"{yr}-12-31")
        md_tr = trunc(md, a - pd.Timedelta(days=1))
        pr = PITRegime(md_tr).probs(md).loc[a:b]
        tr = mf[mf.index < a]
        te = mf[(mf.index >= a) & (mf.index <= b)]
        iso = IsolationForest(n_estimators=300, contamination=0.02, random_state=7).fit(tr.values)
        sc = pd.Series(-iso.score_samples(te.values), index=te.index)
        rows.append(pd.DataFrame({"part": "val" if yr in VAL_YEARS else "test", "p_not_calm": 1 - pr[0], "anomaly": sc, "vix": md.macro["vix"].reindex(te.index),
                                  "mvol": te["mkt_vol_21d"]}))
    d = pd.concat(rows).join(fwd[["mdd_21d", "vol_21d"]]).dropna()
    d["event"] = (d.mdd_21d <= -0.05).astype(int)
    res = {}
    for part in ("val", "test"):
        s = d[d.part == part]
        res[part] = {k: float(roc_auc_score(s.event, s[k])) for k in ("p_not_calm", "anomaly", "vix", "mvol")}
        res[part]["base_rate"] = float(s.event.mean())
        res[part]["n"] = int(len(s))
        print(part, {k: round(v, 3) for k, v in res[part].items()})
    (C.REPORTS_DIR / "model_search_v4_labels.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__" and sys.argv[1] != "warning":
    {"vol": run_vol, "returns": run_returns, "mc": run_mc, "labels": run_labels}[sys.argv[1]]()


def run_warning():
    """Point-in-time logistic 'drawdown warning': P(market falls >= 5% peak-to-trough within 21 days)."""
    from eval_risk import PITRegime, forward_market_stats
    from sklearn.ensemble import IsolationForest
    from sklearn.linear_model import LogisticRegression
    md = data.load()
    fwd = forward_market_stats(md)
    mf = F.market_features(md).dropna()
    X = mf.copy()
    X["vix"] = md.macro["vix"].reindex(X.index)
    X["vix_chg_5"] = md.macro["vix"].pct_change(5).reindex(X.index)
    X = X.join(fwd[["mdd_21d"]])
    X["event"] = (X.mdd_21d <= -0.05).astype(float)
    X.loc[X.mdd_21d.isna(), "event"] = np.nan
    feats = [c for c in X.columns if c not in ("mdd_21d", "event")]
    rows = []
    for yr in VAL_YEARS + TEST_YEARS:
        a, b = pd.Timestamp(f"{yr}-01-01"), pd.Timestamp(f"{yr}-12-31")
        tr = X[X.index < a - pd.Timedelta(days=31)].dropna()
        te = X[(X.index >= a) & (X.index <= b)].dropna()
        pr = PITRegime(trunc(md, a - pd.Timedelta(days=1))).probs(md)
        iso = IsolationForest(n_estimators=300, random_state=7).fit(mf[mf.index < a].values)
        def aug(df):
            df = df.copy()
            df["p_not_calm"] = 1 - pr[0].reindex(df.index)
            df["anomaly"] = -iso.score_samples(mf.reindex(df.index).values)
            return df.dropna()
        tr, te = aug(tr), aug(te)
        cols = feats + ["p_not_calm", "anomaly"]
        m = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=2000)).fit(tr[cols].values, tr.event.values)
        rows.append(pd.DataFrame({"part": "val" if yr in VAL_YEARS else "test", "p": m.predict_proba(te[cols].values)[:, 1], "vix": te.vix,
                                  "event": te.event}, index=te.index))
    d = pd.concat(rows)
    res = {}
    for part in ("val", "test"):
        s = d[d.part == part]
        res[part] = dict(auc_warning_model=float(roc_auc_score(s.event, s.p)), auc_vix=float(roc_auc_score(s.event, s.vix)),
                         brier=float(((s.p - s.event) ** 2).mean()), brier_base=float(((s.event.mean() - s.event) ** 2).mean()), n=int(len(s)))
        print(part, {k: round(v, 4) for k, v in res[part].items()})
    (C.REPORTS_DIR / "model_search_v4_warning.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__" and sys.argv[1] == "warning":
    run_warning()
