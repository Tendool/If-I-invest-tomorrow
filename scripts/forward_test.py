"""Prospective (forward) test of the frozen models: the only evidence no model choice could have seen.

    python scripts/forward_test.py log      # record today's forecasts (after scripts/download_data.py), one file per data date
    python scripts/forward_test.py score    # score every logged forecast whose 21 trading days have passed

Each log stores the git commit and model versions that produced it, so a forecast can be tied to frozen code. Logged files are never
overwritten. Scored, per forecast date and pooled:
  * volatility   - R2 of the 21-day log-volatility forecast per asset (and of "same as last quarter" for comparison)
  * return signal - Spearman IC between the 21-day relative-return forecast and the realised relative return
  * Monte Carlo  - share of 1-month outcomes of four reference portfolios inside the simulated 50% and 90% bands
"""
import json
import subprocess
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
from calibration import PORTFOLIOS  # noqa: E402

OUT = C.REPORTS_DIR / "forward"
H = 21
ANN = np.sqrt(C.TRADING_DAYS)


def _commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def log():
    from ifit.engine import Engine
    e = Engine()
    asof = str(e.md.last_date.date())
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"forecast_{asof}.json"
    if path.exists():
        print("already logged:", path.name)
        return
    rets = e.md.returns
    trail63 = (rets.iloc[-63:].std() * ANN)
    risky = [s for s in e.rm.symbols if C.UNIVERSE[s][2] != "cash"]
    ports = {}
    for name, wd in PORTFOLIOS.items():
        w = pd.Series(wd).reindex(e.rm.symbols).fillna(0.0)
        st = risk.portfolio_stats(w, e.mu, e.rm.cov, e.rm.beta)
        sim = MC.simulate_paths(st["exp_return"], st["volatility"], st["beta"], e.regime, H / C.TRADING_DAYS, n_paths=10_000, seed=11)[:, -1] - 1
        ports[name] = dict(weights={k: float(v) for k, v in wd.items()},
                           quantiles={str(q): float(np.quantile(sim, q)) for q in (0.05, 0.25, 0.5, 0.75, 0.95)})
    rec = dict(
        asof=asof, logged_with_commit=_commit(),
        return_model=dict(name=e.estimator.model_name, skill_weight=float(e.estimator.skill_weight)),
        vol_model=json.loads((C.MODELS_DIR / "vol_model_meta.json").read_text(encoding="utf-8")).get("version"),
        mc=dict(dof=C.MC_T_DOF, vol_uncertainty=C.MC_VOL_UNCERTAINTY),
        regime=dict(name=e.regime.current_name, probs=[float(x) for x in e.regime.current_probs]),
        vol_forecast_21d={s: float(e.vol_fc[s]) for s in risky},
        vol_trailing_63d={s: float(trail63[s]) for s in risky},
        return_forecast_21d={s: float(v) for s, v in e.estimator.ml_forecast_21d.items() if s in risky},
        portfolios_1m=ports,
    )
    path.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print("logged", path.name, "commit", rec["logged_with_commit"])


def score():
    md = data.load()
    idx = md.prices.index
    rows, pooled = [], dict(vol=[], ic=[], in50=[], in90=[])
    for f in sorted(OUT.glob("forecast_*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        t = pd.Timestamp(rec["asof"])
        pos = idx.searchsorted(t, side="right") - 1
        if pos + H >= len(idx):
            rows.append(dict(asof=rec["asof"], status=f"waiting: {pos + H - len(idx) + 1} more trading days of data"))
            continue
        fwd = md.prices.iloc[pos: pos + H + 1]
        r = fwd.pct_change().iloc[1:]
        real_vol = np.log((r.std() * ANN).clip(lower=0.01))
        syms = [s for s in rec["vol_forecast_21d"] if s in real_vol.index]
        y = real_vol[syms]
        p = np.log(pd.Series(rec["vol_forecast_21d"])[syms])
        n63 = np.log(pd.Series(rec["vol_trailing_63d"])[syms])
        r2 = lambda yy, pp: float(1 - ((yy - pp) ** 2).sum() / ((yy - yy.mean()) ** 2).sum())
        tot = fwd.iloc[-1] / fwd.iloc[0] - 1
        fc = pd.Series(rec["return_forecast_21d"])
        common = [s for s in fc.index if s in tot.index]
        rel = tot[common] - tot[common].mean()
        ic = float(fc[common].rank().corr(rel.rank()))
        cov = {}
        for name, pr in rec["portfolios_1m"].items():
            w = pd.Series(pr["weights"])
            real = float((1 + (r[w.index] * w.values).sum(axis=1)).prod() - 1)
            q = {float(k): v for k, v in pr["quantiles"].items()}
            cov[name] = dict(realised=real, in50=bool(q[0.25] <= real <= q[0.75]), in90=bool(q[0.05] <= real <= q[0.95]))
            pooled["in50"].append(cov[name]["in50"])
            pooled["in90"].append(cov[name]["in90"])
        pooled["vol"].append((y.values, p.values, n63.values))
        pooled["ic"].append(ic)
        rows.append(dict(asof=rec["asof"], commit=rec["logged_with_commit"], vol_r2=r2(y, p), vol_r2_naive63=r2(y, n63), ic=ic, portfolios=cov))
    out = dict(forecasts=rows)
    if pooled["vol"]:
        Y = np.concatenate([a for a, _, _ in pooled["vol"]])
        P = np.concatenate([b for _, b, _ in pooled["vol"]])
        N = np.concatenate([c for _, _, c in pooled["vol"]])
        out["pooled"] = dict(n_dates=len(pooled["ic"]), vol_r2=float(1 - ((Y - P) ** 2).sum() / ((Y - Y.mean()) ** 2).sum()),
                             vol_r2_naive63=float(1 - ((Y - N) ** 2).sum() / ((Y - Y.mean()) ** 2).sum()),
                             mean_ic=float(np.mean(pooled["ic"])), cover50=float(np.mean(pooled["in50"])), cover90=float(np.mean(pooled["in90"])))
    (OUT / "scores.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    for row in rows:
        print(row if "status" in row else {k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items() if k != "portfolios"})
    if "pooled" in out:
        print("pooled:", {k: round(v, 3) if isinstance(v, float) else v for k, v in out["pooled"].items()})


if __name__ == "__main__":
    {"log": log, "score": score}[sys.argv[1]]()
