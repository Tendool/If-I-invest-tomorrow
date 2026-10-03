"""Round 2 of the model search: push each model as far as the data honestly allows.

    python scripts/model_search_v2.py vol        # volatility forecaster (adds High/Low range estimators)
    python scripts/model_search_v2.py returns    # relative-return ranker (rank features, rank targets, horizons)

Protocol (unchanged, so numbers are comparable with scripts/model_search.py):
  * hyper-parameters / variants are chosen on an inner validation window (train < 2019, validate 2019-2020)
  * the chosen setup is then scored on the untouched expanding-window walk-forward, test years 2021-2026,
    with targets purged by 1.5 x the forecast horizon.
"""
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

import lightgbm as lgb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xgboost as xgb  # noqa: E402
from scipy import stats  # noqa: E402
from sklearn.ensemble import RandomForestRegressor  # noqa: E402
from sklearn.linear_model import Ridge  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from ifit import config as C, data, features as F  # noqa: E402

TEST_YEARS = (2021, 2022, 2023, 2024, 2025, 2026)
ANN = np.sqrt(C.TRADING_DAYS)


# ============================================================================== shared
def split(panel, years, horizon_days=21):
    dates = panel.index.get_level_values(0)
    purge = pd.Timedelta(days=int(horizon_days * 1.5))
    for yr in years:
        a, b = pd.Timestamp(f"{yr}-01-01"), pd.Timestamp(f"{yr}-12-31")
        yield yr, panel[dates < a - purge], panel[(dates >= a) & (dates <= b)]


def inner(panel, horizon_days=21):
    dates = panel.index.get_level_values(0)
    purge = pd.Timedelta(days=int(horizon_days * 1.5))
    tr = panel[dates < pd.Timestamp("2019-01-01") - purge]
    va = panel[(dates >= "2019-01-01") & (dates <= "2020-12-31")]
    return tr, va


def load_ohlc(md):
    """High/Low/Open aligned to the cleaned calendar (raw files; ratios within a day are split-proof)."""
    out = {k: {} for k in ("open", "high", "low", "close")}
    for sym in md.prices.columns:
        raw = data._read_raw(sym)
        if raw is None:
            continue
        raw = raw.reindex(md.prices.index)
        for k, col in (("open", "Open"), ("high", "High"), ("low", "Low"), ("close", "Close")):
            out[k][sym] = raw[col]
    return {k: pd.DataFrame(v) for k, v in out.items()}


# ========================================================================= volatility
def vol_panel(md):
    r = md.returns
    o = load_ohlc(md)
    hl = np.log(o["high"] / o["low"]).clip(0, 0.25)                       # ln(H/L); NSE circuit limits keep this small
    co = np.log(o["close"] / o["open"]).clip(-0.25, 0.25)
    ho = np.log(o["high"] / o["open"]).clip(0, 0.25)
    lo = np.log(o["low"] / o["open"]).clip(-0.25, 0)
    gk = (0.5 * hl ** 2 - (2 * np.log(2) - 1) * co ** 2).clip(lower=0)    # Garman-Klass variance
    rs = (ho * (ho - co) + lo * (lo - co)).clip(lower=0)                  # Rogers-Satchell variance
    park = hl ** 2 / (4 * np.log(2))                                      # Parkinson variance
    gap = np.log(o["open"] / o["close"].shift(1)).clip(-0.25, 0.25)
    vol = md.volume.replace(0, np.nan)

    feats: dict[str, pd.DataFrame] = {}
    for k in (1, 5, 10, 21, 63, 126, 252):
        feats[f"rv_{k}"] = np.log((r.rolling(k, min_periods=max(2, k // 2)).std() * ANN).clip(lower=0.01)) if k > 1 else np.log((r.abs() * ANN).clip(lower=0.01))
    for k in (5, 21, 63):
        feats[f"park_{k}"] = np.log(np.sqrt(park.rolling(k).mean() * C.TRADING_DAYS).clip(lower=0.01))
    feats["gk_21"] = np.log(np.sqrt(gk.rolling(21).mean() * C.TRADING_DAYS).clip(lower=0.01))
    feats["gk_5"] = np.log(np.sqrt(gk.rolling(5).mean() * C.TRADING_DAYS).clip(lower=0.01))
    feats["rs_21"] = np.log(np.sqrt(rs.rolling(21).mean() * C.TRADING_DAYS).clip(lower=0.01))
    for lam in (0.94, 0.985):
        feats[f"ewma_{lam}"] = np.log(np.sqrt((r ** 2).ewm(alpha=1 - lam, adjust=False).mean() * C.TRADING_DAYS).clip(lower=0.01))
    feats["semi_dn_21"] = np.log((np.sqrt((r.clip(upper=0) ** 2).rolling(21).mean()) * ANN).clip(lower=0.01))
    feats["semi_up_21"] = np.log((np.sqrt((r.clip(lower=0) ** 2).rolling(21).mean()) * ANN).clip(lower=0.01))
    feats["maxabs_21"] = r.abs().rolling(21).max()
    feats["gap_21"] = gap.abs().rolling(21).mean()
    feats["volofvol_63"] = (r.rolling(5).std() * ANN).rolling(63).std() / (r.rolling(63).std() * ANN)
    feats["ret_1"] = r
    feats["ret_21"] = md.prices.pct_change(21)
    feats["ret_63"] = md.prices.pct_change(63)
    feats["dd_252"] = md.prices / md.prices.rolling(252, min_periods=60).max() - 1
    feats["vlm_ratio"] = np.log(vol.rolling(5).mean() / vol.rolling(63).mean())
    feats["rv5_over_63"] = feats["rv_5"] - feats["rv_63"]
    feats["rv21_over_252"] = feats["rv_21"] - feats["rv_252"]

    frames = {k: v.stack().rename(k) for k, v in feats.items()}
    panel = pd.concat(frames.values(), axis=1)
    panel.index.names = ["date", "symbol"]

    mf = F.market_features(md)
    mr = md.market.pct_change()
    mk = pd.DataFrame({
        "m_rv_5": np.log((mr.rolling(5).std() * ANN).clip(lower=0.01)),
        "m_rv_21": np.log((mr.rolling(21).std() * ANN).clip(lower=0.01)),
        "m_rv_63": np.log((mr.rolling(63).std() * ANN).clip(lower=0.01)),
        "vix": md.macro["vix"] / 100, "vix_chg_5": md.macro["vix"].pct_change(5), "vix_chg_21": md.macro["vix"].pct_change(21),
        "vix_rv_gap": np.log(md.macro["vix"] / 100) - np.log((mr.rolling(21).std() * ANN).clip(lower=0.01)),
        "m_dd": mf["mkt_dd"], "usdinr_21": mf["usdinr_ret_21d"], "brent_21": mf["brent_ret_21d"],
    })
    panel = panel.join(mk, on="date")
    # cross-sectional context: average log vol of the whole universe today
    panel["cs_mean_rv21"] = panel.groupby(level=0)["rv_21"].transform("mean")
    panel["rv21_vs_cs"] = panel["rv_21"] - panel["cs_mean_rv21"]

    fvol = r.rolling(21).std().shift(-21) * ANN
    panel["y"] = np.log(fvol.stack().rename("y").clip(lower=0.01)).reindex(panel.index)
    return panel.replace([np.inf, -np.inf], np.nan)


def r2(y, p):
    return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def vol_scores(df):
    y, p = df["y"].values, df["p"].values
    return dict(r2=r2(y, p), corr=float(np.corrcoef(y, p)[0, 1]), mape=float(np.mean(np.abs(np.exp(p - y) - 1))),
                rmse_log=float(np.sqrt(np.mean((y - p) ** 2))))


def vol_model(name, prm):
    if name == "HAR-Ridge":
        return make_pipeline(StandardScaler(), Ridge(**prm))
    if name == "LightGBM":
        return lgb.LGBMRegressor(random_state=7, verbose=-1, n_jobs=-1, **prm)
    if name == "XGBoost":
        return xgb.XGBRegressor(random_state=7, verbosity=0, n_jobs=-1, **prm)
    if name == "Random Forest":
        return RandomForestRegressor(random_state=7, n_jobs=-1, **prm)
    raise KeyError(name)


VOL_GRIDS = {
    "HAR-Ridge": [dict(alpha=a) for a in (1, 30, 300, 3000)],
    "LightGBM": [dict(n_estimators=n, num_leaves=l, learning_rate=0.03, subsample=0.7, subsample_freq=1, colsample_bytree=0.7,
                      min_child_samples=m, reg_lambda=10.0) for n in (300, 700) for l in (7, 15) for m in (100, 400)],
    "XGBoost": [dict(n_estimators=n, max_depth=d, learning_rate=0.03, subsample=0.7, colsample_bytree=0.7, min_child_weight=m, reg_lambda=10.0)
                for n in (300, 700) for d in (3, 4) for m in (50, 200)],
    "Random Forest": [dict(n_estimators=200, max_depth=d, min_samples_leaf=l, max_features=0.5) for d in (8, 12) for l in (50, 200)],
}


def run_vol(md):
    panel = vol_panel(md)
    feats = [c for c in panel.columns if c != "y"]
    d = panel.dropna(subset=feats + ["y"])
    print(f"vol panel: {len(d):,} rows, {len(feats)} features")
    tr, va = inner(d)
    chosen = {}
    for name, grid in VOL_GRIDS.items():
        best, bs = None, -9
        for prm in grid:
            m = vol_model(name, prm).fit(tr[feats].values[::3], tr["y"].values[::3])
            s = r2(va["y"].values, m.predict(va[feats].values))
            if s > bs:
                best, bs = prm, s
        chosen[name] = best
        print(f"  tuned {name}: inner R2={bs:.4f} {best}")

    oos = {n: [] for n in chosen}
    stack_parts = []
    for yr, trn, te in split(d, TEST_YEARS):
        preds = {}
        for n, prm in chosen.items():
            m = vol_model(n, prm).fit(trn[feats].values[::3], trn["y"].values[::3])
            preds[n] = m.predict(te[feats].values)
            oos[n].append(pd.DataFrame({"y": te["y"].values, "p": preds[n]}, index=te.index))
        stack_parts.append(pd.DataFrame(preds, index=te.index).assign(y=te["y"].values))
    res = {}
    for n, parts in oos.items():
        res[n] = vol_scores(pd.concat(parts))
    sp = pd.concat(stack_parts)
    mods = list(chosen)
    for combo_name, combo in (("Ensemble (all)", mods), ("Ensemble (Ridge+LightGBM)", ["HAR-Ridge", "LightGBM"]),
                              ("Ensemble (Ridge+LightGBM+XGBoost)", ["HAR-Ridge", "LightGBM", "XGBoost"])):
        res[combo_name] = vol_scores(pd.DataFrame({"y": sp["y"], "p": sp[combo].mean(axis=1)}))
    # baselines on the same rows
    base = sp[["y"]].copy()
    for nm, col in (("Naive: trailing 21d vol", "rv_21"), ("Naive: trailing 63d vol", "rv_63")):
        res[nm] = vol_scores(pd.DataFrame({"y": base["y"], "p": d.loc[base.index, col]}))
    old = {"Previous production ensemble (round 1)": dict(r2=0.719, corr=0.849, mape=0.254)}
    res.update(old)
    return res, chosen, feats


# ============================================================================ returns
def ret_panel(md, horizon):
    panel = F.build_panel(md, with_target=False)
    r = md.returns
    px = md.prices
    fwd = (px.shift(-horizon) / px - 1).stack().rename("fwd").reindex(panel.index)
    panel["fwd"] = fwd
    g = panel.groupby(level=0)
    panel["excess"] = panel["fwd"] - g["fwd"].transform("mean")
    panel["rank_t"] = g["excess"].rank(pct=True) - 0.5                    # cross-sectional rank target in [-0.5, 0.5]
    # extra signals
    mkt = md.market.pct_change()
    beta = F.asset_features  # noqa: F841
    resid = r.sub(mkt, axis=0)                                             # market-relative daily return
    sig = {
        "mom_12_1": px.shift(21) / px.shift(252) - 1,
        "mom_6_1": px.shift(21) / px.shift(126) - 1,
        "rev_5": -px.pct_change(5),
        "rev_21": -px.pct_change(21),
        "resid_mom_63": resid.rolling(63).sum(),
        "resid_mom_126": resid.rolling(126).sum(),
        "resid_rev_21": -resid.rolling(21).sum(),
        "vol_adj_mom": (px.shift(21) / px.shift(252) - 1) / (r.rolling(252).std() * ANN),
        "lowvol": -(r.rolling(63).std() * ANN),
        "dd_dist": px / px.rolling(252, min_periods=60).max() - 1,
        "max_ret_21": -r.rolling(21).max(),
        "skew_63": -r.rolling(63).skew(),
    }
    for k, v in sig.items():
        panel[k] = v.stack().reindex(panel.index)
    base_cols = [c for c in F.feature_columns(panel) if c not in ("fwd", "excess", "rank_t") and c not in sig]
    rank_src = base_cols[:0] + ["ret_5d", "ret_21d", "ret_63d", "ret_126d", "ret_252d", "vol_21d", "vol_63d", "px_sma20", "px_sma50",
                                "sma50_sma200", "rsi14", "macd_hist", "dd_252", "beta_63d", "corr_mkt_63d", "skew_63d"] + list(sig)
    for c in rank_src:
        panel["cs_" + c] = panel.groupby(level=0)[c].rank(pct=True) - 0.5
    return panel.replace([np.inf, -np.inf], np.nan), base_cols, ["cs_" + c for c in rank_src]


def rel_scores(df):
    ic = df.groupby(level=0).apply(lambda g: stats.spearmanr(g["y"], g["p"])[0] if len(g) > 8 else np.nan).dropna()
    q = df.copy()
    q["rk"] = q.groupby(level=0)["p"].rank(pct=True)
    top, bot = q[q.rk >= 0.8]["y"].groupby(level=0).mean(), q[q.rk <= 0.2]["y"].groupby(level=0).mean()
    sp = (top - bot).dropna()
    n_eff = max(1, len(sp) / 21)                                           # overlapping horizon -> fewer independent samples
    return dict(ic=float(ic.mean()), icir=float(ic.mean() / ic.std()), ic_pos=float((ic > 0).mean()),
                hit=float((np.sign(df.y) == np.sign(df.p - df.p.groupby(level=0).transform("mean"))).mean()),
                spread=float(sp.mean()), spread_t=float(sp.mean() / (sp.std() / np.sqrt(n_eff))))


def ret_model(name, prm):
    if name == "Ridge":
        return make_pipeline(StandardScaler(), Ridge(**prm))
    if name == "LightGBM":
        return lgb.LGBMRegressor(random_state=7, verbose=-1, n_jobs=-1, **prm)
    if name == "XGBoost":
        return xgb.XGBRegressor(random_state=7, verbosity=0, n_jobs=-1, **prm)
    raise KeyError(name)


RET_GRIDS = {
    "Ridge": [dict(alpha=a) for a in (100, 1000, 10000, 100000)],
    "LightGBM": [dict(n_estimators=n, num_leaves=l, learning_rate=0.02, subsample=0.7, subsample_freq=1, colsample_bytree=0.6,
                      min_child_samples=m, reg_lambda=50.0) for n in (150, 400) for l in (4, 8) for m in (300, 1000)],
    "XGBoost": [dict(n_estimators=n, max_depth=d, learning_rate=0.02, subsample=0.7, colsample_bytree=0.6, min_child_weight=m, reg_lambda=50.0)
                for n in (150, 400) for d in (2, 3) for m in (200, 800)],
}


def run_returns(md):
    out, best_cfg = {}, None
    for horizon in (21, 63):
        panel, base_cols, rank_cols = ret_panel(md, horizon)
        variants = {
            "raw features -> excess return": (base_cols, "excess"),
            "rank features -> rank target": (rank_cols, "rank_t"),
            "rank + raw features -> rank target": (rank_cols + base_cols, "rank_t"),
        }
        for vname, (cols, tgt) in variants.items():
            d = panel.dropna(subset=cols + [tgt, "excess"])
            tr, va = inner(d, horizon)
            chosen = {}
            for name, grid in RET_GRIDS.items():
                best, bs = None, -9
                for prm in grid:
                    m = ret_model(name, prm).fit(tr[cols].values[::3], tr[tgt].values[::3])
                    sc = rel_scores(pd.DataFrame({"y": va["excess"].values, "p": m.predict(va[cols].values)}, index=va.index))["ic"]
                    if sc > bs:
                        best, bs = prm, sc
                chosen[name] = (best, bs)
            oos = {n: [] for n in chosen}
            for yr, trn, te in split(d, TEST_YEARS, horizon):
                for n, (prm, _) in chosen.items():
                    m = ret_model(n, prm).fit(trn[cols].values[::3], trn[tgt].values[::3])
                    oos[n].append(pd.DataFrame({"y": te["excess"].values, "p": m.predict(te[cols].values)}, index=te.index))
            preds = {n: pd.concat(p) for n, p in oos.items()}
            # ensemble: average of cross-sectional ranks of each model's prediction
            ens = preds["Ridge"].copy()
            ens["p"] = np.mean([p["p"].groupby(level=0).rank(pct=True) for p in preds.values()], axis=0)
            preds["Ensemble (rank-average)"] = ens
            for n, p in preds.items():
                key = f"{horizon}d | {vname} | {n}"
                out[key] = rel_scores(p) | {"inner_ic": chosen.get(n, (None, float('nan')))[1], "horizon": horizon}
                print(f"  {key:70s} IC {out[key]['ic']:+.3f}  t {out[key]['spread_t']:+.1f}  inner {out[key]['inner_ic']:+.3f}")
        # reference rules at this horizon
        d = panel.dropna(subset=["rev_21", "excess"])
        d = d[d.index.get_level_values(0) >= "2021-01-01"]
        for nm, col in (("Rule: 1-month reversal", "rev_21"), ("Rule: residual reversal", "resid_rev_21"), ("Rule: 12-1 momentum", "mom_12_1"), ("Rule: low volatility", "lowvol")):
            dd = panel.dropna(subset=[col, "excess"])
            dd = dd[dd.index.get_level_values(0) >= "2021-01-01"]
            out[f"{horizon}d | {nm}"] = rel_scores(pd.DataFrame({"y": dd["excess"], "p": dd[col]})) | {"inner_ic": float("nan"), "horizon": horizon}
    return out


def without_cash(md):
    """Drop the liquid-fund series: it is a flat accrual (vol ~0.1%), so it is trivially 'predicted' / 'ranked last'
    and inflates pooled R2 and rank correlations without saying anything about stock selection."""
    import dataclasses
    keep = [c for c in md.prices.columns if C.UNIVERSE[c][2] != "cash"]
    return dataclasses.replace(md, prices=md.prices[keep], volume=md.volume[keep])


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "vol"
    md = without_cash(data.load())
    if what == "vol":
        res, chosen, feats = run_vol(md)
        (C.REPORTS_DIR / "model_search_v2_vol.json").write_text(json.dumps(dict(results=res, params=chosen, features=feats), indent=1, default=float), encoding="utf-8")
        print(f"\n{'model':44s} {'R2':>7s} {'corr':>7s} {'err%':>7s}")
        for n, m in sorted(res.items(), key=lambda kv: -kv[1]["r2"]):
            print(f"{n:44s} {m['r2']:7.4f} {m['corr']:7.4f} {m['mape'] * 100:6.1f}%")
    else:
        res = run_returns(md)
        (C.REPORTS_DIR / "model_search_v2_returns.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
