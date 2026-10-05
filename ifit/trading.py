"""Portfolio management logic used by the agent's trading tools (demo money only).

* ``target_orders``      - orders that move current holdings to a set of target weights
* ``portfolio_health``   - detects stop-loss hits, concentration drift, risk-limit breaches,
                           bear-regime exposure and idle cash, and proposes the orders to fix them
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import config as C
from . import data as D
from . import risk

STOP_LOSS = 0.15          # sell a position that is down >= 15 % from its average cost
DRIFT_TOLERANCE = 0.03    # a holding may exceed its cap by 3pp before we trim
IDLE_CASH_FRACTION = 0.25
MIN_TRADE_FRACTION = 0.01  # ignore rebalancing trades smaller than 1 % of the capital
COST = C.BROKERAGE_RATE + C.SLIPPAGE_RATE


def holdings_qty(s) -> dict[str, int]:
    h = s.wallet.holdings()
    return {r.symbol: int(r.qty) for r in h.itertuples()}


def holdings_value(s) -> float:
    px = s.engine.md.last_prices()
    return float(sum(q * px[sym] for sym, q in holdings_qty(s).items()))


def target_orders(s, weights: pd.Series, capital: float, min_frac: float = MIN_TRADE_FRACTION) -> list[dict]:
    """Orders to move the wallet to ``weights`` of ``capital`` (whole shares, latest close)."""
    px = s.engine.md.last_prices()
    cur = holdings_qty(s)
    orders = []
    for sym in sorted(set(cur) | set(weights[weights > 0].index)):
        w = float(weights.get(sym, 0.0))
        price = float(px[sym])
        tgt = int(math.floor(w * capital / (1 + COST) / price))
        delta = tgt - cur.get(sym, 0)
        if delta == 0:
            continue
        if abs(delta) * price < min_frac * capital and tgt > 0 and cur.get(sym, 0) > 0:
            continue                                  # not worth the trading costs
        orders.append(dict(symbol=sym, side="BUY" if delta > 0 else "SELL", qty=abs(delta), price=price))
    # affordability: scale buys down if cash (+ sell proceeds) is not enough
    cash = s.wallet.cash() + sum(o["qty"] * o["price"] * (1 - COST) for o in orders if o["side"] == "SELL")
    need = sum(o["qty"] * o["price"] * (1 + COST) for o in orders if o["side"] == "BUY")
    if need > cash and need > 0:
        f = cash / need
        for o in orders:
            if o["side"] == "BUY":
                o["qty"] = int(o["qty"] * f)
        orders = [o for o in orders if o["qty"] > 0]
    return orders


def describe_orders(orders: list[dict]) -> list[dict]:
    return [dict(side=o["side"], symbol=o["symbol"], ticker=D.short(o["symbol"]), name=C.UNIVERSE[o["symbol"]][0],
                 sector=C.UNIVERSE[o["symbol"]][1], qty=int(o["qty"]), price=float(o["price"]),
                 value=float(o["qty"] * o["price"])) for o in orders]


def portfolio_health(s) -> dict:
    """Review the demo portfolio and propose corrective orders."""
    eng, md = s.engine, s.engine.md
    p = s.profile.normalised()
    prof = C.RISK_PROFILES[p.risk]
    val = s.wallet.valuation(md.last_prices(), asof=str(md.last_date.date()), record=False)
    pos = val["positions"]
    invested, cash, total = val["invested_value"], val["cash"], val["total_value"]
    issues: list[dict] = []
    out = dict(total_value=total, cash=cash, invested=invested, issues=issues, orders=[], label="",
               regime=eng.regime.current_name, metrics={})
    if not len(pos):
        if cash > 0.5 * val["starting_cash"]:
            issues.append(dict(code="IDLE_CASH", severity="info",
                               message=f"Nothing is invested yet - Rs.{cash:,.0f} of demo cash is idle."))
        return out

    w = pd.Series({r.symbol: r.value / invested for r in pos.itertuples()}).reindex(eng.rm.symbols).fillna(0.0)
    st = risk.portfolio_stats(w, eng.mu, eng.rm.cov, eng.rm.beta)
    out["metrics"] = dict(exp_return=st["exp_return"], volatility=st["volatility"], beta=st["beta"],
                          vol_limit=prof["max_annual_vol"], equity_share=float(
                              sum(w[x] for x in w.index if C.UNIVERSE[x][2] in ("stock", "etf"))))

    stop_syms = [r.symbol for r in pos.itertuples() if r.pnl_pct <= -STOP_LOSS]
    for r in pos.itertuples():
        if r.symbol in stop_syms:
            issues.append(dict(code="STOP_LOSS", severity="high", symbol=D.short(r.symbol),
                               message=f"{D.short(r.symbol)} is down {r.pnl_pct:.1%} from cost (stop-loss {STOP_LOSS:.0%}) - sell."))
    b = eng.bounds(p)
    caps = dict(zip(b.symbols, b.ub))
    over = [x for x in w.index if w[x] > caps.get(x, 1) + DRIFT_TOLERANCE and x not in stop_syms]
    for x in over:
        # a zero cap means the stock is outside the preferred sectors, not that the cap is "0 %"
        why = ("outside your preferred sectors" if caps[x] <= 0 else f"cap {caps[x]:.0%}")
        issues.append(dict(code="DRIFT", severity="medium", symbol=D.short(x),
                           message=f"{D.short(x)} is {w[x]:.0%} of the portfolio ({why}) - trim."))
    breach = st["volatility"] > prof["max_annual_vol"] * 1.10
    if breach:
        issues.append(dict(code="RISK_BREACH", severity="high",
                           message=f"Portfolio volatility {st['volatility']:.1%} exceeds your {p.risk}-risk limit "
                                   f"{prof['max_annual_vol']:.0%} - de-risk."))
    bear = eng.regime.current == 2 and p.risk != "high" and out["metrics"]["equity_share"] > 0.60
    if bear:
        issues.append(dict(code="BEAR_REGIME", severity="high",
                           message=f"Market regime is {eng.regime.current_name} and equity exposure is "
                                   f"{out['metrics']['equity_share']:.0%} - move to defensive assets."))
    idle = cash > IDLE_CASH_FRACTION * total and cash > 0.1 * p.amount
    if idle:
        issues.append(dict(code="IDLE_CASH", severity="info",
                           message=f"{cash / total:.0%} of the wallet (Rs.{cash:,.0f}) is idle cash."))

    if not issues:
        return out

    # ---- build the corrective orders
    rebalance = bool(over or breach or bear)
    if rebalance:
        board = s.ensure_board()
        name = "Crash-Resistant" if bear else (s.recommended or "Max Sharpe")
        if breach and not bear:
            name = "Min Risk" if st["volatility"] > 1.5 * prof["max_annual_vol"] else (s.recommended or "Max Sharpe")
        tw = board[name].weights.copy()
        for x in stop_syms:
            tw[x] = 0.0
        tw = tw / tw.sum()
        capital = invested + (cash if idle else 0.0)
        capital = min(capital, total)
        orders = target_orders(s, tw, capital)
        out["label"] = f"auto-manage: rebalance to {name}"
    elif stop_syms:
        px = md.last_prices()
        orders = [dict(symbol=x, side="SELL", qty=holdings_qty(s)[x], price=float(px[x])) for x in stop_syms]
        out["label"] = "auto-manage: stop-loss"
    elif idle:
        board = s.ensure_board()
        name = s.recommended
        tw = board[name].weights
        capital = min(total, max(p.amount, invested))
        orders = target_orders(s, tw, capital)
        out["label"] = f"auto-manage: deploy idle cash into {name}"
    else:
        orders = []
    out["orders"] = orders
    return out
