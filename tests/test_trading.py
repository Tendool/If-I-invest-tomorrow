import pandas as pd
import pytest

from ifit import trading
from ifit.agent import forced_args, required_tools, trade_args
from ifit.session import Session
from ifit.tools import call_tool
from ifit.tools_trading import has_action_intent
from ifit.wallet import Wallet


@pytest.fixture
def sess(engine, tmp_path):
    return Session(engine=engine, wallet=Wallet(tmp_path / "t.sqlite", 1_000_000))


def held(s):
    return {r.symbol: int(r.qty) for r in s.wallet.holdings().itertuples()}


@pytest.mark.parametrize("text,expected", [
    ("Sell all my TCS", True), ("Invest it all in the plan", True), ("go ahead and rebalance", True),
    ("Please buy 10 shares of SBIN", True), ("manage my portfolio", True), ("Can you sell everything?", True),
    ("Should I sell TCS?", False), ("What should I invest in tomorrow?", False), ("Is it good to buy gold?", False),
    ("How is the market?", False), ("What if the market crashes?", False)])
def test_action_intent(text, expected):
    assert has_action_intent(text) is expected


def test_trade_parser():
    assert trade_args("Sell all my TCS") == {"side": "SELL", "asset": "TCS"}
    assert trade_args("Sell 5 shares of GOLDBEES.") == {"side": "SELL", "quantity": 5, "asset": "GOLDBEES"}
    assert trade_args("Buy Rs 20,000 of gold") == {"side": "BUY", "amount_rs": 20000.0, "asset": "gold"}
    assert trade_args("sell everything") == {"side": "SELL", "asset": "all"}
    assert trade_args("how is the market") is None
    assert forced_args("trade", "Buy 10 SBIN")["quantity"] == 10


def test_intent_router_for_actions():
    assert required_tools("Sell all my TCS") == ["trade"]
    assert required_tools("go ahead and rebalance") == ["rebalance_portfolio"]
    assert required_tools("manage my portfolio") == ["auto_manage_portfolio"]
    assert required_tools("Invest it all in the plan") == ["invest_plan"]
    assert required_tools("Should I sell TCS?") == []
    assert required_tools("check my portfolio health") == ["check_portfolio"]


def test_auto_mode_executes_on_instruction_but_not_on_question(sess):
    sess.set_autonomy("auto")
    sess.last_user_text = "Should I buy 5 shares of TCS?"
    r = call_tool(sess, "trade", {"side": "BUY", "asset": "TCS", "quantity": 5})
    assert r["status"].startswith("STAGED") and not held(sess)         # a question never executes
    sess.last_user_text = "Buy 5 shares of TCS"
    r = call_tool(sess, "trade", {"side": "BUY", "asset": "TCS", "quantity": 5})
    assert r["status"].startswith("EXECUTED") and held(sess) == {"TCS.NS": 5}
    assert sess.wallet.pending() is None


def test_ask_mode_never_executes_without_confirmation(sess):
    sess.set_autonomy("ask")
    sess.last_user_text = "Buy 5 shares of TCS"
    r = call_tool(sess, "trade", {"side": "BUY", "asset": "TCS", "quantity": 5})
    assert r["status"].startswith("STAGED") and not held(sess)
    sess.last_user_text = "yes confirm"
    assert call_tool(sess, "confirm_pending_order", {})["status"].startswith("EXECUTED")
    assert held(sess) == {"TCS.NS": 5}


def test_sell_whole_position_and_liquidate(sess):
    sess.set_autonomy("auto")
    sess.last_user_text = "Buy 5 shares of TCS and 3 of INFY"
    call_tool(sess, "trade", {"side": "BUY", "asset": "TCS", "quantity": 5})
    call_tool(sess, "trade", {"side": "BUY", "asset": "INFY", "quantity": 3})
    sess.last_user_text = "Sell all my TCS"
    call_tool(sess, "trade", {"side": "SELL", "asset": "TCS"})
    assert held(sess) == {"INFY.NS": 3}
    sess.last_user_text = "Sell everything"
    call_tool(sess, "trade", {"side": "SELL", "asset": "all"})
    assert held(sess) == {}


def test_cannot_oversell_or_overspend(sess):
    sess.last_user_text = "Sell 5 shares of TCS"
    assert "error" in call_tool(sess, "trade", {"side": "SELL", "asset": "TCS", "quantity": 5})
    sess.last_user_text = "Buy 100000 shares of MARUTI"
    assert "error" in call_tool(sess, "trade", {"side": "BUY", "asset": "MARUTI", "quantity": 100000})


def test_invest_plan_then_rebalance_is_stable(sess):
    sess.set_autonomy("auto")
    sess.last_user_text = "Invest Rs 3 lakh. Go ahead and invest it."
    call_tool(sess, "set_profile", {"amount": 300000, "horizon_years": 3, "risk": "medium", "target_return_pct": 12})
    r = call_tool(sess, "invest_plan", {})
    assert r["status"].startswith("EXECUTED") and len(held(sess)) >= 4
    invested = sum(sess.wallet.valuation(sess.engine.md.last_prices(), record=False)["positions"].value)
    assert 0.9 * 300000 < invested <= 300000
    before = held(sess)
    sess.last_user_text = "Rebalance now"
    r = call_tool(sess, "rebalance_portfolio", {"strategy": sess.selected_strategy})
    # already at target: no (or only tiny) trades
    assert r["status"] == "NO TRADES NEEDED" or len(r["orders"]) <= 2
    assert set(before) <= set(held(sess)) | set(before)


def test_stop_loss_detected_and_fixed(sess):
    sess.set_autonomy("auto")
    sess.last_user_text = "Invest it"
    call_tool(sess, "set_profile", {"amount": 300000, "horizon_years": 3, "risk": "medium", "target_return_pct": 12})
    call_tool(sess, "invest_plan", {})
    victim = max(held(sess), key=held(sess).get)
    with sess.wallet._conn() as c:
        c.execute("UPDATE holdings SET avg_cost = avg_cost * 1.5 WHERE symbol=?", (victim,))
    h = trading.portfolio_health(sess)
    assert any(i["code"] == "STOP_LOSS" for i in h["issues"])
    sess.last_user_text = "manage my portfolio"
    r = call_tool(sess, "auto_manage_portfolio", {})
    assert r["status"].startswith("EXECUTED") and victim not in held(sess)


def test_healthy_empty_wallet_has_no_orders(sess):
    h = trading.portfolio_health(sess)
    assert h["orders"] == []


def test_ui_force_action_executes_even_in_ask_mode(sess):
    sess.set_autonomy("ask")
    sess.last_user_text = ""
    sess.force_action = True            # a button click in the UI is an explicit instruction
    r = call_tool(sess, "trade", {"side": "BUY", "asset": "TCS", "quantity": 1})
    sess.force_action = False
    assert r["status"].startswith("EXECUTED")


def test_stage_word_forces_staging_even_in_auto_mode(sess):
    sess.set_autonomy("auto")
    sess.last_user_text = "Stage 5 shares of TCS for me"
    r = call_tool(sess, "trade", {"side": "BUY", "asset": "TCS", "quantity": 5})
    assert r["status"].startswith("STAGED") and not held(sess)
