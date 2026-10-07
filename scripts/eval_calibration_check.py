"""Why does the Monte Carlo's 90% band hold 84% of outcomes instead of 90%, and can it be fixed without needlessly wide bands?

    python scripts/eval_calibration_check.py portfolios   # the 4 calibration portfolios, quarterly origins 2016-2025
    python scripts/eval_calibration_check.py nifty        # NIFTY alone, monthly origins 2009-2025 (long history)

Scores that reward both calibration and sharpness (Gneiting & Raftery 2007):
  interval score (90%) = width + 20 x distance outside the band (lower is better; a band that is too wide pays for its width)
  CRPS                 = expected distance between a simulated outcome and the real one, minus half the spread (lower is better)
Candidates: extra uncertainty in the expected return (s.e. 3/6/10% a year), and recentring the expected return by the average error of
earlier forecasts whose outcome was already known (point in time).
Rule fixed before running: adopt a candidate only if it lowers the mean 90% interval score on origins before 2019 (2016-18 for the
portfolios, 2009-17 for NIFTY) in both samples. 2019-25 is reported, never used to choose. The coverage of the production setting on
2019-25 also gets a block-bootstrap interval (blocks of 4 quarterly origins = one year, because the 1-year outcomes overlap).
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

from ifit import config as C, data, ml, montecarlo as MC, risk  # noqa: E402
from calibration import HORIZON, PORTFOLIOS, truncate  # noqa: E402

CANDS = {"production": 0.0, "+ drift uncertainty 0.03": 0.03, "+ drift uncertainty 0.06": 0.06, "+ drift uncertainty 0.10": 0.10}
RECENTRE = "recentred by past errors (point in time)"


def crps(sim: np.ndarray, y: float) -> float:
    x = np.sort(sim)
    n = len(x)
    e_xy = np.abs(x - y).mean()
    e_xx = 2.0 / (n * n) * np.sum((2 * np.arange(1, n + 1) - n - 1) * x)
    return float(e_xy - 0.5 * e_xx)


def score_row(sim, y):
    lo, hi = np.quantile(sim, [0.05, 0.95])
    q25, q75 = np.quantile(sim, [0.25, 0.75])
    return dict(in90=bool(lo <= y <= hi), in50=bool(q25 <= y <= q75), width90=float(hi - lo),
                is90=float((hi - lo) + 20 * max(lo - y, 0) + 20 * max(y - hi, 0)), crps=crps(sim, y), pred_mean=float(sim.mean()), realised=y)


def simulate_all(origins, setup):
    """setup(t) -> list of (name, mu, sigma, beta, regime, realised). Runs every candidate; recentring uses errors of earlier origins
    whose 1-year outcome ended on or before t."""
    rows, known = [], []
    for t, pos in origins:
        past = [e for (end, e) in known if end <= t]
        shift = float(np.mean(past)) if past else 0.0
        for name, mu, sig, beta, regime, real, end in setup(t, pos):
            for cname, xd in list(CANDS.items()) + [(RECENTRE, None)]:
                m = mu + shift if xd is None else mu
                sim = MC.simulate_paths(m, sig, beta, regime, 1, n_paths=4000, steps_per_year=252, seed=11, dof=C.MC_T_DOF,
                                        extra_drift_se=0.0 if xd is None else xd)[:, -1].astype(float) - 1
                rows.append(dict(date=t, portfolio=name, cand=cname, shift=shift if xd is None else 0.0, **score_row(sim, real)))
                if cname == "production":
                    known.append((end, real - float(sim.mean())))
        print("origin", t.date(), "shift", round(shift, 3), flush=True)
    return pd.DataFrame(rows)


def summary(df, split):
    out = {}
    for period, g in (("before 2019", df[df.date < split]), ("2019-25", df[df.date >= split])):
        out[period] = {c: dict(n=int(len(x)), cover90=float(x.in90.mean()), cover50=float(x.in50.mean()), width90=float(x.width90.mean()),
                               is90=float(x.is90.mean()), crps=float(x.crps.mean()), mean_error=float((x.realised - x.pred_mean).mean()))
                       for c, x in g.groupby("cand")}
    return out


def block_ci(g, block=4, n_boot=2000, seed=7):
    """Coverage of the 90% band with a moving-block bootstrap over origin dates (all portfolios of a date move together)."""
    dates = sorted(g.date.unique())
    by = {d: g[g.date == d].in90.values for d in dates}
    rng = np.random.default_rng(seed)
    n, k = len(dates), int(np.ceil(len(dates) / block))
    cov = []
    for _ in range(n_boot):
        starts = rng.integers(0, n, size=k)
        pick = [dates[(s + j) % n] for s in starts for j in range(block)][:n]
        cov.append(np.concatenate([by[d] for d in pick]).mean())
    return float(np.quantile(cov, 0.05)), float(np.quantile(cov, 0.95))


def run_portfolios():
    md = data.load()
    idx = md.prices.index
    origins = []
    for q in pd.date_range("2016-03-31", "2025-09-30", freq="QE"):
        pos = idx.searchsorted(q, side="right") - 1
        if pos + HORIZON < len(idx):
            origins.append((idx[pos], pos))

    def setup(t, pos):
        md_t = truncate(md, t)
        rm = risk.build_risk_model(md_t)
        mu = ml.expected_returns(rm, None)["expected"]
        regime = ml.fit_regimes(md_t)
        out = []
        rets = md.prices.pct_change().iloc[pos + 1: pos + 1 + HORIZON]
        for name, wd in PORTFOLIOS.items():
            w = pd.Series(wd).reindex(rm.symbols).fillna(0.0)
            if w.sum() < 0.999:
                continue
            st = risk.portfolio_stats(w, mu, rm.cov, rm.beta)
            real = float((1 + (rets * w.reindex(rets.columns).fillna(0.0)).sum(axis=1)).prod() - 1)
            out.append((name, st["exp_return"], st["volatility"], st["beta"], regime, real, idx[pos + HORIZON]))
        return out

    df = simulate_all(origins, setup)
    df.to_csv(C.REPORTS_DIR / "calibration_check_portfolios_raw.csv", index=False)
    summarise_portfolios(df)


def summarise_portfolios(df=None):
    if df is None:
        df = pd.read_csv(C.REPORTS_DIR / "calibration_check_portfolios_raw.csv", parse_dates=["date"])
    res = summary(df, pd.Timestamp("2019-01-01"))
    prod = df[(df.cand == "production") & (df.date >= "2019-01-01")]
    res["production_2019_25_cover90_ci"] = block_ci(prod)
    res["production_2019_25_misses_by_portfolio"] = prod[~prod.in90].groupby("portfolio").size().to_dict()
    res["production_by_portfolio_2019_25"] = {p: dict(cover90=float(g.in90.mean()), mean_error=float((g.realised - g.pred_mean).mean()))
                                              for p, g in prod.groupby("portfolio")}
    show(res)
    (C.REPORTS_DIR / "calibration_check_portfolios.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")


def run_nifty():
    from ifit.data import MarketData
    full = data.load()
    L = full.regime_long.dropna(subset=["market"])
    px = L["market"]
    idx = px.index
    tr = px * np.exp(0.013 * np.arange(len(px)) / C.TRADING_DAYS)            # + ~1.3% dividend yield
    sym = "NIFTYBEES.NS"
    md = MarketData(prices=pd.DataFrame({sym: tr}), volume=pd.DataFrame({sym: 0.0}, index=idx), market=px,
                    macro=pd.DataFrame({"brent": px, "vix": L["vix"]}, index=idx), report={}, regime_long=L)
    origins = []
    for q in pd.date_range("2009-06-30", "2025-09-30", freq="ME"):
        pos = idx.searchsorted(q, side="right") - 1
        if pos + C.TRADING_DAYS < len(idx):
            origins.append((idx[pos], pos))

    def setup(t, pos):
        md_t = dataclasses.replace(md, prices=md.prices.loc[:t], volume=md.volume.loc[:t], market=md.market.loc[:t], macro=md.macro.loc[:t])
        rm = risk.build_risk_model(md_t)
        mu = float(ml.expected_returns(rm, None)["expected"][sym])
        real = float(tr.iloc[pos + C.TRADING_DAYS] / tr.iloc[pos] - 1)
        return [("NIFTY 50", mu, float(np.sqrt(rm.cov.loc[sym, sym])), float(rm.capm.loc[sym, "beta"]), ml.fit_regimes(md_t), real, idx[pos + C.TRADING_DAYS])]

    df = simulate_all(origins, setup)
    df.to_csv(C.REPORTS_DIR / "calibration_check_nifty_raw.csv", index=False)
    res = summary(df, pd.Timestamp("2018-01-01"))                              # 2009-17 origins: outcomes end by Dec 2018
    res = {{"before 2019": "2009-17 origins", "2019-25": "2018-25 origins"}[k]: v for k, v in res.items()}
    show(res)
    (C.REPORTS_DIR / "calibration_check_nifty.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")


def show(res):
    for period, d in res.items():
        if not isinstance(d, dict) or not all(isinstance(v, dict) and "n" in v for v in d.values()):
            print(period, d)
            continue
        print("\n" + period)
        for c, v in d.items():
            print(f"  {c:44s} n {v['n']:3d}  90% {v['cover90']:.0%}  50% {v['cover50']:.0%}  width90 {v['width90']:.3f}  IS90 {v['is90']:.3f}  CRPS {v['crps']:.4f}  mean err {v['mean_error']:+.3f}")


if __name__ == "__main__":
    {"portfolios": run_portfolios, "nifty": run_nifty, "summarise": summarise_portfolios}[sys.argv[1]]()
