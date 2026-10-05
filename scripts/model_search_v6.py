"""Round 7: more documented ideas. Rules fixed BEFORE running (the 2017-20 validation years have been used in earlier rounds,
so a candidate must beat the incumbent on validation, not just be positive):

    python scripts/model_search_v6.py returns   # adopt only if validation t (independent windows) > incumbent (reversal + momentum, 2.25)
    python scripts/model_search_v6.py vol       # adopt only if validation R2 > incumbent (seasonal production, 0.536)
    python scripts/model_search_v6.py mc        # decide on 2016-18 forecast origins (never used for a decision), report 2019-25

Test results (2021-26 for returns/vol, 2019-25 origins for the Monte Carlo) are reported, never used to choose.
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

from ifit import config as C, data, ml  # noqa: E402
from model_search_v4 import TEST_YEARS, VAL_YEARS, fold, r2, risky, within_r2  # noqa: E402
from model_search_v5 import BLEND_GRID  # noqa: E402

INCUMBENT_RET_T = 2.25
INCUMBENT_VOL_R2 = 0.5360


# ================================================================================ returns
def add_factors(md, panel):
    """Documented cross-sectional factors, all point in time. Wide frames are computed per asset, then stacked."""
    px = md.prices
    r = px.pct_change()
    mr = md.market.pct_change().reindex(r.index)
    beta = r.rolling(252, min_periods=126).cov(mr).div(mr.rolling(252, min_periods=126).var(), axis=0)
    resid = r - beta.shift(1).mul(mr, axis=0)                                    # yesterday's beta: no look-ahead
    res_mom = resid.rolling(231, min_periods=120).sum().shift(21) / (resid.rolling(231, min_periods=120).std().shift(21) * np.sqrt(231))
    res_rev = resid.rolling(21).sum()
    seas = pd.concat([(px.shift(252 * k - 21) / px.shift(252 * k) - 1).stack().rename(k) for k in range(1, 6)], axis=1)
    seas_mean = seas.mean(axis=1).where(seas.notna().sum(axis=1) >= 2)
    out = panel.copy()
    out["res_mom"] = res_mom.stack().reindex(out.index)
    out["res_rev"] = res_rev.stack().reindex(out.index)
    out["seas"] = seas_mean.reindex(out.index)
    rk = lambda s: s.groupby(level=0).rank(pct=True) - 0.5
    out["f_reversal"] = -rk(out["ret_21d"])
    out["f_momentum"] = rk(out["ret_252d"] - out["ret_21d"])
    out["f_high52"] = rk(out["dd_252"])                                         # close to the 52-week high
    out["f_res_mom"] = rk(out["res_mom"])
    out["f_res_rev"] = -rk(out["res_rev"])
    out["f_seas"] = rk(out["seas"])
    return out


def run_returns():
    from eval_models import build_return_panel, daily_ic, ic_stats
    md = risky(data.load())
    panel, _ = build_return_panel(md)
    d = add_factors(md, panel).dropna(subset=["y_rel"])
    combos = {
        "reversal + momentum (incumbent)": ["f_reversal", "f_momentum"],
        "52-week high": ["f_high52"],
        "residual momentum": ["f_res_mom"],
        "residual reversal": ["f_res_rev"],
        "seasonality (same month, past years)": ["f_seas"],
        "residual reversal + residual momentum": ["f_res_rev", "f_res_mom"],
        "reversal + momentum + 52-week high": ["f_reversal", "f_momentum", "f_high52"],
        "reversal + residual momentum": ["f_reversal", "f_res_mom"],
        "reversal + momentum + seasonality": ["f_reversal", "f_momentum", "f_seas"],
        "all six, equal weight": ["f_reversal", "f_momentum", "f_high52", "f_res_mom", "f_res_rev", "f_seas"],
    }
    dates = d.index.get_level_values(0)
    vm, tm = (dates >= "2017-01-01") & (dates <= "2020-12-31"), dates >= "2021-01-01"
    res = {}

    def score(name, pred):
        x = pd.DataFrame({"y": d["y_rel"], "p": pred}).dropna()
        xd = x.index.get_level_values(0)
        vi = daily_ic(x[(xd >= "2017-01-01") & (xd <= "2020-12-31")])
        ti = daily_ic(x[xd >= "2021-01-01"])
        vs, ts = ic_stats(vi), ic_stats(ti)
        res[name] = dict(val_ic=vs["mean"], val_t=vs["t_nonoverlap"], test_ic=ts["mean"], test_t=ts["t_nonoverlap"], test_t_nw=ts["t_newey_west"],
                         test_pct_pos=ts["pct_pos"])
        print(f"{name:44s} val IC {vs['mean']:+.4f} t {vs['t_nonoverlap']:+.2f} | test IC {ts['mean']:+.4f} t {ts['t_nonoverlap']:+.2f}", flush=True)

    for name, cols in combos.items():
        score(name, d[cols].mean(axis=1, skipna=False))

    # small fitted model on the six factor ranks (few inputs: less room to overfit than the 30-feature Ridge)
    fcols = combos["all six, equal weight"]
    dr = d.dropna(subset=fcols)
    parts = []
    for yr in VAL_YEARS + TEST_YEARS:
        tr, te = fold(dr, yr)
        m = make_pipeline(StandardScaler(), Ridge(alpha=1000.0)).fit(tr[fcols].values[::3], tr["y_rel"].values[::3])
        parts.append(pd.Series(m.predict(te[fcols].values), index=te.index))
    score("Ridge on the six factor ranks (fitted)", pd.concat(parts).reindex(d.index))

    ok = {k: v for k, v in res.items() if v["val_ic"] > 0 and v["val_t"] > INCUMBENT_RET_T and "incumbent" not in k}
    chosen = max(ok, key=lambda k: ok[k]["val_t"]) if ok else "reversal + momentum (incumbent)"
    print("decision (validation t must beat the incumbent's 2.25):", chosen)
    (C.REPORTS_DIR / "model_search_v6_returns.json").write_text(json.dumps(dict(results=res, chosen=chosen), indent=1), encoding="utf-8")


# ================================================================================ volatility
def run_vol():
    md = risky(data.load())
    panel = ml.vol_panel(md)
    base = ml.vol_features(panel)
    panel["log_vix"] = np.log(panel["vix"].clip(lower=0.05))
    panel["log_vix_sq"] = panel["log_vix"] ** 2
    cls = pd.Series([C.UNIVERSE[s][2] for s in panel.index.get_level_values(1)], index=panel.index)
    inter = []
    for c in ("etf", "gold", "bond"):
        dmy = (cls == c).astype(float)
        panel[f"is_{c}"] = dmy
        inter.append(f"is_{c}")
        for f in ("rv_21", "rv_63", "m_rv_21", "lr_level"):
            panel[f"{f}_x_{c}"] = panel[f] * dmy
            inter.append(f"{f}_x_{c}")
    cands = {
        "A production (round 6)": (base, None),
        "B + log VIX nonlinearity": (base + ["log_vix", "log_vix_sq"], None),
        "C + asset-class effects": (base + inter, None),
        "D recency-weighted training (half-life 3 years)": (base, 3.0),
        "E B + C": (base + ["log_vix", "log_vix_sq"] + inter, None),
        "F B + C + recency weighting": (base + ["log_vix", "log_vix_sq"] + inter, 3.0),
    }
    preds = {k: {"val": [], "test": []} for k in cands}
    for yr in VAL_YEARS + TEST_YEARS:
        part = "val" if yr in VAL_YEARS else "test"
        for name, (cols, hl) in cands.items():
            tr, te = fold(panel.dropna(subset=cols + ["y"]), yr)
            if len(tr) < 1500 or te.empty:
                continue
            trs = tr.iloc[::3]
            sw = None
            if hl:
                age = (pd.Timestamp(f"{yr}-01-01") - trs.index.get_level_values(0)).days / 365.25
                sw = 0.5 ** (age.values / hl)
            m = make_pipeline(StandardScaler(), Ridge(alpha=ml.VOL_ALPHA))
            m.fit(trs[cols].values, trs["y"].values, ridge__sample_weight=sw)
            preds[name][part].append(pd.DataFrame({"y": te["y"], "p": m.predict(te[cols].values), "n63": te["rv_63"]}, index=te.index))
        print("fold", yr, flush=True)
    res = {}
    for name in cands:
        v, t = pd.concat(preds[name]["val"]), pd.concat(preds[name]["test"])
        w = max(BLEND_GRID, key=lambda x: r2(v.y, (1 - x) * v.p + x * v.n63))
        vb, tb = (1 - w) * v.p + w * v.n63, (1 - w) * t.p + w * t.n63
        res[name] = dict(blend=float(w), val_r2=r2(v.y, vb), test_r2=r2(t.y, tb), test_within=within_r2(pd.DataFrame({"y": t.y, "p": tb})),
                         test_err=float(np.mean(np.abs(np.exp(tb - t.y) - 1))))
        x = res[name]
        print(f"{name:48s} w={w:.2f}  val R2 {x['val_r2']:.4f} | test R2 {x['test_r2']:.4f} within {x['test_within']:.4f} err {x['test_err'] * 100:.1f}%", flush=True)
    ok = {k: v for k, v in res.items() if v["val_r2"] > INCUMBENT_VOL_R2 + 1e-4 and not k.startswith("A ")}
    chosen = max(ok, key=lambda k: ok[k]["val_r2"]) if ok else "A production (round 6)"
    print("decision (validation R2 must beat 0.536):", chosen)
    (C.REPORTS_DIR / "model_search_v6_vol.json").write_text(json.dumps(dict(results=res, chosen=chosen), indent=1), encoding="utf-8")


# ================================================================================ Monte Carlo
def run_mc(n_paths=4000):
    from calibration import HORIZON, PORTFOLIOS, truncate
    from ifit import montecarlo as MC, risk
    md = data.load()
    idx = md.prices.index
    variants = {
        "A production (round 6)": dict(dof=5, model_unc=False),
        "B + expected-return model uncertainty": dict(dof=5, model_unc=True),
        "C Student-t dof 4": dict(dof=4, model_unc=False),
        "D Student-t dof 8": dict(dof=8, model_unc=False),
        "E B + dof 4": dict(dof=4, model_unc=True),
    }
    rows = []
    for q in pd.date_range("2016-03-31", "2025-09-30", freq="QE"):
        pos = idx.searchsorted(q, side="right") - 1
        if pos + HORIZON >= len(idx):
            continue
        t = idx[pos]
        md_t = truncate(md, t)
        rm = risk.build_risk_model(md_t)
        er = ml.expected_returns(rm, None)
        mu = er["expected"]
        regime = ml.fit_regimes(md_t)
        for name, wd in PORTFOLIOS.items():
            w = pd.Series(wd).reindex(rm.symbols).fillna(0.0)
            if w.sum() < 0.999:
                continue
            st = risk.portfolio_stats(w, mu, rm.cov, rm.beta)
            # uncertainty about the CAPM / history blend weight: uniform on [0, 1] -> sd = |CAPM - history| / sqrt(12)
            gap = float((w * (er["capm"] - er["hist"]).reindex(w.index).fillna(0.0)).sum())
            rets = md.prices.pct_change().iloc[pos + 1: pos + 1 + HORIZON]
            real = float((1 + (rets * w.reindex(rets.columns).fillna(0.0)).sum(axis=1)).prod() - 1)
            row = dict(date=t, portfolio=name, part="val" if t < pd.Timestamp("2019-01-01") else "test")
            for vn, cfg in variants.items():
                sim = MC.simulate_paths(st["exp_return"], st["volatility"], st["beta"], regime, 1, n_paths=n_paths, steps_per_year=252, seed=11,
                                        dof=cfg["dof"], extra_drift_se=abs(gap) / np.sqrt(12) if cfg["model_unc"] else 0.0)[:, -1].astype(float) - 1
                row[vn] = float((sim < real).mean())
            rows.append(row)
        print("done", t.date(), flush=True)
    df = pd.DataFrame(rows)
    levels = (0.5, 0.75, 0.9, 0.95, 0.99)
    res = {}
    for vn in variants:
        res[vn] = {}
        for part in ("val", "test"):
            p = df[df.part == part][vn].values
            cov = {str(int(q * 100)): float(((p >= (1 - q) / 2) & (p <= 1 - (1 - q) / 2)).mean()) for q in levels}
            cov["gap"] = float(np.mean([abs(cov[str(int(q * 100))] - q) for q in levels]))
            cov["n"] = int(len(p))
            res[vn][part] = cov
        a, b = res[vn]["val"], res[vn]["test"]
        print(f"{vn:40s} VAL gap {a['gap']:.3f} (90%:{a['90']:.0%}, n={a['n']}) | TEST gap {b['gap']:.3f} " +
              " ".join(f"{k}%:{b[k]:.0%}" for k in ("50", "75", "90", "95", "99")), flush=True)
    chosen = min(res, key=lambda k: res[k]["val"]["gap"])
    if res[chosen]["val"]["gap"] >= res["A production (round 6)"]["val"]["gap"] - 1e-9:
        chosen = "A production (round 6)"
    print("decision (lowest calibration gap on 2016-18 origins):", chosen)
    (C.REPORTS_DIR / "model_search_v6_mc.json").write_text(json.dumps(dict(results=res, chosen=chosen), indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"returns": run_returns, "vol": run_vol, "mc": run_mc}[sys.argv[1]]()
