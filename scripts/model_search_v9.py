"""Round 10. Rules fixed before running, as in rounds 7 and 9: a candidate is adopted only if it beats the model in use on
the 2017-20 validation years; 2021-26 is reported, never used to choose.

    python scripts/model_search_v9.py vol        # volatility: error correction, cleaner training target, full training sample
    python scripts/model_search_v9.py ceiling    # how much of the volatility target is predictable at all (split-half reliability)
    python scripts/model_search_v9.py returns    # return signal: documented signals not tried before (rule: validation t > 3.19)

Volatility ideas
  * error correction - each asset's average forecast error over a past window, known at the forecast date (errors of forecasts
    whose 21-day target has fully passed), added back with weight k. (k, window) chosen on 2017-20.
  * cleaner training target - the 21-day close-to-close volatility is a noisy measure of true volatility (21 fat-tailed returns).
    Train on a mix with a range-based measure of the same 21 days (intraday Garman-Klass + overnight return squared), which
    uses more of each day's information; always scored against the usual close-to-close target.
  * full training sample - every day instead of every third day.
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

YEARS = VAL_YEARS + TEST_YEARS
ANN = np.sqrt(C.TRADING_DAYS)
H = 21


def range_target(md, panel):
    """log annualised volatility of the next 21 days from daily ranges: intraday Garman-Klass + overnight return squared.
    Overnight = adjusted close-to-close log return minus the raw open-to-close log return (split-proof)."""
    o = ml._load_ohlc(md)
    hl = np.log(o["high"] / o["low"]).clip(0, 0.25)
    co = np.log(o["close"] / o["open"]).clip(-0.25, 0.25)
    gk = (0.5 * hl ** 2 - (2 * np.log(2) - 1) * co ** 2).clip(lower=0)
    lr = np.log1p(md.returns)
    ov = (lr - co.reindex_like(lr)).clip(-0.25, 0.25)
    v = (gk.reindex_like(lr) + ov ** 2)
    fwd = v.rolling(H, min_periods=H).mean().shift(-H)                       # days t+1 .. t+21
    y = np.log(np.sqrt(fwd * C.TRADING_DAYS).clip(lower=0.01))
    return y.stack().reindex(panel.index)


def walk_forward(panel, cols, step=3, blend=ml.VOL_NAIVE_WEIGHT, target=None):
    """Out-of-sample predictions for every year 2017-26 (model refit each year on data before it, purged).
    `target(train_rows)` builds the training target from training rows only (default: the usual close-to-close target)."""
    out = []
    for yr in YEARS:
        tr, _ = fold(panel.dropna(subset=cols + ["y"]), yr)
        tr = tr.iloc[::step]
        yt = tr["y"].values if target is None else target(tr)
        m = make_pipeline(StandardScaler(), Ridge(alpha=ml.VOL_ALPHA)).fit(tr[cols].values, yt)
        te = panel[(panel.index.get_level_values(0).year == yr)].dropna(subset=cols)
        p = m.predict(te[cols].values)
        out.append(pd.DataFrame({"raw": p, "n63": te["rv_63"].values, "y": te["y"].values}, index=te.index))
    df = pd.concat(out)
    if blend is None:                                                    # blend weight with last quarter chosen on 2017-20
        v = df[np.isin(df.index.get_level_values(0).year, VAL_YEARS)].dropna(subset=["y"])
        blend = max(np.arange(0, 0.55, 0.05), key=lambda x: r2(v.y, (1 - x) * v.raw + x * v.n63))
    df["p"] = (1 - blend) * df["raw"] + blend * df["n63"]
    df.attrs["blend"] = float(blend)
    return df


def score(df, col="p"):
    d = df.dropna(subset=["y", col])
    yr = d.index.get_level_values(0).year
    v, t = d[np.isin(yr, VAL_YEARS)], d[np.isin(yr, TEST_YEARS)]
    stock = np.array([C.UNIVERSE[s][2] == "stock" for s in t.index.get_level_values(1)])
    return dict(val_r2=r2(v.y, v[col]), test_r2=r2(t.y, t[col]), test_within=within_r2(pd.DataFrame({"y": t.y, "p": t[col]})),
                test_err=float(np.mean(np.abs(np.exp(t[col] - t.y) - 1))), test_stock_r2=r2(t.y[stock], t[col][stock]),
                test_by_year={int(y): r2(g.y, g[col]) for y, g in t.groupby(t.index.get_level_values(0).year)})


def error_correction(df, window, k):
    """p + k x (asset's mean error over the `window` latest forecasts whose 21-day outcome is already known)."""
    e = (df["y"] - df["p"]).unstack()
    corr = e.rolling(window, min_periods=max(10, window // 3)).mean().shift(H)     # origin s is known from s + 21 trading days
    c = corr.stack().reindex(df.index).fillna(0.0)
    return df["p"] + k * c


def run_vol():
    md = risky(data.load())
    panel = ml.vol_panel(md)
    feats = ml.vol_features(panel)
    stock = np.array([C.UNIVERSE[s][2] == "stock" for s in panel.index.get_level_values(1)])
    panel["y_rng"] = range_target(md, panel).where(stock)            # ETF high/low prints are unreliable: stocks only
    res, cand = {}, {}

    base = walk_forward(panel, feats)
    cand["A production (round 9)"] = base
    res["A production (round 9)"] = score(base)
    print("A production", {k: round(v, 4) for k, v in res["A production (round 9)"].items() if k != "test_by_year"}, flush=True)

    # B: cleaner training target, mix weight w in log space
    def mix_target(w):
        def f(tr):
            ok = tr["y_rng"].notna()
            bias = float((tr["y_rng"] - tr["y"])[ok].mean())                 # range-based runs ~10% higher; offset from training rows only
            return np.where(ok, (1 - w) * tr["y"] + w * (tr["y_rng"] - bias), tr["y"])
        return f

    for w in (0.25, 0.5, 0.75, 1.0):
        df = walk_forward(panel, feats, blend=None, target=mix_target(w))
        name = f"B train on {int(w * 100)}% range-based target"
        cand[name], res[name] = df, dict(score(df), blend=df.attrs["blend"])
        print(name, {k: round(v, 4) for k, v in res[name].items() if k != "test_by_year"}, flush=True)

    # C: full training sample
    df = walk_forward(panel, feats, step=1)
    cand["C every day in training"], res["C every day in training"] = df, score(df)
    print("C full sample", {k: round(v, 4) for k, v in res["C every day in training"].items() if k != "test_by_year"}, flush=True)

    # D: error correction on top of A and on top of the best B (by validation); (window, k) chosen on validation
    best_b = max([n for n in res if n.startswith("B ")], key=lambda n: res[n]["val_r2"])
    grid = []
    for src in ("A production (round 9)", best_b):
        df = cand[src]
        for window in (21, 63, 126, 252):
            for k in (0.25, 0.5, 0.75, 1.0):
                d2 = df.copy()
                d2["pc"] = error_correction(df, window, k)
                s = score(d2, "pc")
                grid.append(dict(src=src, window=window, k=k, val_r2=s["val_r2"], test_r2=s["test_r2"]))
        g = max([x for x in grid if x["src"] == src], key=lambda x: x["val_r2"])
        res[f"D error correction on [{src}]"] = dict(score(cand[src].assign(pc=error_correction(cand[src], g["window"], g["k"])), "pc"), window=g["window"], k=g["k"])
        print(f"D on [{src}] best window {g['window']} k {g['k']}", {k: round(v, 4) for k, v in res[f'D error correction on [{src}]'].items() if k not in ('test_by_year',)}, flush=True)

    inc = res["A production (round 9)"]["val_r2"]
    ok = {k: v for k, v in res.items() if not k.startswith("A ") and v["val_r2"] > inc + 1e-4}
    chosen = max(ok, key=lambda k: ok[k]["val_r2"]) if ok else "A production (round 9)"
    print("decision (validation R2 must beat the production model's):", chosen, flush=True)
    (C.REPORTS_DIR / "model_search_v9_vol.json").write_text(json.dumps(dict(results=res, grid=grid, chosen=chosen, incumbent_val_r2=inc), indent=1), encoding="utf-8")


def run_ceiling():
    """Split-half reliability of the 21-day volatility target: log vol of the odd days vs the even days of the same window.
    Both measure the same true volatility with independent sampling noise; Spearman-Brown turns their correlation into the
    reliability of the full 21-day measure, i.e. the R2 a forecaster that knew next month's true volatility would reach."""
    md = risky(data.load())
    r = md.returns
    out = {}
    for name, sel in (("all assets", None), ("stocks", "stock")):
        cols = [c for c in r.columns if sel is None or C.UNIVERSE[c][2] == sel]
        rr = r[cols]
        m = np.tile((np.arange(len(rr)) % 2 == 1)[:, None], (1, rr.shape[1]))
        odd, even = rr.where(m), rr.where(~m)
        f = lambda x: np.log((np.sqrt((x ** 2).rolling(H, min_periods=8).mean().shift(-H)) * ANN).clip(lower=0.01))
        yo, ye = f(odd).stack(), f(even).stack()
        full = np.log((rr.rolling(H).std().shift(-H) * ANN).clip(lower=0.01)).stack()
        d = pd.concat([yo.rename("o"), ye.rename("e"), full.rename("y")], axis=1).dropna()
        d = d[d.index.get_level_values(0) >= "2021-01-01"]
        rho = float(d["o"].corr(d["e"]))
        # within-asset version (timing only)
        g = d.groupby(level=1)
        dw = d - g.transform("mean")
        rho_w = float(dw["o"].corr(dw["e"]))
        out[name] = dict(split_half_corr=rho, reliability=2 * rho / (1 + rho), within_split_half_corr=rho_w, within_reliability=2 * rho_w / (1 + rho_w), n=int(len(d)))
        print(name, {k: round(v, 4) if isinstance(v, float) else v for k, v in out[name].items()}, flush=True)
    # the production forecast against the cleaner range-based measure of the same 21 days (Andersen & Bollerslev 1998)
    panel = ml.vol_panel(md)
    feats = ml.vol_features(panel)                                       # before adding the range target (not a feature)
    stock = np.array([C.UNIVERSE[s][2] == "stock" for s in panel.index.get_level_values(1)])
    panel["y_rng"] = range_target(md, panel).where(stock)
    df = walk_forward(panel, feats)
    df["y_rng"] = panel["y_rng"].reindex(df.index)
    t = df[np.isin(df.index.get_level_values(0).year, TEST_YEARS)].dropna(subset=["y", "y_rng", "p"])          # stocks only
    t = t.assign(y_rng=t["y_rng"] - float((t["y_rng"] - t["y"]).mean()))
    out["stocks_production_vs_close_to_close"] = r2(t.y, t.p)
    out["stocks_production_vs_range_based"] = r2(t.y_rng, t.p)
    out["corr2_close_to_close"] = float(np.corrcoef(t.y, t.p)[0, 1] ** 2)
    out["corr2_range_based"] = float(np.corrcoef(t.y_rng, t.p)[0, 1] ** 2)
    print({k: round(v, 4) for k, v in out.items() if isinstance(v, float)}, flush=True)
    (C.REPORTS_DIR / "model_search_v9_ceiling.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


def run_vol_combos():
    """Follow-up (still chosen on 2017-20 only): the every-day training sample (C, adopted above) combined with B and D."""
    md = risky(data.load())
    panel = ml.vol_panel(md)
    feats = ml.vol_features(panel)
    stock = np.array([C.UNIVERSE[s][2] == "stock" for s in panel.index.get_level_values(1)])
    panel["y_rng"] = range_target(md, panel).where(stock)
    res = {}
    c = walk_forward(panel, feats, step=1)
    res["C every day in training"] = score(c)

    def mix_target(w):
        def f(tr):
            ok = tr["y_rng"].notna()
            bias = float((tr["y_rng"] - tr["y"])[ok].mean())
            return np.where(ok, (1 - w) * tr["y"] + w * (tr["y_rng"] - bias), tr["y"])
        return f

    for w in (0.25, 0.5):
        df = walk_forward(panel, feats, step=1, blend=None, target=mix_target(w))
        res[f"C + B {int(w * 100)}% range-based target"] = dict(score(df), blend=df.attrs["blend"])
    best = None
    for window in (63, 126, 252):
        for k in (0.25, 0.5):
            s = score(c.assign(pc=error_correction(c, window, k)), "pc")
            if best is None or s["val_r2"] > best[2]["val_r2"]:
                best = (window, k, s)
    res["C + D error correction"] = dict(best[2], window=best[0], k=best[1])
    for n, v in res.items():
        print(n, {k: round(x, 4) for k, x in v.items() if k != "test_by_year"}, flush=True)
    inc = res["C every day in training"]["val_r2"]
    ok = {k: v for k, v in res.items() if not k.startswith("C every") and v["val_r2"] > inc + 1e-4}
    chosen = max(ok, key=lambda k: ok[k]["val_r2"]) if ok else "C every day in training"
    print("decision (validation R2 must beat C):", chosen, flush=True)
    (C.REPORTS_DIR / "model_search_v9_vol_combos.json").write_text(json.dumps(dict(results=res, chosen=chosen), indent=1), encoding="utf-8")


MC_GRID = [(vu, xd) for vu in (0.17, 0.25, 0.35) for xd in (0.0, 0.03, 0.06)]       # (volatility uncertainty, extra drift s.e.)
MC_LEVELS = (0.50, 0.75, 0.90, 0.95, 0.99)


def run_mc():
    """Monte Carlo calibration on the long NIFTY history (2007-), which the 2019-25 test never used for a choice.
    At each month-end from mid-2009 the production pipeline (risk model, CAPM + history prior, regime model with the long
    history) is run on NIFTY data up to that date, a 1-year simulation is made and the realised total return is located in it.
    Rule fixed before running: choose (volatility uncertainty, extra drift uncertainty) by the mean absolute coverage error over
    the 50/75/90/95/99% bands on origins up to Dec 2017 (outcomes to Dec 2018); adopt only if it beats the production setting."""
    import dataclasses
    from ifit import montecarlo as MC, risk
    from ifit.data import MarketData
    full = data.load()
    L = full.regime_long.dropna(subset=["market"])
    px = L["market"]
    idx = px.index
    tr = px * np.exp(0.013 * np.arange(len(px)) / C.TRADING_DAYS)            # + ~1.3% dividend yield (total return)
    sym = "NIFTYBEES.NS"
    md = MarketData(prices=pd.DataFrame({sym: tr}), volume=pd.DataFrame({sym: 0.0}, index=idx), market=px,
                    macro=pd.DataFrame({"brent": px, "vix": L["vix"]}, index=idx), report={}, regime_long=L)
    rows = []
    vu0 = C.MC_VOL_UNCERTAINTY
    for q in pd.date_range("2009-06-30", "2025-09-30", freq="ME"):
        pos = idx.searchsorted(q, side="right") - 1
        if pos + C.TRADING_DAYS >= len(idx):
            continue
        t = idx[pos]
        md_t = dataclasses.replace(md, prices=md.prices.loc[:t], volume=md.volume.loc[:t], market=md.market.loc[:t], macro=md.macro.loc[:t])
        rm = risk.build_risk_model(md_t)
        mu = float(ml.expected_returns(rm, None)["expected"][sym])
        sig = float(np.sqrt(rm.cov.loc[sym, sym]))
        beta = float(rm.capm.loc[sym, "beta"])
        regime = ml.fit_regimes(md_t)
        real = float(tr.iloc[pos + C.TRADING_DAYS] / tr.iloc[pos] - 1)
        for vu, xd in MC_GRID:
            C.MC_VOL_UNCERTAINTY = vu
            sim = MC.simulate_paths(mu, sig, beta, regime, 1, n_paths=4000, steps_per_year=252, seed=11, dof=C.MC_T_DOF, extra_drift_se=xd)[:, -1].astype(float) - 1
            rows.append(dict(date=str(t.date()), vol_unc=vu, extra_drift=xd, pit=float((sim < real).mean()), realised=real, pred_mean=float(sim.mean()),
                             mu=mu, sigma=sig))
        C.MC_VOL_UNCERTAINTY = vu0
        if t.month == 12:
            print("origins done to", t.date(), flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(C.REPORTS_DIR / "model_search_v9_mc_raw.csv", index=False)

    def cov_err(g):
        cov = {q: float(((g.pit >= (1 - q) / 2) & (g.pit <= 1 - (1 - q) / 2)).mean()) for q in MC_LEVELS}
        return cov, float(np.mean([abs(cov[q] - q) for q in MC_LEVELS]))

    res = {}
    for (vu, xd), g in df.groupby(["vol_unc", "extra_drift"]):
        sel, rep = g[g.date <= "2017-12-31"], g[g.date >= "2019-01-01"]
        c1, e1 = cov_err(sel)
        c2, e2 = cov_err(rep)
        res[f"vol_unc {vu:.2f}, extra drift {xd:.2f}"] = dict(vol_unc=vu, extra_drift=xd, choice_coverage=c1, choice_err=e1, report_coverage=c2, report_err=e2,
                                                             n_choice=int(len(sel)), n_report=int(len(rep)),
                                                             choice_mean_error=float((sel.realised - sel.pred_mean).mean()),
                                                             report_mean_error=float((rep.realised - rep.pred_mean).mean()))
    for k, v in res.items():
        print(f"{k:34s} 2009-17 origins: " + " ".join(f"{int(q * 100)}%:{v['choice_coverage'][q]:.0%}" for q in MC_LEVELS) + f" err {v['choice_err']:.3f}"
              f" | 2019-25: " + " ".join(f"{int(q * 100)}%:{v['report_coverage'][q]:.0%}" for q in MC_LEVELS) + f" err {v['report_err']:.3f}", flush=True)
    prod = f"vol_unc {C.MC_VOL_UNCERTAINTY:.2f}, extra drift 0.00"
    best = min(res, key=lambda k: res[k]["choice_err"])
    chosen = best if res[best]["choice_err"] < res[prod]["choice_err"] - 1e-9 else prod
    print("decision (coverage error on 2009-17 origins must beat production):", chosen, flush=True)
    (C.REPORTS_DIR / "model_search_v9_mc.json").write_text(json.dumps(dict(results=res, chosen=chosen, production=prod), indent=1, default=str), encoding="utf-8")


def run_returns():
    """Documented signals not tried in rounds 1-9, alone and added to the incumbent (residual reversal + momentum).
    Rule fixed before running (as in round 9): adopt only if the validation IC is positive and its t-statistic on
    independent windows beats the incumbent's 3.19."""
    from eval_models import build_return_panel, daily_ic, ic_stats
    from model_search_v6 import add_factors
    md = risky(data.load())
    panel, _ = build_return_panel(md)
    d = add_factors(md, panel)
    r = md.prices.pct_change()
    mr = md.market.pct_change().reindex(r.index)
    beta = r.rolling(252, min_periods=126).cov(mr).div(mr.rolling(252, min_periods=126).var(), axis=0)
    resid = r - beta.shift(1).mul(mr, axis=0)
    vol = md.volume.replace(0, np.nan)
    sector = pd.Series({s: C.UNIVERSE[s][1] for s in r.columns})
    rr21 = resid.rolling(21).sum()
    ind_adj = rr21.sub(rr21.T.groupby(sector).transform("mean").T)                  # residual reversal relative to the sector
    raw = {
        "rev5": resid.rolling(5).sum(),                                             # Lehmann (1990): 1-week reversal
        "maxret": r.rolling(21).max(),                                              # Bali, Cakici & Whitelaw (2011): MAX effect
        "ivol": resid.rolling(63, min_periods=40).std(),                            # Ang, Hodrick, Xing & Zhang (2006)
        "abvol": np.log(vol.rolling(5).mean() / vol.rolling(63).mean()),            # Gervais, Kaniel & Mingelgrin (2001)
        "beta": beta,                                                               # Frazzini & Pedersen (2014): betting against beta
        "ind_rev": ind_adj,                                                         # Da, Liu & Schaumburg (2014): within-industry reversal
    }
    rk = lambda x: x.groupby(level=0).rank(pct=True) - 0.5
    sign = {"rev5": -1, "maxret": -1, "ivol": -1, "abvol": 1, "beta": -1, "ind_rev": -1}
    for k, v in raw.items():
        d["f_" + k] = sign[k] * rk(v.stack().reindex(d.index))
    d = d.dropna(subset=["y_rel"])
    inc = ["f_res_rev", "f_res_mom"]
    combos = {"residual reversal + momentum (incumbent)": inc}
    names = {"rev5": "1-week reversal", "maxret": "MAX effect (low max daily return)", "ivol": "low idiosyncratic volatility",
             "abvol": "abnormal volume", "beta": "low beta", "ind_rev": "within-sector residual reversal"}
    for k, n in names.items():
        combos[n] = ["f_" + k]
        combos["incumbent + " + n] = inc + ["f_" + k]
    combos["sector-adjusted reversal + residual momentum"] = ["f_ind_rev", "f_res_mom"]
    res = {}
    for name, cols in combos.items():
        x = pd.DataFrame({"y": d["y_rel"], "p": d[cols].mean(axis=1, skipna=False)}).dropna()
        xd = x.index.get_level_values(0)
        vs = ic_stats(daily_ic(x[(xd >= "2017-01-01") & (xd <= "2020-12-31")]))
        ts = ic_stats(daily_ic(x[xd >= "2021-01-01"]))
        res[name] = dict(val_ic=vs["mean"], val_t=vs["t_nonoverlap"], test_ic=ts["mean"], test_t=ts["t_nonoverlap"])
        print(f"{name:58s} val IC {vs['mean']:+.4f} t {vs['t_nonoverlap']:+.2f} | test IC {ts['mean']:+.4f} t {ts['t_nonoverlap']:+.2f}", flush=True)
    inc_t = res["residual reversal + momentum (incumbent)"]["val_t"]
    ok = {k: v for k, v in res.items() if "(incumbent)" not in k and v["val_ic"] > 0 and v["val_t"] > inc_t}
    chosen = max(ok, key=lambda k: ok[k]["val_t"]) if ok else "residual reversal + momentum (incumbent)"
    print(f"decision (validation t must beat {inc_t:.2f}):", chosen, flush=True)
    (C.REPORTS_DIR / "model_search_v9_returns.json").write_text(json.dumps(dict(results=res, chosen=chosen), indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"vol": run_vol, "vol_combos": run_vol_combos, "ceiling": run_ceiling, "mc": run_mc, "returns": run_returns}[sys.argv[1]]()
