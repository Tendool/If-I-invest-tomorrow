"""Risk-layer evaluation: Monte Carlo calibration curve (several simulators), regime model usefulness, anomaly detector usefulness.

    python scripts/eval_risk.py calibration
    python scripts/eval_risk.py regimes
    python scripts/eval_risk.py anomalies

Regime and anomaly models are refit each year on data from *before* that year only and then applied forward, so every
number below is point-in-time (the in-production models are fit on all history, which is fine for today's decision but
would leak into a backtest).
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
from scipy import stats  # noqa: E402
from sklearn.ensemble import IsolationForest  # noqa: E402
from sklearn.linear_model import Ridge  # noqa: E402
from sklearn.mixture import GaussianMixture  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from ifit import config as C, data, features as F, ml, montecarlo as MC, risk  # noqa: E402
from calibration import HORIZON, PORTFOLIOS, truncate  # noqa: E402

YEARS = (2021, 2022, 2023, 2024, 2025, 2026)
LEVELS = (0.50, 0.75, 0.90, 0.95, 0.99)


# ================================================================================ Monte Carlo calibration
def block_bootstrap(hist: np.ndarray, mu_daily: float, n_paths: int, seed: int, block=21):
    """Resample 21-day blocks of the portfolio's own trailing daily returns (keeps volatility clustering and fat tails),
    recentred on the model's expected return."""
    rng = np.random.default_rng(seed)
    h = hist - hist.mean() + mu_daily
    n_blocks = int(np.ceil(HORIZON / block))
    starts = rng.integers(0, len(h) - block, size=(n_paths, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_paths, -1)[:, :HORIZON]
    return np.prod(1 + h[idx], axis=1) - 1


def run_calibration(n_paths=4000):
    md = data.load()
    idx = md.prices.index
    qends = pd.date_range("2019-03-31", "2025-09-30", freq="QE")
    rows = []
    for q in qends:
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
            hist = (rm.rets[rm.symbols] * w.values).sum(axis=1).values
            rets = md.prices.pct_change().iloc[pos + 1: pos + 1 + HORIZON]
            real = float((1 + (rets * w.reindex(rets.columns).fillna(0.0)).sum(axis=1)).prod() - 1)
            sims = {
                "Current (Student-t dof 5, regime switching)": MC.simulate_paths(st["exp_return"], st["volatility"], st["beta"], regime, 1, n_paths=n_paths,
                                                                                steps_per_year=252, seed=11, dof=5)[:, -1].astype(float) - 1,
                "Student-t dof 3 (fatter tails)": MC.simulate_paths(st["exp_return"], st["volatility"], st["beta"], regime, 1, n_paths=n_paths,
                                                                   steps_per_year=252, seed=11, dof=3)[:, -1].astype(float) - 1,
                "Block bootstrap of own history (21-day blocks)": block_bootstrap(hist, st["exp_return"] / 252, n_paths, 11),
            }
            for m, sim in sims.items():
                pit = float((sim < real).mean() + 0.5 * (sim == real).mean())
                rows.append(dict(date=str(t.date()), portfolio=name, method=m, pit=pit, realised=real, pred_mean=float(sim.mean()), pred_sd=float(sim.std()),
                                 pred_p5=float(np.quantile(sim, .05)), pred_p95=float(np.quantile(sim, .95))))
        print("done", t.date(), flush=True)
    return pd.DataFrame(rows)


def coverage_table(df):
    out = {}
    for m, g in df.groupby("method"):
        pit = g["pit"].values
        out[m] = {f"{int(q * 100)}": float(((pit >= (1 - q) / 2) & (pit <= 1 - (1 - q) / 2)).mean()) for q in LEVELS}
        out[m]["n"] = int(len(g))
        out[m]["mean_error"] = float((g["realised"] - g["pred_mean"]).mean())
        out[m]["ks_p"] = float(stats.kstest(pit, "uniform").pvalue)
        ex = g[~g["date"].between("2019-12-01", "2020-12-31")]                 # origins whose year contains the COVID crash
        pit2 = ex["pit"].values
        out[m]["cover90_excl_2020"] = float(((pit2 >= .05) & (pit2 <= .95)).mean())
        out[m]["cover90_2020_origins"] = float(((g[g["date"].between("2019-12-01", "2020-12-31")]["pit"] >= .05) & (g[g["date"].between("2019-12-01", "2020-12-31")]["pit"] <= .95)).mean())
    return out


def plot_calibration(tab):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(5.2, 4.4))
    ax.plot([0.4, 1], [0.4, 1], color="#999", lw=1, ls="--", label="Perfectly calibrated")
    for m, v in tab.items():
        ax.plot([q for q in LEVELS], [v[str(int(q * 100))] for q in LEVELS], marker="o", ms=4, lw=1.4, label=m.split(" (")[0])
    ax.set_xlabel("Stated probability of the interval")
    ax.set_ylabel("Share of outcomes inside it")
    ax.legend(fontsize=7, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    (C.REPORTS_DIR / "figures").mkdir(exist_ok=True)
    fig.savefig(C.REPORTS_DIR / "figures" / "calibration_curve.png", dpi=170)


def calibration():
    df = run_calibration()
    df.to_csv(C.REPORTS_DIR / "calibration_methods_raw.csv", index=False)
    tab = coverage_table(df)
    (C.REPORTS_DIR / "eval_calibration.json").write_text(json.dumps(tab, indent=1), encoding="utf-8")
    plot_calibration(tab)
    print(f"{'method':50s} " + " ".join(f"{int(q * 100):>5d}%" for q in LEVELS) + "  ex-2020  2020-origins  meanErr")
    for m, v in tab.items():
        print(f"{m:50s} " + " ".join(f"{v[str(int(q * 100))]:6.0%}" for q in LEVELS) + f"   {v['cover90_excl_2020']:6.0%}   {v['cover90_2020_origins']:8.0%}   {v['mean_error']:+.1%}")


# ================================================================================ regimes (point in time)
class PITRegime:
    def __init__(self, md_train, k=3, seed=7):
        mf = F.market_features(md_train)[F.REGIME_COLS].dropna()
        self.sc = StandardScaler().fit(mf.values)
        self.gmm = GaussianMixture(n_components=k, covariance_type="full", n_init=5, random_state=seed).fit(self.sc.transform(mf.values))
        raw = self.gmm.predict(self.sc.transform(mf.values))
        mret = md_train.market.pct_change().reindex(mf.index).fillna(0.0)
        score = [mret[raw == c].mean() * 252 - 1.5 * mret[raw == c].std() * np.sqrt(252) if (raw == c).any() else -9 for c in range(k)]
        self.order = np.argsort(score)[::-1]

    def probs(self, md) -> pd.DataFrame:
        mf = F.market_features(md)[F.REGIME_COLS].dropna()
        p = self.gmm.predict_proba(self.sc.transform(mf.values))[:, self.order]
        return pd.DataFrame(p, index=mf.index, columns=[0, 1, 2])


def pit_regime_probs(md) -> pd.DataFrame:
    parts = []
    for yr in YEARS:
        a, b = pd.Timestamp(f"{yr}-01-01"), pd.Timestamp(f"{yr}-12-31")
        tr = dataclasses.replace(md, prices=md.prices.loc[:a - pd.Timedelta(days=1)], volume=md.volume.loc[:a - pd.Timedelta(days=1)],
                                 market=md.market.loc[:a - pd.Timedelta(days=1)], macro=md.macro.loc[:a - pd.Timedelta(days=1)])
        pr = PITRegime(tr).probs(md)
        parts.append(pr.loc[a:b])
    return pd.concat(parts)


def forward_market_stats(md):
    m = md.market
    r = m.pct_change()
    fwd = pd.DataFrame(index=m.index)
    for h in (1, 5, 21):
        fwd[f"ret_{h}d"] = m.shift(-h) / m - 1
    fwd["vol_21d"] = r.rolling(21).std().shift(-21) * np.sqrt(252)
    # worst peak-to-trough fall inside the next 21 days
    arr = m.values
    mdd = np.full(len(arr), np.nan)
    for i in range(len(arr) - 21):
        w = arr[i: i + 22]
        mdd[i] = (w / np.maximum.accumulate(w) - 1).min()
    fwd["mdd_21d"] = mdd
    return fwd


def regimes():
    md = data.load()
    full = ml.fit_regimes(md)
    names = ml.REGIME_NAMES
    daily = pd.DataFrame(full.transition, index=names, columns=names)
    lab = full.labels
    h = 21
    T21 = np.full((3, 3), 1e-3)
    for a, b in zip(lab.values[:-h], lab.values[h:]):
        T21[a, b] += 1
    T21 = pd.DataFrame(T21 / T21.sum(axis=1, keepdims=True), index=names, columns=names)
    print("daily transition matrix\n", daily.round(3), "\n21-day transition matrix\n", T21.round(3))

    probs = pit_regime_probs(md)
    lab_pit = probs.values.argmax(axis=1)
    lab_pit = pd.Series(lab_pit, index=probs.index)
    fwd = forward_market_stats(md).reindex(probs.index)
    cond = {}
    for c in range(3):
        m = lab_pit == c
        f = fwd[m].dropna()
        cond[names[c]] = dict(days=int(m.sum()), share=float(m.mean()), ret_21d_mean=float(f["ret_21d"].mean()), ret_21d_median=float(f["ret_21d"].median()),
                              ret_21d_sd=float(f["ret_21d"].std()), vol_next_21d=float(f["vol_21d"].mean()), mdd_next_21d=float(f["mdd_21d"].mean()),
                              p_drawdown_5pct=float((f["mdd_21d"] <= -0.05).mean()), p_loss_21d=float((f["ret_21d"] < 0).mean()))
    print("\npoint-in-time conditional outcomes (2021-26)")
    print(pd.DataFrame(cond).T.round(3).to_string())

    # does the regime improve the volatility forecast?
    sub = dataclasses.replace(md, prices=md.prices[[c for c in md.prices.columns if C.UNIVERSE[c][2] != "cash"]],
                              volume=md.volume[[c for c in md.prices.columns if C.UNIVERSE[c][2] != "cash"]])
    panel = ml.vol_panel(sub)
    feats = ml.vol_features(panel)
    d = panel.index.get_level_values(0)
    purge = pd.Timedelta(days=31)
    p_no, p_with, ys = [], [], []
    for yr in YEARS:
        a, b = pd.Timestamp(f"{yr}-01-01"), pd.Timestamp(f"{yr}-12-31")
        tr_md = dataclasses.replace(md, prices=md.prices.loc[:a - pd.Timedelta(days=1)], volume=md.volume.loc[:a - pd.Timedelta(days=1)],
                                    market=md.market.loc[:a - pd.Timedelta(days=1)], macro=md.macro.loc[:a - pd.Timedelta(days=1)])
        rp = PITRegime(tr_md).probs(md)
        rp.columns = ["reg_bull", "reg_neutral", "reg_bear"]
        pp = panel.join(rp, on="date")
        f2 = feats + ["reg_neutral", "reg_bear"]
        tr = pp[d < a - purge].dropna(subset=f2 + ["y"]).iloc[::3]
        te = pp[(d >= a) & (d <= b)].dropna(subset=f2 + ["y"])
        m0 = make_pipeline(StandardScaler(), Ridge(alpha=3000)).fit(tr[feats].values, tr["y"].values)
        m1 = make_pipeline(StandardScaler(), Ridge(alpha=3000)).fit(tr[f2].values, tr["y"].values)
        p_no.append(pd.Series(m0.predict(te[feats].values), index=te.index))
        p_with.append(pd.Series(m1.predict(te[f2].values), index=te.index))
        ys.append(te["y"])
    y, p0, p1 = pd.concat(ys), pd.concat(p_no), pd.concat(p_with)
    r2 = lambda p: float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())
    vol_gain = dict(r2_without_regime=r2(p0), r2_with_regime=r2(p1), err_without=float(np.mean(np.abs(np.exp(p0 - y) - 1))), err_with=float(np.mean(np.abs(np.exp(p1 - y) - 1))))
    print("\nvolatility model with / without regime probabilities:", {k: round(v, 4) for k, v in vol_gain.items()})
    json.dump(dict(daily_transition=daily.round(4).to_dict(), transition_21d=T21.round(4).to_dict(), conditional_pit=cond, vol_with_regime=vol_gain),
              open(C.REPORTS_DIR / "eval_regimes.json", "w"), indent=1)


# ================================================================================ anomalies (point in time)
def anomalies():
    md = data.load()
    mf_all = F.market_features(md).dropna()
    fwd = forward_market_stats(md)
    scores = []
    for yr in YEARS:
        a, b = pd.Timestamp(f"{yr}-01-01"), pd.Timestamp(f"{yr}-12-31")
        tr = mf_all[mf_all.index < a]
        te = mf_all[(mf_all.index >= a) & (mf_all.index <= b)]
        iso = IsolationForest(n_estimators=300, contamination=0.02, random_state=7).fit(tr.values)
        tr_sc = np.sort(-iso.score_samples(tr.values))
        sc = pd.Series(-iso.score_samples(te.values), index=te.index)
        # percentile of each test day's score within the (past-only) training distribution
        scores.append(pd.DataFrame({"score": sc, "pct": np.searchsorted(tr_sc, sc.values) / len(tr_sc)}))
    f = pd.concat(scores).join(fwd).dropna()
    res = {}
    for label, cut in (("top 2% (production setting)", 0.98), ("top 5%", 0.95), ("top 10%", 0.90)):
        flag = f.pct >= cut
        blk = {}
        for lab, g in (("flagged", f[flag]), ("normal", f[~flag])):
            blk[lab] = dict(days=int(len(g)), ret_1d=float(g.ret_1d.mean()), ret_5d=float(g.ret_5d.mean()), ret_21d_mean=float(g.ret_21d.mean()),
                            ret_21d_median=float(g.ret_21d.median()), vol_next_21d=float(g.vol_21d.mean()), mdd_next_21d=float(g.mdd_21d.mean()),
                            p_21d_loss_gt_3pct=float((g.ret_21d < -0.03).mean()), p_drawdown_5pct=float((g.mdd_21d <= -0.05).mean()))
        if flag.sum() >= 5:
            blk["mannwhitney_p"] = {k: float(stats.mannwhitneyu(f[flag][k], f[~flag][k]).pvalue) for k in ("ret_1d", "ret_5d", "ret_21d", "vol_21d", "mdd_21d")}
        blk["episodes"] = int((flag.astype(int).diff() == 1).sum() + int(flag.iloc[0]))
        res[label] = blk
        print(f"== {label}: {int(flag.sum())} flagged days in {blk['episodes']} episodes")
        print(pd.DataFrame({k: v for k, v in blk.items() if k in ("flagged", "normal")}).round(4).to_string())
        if "mannwhitney_p" in blk:
            print("Mann-Whitney p:", {k: round(v, 3) for k, v in blk["mannwhitney_p"].items()})
    json.dump(res, open(C.REPORTS_DIR / "eval_anomalies.json", "w"), indent=1)


if __name__ == "__main__":
    {"calibration": calibration, "regimes": regimes, "anomalies": anomalies}[sys.argv[1]]()
