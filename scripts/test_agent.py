"""End-to-end conversation test of the Qwen3.5-4B agent (needs Ollama running).

    python scripts/test_agent.py            # writes reports/agent_test_log.md

Each case = (prompt, must-call tools, must-not-call tools, optional state check(session) -> bool).
Uses a throw-away wallet database so the real demo wallet is untouched.
"""
import sys
import tempfile
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from ifit import config as C  # noqa: E402
from ifit.agent import Agent  # noqa: E402
from ifit.engine import Engine  # noqa: E402
from ifit.session import Session  # noqa: E402
from ifit.wallet import Wallet  # noqa: E402

state: dict = {}


def held(s):
    return {r.symbol: int(r.qty) for r in s.wallet.holdings().itertuples()}


def make_stop_loss(s):
    """Pretend the biggest holding was bought 40 % higher, so it is deep in the red."""
    h = s.wallet.holdings().sort_values("qty", ascending=False).iloc[0]
    state["victim"] = h.symbol
    with s.wallet._conn() as c:
        c.execute("UPDATE holdings SET avg_cost = avg_cost * 1.6 WHERE symbol = ?", (h.symbol,))
    return True


CASES = [
    # ---- analysis (unchanged capabilities)
    ("I have Rs 2,00,000 to invest for 3 years, medium risk, target 12% a year. I like IT and banking. What should I invest in tomorrow?",
     ["set_profile", "get_investment_plan"], ["invest_plan", "trade"], lambda s: not held(s)),
    ("Compare all five strategies for me.", ["compare_strategies"], ["invest_plan", "trade"], None),
    ("Now stress test the plan against market crashes.", ["stress_test"], [], None),
    ("What is the probability I reach my target? Show best and worst case.", ["run_monte_carlo"], [], None),
    ("Is it better to invest now or do a SIP?", ["compare_timing"], ["invest_plan", "trade"], lambda s: not held(s)),
    ("Backtest these strategies over the last 3 years.", ["run_backtest"], [], None),
    ("How is the market today?", ["get_market_overview"], [], None),
    ("Tell me about the TCS stock - risk and expected return.", ["analyze_asset"], ["trade"], None),
    ("How did you validate your ML models?", ["get_model_report"], [], None),
    # ---- autonomous investing
    ("Go ahead and invest it in the plan.", ["invest_plan"], [], lambda s: len(held(s)) >= 4),
    ("Show my demo wallet.", ["wallet_status"], [], None),
    # ---- questions must NOT trade
    ("Should I sell my biggest holding?", [], ["trade", "auto_manage_portfolio", "rebalance_portfolio"], lambda s: len(held(s)) >= 4),
    # ---- autonomous selling of one asset (symbol discovered at runtime)
    ("__SELL_ONE__", ["trade"], [], lambda s: state["sold"] not in held(s)),
    # ---- health check + stop-loss auto-management
    ("__STOPLOSS__", ["auto_manage_portfolio"], [], lambda s: state["victim"] not in held(s)),
    ("Check my portfolio health.", ["check_portfolio"], ["trade", "auto_manage_portfolio"], None),
    # ---- rebalance
    ("Rebalance my portfolio to the Max Sharpe strategy.", ["rebalance_portfolio"], [], None),
    # ---- ask-first mode: stage then confirm
    ("Switch to ask-first mode.", ["set_autonomy"], ["trade"], lambda s: s.autonomy == "ask"),
    ("Buy 5 shares of NTPC.", ["trade"], ["confirm_pending_order"], lambda s: s.wallet.pending() is not None),
    ("yes, confirm", ["confirm_pending_order"], [], lambda s: s.wallet.pending() is None and "NTPC.NS" in held(s)),
    ("Switch back to autonomous mode.", ["set_autonomy"], [], lambda s: s.autonomy == "auto"),
    # ---- liquidation + misc
    ("Sell everything.", ["trade"], [], lambda s: not held(s)),
    ("Add Rs 50,000 more demo money to my wallet.", ["add_demo_funds"], [], None),
    ("Show my trade history.", ["wallet_history"], [], None),
]


def main():
    tmp = Path(tempfile.mkdtemp()) / "test_wallet.sqlite"
    s = Session(engine=Engine(), wallet=Wallet(tmp))
    a = Agent(s)
    log, passed = ["# Agent test log (Qwen3.5-4B via Ollama)\n"], 0
    for i, (q, must, mustnot, check) in enumerate(CASES, 1):
        if q == "__SELL_ONE__":
            h = s.wallet.holdings().sort_values("qty").iloc[0]
            state["sold"] = h.symbol
            q = f"Sell all my {h.symbol.replace('.NS', '')}."
        elif q == "__STOPLOSS__":
            make_stop_loss(s)
            q = "Please manage my portfolio and do whatever it needs."
        t = time.time()
        reply = a.chat(q)
        names = [n for n, _ in reply.tool_calls]
        ok = all(m in names for m in must) and not any(m in names for m in mustnot)
        why = ""
        if ok and check is not None:
            try:
                ok = bool(check(s))
                why = "" if ok else "state check failed"
            except Exception as e:  # noqa
                ok, why = False, f"check error {e}"
        elif not ok:
            why = f"tools={names}"
        passed += ok
        print(f"[{i:02d}] {'PASS' if ok else 'FAIL'} {time.time() - t:5.1f}s tools={names} {why}\n     Q: {q}\n     A: {reply.text[:240].replace(chr(10), ' ')}\n")
        log.append(f"## {i}. {'PASS' if ok else 'FAIL'} - {q}\n- tools: `{names}` {why}\n- time: {time.time() - t:.1f}s\n\n{reply.text}\n")
    summary = f"\n**{passed}/{len(CASES)} cases passed**\n"
    print(summary)
    log.insert(1, summary)
    (C.REPORTS_DIR / "agent_test_log.md").write_text("\n".join(log), encoding="utf-8")


if __name__ == "__main__":
    main()
