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


# ------------------------------------------------------------ invest a specific amount
def test_parse_amount_from_user_words():
    from ifit.agent import parse_amount
    assert parse_amount("invest 200000") == 200000
    assert parse_amount("give the investment plan of Rs. 9,06,120") == 906120
    assert parse_amount("invest 2 lakh") == 200000 and parse_amount("put 50k") == 50000
    assert parse_amount("invest the complete cash i have") == "all"
    assert parse_amount("invest it") is None
    assert parse_amount("Rs 1,00,000 for 3 years at 12%") == 100000      # years and % are not rupees


def test_model_cannot_change_the_amount():
    from ifit.agent import fix_amount_args
    assert fix_amount_args("invest_plan", {"amount_rs": 906120}, "invest it") == {}             # invented by the model -> dropped
    assert fix_amount_args("invest_plan", {}, "invest 200000") == {"amount_rs": 200000}         # dropped by the model -> restored
    assert fix_amount_args("trade", {"amount_rs": 5}, "buy rs 5 of tcs") == {"amount_rs": 5}    # other tools untouched


def test_invest_plan_uses_requested_amount_and_caps_to_cash(sess):
    sess.set_autonomy("auto")
    sess.last_user_text = "invest 200000"
    r = call_tool(sess, "invest_plan", {"amount_rs": 200000})
    assert r["status"].startswith("EXECUTED") and r["plan_amount_rs"] == 200000
    assert 190_000 < 1_000_000 - sess.wallet.cash() <= 200_000
    sess.last_user_text = "invest the complete cash i have"
    r = call_tool(sess, "invest_plan", {"amount_rs": "all"})
    assert r["status"].startswith("EXECUTED") and sess.wallet.cash() < 20_000
    sess.last_user_text = "invest 5 lakh"
    r = call_tool(sess, "invest_plan", {"amount_rs": 500000})
    assert "error" in r or "only" in r.get("note", "")


# ------------------------------------------------------------ SIPs
def test_sip_lifecycle(sess):
    sess.set_autonomy("auto")
    sess.last_user_text = "start a sip of 10000 for 6 months"
    r = call_tool(sess, "start_sip", {"amount_rs": 10000, "months": 6})
    assert r["status"].startswith("SIP #") and r["first_instalment"]["status"].startswith("EXECUTED")
    sip = sess.wallet.sips()[0]
    assert sip["done"] == 1 and sip["active"] == 1 and 9_000 < sip["invested"] <= 10_000
    cash0 = sess.wallet.cash()
    # nothing is due until a new month of data arrives
    assert call_tool(sess, "run_due_sips", {})["count"] == 0
    # pretend two months have passed: both instalments are invested at the latest close
    with sess.wallet._conn() as c:
        c.execute("UPDATE sips SET next_date = ?", (str((sess.engine.md.last_date - pd.DateOffset(months=1)).date()),))
    assert call_tool(sess, "run_due_sips", {})["count"] == 2
    assert sess.wallet.sips()[0]["done"] == 3 and sess.wallet.cash() < cash0 - 18_000
    assert call_tool(sess, "stop_sip", {})["status"] == "stopped 1 SIP(s)"
    assert call_tool(sess, "sip_status", {})["active"] == 0


def test_sip_routing_and_args():
    assert required_tools("start a sip for 6 months") == ["start_sip"]
    assert forced_args("start_sip", "start a SIP of 10000 for 12 months") == {"amount_rs": 10000.0, "months": 12}
    assert required_tools("plan for a sip of 10000 every month") == ["project_sip"]
    assert required_tools("stop my sip") == ["stop_sip"]
    assert required_tools("should I do a SIP or lump sum?") == ["compare_timing"]
    assert has_action_intent("start a sip for 6 months") and not has_action_intent("should I start a sip?")


def test_strategy_and_horizon_come_from_the_users_words():
    a = forced_args("get_investment_plan", "give me a new plan for 10000 for maximum returns in 3 months")
    assert a == {"amount_rs": 10000.0, "horizon_years": 0.25, "strategy": "Max Return"}


def test_short_horizon_is_explained_not_ignored(sess):
    sess.last_user_text = "plan for 10000 for maximum returns in 3 months"
    r = call_tool(sess, "get_investment_plan", {"amount_rs": 10000, "horizon_years": 0.25, "strategy": "Max Return"})
    assert r["strategy"] == "Max Return" and "1 year" in r["note"] and "LIQUIDBEES" in r["note"]


def test_no_mutual_funds_and_unknown_fund_house_is_flagged(sess):
    assert required_tools("best mutual funds now?") == ["list_assets"] and required_tools("navi nifty 50") == ["list_assets"]
    sess.last_user_text = "best mutual funds now?"
    r = call_tool(sess, "list_assets", {"sector_or_class": "funds"})
    assert "no mutual funds" in r["funds_note"] and all(a["asset_class"] != "stock" for a in r["assets"])
    sess.last_user_text = "navi nifty 50"
    r = call_tool(sess, "analyze_asset", {"asset": "NIFTYBEES"})
    assert "Navi" in r["note"] and r["daily_var95_rs_per_1000"] > 5


def test_sip_is_not_started_by_a_planning_question(sess):
    sess.set_autonomy("auto")
    sess.last_user_text = "plan for a sip of 10000 every month"
    r = call_tool(sess, "start_sip", {"amount_rs": 10000})
    assert "REFUSED" in r["error"] and sess.wallet.sips() == []
    assert "median_final_rs" in call_tool(sess, "project_sip", {"monthly_rs": 10000, "years": 3})


def test_staged_sip_instalment_counts_when_confirmed(sess):
    sess.set_autonomy("ask")
    sess.last_user_text = "start a sip of 10000 for 6 months"
    r = call_tool(sess, "start_sip", {"amount_rs": 10000, "months": 6})
    assert r["first_instalment"]["status"].startswith("STAGED")
    assert sess.wallet.sips()[0]["done"] == 0
    sess.wallet.confirm_pending()
    sip = sess.wallet.sips()[0]
    assert sip["done"] == 1 and sip["invested"] > 9_000


def test_model_cannot_invent_sip_lump_sum():
    from ifit.agent import fix_user_args
    assert fix_user_args("project_sip", {"initial_rs": 990022, "monthly_rs": 5}, "plan for a sip of 10000 every month") == {"monthly_rs": 10000.0}
