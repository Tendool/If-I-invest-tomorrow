"""Trading tools of the agent (demo money only).

AUTO mode  : the agent executes trades itself when the user's message is an instruction.
ASK mode   : orders are only staged; the user must confirm (or the message was a question).
"""
from __future__ import annotations

import re

from . import config as C
from . import data as D
from .session import Session
from .tools import _inr, _r, _resolve_strategy, get_investment_plan
from .wallet import WalletError

_QUESTION = re.compile(r"^(should|would|could|is|are|was|does|do|did|what|which|how|why|when|where|who|shall)\b"
                       r"|\bshould i\b|\bdo you think\b|\bwhat if\b", re.I)
_PRE = re.compile(r"^(please|ok(ay)?|now|then|and|so|hey|alright|cool|great|thanks?|yes|yep|sure)[,!.\s]+", re.I)
_VERBS = re.compile(r"^(stage|place|invest|buy|sell|liquidate|rebalance|deploy|put|exit|manage|execute|dump|square|trim|reduce|"
                    r"increase|cash out|book|purchase|get rid|switch|move|shift|de-?risk|take care|fix|do whatever|act)\b", re.I)
_GENERAL = re.compile(r"(go ahead|do it|\binvest it\b|\binvest (the |my )?(money|amount|plan|everything|all)|"
                      r"put (it|the money|my money)|execute (the )?plan|\bsell (it|them|all|everything)\b)", re.I)


def has_action_intent(text: str) -> bool:
    """True when the user's message is an instruction to act (not a question about acting)."""
    t = (text or "").strip()
    for _ in range(3):
        t = _PRE.sub("", t)
    t = re.sub(r"^(can|could|would|will) you( please)?\s+", "", t, flags=re.I)
    t = re.sub(r"^(go ahead and|i want you to|i want to|i'd like to|i would like to|let's|lets|just)\s+", "", t, flags=re.I)
    if _QUESTION.search(t) and not t.lower().startswith("do it"):
        return False
    return bool(_VERBS.search(t) or _GENERAL.search(t))


def _place(s: Session, orders: list[dict], label: str) -> dict:
    """Execute (auto mode + instruction) or stage (otherwise) a list of orders."""
    from .trading import describe_orders
    orders = [o for o in orders if o["qty"] > 0]
    if not orders:
        return dict(status="NO TRADES NEEDED", message="The wallet already matches the target.")
    wants_stage_only = bool(re.search(r"stage", s.last_user_text or "", re.I)) and not s.force_action
    execute = s.force_action or (s.autonomy == "auto" and has_action_intent(s.last_user_text) and not wants_stage_only)
    try:
        if execute:
            s.wallet.execute_orders(orders, label)
        else:
            s.wallet.stage_orders(orders, label)
    except WalletError as e:
        return dict(error=str(e))
    md = s.engine.md
    v = s.wallet.valuation(md.last_prices(), asof=str(md.last_date.date()))
    desc = describe_orders(orders)
    s.emit("orders", "Executed orders" if execute else "Staged orders",
           dict(executed=execute, label=label, orders=desc, cash=v["cash"], total_value=v["total_value"]))
    rows = [dict(side=o["side"], ticker=o["ticker"], name=o["name"], qty=o["qty"], price=_r(o["price"]),
                 value_rs=_inr(o["value"])) for o in desc]
    if execute:
        return dict(status="EXECUTED with demo money", label=label, orders=rows, cash_left_rs=_inr(v["cash"]),
                    total_wallet_value_rs=_inr(v["total_value"]))
    return dict(status=f"STAGED - waiting for the user's confirmation (autonomy mode: {s.autonomy})", label=label,
                orders=rows, instruction="Show the orders and ask the user to reply 'confirm' to execute with demo money.")


def invest_plan(s: Session, strategy: str | None = None) -> dict:
    """Invest the current plan in the demo wallet: buys every asset in tomorrow's plan."""
    if s.last_plan is None or (strategy and _resolve_strategy(s, strategy) != s.selected_strategy):
        get_investment_plan(s, strategy)
    name = s.selected_strategy
    orders = [dict(symbol=r.symbol, side="BUY", qty=int(r.shares), price=float(r.price))
              for r in s.last_plan.itertuples() if int(r.shares) > 0]
    res = _place(s, orders, f"invest plan: {name}")
    res["strategy"] = name
    return res


def trade(s: Session, side: str, asset: str, quantity: int | None = None, amount_rs: float | None = None) -> dict:
    """Buy or sell one asset (by quantity or rupee amount). asset='all' with SELL liquidates every holding."""
    side = str(side).upper()
    if side not in ("BUY", "SELL"):
        return dict(error="side must be BUY or SELL")
    px = s.engine.md.last_prices()
    held = {r.symbol: int(r.qty) for r in s.wallet.holdings().itertuples()}
    if side == "SELL" and str(asset).strip().lower() in ("all", "everything", "all holdings", "portfolio"):
        orders = [dict(symbol=sym, side="SELL", qty=q, price=float(px[sym])) for sym, q in held.items()]
        return _place(s, orders, "liquidate everything") if orders else dict(error="there is nothing to sell")
    sym = s.engine.resolve_symbol(asset)
    if sym is None:
        return dict(error=f"unknown asset {asset!r}; use list_assets")
    price = float(px[sym])
    if side == "SELL" and (quantity is None or str(quantity).lower() == "all") and amount_rs is None:
        quantity = held.get(sym, 0)                      # "sell TCS" = sell the whole position
    if quantity is None and amount_rs is not None:
        quantity = int(float(amount_rs) // (price * (1 + C.BROKERAGE_RATE + C.SLIPPAGE_RATE)))
    if not quantity or int(quantity) <= 0:
        return dict(error="quantity is zero - no holding, amount too small for one share, or no quantity given")
    return _place(s, [dict(symbol=sym, side=side, qty=int(quantity), price=price)], f"{side.lower()} {D.short(sym)}")


def rebalance_portfolio(s: Session, strategy: str | None = None) -> dict:
    """Rebalance current holdings (plus idle cash up to the profile amount) to a strategy's target weights."""
    from . import trading
    name = _resolve_strategy(s, strategy)
    tw = s.ensure_board()[name].weights
    p = s.profile.normalised()
    held_val, cash = trading.holdings_value(s), s.wallet.cash()
    capital = min(held_val + cash, max(held_val, p.amount))
    orders = trading.target_orders(s, tw, capital)
    s.selected_strategy = name
    res = _place(s, orders, f"rebalance to {name}")
    res["strategy"] = name
    return res


def check_portfolio(s: Session) -> dict:
    """Health-check the demo portfolio: stop-loss, concentration drift, risk limits, bear regime, idle cash."""
    from . import trading
    h = trading.portfolio_health(s)
    s.emit("health", "Portfolio health check", dict(
        issues=h["issues"], orders=trading.describe_orders(h["orders"]), label=h["label"], metrics=h["metrics"],
        regime=h["regime"], total_value=h["total_value"], cash=h["cash"]))
    return dict(regime=h["regime"], total_value_rs=_inr(h["total_value"]), cash_rs=_inr(h["cash"]),
                issues=[i["message"] for i in h["issues"]] or ["No problems found - the portfolio is healthy."],
                proposed_orders=[f"{o['side']} {o['qty']} {D.short(o['symbol'])}" for o in h["orders"]],
                next_step="Call auto_manage_portfolio to apply these orders." if h["orders"] else "Nothing to do.")


def auto_manage_portfolio(s: Session) -> dict:
    """Act on the health check: sell stop-loss positions, trim drift, de-risk, rebalance, deploy idle cash."""
    from . import trading
    h = trading.portfolio_health(s)
    if not h["orders"]:
        return dict(status="NO TRADES NEEDED", issues=[i["message"] for i in h["issues"]] or ["Portfolio is healthy."])
    res = _place(s, h["orders"], h["label"])
    res["issues_addressed"] = [i["message"] for i in h["issues"]]
    return res


def set_autonomy(s: Session, mode: str) -> dict:
    """Switch between 'auto' (agent executes trades when told to) and 'ask' (agent only stages; user confirms)."""
    return dict(autonomy=s.set_autonomy(mode))
