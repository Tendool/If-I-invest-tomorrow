"""Calibration backtest of the Monte Carlo: are the predicted distributions honest?

    python scripts/calibration.py

At each quarter-end from 2019 to 2025 the full pipeline is rebuilt from the data available *at that date only*
(risk model, expected-return prior, market regime), a 1-year Monte Carlo is run for several portfolios, and the
realised next-year return is located inside the simulated distribution (the probability integral transform, PIT).
A calibrated simulator gives PIT ~ Uniform(0,1): 90% of outcomes inside the 5-95 band, 50% inside 25-75, etc.

Writes reports/calibration.json and reports/calibration.md.
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

from ifit import config as C, data, ml, montecarlo as MC, risk  # noqa: E402

PORTFOLIOS = {
    "NIFTY 50 ETF": {"NIFTYBEES.NS": 1.0},
    "Gold": {"GOLDBEES.NS": 1.0},
    "Balanced (60 index / 20 gold / 20 liquid)": {"NIFTYBEES.NS": 0.6, "GOLDBEES.NS": 0.2, "LIQUIDBEES.NS": 0.2},
    "8 large stocks, equal weight": {s + ".NS": 1 / 8 for s in ("RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "ITC", "LT", "HINDUNILVR")},
}
HORIZON = 252


def truncate(md, asof):
    return dataclasses.replace(md, prices=md.prices.loc[:asof], volume=md.volume.loc[:asof], market=md.market.loc[:asof],
                               macro=md.macro.loc[:asof])


def run(vol_mult: float = 1.0, n_paths: int = 4000, dof: int = C.MC_T_DOF, verbose=True):
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
            v = MC.simulate_paths(st["exp_return"], st["volatility"] * vol_mult, st["beta"], regime, 1, n_paths=n_paths, steps_per_year=252,
                                  seed=11, dof=dof)
            sim = v[:, -1].astype(float) - 1
            rets = md.prices.pct_change().iloc[pos + 1: pos + 1 + HORIZON]
            real = float((1 + (rets * w.reindex(rets.columns).fillna(0.0)).sum(axis=1)).prod() - 1)
            pit = float((sim < real).mean() + 0.5 * (sim == real).mean())
            rows.append(dict(date=str(t.date()), portfolio=name, pred_mean=float(sim.mean()), pred_median=float(np.median(sim)),
                             pred_p5=float(np.quantile(sim, .05)), pred_p95=float(np.quantile(sim, .95)), pred_sd=float(sim.std()),
                             realised=real, pit=pit, z=(real - sim.mean()) / sim.std()))
        if verbose:
            print("done", t.date(), flush=True)
    return pd.DataFrame(rows)


def summarise(df: pd.DataFrame) -> dict:
    def block(d):
        pit = d["pit"].values
        return dict(n=int(len(d)), cover90=float(((pit >= .05) & (pit <= .95)).mean()), cover50=float(((pit >= .25) & (pit <= .75)).mean()),
                    below_p5=float((pit < .05).mean()), above_p95=float((pit > .95).mean()), mean_pit=float(pit.mean()),
                    mean_error=float((d["realised"] - d["pred_mean"]).mean()), mae=float((d["realised"] - d["pred_median"]).abs().mean()),
                    z_sd=float(d["z"].std()), ks_p=float(stats.kstest(pit, "uniform").pvalue))
    out = {"All portfolios": block(df)}
    for p, d in df.groupby("portfolio"):
        out[p] = block(d)
    return out


if __name__ == "__main__":
    df = run()
    df.to_csv(C.REPORTS_DIR / "calibration_raw.csv", index=False)
    res = summarise(df)
    (C.REPORTS_DIR / "calibration.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    lines = ["# Monte Carlo calibration (1-year horizon, quarterly 2019-2025, information as of each date)\n",
             "| Portfolio | n | Inside 5-95 band (ideal 90%) | Inside 25-75 (ideal 50%) | Below 5th | Above 95th | Mean error of expected return | Realised/predicted spread |",
             "|---|---|---|---|---|---|---|---|"]
    for k, m in res.items():
        lines.append(f"| {k} | {m['n']} | {m['cover90']:.0%} | {m['cover50']:.0%} | {m['below_p5']:.0%} | {m['above_p95']:.0%} | {m['mean_error']:+.1%} | {m['z_sd']:.2f} |")
    (C.REPORTS_DIR / "calibration.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
