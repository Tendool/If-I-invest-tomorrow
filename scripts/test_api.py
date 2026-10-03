"""Smoke-test every REST endpoint of the running API (python -m uvicorn ifit.api:app --port 8000)."""
import json
import sys

import requests

B = "http://127.0.0.1:8000/api"
fails = 0


def check(name, r, cond=lambda j: True):
    global fails
    try:
        j = r.json()
        ok = r.status_code == 200 and cond(j)
    except Exception as e:  # noqa
        j, ok = str(e), False
    fails += (not ok)
    print(f"{'ok  ' if ok else 'FAIL'} {name:34s} {r.status_code} {len(r.content):>8d} bytes")
    if not ok:
        print("     ", str(j)[:300])
    return j


g = lambda p: requests.get(B + p, timeout=300)            # noqa: E731
p = lambda path, body=None: requests.post(B + path, json=body or {}, timeout=300)  # noqa: E731

check("state", g("/state"))
check("profile", p("/profile", dict(amount=200000, horizon_years=3, risk="medium", target_return_pct=12, preferred_sectors=[])),
      lambda j: j["profile"]["amount"] == 200000)
j = check("plan (5 strategies)", p("/plan"), lambda j: len(j["strategies"]["strategies"]) == 5)
check("plan/recommended", g("/plan/recommended"), lambda j: len(j["plan"]) > 3)
check("plan/max-sharpe", g("/plan/max-sharpe"), lambda j: j["strategy"] == "Max Sharpe")
check("montecarlo", g("/montecarlo/recommended"), lambda j: len(j["mc"]["fan"]) > 10 and len(j["mc"]["hist"]) > 10)
check("stress", g("/stress/crash-resistant"), lambda j: len(j["stress"]) >= 8)
check("timing", g("/timing/recommended"), lambda j: len(j["table"]) >= 4)
check("backtest", g("/backtest?years=3"), lambda j: len(j["curves"]) > 100)
check("frontier", g("/frontier"), lambda j: len(j["frontier"]) > 5)
check("market", g("/market"), lambda j: "overview" in j and len(j["timeline"]) > 100)
check("correlation", g("/correlation"), lambda j: len(j["matrix"]) == len(j["labels"]))
check("assets", g("/assets"), lambda j: len(j) >= 30)
check("assets/TCS", g("/assets/TCS"), lambda j: len(j["series"]) > 100)
check("simulate presets", g("/simulate/presets"), lambda j: len(j) >= 5)
check("simulate", p("/simulate", dict(amount=100000, monthly=5000, years=5, holdings=[dict(asset="TCS", weight=50), dict(asset="GOLDBEES", weight=50)])), lambda j: len(j["table"]) == 5 and j["summary"]["total_invested"] == 400000)
check("models", g("/models"), lambda j: len(j["metrics"]) >= 4)

p("/wallet/reset")
j = check("wallet/invest", p("/wallet/invest", {}), lambda j: j["result"]["status"].startswith("EXECUTED"))
w = check("wallet", g("/wallet"), lambda j: len(j["valuation"]["positions"]) > 0)
tick = w["valuation"]["positions"][0]["ticker"]
check("wallet/trade sell", p("/wallet/trade", dict(side="SELL", asset=tick, quantity=1)), lambda j: j["result"]["status"].startswith("EXECUTED"))
check("wallet/trade buy", p("/wallet/trade", dict(side="BUY", asset="gold", amount_rs=5000)), lambda j: "status" in j["result"])
check("wallet/health", g("/wallet/health"))
check("wallet/auto-manage", p("/wallet/auto-manage"))
check("wallet/rebalance", p("/wallet/rebalance", {}))
check("wallet/funds", p("/wallet/funds", dict(amount=1000)))
check("autopilot run", p("/autopilot/run"))
check("autonomy ask", p("/autonomy", dict(mode="ask")), lambda j: j["autonomy"] == "ask")
check("autonomy auto", p("/autonomy", dict(mode="auto")), lambda j: j["autonomy"] == "auto")
check("wallet/trade liquidate", p("/wallet/trade", dict(side="SELL", asset="all")), lambda j: j["result"]["status"].startswith("EXECUTED"))
p("/wallet/reset")
print("FAILED:", fails)
sys.exit(1 if fails else 0)
