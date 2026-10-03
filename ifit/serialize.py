"""Convert engine / tool artifacts into plain JSON for the Next.js front end."""
from __future__ import annotations

import json
import math
from pathlib import Path
from datetime import date, datetime

import numpy as np
import pandas as pd

from . import config as C
from . import data as D
from .engine import STRATEGY_BLURB


def clean(o):
    """Recursively make an object JSON-safe (numpy -> python, NaN/inf -> None, Timestamps -> str)."""
    if o is None or isinstance(o, (str, bool)):
        return o
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (int, np.integer)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(o, (pd.Timestamp, datetime, date)):
        return str(o)[:10]
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return [clean(v) for v in o.tolist()]
    if isinstance(o, pd.Series):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, pd.DataFrame):
        return [clean(r) for r in o.to_dict("records")]
    return str(o)


def profile(p) -> dict:
    p = p.normalised()
    return dict(amount=p.amount, horizon_years=p.horizon_years, risk=p.risk,
                target_return_pct=round(p.target_return * 100, 2), preferred_sectors=p.preferred_sectors)


def plan_rows(plan: pd.DataFrame) -> list[dict]:
    return [dict(symbol=r.symbol, ticker=r.ticker, name=r.name, sector=r.sector, asset_class=r.asset_class,
                 weight=r.weight, target_amount=r.target_amount, price=r.price, shares=int(r.shares),
                 invested=r.invested) for r in plan.itertuples()]


def weights(w: pd.Series) -> list[dict]:
    w = w[w > 0].sort_values(ascending=False)
    return [dict(symbol=s, ticker=D.short(s), name=C.UNIVERSE[s][0], sector=C.UNIVERSE[s][1],
                 asset_class=C.UNIVERSE[s][2], weight=float(x)) for s, x in w.items()]


def mc(m, full: bool = True) -> dict:
    out = dict(years=m.years, amount=m.amount, target=m.target, n_paths=m.n_paths, stats=m.stats,
               fan=m.fan.round(2).to_dict("records"))
    if full:
        centers = (m.hist_edges[:-1] + m.hist_edges[1:]) / 2
        out["hist"] = [dict(x=float(c), pct=float(n) / m.n_paths * 100) for c, n in zip(centers, m.hist_counts)]
        out["paths"] = [[round(float(v), 2) for v in row] for row in m.sample_paths[:14]]
        out["grid_years"] = [round(float(y), 3) for y in m.grid_years]
        out["hist_edges"] = [float(e) for e in m.hist_edges]
    return out


def stress(df: pd.DataFrame) -> list[dict]:
    return [dict(scenario=r.scenario, portfolio_return=r.portfolio_return, pnl=r.pnl, survives=bool(r.survives),
                 top_hits=r.top_hits) for r in df.itertuples()]


def evaluation(e, recommended: str | None = None, full_mc: bool = False) -> dict:
    return dict(strategy=e.strategy, blurb=STRATEGY_BLURB[e.strategy], recommended=(e.strategy == recommended),
                weights=weights(e.weights), stats=e.stats, mc=mc(e.mc, full_mc), stress=stress(e.stress),
                breaches=e.breaches, within_limits=e.within_tolerance, n_holdings=int((e.weights > 0).sum()))


def valuation(v: dict) -> dict:
    pos = v["positions"]
    rows = []
    if len(pos):
        rows = [dict(symbol=r.symbol, ticker=D.short(r.symbol), name=r.name, sector=r.sector, qty=int(r.qty),
                     avg_cost=r.avg_cost, price=r.price, value=r.value, cost=r.cost, pnl=r.pnl, pnl_pct=r.pnl_pct)
                for r in pos.itertuples()]
    return dict(cash=v["cash"], invested_value=v["invested_value"], total_value=v["total_value"],
                starting_cash=v["starting_cash"], pnl=v["pnl"], pnl_pct=v["pnl_pct"], positions=rows)


def pending(p: dict | None) -> dict | None:
    if not p:
        return None
    return dict(created=p["created"], label=p["label"], buy_cost=p["buy_cost"], sell_proceeds=p["sell_proceeds"],
                orders=[dict(side=o["side"], symbol=o["symbol"], ticker=D.short(o["symbol"]), name=C.UNIVERSE[o["symbol"]][0],
                             qty=o["qty"], price=o["price"], value=o["qty"] * o["price"]) for o in p["orders"]])


def trades(df: pd.DataFrame) -> list[dict]:
    if not len(df):
        return []
    return [dict(id=int(r.id), ts=r.ts, symbol=r.symbol, ticker=D.short(r.symbol), name=C.UNIVERSE[r.symbol][0],
                 side=r.side, qty=int(r.qty), price=r.price, fee=r.fee, note=r.note) for r in df.itertuples()]


def backtest(bt: dict, step: int = 3) -> dict:
    cv = bt["curves"].iloc[::step]
    rows = []
    for idx, r in cv.iterrows():
        d = {"date": str(idx)[:10]}
        d.update({k: float(v) for k, v in r.items()})
        rows.append(d)
    return dict(start=bt["start"], end=bt["end"], years=bt["years"], series=list(bt["curves"].columns),
                curves=rows, table=bt["table"].to_dict("records"))


def metrics_table(t: pd.DataFrame) -> list[dict]:
    out = []
    for name, r in t.iterrows():
        out.append(dict(model=name, **{k: (None if pd.isna(v) else float(v)) for k, v in r.items()}))
    return out


# ------------------------------------------------------------------ artifacts
def model_extras(est) -> dict:
    """Fields the Models view needs beyond the walk-forward table: selected model, skill weight, the measured volatility
    model accuracy and the stored model-search results (same payload for /api/models and the chat artifact)."""
    search_p = C.REPORTS_DIR / "model_search.json"
    if not search_p.exists():                       # fresh container: use the copy shipped with the package
        search_p = Path(__file__).parent / "assets" / "model_search.json"
    vol_p = C.MODELS_DIR / "vol_model_meta.json"
    return dict(selected=est.model_name, skill_weight=est.skill_weight,
                search=json.loads(search_p.read_text(encoding="utf-8")) if search_p.exists() else None,
                volatility=json.loads(vol_p.read_text(encoding="utf-8")) if vol_p.exists() else None)


def artifact(a: dict, session) -> dict:
    """Serialise a ``Session.emit`` artifact for the UI."""
    kind, pl = a["kind"], a["payload"]
    if kind == "plan":
        e = pl["evaluation"]
        data = dict(strategy=e.strategy, recommended=pl["recommended"], profile=profile(pl["profile"]),
                    plan=plan_rows(pl["plan"]), cash_left=pl["plan"].attrs.get("cash_left", 0.0),
                    evaluation=evaluation(e, pl["recommended"], full_mc=False),
                    data_as_of=str(session.engine.md.last_date.date()))
    elif kind == "strategies":
        data = dict(recommended=pl["recommended"], why=pl["why"], profile=profile(pl["profile"]),
                    strategies=[evaluation(e, pl["recommended"]) for e in pl["board"].values()])
    elif kind == "montecarlo":
        data = dict(strategy=pl["strategy"], profile=profile(pl["profile"]), mc=mc(pl["mc"]),
                    regime=session.engine.regime.current_name)
    elif kind == "stress":
        data = dict(strategy=pl["strategy"], profile=profile(pl["profile"]), stress=stress(pl["stress"]),
                    shock_mc=pl["shock_mc"].to_dict("records"),
                    loss_limit=C.RISK_PROFILES[pl["profile"].risk]["max_stress_loss"])
    elif kind == "timing":
        data = dict(strategy=pl["strategy"], profile=profile(pl["profile"]), table=pl["table"].to_dict("records"),
                    regime=session.engine.regime.current_name)
    elif kind == "backtest":
        data = backtest(pl)
    elif kind == "market":
        data = pl
    elif kind == "models":
        data = dict(metrics=metrics_table(pl["metrics"]), **model_extras(session.engine.estimator),
                    regimes=[dict(regime=i, **r.to_dict()) for i, r in pl["regimes"].iterrows()],
                    importance=([dict(feature=k, value=float(v)) for k, v in pl["importance"].head(12).items()]
                                if pl["importance"] is not None else []))
    elif kind == "asset":
        data = asset_detail(session, pl)
    elif kind == "wallet":
        data = dict(valuation=valuation(pl["valuation"]), equity=pl["equity"].to_dict("records") if len(pl["equity"]) else [],
                    pending=pending(pl["pending"]))
    elif kind == "trades":
        data = dict(trades=trades(pl))
    elif kind in ("orders", "health"):
        data = pl
    else:
        data = pl
    return dict(kind=kind, title=a["title"], data=clean(data))


def asset_detail(session, rep: dict) -> dict:
    md = session.engine.md
    sym = rep["symbol"]
    px = md.prices[sym].dropna()
    mk = md.market.reindex(px.index).ffill()
    w = pd.DataFrame({"asset": px / px.iloc[-756:].iloc[0] * 100, "nifty": mk / mk.loc[px.iloc[-756:].index[0]] * 100}).iloc[-756:].iloc[::3]
    rep = dict(rep)
    rep["series"] = [dict(date=str(i)[:10], asset=float(r.asset), nifty=float(r.nifty)) for i, r in w.iterrows()]
    return rep
