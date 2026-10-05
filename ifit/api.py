"""FastAPI backend for the Next.js front end.

    uvicorn ifit.api:app --port 8000
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

warnings.filterwarnings("ignore")

from . import config as C           # noqa: E402
from . import data as D             # noqa: E402
from . import serialize as Z        # noqa: E402
from . import simulator             # noqa: E402
from . import trading               # noqa: E402
from .agent import Agent            # noqa: E402
from .engine import STRATEGIES, UserProfile  # noqa: E402
from .session import Session        # noqa: E402
from .sip import sip_rows            # noqa: E402
from .tools import call_tool        # noqa: E402

app = FastAPI(title="If I Invest Tomorrow API", version="1.0")
ORIGINS = [o.strip() for o in os.environ.get("IFIT_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])

LOCK = threading.Lock()
_state: dict = {}


def S() -> Session:
    if "s" not in _state:
        _state["s"] = Session.create()
        _state["agent"] = Agent(_state["s"])
    return _state["s"]


def AG() -> Agent:
    S()
    return _state["agent"]


def strat(name: str | None) -> str:
    s = S()
    s.ensure_board()
    if not name or name.lower() in ("recommended", "default"):
        return s.selected_strategy or s.recommended
    for n in STRATEGIES:
        if n.lower().replace(" ", "-") == name.lower() or n.lower() == name.lower():
            return n
    raise HTTPException(404, f"unknown strategy {name}")


def wallet_state(s: Session) -> dict:
    md = s.engine.md
    v = s.wallet.valuation(md.last_prices(), asof=str(md.last_date.date()))
    return dict(valuation=Z.valuation(v), equity=s.wallet.equity_curve().to_dict("records"),
                pending=Z.pending(s.wallet.pending()), trades=Z.trades(s.wallet.trades(100)),
                sips=sip_rows(s),
                autonomy=s.autonomy, autopilot=s.autopilot)


def tape(s: Session) -> list[dict]:
    """Scrolling-tape items: indices / macro first, then every investable asset with its 1-day change."""
    md = s.engine.md
    out = []

    def add(label, series, kind, fmt="num"):
        x = series.dropna()
        if len(x) >= 2:
            out.append(dict(label=label, value=float(x.iloc[-1]), change=float(x.iloc[-1] / x.iloc[-2] - 1), kind=kind, fmt=fmt))

    add("NIFTY 50", md.market, "index")
    if "banknifty" in md.macro:
        add("BANK NIFTY", md.macro["banknifty"], "index")
    add("INDIA VIX", md.macro["vix"], "macro")
    add("USD/INR", md.macro["usdinr"], "macro")
    add("BRENT", md.macro["brent"], "macro", "usd")
    for sym in md.prices.columns:
        if C.UNIVERSE[sym][2] == "cash":      # the liquid fund is a flat accrual series; not interesting on a tape
            continue
        add(D.short(sym), md.prices[sym], C.UNIVERSE[sym][2])
    return out


def state(s: Session) -> dict:
    md = s.engine.md
    v = s.wallet.valuation(md.last_prices(), asof=str(md.last_date.date()), record=False)
    m, mac = md.market.dropna(), md.macro
    ticker = dict(nifty=m.iloc[-1], nifty_1d=m.iloc[-1] / m.iloc[-2] - 1, vix=mac["vix"].iloc[-1],
                  usdinr=mac["usdinr"].iloc[-1], brent=mac["brent"].iloc[-1],
                  banknifty=mac["banknifty"].iloc[-1] if "banknifty" in mac else None)
    return Z.clean(dict(
        as_of=str(md.last_date.date()), profile=Z.profile(s.profile), profile_set=s.profile_confirmed, ticker=ticker, tape=tape(s),
        autonomy=s.autonomy, autopilot=s.autopilot, strategies=STRATEGIES,
        regime=s.engine.regime.current_name, llm=C.LLM_MODEL,
        sectors=C.SECTORS + ["Gold", "Bonds"], recommended=s.recommended,
        wallet=dict(cash=v["cash"], total_value=v["total_value"], pnl=v["pnl"], pnl_pct=v["pnl_pct"],
                    starting_cash=v["starting_cash"], pending=s.wallet.pending() is not None)))


def run_tool(name: str, args: dict | None = None, force: bool = True) -> dict:
    """Run an agent tool on behalf of a UI button (a click is an explicit instruction)."""
    s = S()
    s.force_action = force
    try:
        res = call_tool(s, name, args or {})
    finally:
        s.force_action = False
    arts = [Z.artifact(a, s) for a in s.take_artifacts()]
    return Z.clean(dict(result=res, artifacts=arts, wallet=wallet_state(s), state=state(s)))


# ------------------------------------------------------------------ general
@app.get("/api/health")
def health():
    ok = True
    try:
        import ollama
        names = [m.model for m in ollama.Client(host=C.OLLAMA_HOST).list().models]
        ok = any(n.startswith(C.LLM_MODEL.split(":")[0]) for n in names)
    except Exception:
        ok = False
    return dict(status="ok", llm=C.LLM_MODEL, llm_available=ok)


@app.get("/api/state")
def get_state():
    with LOCK:
        return state(S())


@app.post("/api/profile")
def set_profile(body: dict = Body(...)):
    with LOCK:
        s = S()
        try:
            s.set_profile(**{k: v for k, v in dict(
                amount=body.get("amount"), horizon_years=body.get("horizon_years"), risk=body.get("risk"),
                target_return=(body["target_return_pct"] / 100 if body.get("target_return_pct") is not None else None),
                preferred_sectors=body.get("preferred_sectors")).items() if v is not None})
        except ValueError as e:
            raise HTTPException(400, str(e))
        s.ensure_board()
        return state(s)


@app.post("/api/autonomy")
def set_autonomy(body: dict = Body(...)):
    with LOCK:
        s = S()
        s.set_autonomy(body.get("mode", "auto"))
        return state(s)


@app.post("/api/autopilot")
def set_autopilot(body: dict = Body(...)):
    with LOCK:
        s = S()
        s.set_autopilot(bool(body.get("on")))
        return state(s)


# ------------------------------------------------------------------ analysis
@app.get("/api/market")
def market():
    with LOCK:
        s = S()
        eng = s.engine
        reg = eng.regime
        lab = reg.labels.iloc[::5]
        m = eng.md.market.reindex(lab.index)
        timeline = [dict(date=str(d)[:10], nifty=float(m[d]), regime=int(lab[d])) for d in lab.index]
        score = eng.anomaly.market_score.iloc[::5]
        flags = eng.anomaly.market_flags
        anomalies = [dict(date=str(d)[:10], score=float(v), flagged=bool(flags[d])) for d, v in score.items()]
        return Z.clean(dict(
            overview=eng.market_overview(), timeline=timeline, anomalies=anomalies,
            regimes=[dict(regime=i, **r.to_dict()) for i, r in reg.stats.iterrows()],
            transition=reg.transition.tolist(), regime_names=reg.names))


@app.get("/api/correlation")
def correlation():
    with LOCK:
        c = S().engine.rm.corr
        return Z.clean(dict(labels=[D.short(x) for x in c.index], matrix=c.values.round(3).tolist()))


@app.get("/api/assets")
def assets():
    with LOCK:
        eng = S().engine
        t = eng.rm.capm.join(eng.mu_table[["expected", "ml_tilt"]])
        px = eng.md.last_prices()
        rows = [dict(symbol=sym, ticker=D.short(sym), name=C.UNIVERSE[sym][0], sector=C.UNIVERSE[sym][1],
                     asset_class=C.UNIVERSE[sym][2], price=px[sym], beta=r.beta, capm_return=r.capm_return,
                     hist_return=r.hist_return, expected_return=r.expected, vol=r.vol, mdd=r.mdd, sharpe=r.sharpe_hist,
                     ml_tilt=r.ml_tilt) for sym, r in t.iterrows()]
        return Z.clean(rows)


@app.get("/api/assets/{ticker}")
def asset(ticker: str):
    with LOCK:
        s = S()
        try:
            rep = s.engine.asset_report(ticker)
        except KeyError:
            raise HTTPException(404, "unknown asset")
        return Z.clean(Z.asset_detail(s, rep))


@app.get("/api/models")
def models():
    with LOCK:
        s = S()
        est = s.engine.estimator
        return Z.clean(dict(metrics=Z.metrics_table(est.metrics), **Z.model_extras(est),
                            importance=[dict(feature=k, value=float(v)) for k, v in est.feature_importance.head(12).items()]
                            if est.feature_importance is not None else []))


@app.post("/api/plan")
def plan(body: dict | None = Body(default=None)):
    """Build (or reuse) the five-strategy board for the current profile."""
    with LOCK:
        s = S()
        s.ensure_board()
        s.emit("strategies", "Strategy comparison", dict(board=s.board, recommended=s.recommended, why=s.recommended_why,
                                                          profile=s.profile.normalised()))
        a = Z.artifact(s.take_artifacts()[0], s)
        return Z.clean(dict(strategies=a["data"], state=state(s)))


@app.get("/api/plan/{name}")
def plan_for(name: str):
    with LOCK:
        s = S()
        n = strat(name)
        s.selected_strategy = n
        e = s.board[n]
        pl = s.engine.build_plan(e.weights, s.profile.normalised())
        s.last_plan = pl
        a = Z.artifact(dict(kind="plan", title="plan", payload=dict(plan=pl, evaluation=e, profile=s.profile.normalised(),
                                                                       recommended=s.recommended)), s)
        return a["data"]


@app.get("/api/montecarlo/{name}")
def montecarlo(name: str):
    with LOCK:
        s = S()
        n = strat(name)
        e = s.board[n]
        return Z.artifact(dict(kind="montecarlo", title="mc", payload=dict(mc=e.mc, strategy=n, profile=s.profile.normalised())), s)["data"]


@app.get("/api/stress/{name}")
def stress(name: str):
    with LOCK:
        s = S()
        n = strat(name)
        e = s.board[n]
        p = s.profile.normalised()
        sm = s.engine.shock_monte_carlo(e.weights, p)
        return Z.artifact(dict(kind="stress", title="s", payload=dict(stress=e.stress, shock_mc=sm, strategy=n, profile=p)), s)["data"]


@app.get("/api/timing/{name}")
def timing(name: str):
    with LOCK:
        s = S()
        n = strat(name)
        p = s.profile.normalised()
        t = s.engine.timing(s.board[n].weights, p)
        return Z.artifact(dict(kind="timing", title="t", payload=dict(table=t, strategy=n, profile=p)), s)["data"]


@app.get("/api/backtest")
def backtest(years: int = 3):
    with LOCK:
        s = S()
        return Z.clean(Z.backtest(s.engine.backtest(s.profile.normalised(), max(1, min(5, years)))))


@app.get("/api/frontier")
def frontier():
    with LOCK:
        s = S()
        p = s.profile.normalised()
        s.ensure_board()
        fr = s.engine.frontier(p)
        cloud = fr["cloud"].iloc[::6]
        return Z.clean(dict(
            frontier=[dict(vol=r.volatility, ret=r.exp_return) for r in fr["frontier"].itertuples()],
            cloud=[dict(vol=r.vol, ret=r.ret) for r in cloud.itertuples()],
            assets=[dict(ticker=D.short(i), vol=r.vol, ret=r.ret) for i, r in fr["assets"].iterrows()],
            strategies=[dict(strategy=n, vol=e.stats["volatility"], ret=e.stats["exp_return"]) for n, e in s.board.items()]))


# ------------------------------------------------------------------ simulator
@app.get("/api/simulate/presets")
def simulate_presets():
    with LOCK:
        return Z.clean(simulator.presets(S().engine))


@app.post("/api/simulate")
def simulate(body: dict = Body(...)):
    """Project a custom investment: {amount, monthly, years, holdings:[{asset, weight}]}."""
    with LOCK:
        try:
            out = simulator.simulate(S().engine, body.get("holdings") or [], body.get("amount", 0), body.get("years", 5),
                                     body.get("monthly", 0) or 0)
        except simulator.SimulationError as e:
            raise HTTPException(400, str(e))
        return Z.clean(out)


# ------------------------------------------------------------------ wallet
@app.get("/api/wallet")
def wallet():
    with LOCK:
        return Z.clean(wallet_state(S()))


@app.get("/api/wallet/health")
def wallet_health():
    with LOCK:
        s = S()
        h = trading.portfolio_health(s)
        return Z.clean(dict(issues=h["issues"], orders=trading.describe_orders(h["orders"]), label=h["label"],
                            metrics=h["metrics"], regime=h["regime"], total_value=h["total_value"], cash=h["cash"]))


@app.post("/api/wallet/invest")
def wallet_invest(body: dict = Body(default={})):
    with LOCK:
        s = S()
        s.ensure_board()
        return run_tool("invest_plan", {"strategy": body.get("strategy")})


@app.post("/api/wallet/trade")
def wallet_trade(body: dict = Body(...)):
    with LOCK:
        return run_tool("trade", {k: body.get(k) for k in ("side", "asset", "quantity", "amount_rs") if body.get(k) is not None})


@app.post("/api/wallet/rebalance")
def wallet_rebalance(body: dict = Body(default={})):
    with LOCK:
        return run_tool("rebalance_portfolio", {"strategy": body.get("strategy")})


@app.post("/api/wallet/auto-manage")
def wallet_auto():
    with LOCK:
        return run_tool("auto_manage_portfolio")


@app.post("/api/wallet/confirm")
def wallet_confirm():
    with LOCK:
        s = S()
        try:
            s.wallet.confirm_pending()
        except Exception as e:
            raise HTTPException(400, str(e))
        return Z.clean(dict(wallet=wallet_state(s), state=state(s)))


@app.post("/api/wallet/cancel")
def wallet_cancel():
    with LOCK:
        s = S()
        s.wallet.cancel_pending()
        return Z.clean(dict(wallet=wallet_state(s), state=state(s)))


@app.post("/api/wallet/funds")
def wallet_funds(body: dict = Body(...)):
    with LOCK:
        s = S()
        try:
            s.wallet.add_demo_funds(float(body.get("amount", 0)))
        except Exception as e:
            raise HTTPException(400, str(e))
        return Z.clean(dict(wallet=wallet_state(s), state=state(s)))


@app.post("/api/wallet/reset")
def wallet_reset():
    with LOCK:
        s = S()
        s.wallet.reset()
        return Z.clean(dict(wallet=wallet_state(s), state=state(s)))


@app.post("/api/autopilot/run")
def autopilot_run():
    """Run one autopilot pass: review the portfolio and execute whatever it needs."""
    with LOCK:
        return run_tool("auto_manage_portfolio")


@app.post("/api/sips/start")
def sip_start(body: dict = Body(...)):
    """Start a monthly SIP from the UI (a click is an explicit instruction)."""
    with LOCK:
        return run_tool("start_sip", {"amount_rs": body.get("amount"), "months": body.get("months"), "strategy": body.get("strategy")})


@app.post("/api/sips/stop")
def sip_stop(body: dict | None = Body(default=None)):
    with LOCK:
        return run_tool("stop_sip", {"sip_id": (body or {}).get("id")})


@app.post("/api/data/refresh")
def refresh():
    with LOCK:
        out = run_tool("refresh_market_data", force=True)
        s = S()
        out["sips"] = run_tool("run_due_sips")            # SIP instalments that fell due with the new data
        if s.autopilot:
            out["autopilot"] = run_tool("auto_manage_portfolio")
        return out


# ------------------------------------------------------------------ chat (SSE)
def _sse(obj: dict) -> str:
    return "data: " + json.dumps(Z.clean(obj), ensure_ascii=False) + "\n\n"


@app.post("/api/chat")
def chat(body: dict = Body(...)):
    msg = str(body.get("message", "")).strip()
    if not msg:
        raise HTTPException(400, "empty message")

    def gen():
        with LOCK:
            s, agent = S(), AG()
            try:
                for ev in agent.stream(msg):
                    if ev.kind == "tool_call":
                        yield _sse(dict(type="tool_call", name=ev.name, args=ev.data))
                    elif ev.kind == "tool_result":
                        r = ev.data if isinstance(ev.data, dict) else {"value": ev.data}
                        yield _sse(dict(type="tool_result", name=ev.name, ok="error" not in r, result=r))
                    elif ev.kind == "text":
                        yield _sse(dict(type="text", delta=ev.data))
                    elif ev.kind == "error":
                        yield _sse(dict(type="error", message=str(ev.data)))
                    elif ev.kind == "done":
                        arts = [Z.artifact(a, s) for a in ev.data.artifacts]
                        yield _sse(dict(type="done", text=ev.data.text, artifacts=arts, wallet=wallet_state(s), state=state(s)))
            except Exception as e:  # pragma: no cover
                yield _sse(dict(type="error", message=f"{type(e).__name__}: {e}"))

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/chat/reset")
def chat_reset():
    with LOCK:
        AG().reset()
        return dict(ok=True)
