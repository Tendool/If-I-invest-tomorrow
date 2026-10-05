"""The "If I Invest Tomorrow" chat agent - Qwen3.5-4B (local, via Ollama) with tool calling."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Iterator

from . import config as C
from .session import Session
from .tools import TOOL_SCHEMAS, call_tool

SYSTEM_PROMPT = """You are "IfIT", the AI financial decision assistant of the project "If I Invest Tomorrow" \
(a financial decision simulator for Indian markets). You help a user decide WHAT to invest in tomorrow, HOW MUCH \
to allocate, and the PROBABILITY of reaching their target. You work with DEMO (virtual) money only.

You have tools. Numbers must come from tool results - NEVER invent or estimate numbers, prices, weights or \
probabilities yourself. If you need a number, call a tool.

Workflow
1. Investor profile = amount (Rs.), horizon (1/3/5 years), risk (low/medium/high), target annual return (%), \
preferred sectors. When the user gives any of these, call set_profile with ONLY the values they gave. If key facts \
are missing and they ask for a plan, state the defaults you will use (current profile) and proceed - do not interrogate.
2. "What should I invest in / make a plan / tomorrow's plan" -> call get_investment_plan (it uses the recommended \
strategy unless the user names one). "Compare strategies" -> compare_strategies. Questions about probability or \
outcomes -> run_monte_carlo. Crash/shock/risk questions -> stress_test. "Invest now or wait / SIP" -> compare_timing. \
"How has it performed / backtest" -> run_backtest. Market questions -> get_market_overview. One stock -> analyze_asset. \
How the ML works -> get_model_report.
3. Wallet & trading (DEMO money). The current autonomy mode is shown in [State]. wallet_status shows the wallet. When the user INSTRUCTS you to act, ACT with the tools: invest_plan (buy the plan), trade (buy/sell one asset, or asset=all to sell everything), rebalance_portfolio, auto_manage_portfolio (do whatever the portfolio needs: stop-loss, trimming, de-risking, deploying idle cash), check_portfolio (review only). In AUTO mode these tools execute immediately on an instruction and the result says EXECUTED; in ASK mode (or if the user only asked a question such as "should I sell?") they only STAGE orders: then list them and ask the user to reply "confirm", and only after their confirmation call confirm_pending_order. Report exactly what the tool says was executed or staged - never claim a trade happened unless the result says EXECUTED. Questions like "should I sell X?" -> analyse (analyze_asset / check_portfolio) and advise, do not trade. set_autonomy switches AUTO/ASK when the user asks.

Style
- Be concise, clear and friendly. Use short bullet lists. Amounts as Rs.1,00,000-style or Rs.100,000.
- Present plans as: asset - weight% - Rs. amount. Then expected return, volatility, probability of positive return, \
probability of reaching the target, and the stress-test result, exactly as the tool returned them.
- Mention that results are model-based simulations on historical data, not guaranteed, and that no real money is used.
- Tables and charts are shown to the user automatically by the app, so do not repeat every row of big tables; \
summarise the key insight.
- If a tool returns an error, explain it simply and suggest the fix.
- Stay on topic (investing, markets, this project). You are not a licensed financial advisor.
- SIP (monthly investing): start_sip starts a real demo SIP (first instalment now, then automatically every month); project_sip shows what a monthly SIP could grow to; sip_status lists SIPs; stop_sip stops them. compare_timing only compares lump sum vs waiting vs SIP - it does not start anything.
- After any trade, state the tool's summary numbers exactly (amount bought, cash left, wallet value); never compute or guess balances yourself.
- This app's universe has stocks and 6 ETFs, no mutual funds. If the user names a fund or fund house the app does not have (e.g. Navi, SBI, Parag Parikh), say so plainly and only then mention the closest asset the app does have. Never call a stock a fund.
- Expected returns from the tools are model estimates, not past performance or guarantees; say so when ranking assets.
- Horizons: the planner works with 1, 3 or 5 years. If a tool returns a note about the horizon, tell the user.
- Amounts: a plan or investment of a specific amount ("invest 2,00,000", "plan for my whole cash") is built by the tool for exactly that amount - report the tool's plan_amount_rs and allocation; never rescale numbers yourself. For "how much should I invest?" questions: give the facts (cash available, the plan for the profile amount, its risk and worst case), note that money needed within the horizon or as an emergency fund should not be invested, and leave the decision to the user."""


@dataclass
class AgentEvent:
    kind: str          # "tool_call" | "tool_result" | "text" | "done" | "error"
    name: str = ""
    data: object = None


@dataclass
class AgentReply:
    text: str
    tool_calls: list[tuple[str, dict]] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)


# User intents that MUST be answered from a tool result (the 4B model otherwise tends to improvise).
INTENT_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"compar\w*.*strateg|strateg\w*.*compar|all (five|5) strateg|which strategy", re.I), "compare_strategies"),
    (re.compile(r"stress|crash|shock|survive|recession|worst[- ]case scenario", re.I), "stress_test"),
    (re.compile(r"monte ?carlo|probabilit|chance|odds|simulat|how likely|best.*worst", re.I), "run_monte_carlo"),
    (re.compile(r"\bsip\b|systematic|invest now|wait\b|lump ?sum|timing|should i (wait|invest now)", re.I), "compare_timing"),
    (re.compile(r"back-?test|historical(ly)? perform|how (did|would).*(perform|do)", re.I), "run_backtest"),
    (re.compile(r"how is the market|market (today|overview|condition|regime)|\bvix\b|\bregime\b|anomal", re.I), "get_market_overview"),
    (re.compile(r"(my |the )?(demo )?(wallet|balance|holdings|p&l|pnl)|how much (cash|money) do i have", re.I), "wallet_status"),
    (re.compile(r"trade history|my trades|past trades|transactions", re.I), "wallet_history"),
    (re.compile(r"ml model|machine learning|how (does|do).*(model|predict|work)|validated|xgboost|random forest|lstm|gru", re.I), "get_model_report"),
    (re.compile(r"how much.{0,60}\binvest|what (percent|percentage|portion|share|part)\b.{0,40}(wallet|cash|money|invest)|"
                r"how much of my (wallet|cash|money)", re.I), "wallet_status"),
    (re.compile(r"how much.{0,60}\binvest|what (percent|percentage|portion|share|part)\b.{0,40}(wallet|cash|money|invest)|"
                r"how much of my (wallet|cash|money)", re.I), "get_investment_plan"),
    (re.compile(r"what (should|do) i (invest|buy|put)|where (should|do) i (invest|put)|invest(ment)? plan|"
                r"\bplan\b|allocat|build.*portfolio|recommend|tomorrow", re.I), "get_investment_plan"),
]


def trade_args(text: str) -> dict | None:
    """Deterministically parse 'sell all my TCS', 'sell 5 shares of GOLDBEES', 'buy Rs 20,000 of gold' ..."""
    m = re.search(r"\b(sell|buy|purchase|liquidate|dump)\b(.*)", text or "", re.I)
    if not m:
        return None
    verb, rest = m.group(1).lower(), m.group(2)
    side = "SELL" if verb in ("sell", "liquidate", "dump") else "BUY"
    rest = re.split(r"[.!?;]|\b(?:now|please|today|tomorrow|right away|immediately|and then|then)\b", rest, flags=re.I)[0].strip()
    if re.fullmatch(r"(all|everything)( (of )?(my )?(holdings|stocks|positions|shares|portfolio|investments))?|my (holdings|portfolio)", rest, re.I)             or (verb == "liquidate" and not rest):
        return {"side": "SELL", "asset": "all"} if side == "SELL" else None
    out: dict = {"side": side}
    am = re.search(r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)", rest, re.I)
    if am:
        out["amount_rs"] = float(am.group(1).replace(",", ""))
        rest = rest.replace(am.group(0), " ")
    else:
        qm = re.match(r"\s*(\d[\d,]*)\s*(?:shares?|units?|qty)?\b", rest, re.I)
        if qm:
            out["quantity"] = int(qm.group(1).replace(",", ""))
            rest = rest[qm.end():]
    rest = re.sub(r"\b(shares?|units?|worth|of|my|all|the|stock|stocks|position|in)\b", " ", rest, flags=re.I)
    asset = re.sub(r"\s+", " ", rest).strip(" ,")
    if not asset:
        return None
    out["asset"] = asset
    return out


_ALL_CASH = re.compile(r"\b(all|complete|entire|whole|full|remaining|rest of)\b(\s+\w+){0,3}?\s+(cash|money|balance|wallet|funds?)\b|"
                       r"\beverything i have\b|\ball (of )?my money\b", re.I)
_AMOUNT_RX = re.compile(r"(rs\.?|inr|₹)?\s*(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|l|crores?|cr|k|thousand)?\b"
                        r"(\s*(%|percent|years?|yrs?|y\b|months?|days?|shares?|units?|times?))?", re.I)


def parse_amount(text: str) -> float | str | None:
    """Rupee amount the user asked to invest/plan: '2,00,000', 'Rs 1.5 lakh', '50k', '1 crore'; 'all' for
    'all/complete/entire cash'. Percentages, durations and share counts are ignored. None if no amount."""
    t = text or ""
    if _ALL_CASH.search(t):
        return "all"
    best = None
    for m in _AMOUNT_RX.finditer(t):
        if m.group(4):
            continue
        v = float(m.group(2).replace(",", ""))
        u = (m.group(3) or "").lower()
        if u.startswith(("lakh", "lac")) or u == "l":
            v *= 1e5
        elif u.startswith("cr"):
            v *= 1e7
        elif u in ("k", "thousand"):
            v *= 1e3
        elif not m.group(1) and "," not in m.group(2) and 1900 <= v <= 2100:
            continue                                           # a year, not rupees
        if v >= 1000 and (best is None or v > best):
            best = v
    return best


AMOUNT_TOOLS = ("invest_plan", "get_investment_plan")
STRATEGY_TOOLS = ("invest_plan", "get_investment_plan", "compare_timing", "run_monte_carlo", "stress_test", "rebalance_portfolio",
                  "start_sip", "project_sip")
_DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(months?|mos?|years?|yrs?)\b", re.I)


def parse_months(text: str) -> int | None:
    """'for 6 months' -> 6, 'for 2 years' -> 24, 'in 3 months' -> 3. None when no duration is given."""
    m = _DURATION.search(text or "")
    if not m:
        return None
    n = float(m.group(1))
    return int(round(n if m.group(2).lower().startswith("mo") else n * 12))


def named_strategy(text: str) -> str | None:
    """The one strategy the user's message names ('maximum returns' -> Max Return), else None."""
    from .tools import _MENTION
    hits = [n for n, rx in _MENTION.items() if re.search(rx, text or "", re.I)]
    return hits[0] if len(hits) == 1 else None


def fix_user_args(tool: str, args: dict, text: str) -> dict:
    """Amounts, durations and strategy names come from the user's own words, never from the model
    (a 4B model drops them, or invents them from earlier turns)."""
    args = dict(args)
    if tool in AMOUNT_TOOLS:
        args.pop("amount_rs", None)
        args.pop("horizon_years", None)
        amt = parse_amount(text)
        if amt is not None:
            args["amount_rs"] = amt
        mo = parse_months(text)
        if mo is not None:
            args["horizon_years"] = round(mo / 12, 3)
    elif tool == "start_sip":
        args.pop("amount_rs", None)
        args.pop("months", None)
        amt = parse_amount(text)
        if isinstance(amt, float):
            args["amount_rs"] = amt
        mo = parse_months(text)
        if mo is not None:
            args["months"] = mo
    elif tool == "project_sip":
        args.pop("monthly_rs", None)
        args.pop("years", None)
        args.pop("initial_rs", None)                     # a starting lump sum only if the user names one (not supported by parsing)
        amt = parse_amount(text)
        if isinstance(amt, float):
            args["monthly_rs"] = amt
        mo = parse_months(text)
        if mo is not None:
            args["years"] = max(1, round(mo / 12))
    elif tool == "set_autonomy" and autonomy_mode(text):
        args["mode"] = autonomy_mode(text)
    if tool in STRATEGY_TOOLS:
        st = named_strategy(text)
        if st:
            args["strategy"] = st
    return args


fix_amount_args = fix_user_args          # backwards-compatible name


def autonomy_mode(text: str) -> str | None:
    """'ask' / 'auto' when the user's message asks to switch the autonomy mode, else None."""
    t = text or ""
    if not re.search(r"\b(switch|turn|set|go|change|put|move|enable|disable|activate|use|back to|stop)\b", t, re.I) \
            or re.search(r"\b(what|explain|how does|difference)\b", t, re.I):
        return None
    if re.search(r"ask[- ]?(first|mode)|manual|confirm (each|every|before)|\b(disable|turn off|stop)\b.{0,25}\b(auto|autonom)", t, re.I):
        return "ask"
    if re.search(r"autonom(ous|y)|\bauto\b|auto[- ]?(mode|trad\w*|execut\w*)", t, re.I):
        return "auto"
    return None


def forced_args(tool: str, text: str) -> dict:
    if tool == "set_autonomy":
        return {"mode": autonomy_mode(text) or "ask"}
    if tool == "trade":
        return trade_args(text) or {}
    if tool == "list_assets" and re.search(r"mutual|\bmfs?\b|index fund|\bfunds?\b|\betfs?\b|nifty|sensex|index|bees", text or "", re.I):
        return {"sector_or_class": "funds"}
    return fix_user_args(tool, {}, text)


def required_tools(text: str) -> list[str]:
    from .tools import user_confirmed
    from .tools_trading import has_action_intent
    t = text or ""
    if user_confirmed(t) and len(t.split()) <= 6 and not re.search(r"rebalanc|invest|sell|buy|manage|plan", t, re.I):
        return []                                        # a plain "yes / confirm" - no analysis needed
    if re.search(r"\bsips?\b|systematic invest", t, re.I):
        if re.search(r"\b(stop|cancel|pause|end|halt)\b", t, re.I):
            return ["stop_sip"]
        if re.search(r"\b(my|active|current|running|existing)\s+sips?\b|sip status|show.{0,12}sips?|list.{0,12}sips?", t, re.I):
            return ["sip_status"]
        if re.search(r"\b(start|begin|set ?up|create|open|launch|activate)\b", t, re.I) and not re.search(r"\bshould i\b|\bwhat if\b", t, re.I):
            return ["start_sip"]
        if re.search(r"\b(every|each|per|a)\s+month|monthly|sip of|plan for a sip|how much.{0,40}sip|grow", t, re.I):
            return ["project_sip"]
        return ["compare_timing"]                        # 'SIP or lump sum?'
    if re.search(r"mutual funds?|\bmfs?\b|index funds?", t, re.I):
        return ["list_assets"]
    if re.search(r"\b(navi|sbi|hdfc|uti|icici pru\w*|axis|parag parikh|ppfas|kotak|motilal|mirae|zerodha|groww|dsp|quant|edelweiss|bandhan|franklin|aditya birla|hsbc|invesco)\b.{0,25}\b(nifty|sensex|index|fund|etf|bees|gold|liquid)", t, re.I):
        return ["list_assets"]
    if autonomy_mode(t):
        return ["set_autonomy"]                          # the mode must really change, not just be claimed in prose
    if re.search(r"\b(confirm|cancel|reset)\b|\badd\b.*\b(funds?|money|cash)\b|autonomy|ask[- ]first", t, re.I):
        return []
    if has_action_intent(t):
        if re.search(r"rebalanc", t, re.I):
            return ["rebalance_portfolio"]
        if re.search(r"\bmanage\b|take care|do whatever|fix (my )?portfolio|auto[- ]?manage|de-?risk", t, re.I):
            return ["auto_manage_portfolio"]
        if trade_args(t):
            return ["trade"]
        if re.search(r"\b(invest|deploy|put|buy|execute|stage|place|go ahead|do it)\b", t, re.I):
            return ["invest_plan"]
        return []
    if re.search(r"(check|review|audit|health)\b.*\b(portfolio|holdings)|portfolio health|how is my portfolio", t, re.I):
        return ["check_portfolio"]
    out = []
    for rx, tool in INTENT_RULES:
        if rx.search(t) and tool not in out:
            out.append(tool)
    if "compare_strategies" in out and "get_investment_plan" in out:
        out.remove("get_investment_plan")
    if len(out) > 2:
        out = out[:2]
    return out


_THINK = re.compile(r"<think>.*?</think>", re.S)


def _strip_think(t: str) -> str:
    t = _THINK.sub("", t)
    if "</think>" in t:
        t = t.split("</think>", 1)[1]
    return t.strip()


class Agent:
    def __init__(self, session: Session, model: str = C.LLM_MODEL, think: bool = False,
                 max_steps: int = C.AGENT_MAX_STEPS):
        import ollama
        self.client = ollama.Client(host=C.OLLAMA_HOST)
        self.session = session
        self.model = model
        self.think = think
        self.max_steps = max_steps
        self.history: list[dict] = []        # only user / assistant text kept across turns

    # ------------------------------------------------------------------
    def _state_line(self) -> str:
        s = self.session
        p = s.profile.normalised()
        w = s.wallet
        sel = s.selected_strategy or "none yet"
        pend = w.pending()
        return (f"[State] Data as of {s.engine.md.last_date.date()}. Profile ({'user-set' if s.profile_confirmed else 'DEFAULT'}): "
                f"{s.profile.describe()}. Selected strategy: {sel}. Demo wallet cash: Rs.{w.cash():,.0f}. "
                f"Staged order awaiting confirmation: {pend['label'] if pend else 'none'}. "
                f"Autonomy mode: {s.autonomy.upper()} ({'execute trades when told to' if s.autonomy == 'auto' else 'stage and wait for confirm'}).")

    def reset(self) -> None:
        self.history.clear()

    def stream(self, user_text: str) -> Iterator[AgentEvent]:
        """Run one user turn, yielding events (tool calls/results and streamed text)."""
        s = self.session
        s.last_user_text = user_text
        msgs: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + self._state_line()}]
        msgs += self.history[-12:]
        msgs.append({"role": "user", "content": user_text})
        calls_made: list[tuple[str, dict]] = []
        final_text = ""

        called: set[str] = set()
        need = required_tools(user_text)
        forced = False

        for step in range(self.max_steps):
            content, tool_calls = "", []
            missing = [t for t in need if t not in called]
            try:
                resp = self.client.chat(model=self.model, messages=msgs, tools=TOOL_SCHEMAS, stream=True,
                                        think=self.think,
                                        options={"temperature": C.LLM_TEMPERATURE, "num_ctx": C.LLM_NUM_CTX},
                                        keep_alive="30m")
                for chunk in resp:
                    m = chunk.message
                    if m.content:
                        content += m.content
                        if not tool_calls and not missing:       # buffer while a required tool is still missing
                            yield AgentEvent("text", data=m.content)
                    if m.tool_calls:
                        tool_calls.extend(m.tool_calls)
            except Exception as e:
                yield AgentEvent("error", data=f"LLM call failed: {e}. Is Ollama running (`ollama serve`) "
                                               f"and is the model `{self.model}` pulled?")
                return

            if not tool_calls and missing and not forced:
                # The model tried to answer without the tool this request needs -> run it ourselves.
                forced = True
                synth = [(t, forced_args(t, user_text)) for t in missing]
                msgs.append({"role": "assistant", "content": "",
                             "tool_calls": [{"function": {"name": n, "arguments": a}} for n, a in synth]})
                for name, args in synth:
                    calls_made.append((name, args))
                    called.add(name)
                    yield AgentEvent("tool_call", name, args)
                    result = call_tool(s, name, args)
                    yield AgentEvent("tool_result", name, result)
                    msgs.append({"role": "tool", "tool_name": name,
                                 "content": json.dumps(result, default=str, ensure_ascii=False)})
                msgs.append({"role": "user", "content": "(Answer the original question using ONLY the tool results above. "
                                                        "Do not mention assets or numbers that are not in them.)"})
                continue

            if not tool_calls:
                final_text = _strip_think(content)
                if missing:          # still no tool - show whatever we have
                    yield AgentEvent("text", data=final_text)
                break

            msgs.append({"role": "assistant", "content": content,
                         "tool_calls": [{"function": {"name": tc.function.name,
                                                      "arguments": dict(tc.function.arguments or {})}}
                                        for tc in tool_calls]})
            for tc in tool_calls:
                name, args = tc.function.name, dict(tc.function.arguments or {})
                args = fix_user_args(name, args, user_text)
                calls_made.append((name, args))
                called.add(name)
                yield AgentEvent("tool_call", name, args)
                result = call_tool(s, name, args)
                yield AgentEvent("tool_result", name, result)
                msgs.append({"role": "tool", "tool_name": name,
                             "content": json.dumps(result, default=str, ensure_ascii=False)})
        else:
            final_text = "I ran out of steps before finishing - please ask again more specifically."

        if not final_text:
            final_text = "(no answer)"
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": final_text})
        yield AgentEvent("done", data=AgentReply(final_text, calls_made, s.take_artifacts()))

    def chat(self, user_text: str, on_event: Callable[[AgentEvent], None] | None = None) -> AgentReply:
        reply = None
        for ev in self.stream(user_text):
            if on_event:
                on_event(ev)
            if ev.kind == "done":
                reply = ev.data
            elif ev.kind == "error":
                reply = AgentReply(str(ev.data))
        return reply or AgentReply("(no reply)")
