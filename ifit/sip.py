"""Monthly SIPs (systematic investment plans) in the demo wallet, plus SIP projections.

A SIP invests a fixed rupee amount every month into a fixed allocation (the chosen strategy's weights at the time the SIP
was started). The first instalment is placed immediately; later instalments are invested automatically, at the latest
close, when market data for a new month arrives (see run_due_sips, called after a data refresh).
"""
from __future__ import annotations

import dataclasses
import re

import pandas as pd

from .session import Session
from .tools import _inr, _resolve_strategy
from .tools_trading import _place, has_action_intent

SIP_DEFAULT_MONTHS = 12


def _buy_weights(s: Session, weights: pd.Series, amount: float, label: str) -> dict:
    """Buy `weights` for `amount` rupees (whole shares, costs included) without touching the investor profile."""
    p = dataclasses.replace(s.profile.normalised(), amount=float(amount))
    plan = s.engine.build_plan(weights, p)
    orders = [dict(symbol=r.symbol, side="BUY", qty=int(r.shares), price=float(r.price)) for r in plan.itertuples() if int(r.shares) > 0]
    if not orders:
        return dict(error=f"Rs.{amount:,.0f} is too small to buy even one share of this plan; use a larger monthly amount")
    return _place(s, orders, label)


def _next_month(d) -> str:
    return str((pd.Timestamp(d) + pd.DateOffset(months=1)).date())


def _spent(res: dict) -> float:
    if not str(res.get("status", "")).startswith("EXECUTED"):
        return 0.0
    return float(sum(o["value_rs"] for o in res.get("orders", []) if o.get("side") == "BUY"))


def start_sip(s: Session, amount_rs: float | None = None, months: int | None = None, strategy: str | None = None) -> dict:
    """Start a monthly SIP in the demo wallet: invests amount_rs now and again every month (for `months` instalments)
    into the chosen strategy's allocation."""
    asked = has_action_intent(s.last_user_text) and re.search(r"\bsips?\b|systematic|every month|monthly", s.last_user_text or "", re.I)
    if not (s.force_action or asked):
        return dict(error="REFUSED: the user's latest message does not ask to START a SIP. Use project_sip to show what a SIP "
                          "could grow to, then ask whether they want to start it (e.g. 'start a SIP of 10000 for 12 months').")
    given = amount_rs not in (None, "", "all")
    amount = float(amount_rs) if given else s.profile.normalised().amount
    months = int(months) if months not in (None, "") else SIP_DEFAULT_MONTHS
    if amount < 1000:
        return dict(error="a SIP instalment must be at least Rs.1,000 (the plan buys whole shares)")
    if not 1 <= months <= 120:
        return dict(error="a SIP can run for 1 to 120 months")
    if amount > s.wallet.cash():
        return dict(error=f"the first instalment (Rs.{amount:,.0f}) is more than the demo cash (Rs.{s.wallet.cash():,.0f})")
    name = _resolve_strategy(s, strategy)
    w = s.ensure_board()[name].weights
    w = w[w > 0]
    md = s.engine.md
    nxt = _next_month(md.last_date)
    sid = s.wallet.add_sip(name, {k: float(v) for k, v in w.items()}, amount, months, nxt)
    first = _buy_weights(s, w, amount, f"SIP #{sid} instalment 1/{months}: {name} · Rs.{amount:,.0f}")
    if "error" in first:
        s.wallet.delete_sip(sid)
        return first
    executed = str(first.get("status", "")).startswith("EXECUTED")
    if executed:                       # a staged first instalment is counted when the user confirms it
        s.wallet.record_sip_instalment(sid, _spent(first), nxt)
    out = dict(status=f"SIP #{sid} started", strategy=name, monthly_amount_rs=_inr(amount), months=months,
               first_instalment=first, next_instalment_date=nxt,
               summary=(f"SIP #{sid}: Rs.{amount:,.0f} every month for {months} months into the {name} allocation. "
                        f"First instalment {'invested' if executed else 'staged for confirmation'} today; next one on {nxt}."),
               how_it_works="Each later instalment is invested automatically at the latest close once market data for the new "
                            "month arrives (Refresh market data). Demo money only.")
    if not given:
        out["note"] = f"no amount was given - using the profile amount, Rs.{amount:,.0f} per month"
    _emit(s)
    return out


def sip_rows(s: Session) -> list[dict]:
    return [dict(id=r["id"], strategy=r["strategy"], monthly_amount_rs=_inr(r["amount"]), instalments_done=r["done"],
                 instalments_total=r["months"], invested_rs=_inr(r["invested"]),
                 next_date=r["next_date"] if r["active"] else None, status="active" if r["active"] else "stopped / finished")
            for r in s.wallet.sips()]


def _emit(s: Session) -> None:
    s.emit("sips", "SIPs", dict(sips=sip_rows(s)))


def sip_status(s: Session) -> dict:
    """List the demo wallet's SIPs: monthly amount, instalments done, amount invested, next date."""
    rows = sip_rows(s)
    _emit(s)
    return dict(count=len(rows), active=sum(r["status"] == "active" for r in rows), sips=rows)


def stop_sip(s: Session, sip_id: int | None = None) -> dict:
    """Stop one SIP (sip_id) or all active SIPs. Holdings already bought are kept."""
    n = s.wallet.stop_sip(int(sip_id) if sip_id not in (None, "") else None)
    _emit(s)
    return dict(status=f"stopped {n} SIP(s)" if n else "there is no active SIP to stop", holdings_kept=True)


def run_due_sips(s: Session) -> dict:
    """Invest every SIP instalment that has fallen due (called after market data is refreshed)."""
    md = s.engine.md
    out = []
    for r in s.wallet.sips(active_only=True):
        nxt, done = pd.Timestamp(r["next_date"]), int(r["done"])
        while nxt <= md.last_date and done < int(r["months"]):
            if r["amount"] > s.wallet.cash():
                out.append(dict(id=r["id"], skipped=str(nxt.date()), reason="not enough demo cash"))
                break
            res = _buy_weights(s, pd.Series(r["weights"]), r["amount"], f"SIP #{r['id']} instalment {done + 1}/{r['months']}")
            nxt = pd.Timestamp(_next_month(nxt))
            s.wallet.record_sip_instalment(r["id"], _spent(res), str(nxt.date()))
            done += 1
            out.append(dict(id=r["id"], instalment=done, invested_rs=_inr(_spent(res)), error=res.get("error")))
    return dict(instalments=out, count=len(out))


def project_sip(s: Session, monthly_rs: float | None = None, years: float | None = None, initial_rs: float = 0.0,
                strategy: str | None = None) -> dict:
    """What a monthly SIP could grow to: simulated worst 5% / median / best 5% year by year, vs a fixed deposit."""
    from . import simulator
    monthly = float(monthly_rs) if monthly_rs not in (None, "", "all") else s.profile.normalised().amount
    yrs = int(round(float(years))) if years not in (None, "") else int(s.profile.normalised().horizon_years)
    yrs = min(max(yrs, 1), simulator.MAX_YEARS)
    name = _resolve_strategy(s, strategy)
    w = s.ensure_board()[name].weights
    hold = [dict(asset=k, weight=float(v)) for k, v in w[w > 0].items()]
    try:
        r = simulator.simulate(s.engine, hold, float(initial_rs or 0), yrs, monthly)
    except simulator.SimulationError as e:
        return dict(error=str(e))
    sm = r["summary"]
    return dict(strategy=name, monthly_rs=_inr(monthly), years=yrs, total_invested_rs=_inr(sm["total_invested"]),
                median_final_rs=_inr(sm["median_final"]), worst_5pct_rs=_inr(sm["p5_final"]), best_5pct_rs=_inr(sm["p95_final"]),
                chance_of_profit_pct=round(100 * sm["prob_profit"]), median_annual_return_pct=round(100 * sm["median_annual_return"], 1),
                fixed_deposit_final_rs=_inr(sm["fd_final"]),
                by_year=[dict(year=t["year"], invested_rs=_inr(t["invested"]), worst_5pct_rs=_inr(t["p5"]), median_rs=_inr(t["median"]),
                              best_5pct_rs=_inr(t["p95"]), chance_of_profit_pct=round(100 * t["prob_profit"])) for t in r["table"]],
                note="Simulation on historical data, not a guarantee. To start it for real (demo money), say e.g. "
                     "'start a SIP of 10000 for 12 months'.")
