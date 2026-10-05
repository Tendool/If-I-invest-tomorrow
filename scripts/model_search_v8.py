"""Round 9: earnings data (ifit/earnings.py). Rules fixed before running, as in round 7:

    python scripts/model_search_v8.py returns   # adopt only if validation t (2017-20, independent windows) > incumbent's (3.19)
    python scripts/model_search_v8.py vol       # adopt only if validation R2 (2017-20) > incumbent's (0.5375)

2021-26 is reported, never used to choose.
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

from ifit import config as C, data, earnings as E, ml  # noqa: E402
from model_search_v4 import TEST_YEARS, VAL_YEARS, fold, r2, risky, within_r2  # noqa: E402
from model_search_v5 import BLEND_GRID  # noqa: E402

INCUMBENT_RET_T = 3.19
INCUMBENT_VOL_R2 = 0.5375


def run_returns():
    from eval_models import build_return_panel, daily_ic, ic_stats
    from model_search_v6 import add_factors
    md = risky(data.load())
    panel, _ = build_return_panel(md)
    d = add_factors(md, panel)
    ef = E.return_features(md).reindex(d.index)
    rk = lambda s: (s.groupby(level=0).rank(pct=True) - 0.5).fillna(0.0)               # no fresh result / not a stock: neutral
    d["f_sue"] = rk(ef["surprise"])
    d["f_ear"] = rk(ef["ear"])
    d = d.dropna(subset=["y_rel"])
    combos = {
        "residual reversal + momentum (incumbent)": ["f_res_rev", "f_res_mom"],
        "earnings surprise (SUE)": ["f_sue"],
        "earnings announcement return (EAR)": ["f_ear"],
        "post-earnings drift: SUE + EAR": ["f_sue", "f_ear"],
        "incumbent + SUE + EAR": ["f_res_rev", "f_res_mom", "f_sue", "f_ear"],
        "incumbent + EAR": ["f_res_rev", "f_res_mom", "f_ear"],
        "incumbent + SUE": ["f_res_rev", "f_res_mom", "f_sue"],
    }
    res = {}
    for name, cols in combos.items():
        x = pd.DataFrame({"y": d["y_rel"], "p": d[cols].mean(axis=1, skipna=False)}).dropna()
        xd = x.index.get_level_values(0)
        vs = ic_stats(daily_ic(x[(xd >= "2017-01-01") & (xd <= "2020-12-31")]))
        ts = ic_stats(daily_ic(x[xd >= "2021-01-01"]))
        res[name] = dict(val_ic=vs["mean"], val_t=vs["t_nonoverlap"], test_ic=ts["mean"], test_t=ts["t_nonoverlap"], test_pct_pos=ts["pct_pos"])
        print(f"{name:44s} val IC {vs['mean']:+.4f} t {vs['t_nonoverlap']:+.2f} | test IC {ts['mean']:+.4f} t {ts['t_nonoverlap']:+.2f}", flush=True)
    # stocks only (earnings exist only for stocks): how much the signals rank stocks against each other
    st = d[[C.UNIVERSE[s][2] == "stock" for s in d.index.get_level_values(1)]]
    for name in ("residual reversal + momentum (incumbent)", "post-earnings drift: SUE + EAR", "incumbent + SUE + EAR"):
        cols = combos[name]
        x = pd.DataFrame({"y": st["y_rel"], "p": st[cols].mean(axis=1, skipna=False)}).dropna()
        xd = x.index.get_level_values(0)
        vs = ic_stats(daily_ic(x[(xd >= "2017-01-01") & (xd <= "2020-12-31")]))
        ts = ic_stats(daily_ic(x[xd >= "2021-01-01"]))
        res["stocks only: " + name] = dict(val_ic=vs["mean"], val_t=vs["t_nonoverlap"], test_ic=ts["mean"], test_t=ts["t_nonoverlap"])
        print(f"stocks only: {name:32s} val IC {vs['mean']:+.4f} t {vs['t_nonoverlap']:+.2f} | test IC {ts['mean']:+.4f} t {ts['t_nonoverlap']:+.2f}", flush=True)
    ok = {k: v for k, v in res.items() if not k.startswith("stocks only") and "incumbent)" not in k and v["val_ic"] > 0 and v["val_t"] > INCUMBENT_RET_T}
    chosen = max(ok, key=lambda k: ok[k]["val_t"]) if ok else "residual reversal + momentum (incumbent)"
    print("decision (validation t must beat 3.19):", chosen)
    (C.REPORTS_DIR / "model_search_v8_returns.json").write_text(json.dumps(dict(results=res, chosen=chosen), indent=1), encoding="utf-8")


def run_vol():
    md = risky(data.load())
    panel = ml.vol_panel(md)
    base = ml.vol_features(panel)
    vf = E.vol_features(md).reindex(panel.index).fillna(0.0)
    for c in vf.columns:
        panel[c] = vf[c]
    earn = list(vf.columns)
    cands = {
        "A production (round 7)": base,
        "B + earnings window and jump": base + earn,
        "C + earnings window x jump only": base + ["earn_window_x_jump"],
    }
    preds = {k: {"val": [], "test": []} for k in cands}
    for yr in VAL_YEARS + TEST_YEARS:
        part = "val" if yr in VAL_YEARS else "test"
        for name, cols in cands.items():
            tr, te = fold(panel.dropna(subset=cols + ["y"]), yr)
            trs = tr.iloc[::3]
            m = make_pipeline(StandardScaler(), Ridge(alpha=ml.VOL_ALPHA)).fit(trs[cols].values, trs["y"].values)
            preds[name][part].append(pd.DataFrame({"y": te["y"], "p": m.predict(te[cols].values), "n63": te["rv_63"]}, index=te.index))
        print("fold", yr, flush=True)
    res = {}
    for name in cands:
        v, t = pd.concat(preds[name]["val"]), pd.concat(preds[name]["test"])
        w = max(BLEND_GRID, key=lambda x: r2(v.y, (1 - x) * v.p + x * v.n63))
        vb, tb = (1 - w) * v.p + w * v.n63, (1 - w) * t.p + w * t.n63
        stock = np.array([C.UNIVERSE[s][2] == "stock" for s in t.index.get_level_values(1)])
        res[name] = dict(blend=float(w), val_r2=r2(v.y, vb), test_r2=r2(t.y, tb), test_within=within_r2(pd.DataFrame({"y": t.y, "p": tb})),
                         test_err=float(np.mean(np.abs(np.exp(tb - t.y) - 1))), test_stock_r2=r2(t.y[stock], tb[stock]),
                         test_by_year={int(y): r2(g.y, g.p) for y, g in pd.DataFrame({"y": t.y, "p": tb}).groupby(t.index.get_level_values(0).year)})
        x = res[name]
        print(f"{name:36s} w={w:.2f} val R2 {x['val_r2']:.4f} | test R2 {x['test_r2']:.4f} within {x['test_within']:.4f} stocks {x['test_stock_r2']:.4f} err {x['test_err'] * 100:.1f}%", flush=True)
    ok = {k: v for k, v in res.items() if v["val_r2"] > INCUMBENT_VOL_R2 + 1e-4 and not k.startswith("A ")}
    chosen = max(ok, key=lambda k: ok[k]["val_r2"]) if ok else "A production (round 7)"
    print("decision (validation R2 must beat 0.5375):", chosen)
    (C.REPORTS_DIR / "model_search_v8_vol.json").write_text(json.dumps(dict(results=res, chosen=chosen), indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"returns": run_returns, "vol": run_vol}[sys.argv[1]]()
