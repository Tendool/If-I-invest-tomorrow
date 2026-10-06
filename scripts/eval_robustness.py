"""Robustness of the portfolio results: longer history, realistic costs, sub-periods, bootstrap confidence intervals,
and the app's own plan backtest from many start dates.

    python scripts/eval_robustness.py walkforward   # monthly walk-forward Jan 2017 - 2026 (models refit each year on earlier data)
    python scripts/eval_robustness.py plans         # the app's five strategies chosen at every quarter-end, held 1 and 3 years

Costs (ifit/costs.py): STT, stamp duty, exchange and SEBI fees with GST, half bid-ask spread, per asset class; optional
fixed depository charge per security sold. 2017-20 were the validation years on which model choices were made, so they
are not a clean test; 2021-26 is. Sharpe = (CAGR - 6%) / volatility, as everywhere in the project.
"""
import json
import pickle
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ifit import config as C, costs as K, data, risk  # noqa: E402
from ifit.engine import UserProfile, backtest_weights  # noqa: E402

TD = C.TRADING_DAYS
RF = C.RISK_FREE
NIFTY = "NIFTYBEES.NS"
PERIODS = {"2017-18": ("2017", "2018"), "2019-20": ("2019", "2020"), "2021-22": ("2021", "2022"), "2023-24": ("2023", "2024"),
           "2025-26": ("2025", "2026"), "2017-20 (validation years)": ("2017", "2020"), "2021-26 (test years)": ("2021", "2026"),
           "2017-26 (all)": ("2017", "2026")}
CACHE = C.REPORTS_DIR / "_robust_targets.pkl"


def metrics(curve: pd.Series) -> dict:
    s = curve / curve.iloc[0]
    dr = s.pct_change().dropna()
    yrs = len(dr) / TD
    cagr = float(s.iloc[-1] ** (1 / yrs) - 1)
    vol = float(dr.std() * np.sqrt(TD))
    return dict(cagr=cagr, vol=vol, sharpe=(cagr - RF) / vol, max_drawdown=risk.max_drawdown(s.values), total_return=float(s.iloc[-1] - 1))


def simulate(tw: dict, rets: pd.DataFrame, days, buy, sell, mult=1.0, flat=None, capital=None, hold_only=False):
    """Daily value of a portfolio rebalanced to `tw[date]` on each rebalance date (weights drift in between).
    Costs: per-class rates x mult (or a flat rate), plus the fixed DP charge per security sold if `capital` (Rs) is given."""
    cols = rets.columns
    val, hold, out, turn, paid, first = 1.0, pd.Series(0.0, index=cols), [], 0.0, 0.0, True
    for d in days:
        if not first:                                         # the day's return accrues to the holdings carried into it
            hold = hold * (1 + rets.loc[d])
            val = float(hold.sum())
        if d in tw and (first or not hold_only):              # then trade at the day's close (weights use data up to it)
            tgt = tw[d]
            cur = hold / hold.sum() if hold.sum() > 0 else pd.Series(0.0, index=cols)
            trade = tgt - cur if not first else tgt.copy()
            fee = float(trade.abs().sum()) * flat if flat is not None else K.trade_cost(trade, buy, sell, mult)
            if capital is not None and not first:
                fee += K.DP_CHARGE_RS * int(((trade < -1e-4) & (cur > 1e-4)).sum()) / (capital * val)
            paid += fee * val
            turn += float(trade.abs().sum())
            val *= (1 - fee)
            hold = val * tgt
            first = False
        out.append(val)
    return pd.Series(out, index=days), turn / (len(days) / TD), paid


def block_bootstrap_idx(n, n_boot=2000, mean_block=21, seed=7):
    """Stationary bootstrap (Politis & Romano 1994) index sets: random blocks with geometric lengths."""
    rng = np.random.default_rng(seed)
    p = 1 / mean_block
    out = np.empty((n_boot, n), dtype=np.int64)
    for b in range(n_boot):
        i = rng.integers(n)
        for t in range(n):
            out[b, t] = i
            i = rng.integers(n) if rng.random() < p else (i + 1) % n
    return out


def boot_sharpe(dr: np.ndarray, idx: np.ndarray) -> np.ndarray:
    x = dr[idx]
    cagr = np.exp(np.log1p(x).sum(axis=1) * TD / x.shape[1]) - 1
    return (cagr - RF) / (x.std(axis=1) * np.sqrt(TD))


# ================================================================================ walk-forward 2017-26
def run_walkforward():
    from eval_portfolio import NAMES, compute_targets, month_ends
    md = data.load()
    idx = md.prices.index
    dates = month_ends(idx, "2017-01-01")[:-1]
    if CACHE.exists():
        target_w = pickle.load(open(CACHE, "rb"))
    else:
        target_w = compute_targets(md, dates)
        pickle.dump(target_w, open(CACHE, "wb"))
    cols = md.prices.columns
    rets = md.prices.pct_change().fillna(0.0)
    days = idx[idx >= dates[0]]
    buy, sell = K.rates(cols)
    nb = pd.Series(0.0, index=cols)
    nb[NIFTY] = 1.0
    stocks = [c for c in cols if C.UNIVERSE[c][2] == "stock"]
    eqw = pd.Series(0.0, index=cols)
    eqw[stocks] = 1 / len(stocks)
    strategies = {n: target_w[n] for n in NAMES}
    strategies["NIFTY 50 ETF (buy and hold)"] = {dates[0]: nb}
    strategies["Equal-weight stocks (monthly)"] = {t: eqw for t in dates}

    scen = {"flat 0.10% (previous assumption)": dict(flat=0.001), "realistic": dict(), "realistic x2 (stress)": dict(mult=2.0),
            "realistic x3 (stress)": dict(mult=3.0), "realistic + DP charges, Rs 10 lakh": dict(capital=1_000_000),
            "realistic + DP charges, Rs 1 lakh": dict(capital=100_000)}
    res, curves_real = {}, {}
    for sname, kw in scen.items():
        res[sname] = {}
        for n, tw in strategies.items():
            c, turn, paid = simulate(tw, rets, days, buy, sell, hold_only=n.startswith("NIFTY"), **kw)
            if sname == "realistic":
                curves_real[n] = c
            res[sname][n] = {p: metrics(c.loc[a:b]) for p, (a, b) in PERIODS.items()}
            res[sname][n]["turnover_ann"] = turn
            res[sname][n]["costs_pct_of_start"] = paid
        print("costs scenario done:", sname, flush=True)

    # bootstrap confidence intervals (realistic costs), test years and all years
    cis = {}
    for pname in ("2021-26 (test years)", "2017-26 (all)"):
        a, b = PERIODS[pname]
        dr = {n: c.loc[a:b].pct_change().dropna().values for n, c in curves_real.items()}
        n_obs = len(next(iter(dr.values())))
        bi = block_bootstrap_idx(n_obs)
        bs = {n: boot_sharpe(v, bi) for n, v in dr.items()}
        out = {}
        for n in NAMES + ["NIFTY 50 ETF (buy and hold)", "Equal-weight stocks (monthly)"]:
            out[n] = dict(lo=float(np.quantile(bs[n], 0.05)), hi=float(np.quantile(bs[n], 0.95)))
        pairs = {"volatility model, max-Sharpe (C+ - C)": ("C+ C + volatility model", "C  Max-Sharpe, prior returns"),
                 "volatility model, min-variance (B - A)": ("B  Min-variance + volatility model", "A  Min-variance, trailing covariance"),
                 "full system vs NIFTY ETF (E - NIFTY)": ("E  Full system (D + regime overlay)", "NIFTY 50 ETF (buy and hold)"),
                 "max-Sharpe + vol model vs NIFTY ETF (C+ - NIFTY)": ("C+ C + volatility model", "NIFTY 50 ETF (buy and hold)"),
                 "full system vs equal weight (E - EW)": ("E  Full system (D + regime overlay)", "Equal-weight stocks (monthly)")}
        for lab, (x, y) in pairs.items():
            d = bs[x] - bs[y]
            out["DIFF " + lab] = dict(point=float(metrics(curves_real[x].loc[a:b])["sharpe"] - metrics(curves_real[y].loc[a:b])["sharpe"]),
                                      lo=float(np.quantile(d, 0.05)), hi=float(np.quantile(d, 0.95)), share_above_0=float((d > 0).mean()))
        cis[pname] = out
        print("bootstrap done:", pname, flush=True)

    # print the key tables
    show = ["C  Max-Sharpe, prior returns", "C+ C + volatility model", "E  Full system (D + regime overlay)", "B  Min-variance + volatility model",
            "NIFTY 50 ETF (buy and hold)", "Equal-weight stocks (monthly)"]
    print("\nSharpe by period, realistic costs")
    print(pd.DataFrame({n: {p: res["realistic"][n][p]["sharpe"] for p in PERIODS} for n in show}).round(2).to_string())
    print("\nSharpe 2021-26 by cost scenario")
    print(pd.DataFrame({s: {n: res[s][n]["2021-26 (test years)"]["sharpe"] for n in show} for s in scen}).round(2).to_string())
    for pname, out in cis.items():
        print("\n90% bootstrap intervals,", pname)
        for k, v in out.items():
            print(f"  {k:60s} " + " ".join(f"{a}={b:+.2f}" for a, b in v.items()))
    json.dump(dict(start=str(dates[0].date()), end=str(idx[-1].date()), rebalances=len(dates), periods=PERIODS,
                   cost_rates={c: dict(zip(("buy", "sell"), K.per_side(c))) for c in ("stock", "etf", "gold", "bond", "cash")},
                   dp_charge_rs=K.DP_CHARGE_RS, results=res, bootstrap=cis),
              open(C.REPORTS_DIR / "eval_robustness_walkforward.json", "w"), indent=1)
    pd.DataFrame(curves_real).to_csv(C.REPORTS_DIR / "eval_robustness_curves.csv")


# ================================================================================ the app's plan backtest, many start dates
def run_plans():
    md = data.load()
    idx = md.prices.index
    cols = md.prices.columns
    rets = md.prices.pct_change().fillna(0.0)
    buy, sell = K.rates(cols)
    p = UserProfile(100_000, 3, "medium", 0.12, []).normalised()
    rows = []
    for q in pd.date_range("2017-03-31", "2025-09-30", freq="QE"):
        start = idx[idx.searchsorted(q, side="right") - 1]
        rm0, ws = backtest_weights(md, start, p)
        for horizon in (1, 3):
            end_pos = idx.searchsorted(start) + horizon * TD
            if end_pos >= len(idx):
                continue
            days = idx[idx.searchsorted(start): end_pos + 1]                  # buy at the start date's close
            reb = {d: None for d in days[::63]}                                   # quarterly rebalance, as in the app's backtest
            cur = {}
            for name, w in ws.items():
                tw = {d: w.reindex(cols).fillna(0.0) for d in reb}
                g, _, _ = simulate(tw, rets, days, buy, sell, flat=0.0)
                n_, _, _ = simulate(tw, rets, days, buy, sell)
                cur[name] = (g, n_)
            nbw = pd.Series(0.0, index=cols)
            nbw[NIFTY] = 1.0
            ng, _, _ = simulate({days[0]: nbw}, rets, days, buy, sell, flat=0.0, hold_only=True)
            nn, _, _ = simulate({days[0]: nbw}, rets, days, buy, sell, hold_only=True)
            nifty_net = float(nn.iloc[-1] - 1)
            for name, (g, n_) in cur.items():
                m = metrics(n_)
                rows.append(dict(start=str(start.date()), horizon=horizon, strategy=name, gross=float(g.iloc[-1] - 1), net=float(n_.iloc[-1] - 1),
                                 net_sharpe=m["sharpe"], max_drawdown=m["max_drawdown"], nifty_net=nifty_net, beat_nifty=bool(n_.iloc[-1] - 1 > nifty_net)))
        print("plans from", start.date(), flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(C.REPORTS_DIR / "eval_robustness_plans.csv", index=False)
    summ = {}
    for (h, s), g in df.groupby(["horizon", "strategy"]):
        ann = (1 + g["net"]) ** (1 / h) - 1
        nifty_ann = (1 + g["nifty_net"]) ** (1 / h) - 1
        summ[f"{h}y {s}"] = dict(starts=int(len(g)), median_net=float(g["net"].median()), median_ann=float(ann.median()),
                                 worst_net=float(g["net"].min()), best_net=float(g["net"].max()), share_positive=float((g["net"] > 0).mean()),
                                 share_beat_nifty=float(g["beat_nifty"].mean()), median_excess_ann=float((ann - nifty_ann).median()),
                                 median_sharpe=float(g["net_sharpe"].median()), median_cost=float((g["gross"] - g["net"]).median()),
                                 first=str(g["start"].min()), last=str(g["start"].max()))
    for h in (1, 3):
        g = df[(df.horizon == h)].drop_duplicates("start")
        nifty_ann = (1 + g["nifty_net"]) ** (1 / h) - 1
        summ[f"{h}y NIFTY 50 ETF"] = dict(starts=int(len(g)), median_net=float(g["nifty_net"].median()), median_ann=float(nifty_ann.median()),
                                          worst_net=float(g["nifty_net"].min()), best_net=float(g["nifty_net"].max()),
                                          share_positive=float((g["nifty_net"] > 0).mean()))
    print(pd.DataFrame(summ).T.round(3).to_string())
    json.dump(dict(profile="Rs 1 lakh, medium risk, 12% target", rebalance="quarterly", costs="realistic (ifit/costs.py)", summary=summ),
              open(C.REPORTS_DIR / "eval_robustness_plans.json", "w"), indent=1)


if __name__ == "__main__":
    {"walkforward": run_walkforward, "plans": run_plans}[sys.argv[1]]()
