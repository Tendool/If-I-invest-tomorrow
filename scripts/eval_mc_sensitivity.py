"""How much do the Monte Carlo's answers depend on its assumptions?

    python scripts/eval_mc_sensitivity.py

For the sample investor (Rs 1 lakh, 3 years, medium risk, 12% target) the five strategies keep the weights the app chose; only the
simulation assumption changes. For each assumption: the recommended plan's P(reach target), 5% worst case, median outcome and expected
maximum drawdown, and which strategy the app's own rule (best P(target) inside the risk limits, ties within 2 points -> higher Sharpe)
would then recommend. The spread of P(target) across the plausible alternatives is an assumption-sensitivity range, not a statistical
confidence interval. 10,000 paths make the simulation's own sampling error about +-1 point; they do nothing about wrong assumptions,
which is what this table measures.
"""
import copy
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ifit import config as C, montecarlo as MC, risk  # noqa: E402
from ifit.engine import Engine, UserProfile  # noqa: E402

N = 10_000
SEED = 123


def crisis_cov(rm):
    """Correlations between equity assets (stocks and equity ETFs) moved halfway to 1; gold, bonds and cash unchanged."""
    corr = rm.corr.copy()
    eq = [s for s in corr.index if C.UNIVERSE[s][2] in ("stock", "etf")]
    sub = corr.loc[eq, eq]
    corr.loc[eq, eq] = sub + 0.5 * (1 - sub)
    d = np.sqrt(np.diag(rm.cov.values))
    return pd.DataFrame(corr.values * np.outer(d, d), index=rm.cov.index, columns=rm.cov.columns)


def persistent(regime, k=0.5):
    """Regimes last about twice as long: daily transition matrix moved halfway to the identity."""
    r = copy.copy(regime)
    T = (1 - k) * regime.transition + k * np.eye(regime.transition.shape[0])
    r.transition = T / T.sum(axis=1, keepdims=True)
    return r


def bear_start(regime):
    r = copy.copy(regime)
    p = np.zeros_like(regime.current_probs)
    p[-1] = 1.0
    r.current_probs = p
    return r


def bootstrap_paths(e, w, mu_p, years, block=21):
    """Block bootstrap of the plan's own 5-year daily history, recentred on its expected return (no regime model)."""
    h = (e.rm.rets[e.rm.symbols] * w.reindex(e.rm.symbols).fillna(0.0).values).sum(axis=1).values
    h = h - h.mean() + ((1 + mu_p) ** (1 / C.TRADING_DAYS) - 1)
    rng = np.random.default_rng(SEED)
    steps = int(round(years * C.TRADING_DAYS))
    nb = int(np.ceil(steps / block))
    starts = rng.integers(0, len(h) - block, size=(N, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(N, -1)[:, :steps]
    v = np.cumprod(1 + h[idx], axis=1)
    return np.hstack([np.ones((N, 1)), v]).astype(np.float32)


def main():
    e = Engine()
    p = UserProfile(100_000, 3, "medium", 0.12, []).normalised()
    board = e.run_all(p)
    rec0, _ = e.recommend(board, p)
    prof = C.RISK_PROFILES[p.risk]
    mt = e.mu_table
    alts_mu = {"prior (CAPM + history), no return signal": mt["prior"], "CAPM only": mt["capm"], "history only": mt["hist"],
               "production minus 2% a year": mt["expected"] - 0.02}
    cov_crisis = crisis_cov(e.rm)
    vu0 = C.MC_VOL_UNCERTAINTY

    def run(name, w, mu=None, cov=None, regime=e.regime, dof=C.MC_T_DOF, vol_unc=vu0, boot=False):
        mu = e.mu if mu is None else mu
        cov = e.rm.cov if cov is None else cov
        st = risk.portfolio_stats(w, mu, cov, e.rm.beta)
        C.MC_VOL_UNCERTAINTY = vol_unc
        if boot:
            v = bootstrap_paths(e, w, st["exp_return"], p.horizon_years)
        else:
            v = MC.simulate_paths(st["exp_return"], st["volatility"], st["beta"], regime, p.horizon_years, N, 252, 0.0, SEED, dof)
        C.MC_VOL_UNCERTAINTY = vu0
        s = MC.summarise(v, p.horizon_years, p.amount, p.target_return).stats
        ok = st["volatility"] <= prof["max_annual_vol"] + 1e-9 and not any("stress" in b for b in board[name].breaches) and s["var95_1y"] <= prof["max_var95_1y"]
        return dict(ptgt=s["prob_target"], p5=s["worst_case_p5"], med=s["median_final"], mdd=s["exp_max_drawdown"], ppos=s["prob_positive"],
                    sharpe=st["sharpe"], ok=bool(ok))

    scenarios = {
        "Production (Student-t dof 5, regime switching, parameter + volatility uncertainty)": {},
        "Tails: normal shocks": dict(dof=200),
        "Tails: fatter (Student-t dof 3)": dict(dof=3),
        "Tails: block bootstrap of the plan's own history": dict(boot=True),
        "Correlations: equity correlations halfway to 1 (crisis)": dict(cov=cov_crisis),
        "Regimes: no regime switching": dict(regime=None),
        "Regimes: twice as persistent": dict(regime=persistent(e.regime)),
        "Volatility uncertainty: none": dict(vol_unc=0.0),
        "Volatility uncertainty: 0.5": dict(vol_unc=0.5),
        **{f"Expected return: {k}": dict(mu=v) for k, v in alts_mu.items()},
        "Stress (not an assumption): start in the bear regime": dict(regime=bear_start(e.regime)),
    }
    rows = {}
    for sname, kw in scenarios.items():
        res = {n: run(n, ev.weights, **kw) for n, ev in board.items()}
        ok = {n: r for n, r in res.items() if r["ok"]}
        if ok:
            top = max(r["ptgt"] for r in ok.values())
            near = {n: r for n, r in ok.items() if r["ptgt"] >= top - 0.02}
            pick = max(near, key=lambda n: near[n]["sharpe"])
        else:
            pick = min(res, key=lambda n: board[n].stats["volatility"])
        rows[sname] = dict(recommended=pick, plan=rec0, **{k: res[rec0][k] for k in ("ptgt", "p5", "med", "mdd", "ppos")},
                           all={n: dict(ptgt=r["ptgt"], ok=r["ok"]) for n, r in res.items()})
        r = rows[sname]
        print(f"{sname:82s} {rec0}: P(target) {r['ptgt']:.0%}  5% worst Rs {r['p5']:,.0f}  median Rs {r['med']:,.0f}  exp. max DD {r['mdd']:.1%}"
              f"  -> rule picks {pick}", flush=True)
    plausible = {k: v for k, v in rows.items() if not k.startswith("Stress")}
    rng_ = {m: (min(v[m] for v in plausible.values()), max(v[m] for v in plausible.values())) for m in ("ptgt", "p5", "med", "mdd")}
    changes = sorted({v["recommended"] for v in plausible.values()})
    print("\nassumption-sensitivity range (plausible alternatives):", {k: (round(a, 3), round(b, 3)) for k, (a, b) in rng_.items()})
    print("strategies the rule would recommend:", changes)
    out = dict(profile="Rs 1 lakh, 3 years, medium risk, 12% target", plan=rec0, n_paths=N, scenarios=rows, sensitivity_range=rng_,
               recommendations=changes, mc_sampling_se_ptgt=float(np.sqrt(rows[next(iter(rows))]["ptgt"] * (1 - rows[next(iter(rows))]["ptgt"]) / N)))
    (C.REPORTS_DIR / "eval_mc_sensitivity.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
