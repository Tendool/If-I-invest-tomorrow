"""Does the model stack create economic value? Walk-forward portfolio backtest with costs.

    python scripts/eval_portfolio.py

Every month-end from Jan-2021, using only data up to that date:
  * risk model (5y Ledoit-Wolf covariance, CAPM, history prior)           -> built from truncated data
  * volatility model (Ridge, retrained each year on pre-year data)        -> rescales each asset's volatility in the covariance
  * return tilt (residual reversal + momentum + sector-relative reversal, production; nothing fitted) -> prior + lambda x tilt
  * regime (Gaussian mixture refit each year on pre-year data)             -> cuts risky exposure in non-calm regimes
Weights are optimised long-only with the 'medium' risk-profile caps, held with daily drift, and traded at the rebalance date's close
with realistic NSE costs per asset class (ifit/costs.py: STT, stamp duty, exchange fees + GST, half spread; stocks ~0.16% a side).

Two families are compared like-for-like:  minimum variance  (A -> B -> B+regime)  and  maximum Sharpe  (C -> C+vol -> D -> E).
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
from sklearn.linear_model import Ridge  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from ifit import config as C, costs as K, data, features as F, ml, optimizer as O, risk  # noqa: E402
from eval_risk import PITRegime  # noqa: E402

START = "2021-01-01"
TD = C.TRADING_DAYS
LAMBDA = json.load(open(C.MODELS_DIR / "return_model_meta.json"))["skill_weight"]   # production skill weight
PURGE = pd.Timedelta(days=int(F.FWD_DAYS * 1.5))
RISK_PROFILE = "medium"
LIQUID = "LIQUIDBEES.NS"


def trunc(md, t):
    return dataclasses.replace(md, prices=md.prices.loc[:t], volume=md.volume.loc[:t], market=md.market.loc[:t], macro=md.macro.loc[:t])


def month_ends(idx, start=START):
    s = pd.Series(idx, index=idx)
    s = s[s.index >= start]
    return list(s.groupby([s.index.year, s.index.month]).last())


def pit_predictions(md, dates):
    """Per rebalance date: (relative-return forecast per asset, volatility forecast per asset, regime probs) using models
    trained only on data before that calendar year."""
    risky_cols = [c for c in md.prices.columns if C.UNIVERSE[c][2] != "cash"]
    sub = dataclasses.replace(md, prices=md.prices[risky_cols], volume=md.volume[risky_cols])
    rpanel = ml.relative_panel(md)
    fx = ml.residual_factors(md)
    vpanel = ml.vol_panel(sub)
    vfeats = ml.vol_features(vpanel)
    rd, vd = rpanel.index.get_level_values(0), vpanel.index.get_level_values(0)
    ret_fc, vol_fc, reg = {}, {}, {}
    for yr in sorted({d.year for d in dates}):
        a = pd.Timestamp(f"{yr}-01-01")
        cs_sd = float(rpanel[rd < a - PURGE]["target"].dropna().std())      # scale of the refined forecast, pre-year data only
        tv = vpanel[vd < a - PURGE].dropna(subset=vfeats + ["y"]).iloc[::ml.VOL_TRAIN_STEP]
        mv = make_pipeline(StandardScaler(), Ridge(alpha=ml.VOL_ALPHA)).fit(tv[vfeats].values, tv["y"].values)
        pr = PITRegime(trunc(md, a - pd.Timedelta(days=1))).probs(md)
        for t in [d for d in dates if d.year == yr]:
            ret_fc[t] = ml.factor_forecast(fx.loc[[t]], cs_sd).droplevel(0)
            z = vpanel.xs(t, level=0)[vfeats]
            z = z.fillna(z.median())
            vol_fc[t] = pd.Series(np.exp(ml._blend(mv.predict(z.values), z["rv_63"].values)), index=z.index)
            reg[t] = pr.loc[t].values if t in pr.index else np.array([1.0, 0.0, 0.0])
        print("models trained for", yr, flush=True)
    return ret_fc, vol_fc, reg


def scaled_cov(rm, vol_fc_t):
    vh = np.sqrt(np.diag(rm.cov.values))
    target = pd.Series(vh, index=rm.symbols)
    f = vol_fc_t.reindex(rm.symbols)
    target = target.where(f.isna(), f.clip(lower=0.5 * target, upper=2.0 * target))      # forecast, bounded to 0.5x-2x of history
    d = (target.values / vh)
    return pd.DataFrame(rm.cov.values * np.outer(d, d), index=rm.symbols, columns=rm.symbols)


def regime_overlay(w, probs):
    """Move risky exposure into the liquid fund as the regime gets less calm: -25% in Neutral, -50% in Bear (a-priori, not tuned)."""
    cut = 0.25 * probs[1] + 0.50 * probs[2]
    out = w * (1 - cut)
    out[LIQUID] = out.get(LIQUID, 0.0) + (w.sum() - out.sum())
    return out


NAMES = ["A  Min-variance, trailing covariance", "B  Min-variance + volatility model", "B+ B + regime overlay",
             "C  Max-Sharpe, prior returns", "C+ C + volatility model", "D  C+ + return tilt", "E  Full system (D + regime overlay)"]


def compute_targets(md, dates):
    """Target weights of the seven strategies at each rebalance date, from data up to that date only."""
    ret_fc, vol_fc, reg = pit_predictions(md, dates)
    names = NAMES
    target_w = {n: {} for n in names}
    for t in dates:
        md_t = trunc(md, t)
        rm = risk.build_risk_model(md_t)
        syms = rm.symbols
        prior = ml.expected_returns(rm, None)["expected"]
        f = ret_fc[t].reindex(syms).fillna(0.0).clip(-0.12, 0.12)
        tilt = ((f - f.mean()) * (TD / F.FWD_DAYS)).clip(-0.15, 0.15)
        tilt[[s for s in syms if C.UNIVERSE[s][2] == "cash"]] = 0.0
        mu_tilt = prior + LAMBDA * tilt
        cov0 = rm.cov
        cov1 = scaled_cov(rm, vol_fc[t])
        b = O.build_bounds(syms, RISK_PROFILE)
        w = {}
        w[names[0]] = O.min_variance(prior, cov0, b)
        w[names[1]] = O.min_variance(prior, cov1, b)
        w[names[2]] = regime_overlay(w[names[1]], reg[t])
        w[names[3]] = O.max_sharpe(prior, cov0, b)
        w[names[4]] = O.max_sharpe(prior, cov1, b)
        w[names[5]] = O.max_sharpe(mu_tilt, cov1, b)
        w[names[6]] = regime_overlay(w[names[5]], reg[t])
        for n in names:
            target_w[n][t] = w[n].reindex(md.prices.columns).fillna(0.0)
        print("rebalance", t.date(), flush=True)
    return target_w


def run():
    md = data.load()
    idx = md.prices.index
    dates = month_ends(idx)[:-1]
    target_w = compute_targets(md, dates)
    names = NAMES
    rets = md.prices.pct_change().fillna(0.0)

    # ---- simulate with drift and costs
    day_idx = idx[(idx >= dates[0]) & (idx <= idx[-1])]
    curves, turnover, costs = {}, {}, {}
    cols = md.prices.columns
    HALF = " (half-step rebalancing)"
    sim_names = names + [names[1] + HALF, names[6] + HALF, "NIFTY 50 ETF (benchmark)", "Equal-weight stocks (monthly)"]
    stock_cols = [c for c in cols if C.UNIVERSE[c][2] == "stock"]
    buy, sell = K.rates(cols)
    eqw = pd.Series(0.0, index=cols)
    eqw[stock_cols] = 1 / len(stock_cols)
    nb = pd.Series(0.0, index=cols)
    nb["NIFTYBEES.NS"] = 1.0
    for n in sim_names:
        half = n.endswith(HALF)
        tw = target_w.get(n.replace(HALF, ""))
        if tw is None:
            tw = {t: (nb if n.startswith("NIFTY") else eqw) for t in dates}
        val, hold, out, turn, cost_paid = 1.0, pd.Series(0.0, index=cols), [], 0.0, 0.0
        first = True
        for d in day_idx:
            if not first:                                    # the day's return accrues to the holdings carried into it
                hold = hold * (1 + rets.loc[d])
                val = hold.sum()
            if d in tw:                                      # then rebalance at the close (weights use data up to that close)
                tgt = tw[d]
                cur_w = hold / hold.sum() if hold.sum() > 0 else pd.Series(0.0, index=cols)
                if half and not first:                       # trade only halfway to the new target (a-priori rule, halves turnover)
                    tgt = 0.5 * cur_w + 0.5 * tgt
                tv = (tgt - cur_w) if not first else tgt
                if n.startswith("NIFTY") and not first:
                    tv = tv * 0.0
                trade = float(tv.abs().sum())
                fee = val * K.trade_cost(tv, buy, sell)
                val -= fee
                cost_paid += fee
                turn += trade
                hold = val * tgt
                first = False
            out.append(val)
        curves[n] = pd.Series(out, index=day_idx)
        turnover[n] = turn / (len(day_idx) / TD)                      # annualised one-way turnover (multiples of the portfolio)
        costs[n] = cost_paid
    cdf = pd.DataFrame(curves)
    cdf = cdf[cdf.index >= dates[0]]
    bench = cdf["NIFTY 50 ETF (benchmark)"].pct_change().dropna()

    rows = {}
    for n in sim_names:
        s = cdf[n]
        dr = s.pct_change().dropna()
        yrs = len(dr) / TD
        cagr = float(s.iloc[-1] ** (1 / yrs) - 1)
        vol = float(dr.std() * np.sqrt(TD))
        dd = float((dr[dr < 0] ** 2).mean() ** 0.5 * np.sqrt(TD))
        mdd = risk.max_drawdown(s.values)
        monthly = s.resample("ME").last().pct_change().dropna()
        active = (dr - bench.reindex(dr.index)).dropna()
        rows[n] = dict(cagr=cagr, vol=vol, sharpe=(cagr - C.RISK_FREE) / vol, sortino=(cagr - C.RISK_FREE) / dd, max_drawdown=mdd, calmar=cagr / abs(mdd),
                       downside_dev=dd, var95_1d=float(-np.quantile(dr, 0.05)), cvar95_1d=float(-dr[dr <= np.quantile(dr, 0.05)].mean()),
                       hit_rate_monthly=float((monthly > 0).mean()), turnover_ann=turnover[n], costs_pct_of_start=costs[n],
                       vs_benchmark_cagr=cagr - float(cdf["NIFTY 50 ETF (benchmark)"].iloc[-1] ** (1 / yrs) - 1),
                       info_ratio=float(active.mean() * TD / (active.std() * np.sqrt(TD))) if active.std() > 0 else None,
                       total_return=float(s.iloc[-1] - 1))
    tab = pd.DataFrame(rows).T
    pd.set_option("display.width", 250)
    print(f"\nwalk-forward {dates[0].date()} -> {idx[-1].date()}, {len(dates)} monthly rebalances, realistic costs per asset class\n")
    print(tab[["cagr", "vol", "sharpe", "sortino", "max_drawdown", "calmar", "turnover_ann", "vs_benchmark_cagr", "info_ratio"]].round(3).to_string())
    print(tab[["downside_dev", "var95_1d", "cvar95_1d", "hit_rate_monthly", "costs_pct_of_start", "total_return"]].round(4).to_string())
    json.dump(dict(start=str(dates[0].date()), end=str(idx[-1].date()), rebalances=len(dates), costs="realistic per asset class (ifit/costs.py)",
                   cost_rates={c: dict(zip(("buy", "sell"), K.per_side(c))) for c in ("stock", "etf", "gold", "bond", "cash")}, table=rows),
              open(C.REPORTS_DIR / "eval_portfolio.json", "w"), indent=1)
    cdf.to_csv(C.REPORTS_DIR / "eval_portfolio_curves.csv")


if __name__ == "__main__":
    run()
