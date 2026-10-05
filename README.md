# If I Invest Tomorrow - A Financial Decision Simulator

Course project 23CSE322 (Financial Engineering), Team 01. An AI-powered, chatbot-first decision simulator for
Indian markets: given an amount, horizon (1/3/5 y), risk tolerance, target return and preferred sectors it
recommends **tomorrow's concrete investment plan**, simulates thousands of futures, stress-tests it, compares five
strategies, and lets you "execute" it with **demo money**. The chat agent is **Qwen3.5-4B running locally via Ollama**.

> Everything is a model-based simulation on historical data. No real money, broker or exchange is touched. Not investment advice.

## Quick start

```bash
pip install -r requirements.txt
ollama pull qwen3.5:4b                  # already installed on this machine
python scripts/download_data.py         # datasets + quarterly results (Yahoo Finance) -> data/raw, data/earnings, data/processed
python scripts/train_models.py --gru    # ML walk-forward validation + models -> models/, reports/
start.bat                               # API on :8000 + Next.js UI on :3000  -> http://localhost:3000
```

### Docker

```bash
docker compose up -d --build          # UI http://localhost:3000, API http://localhost:8000/docs
docker compose --profile ollama up -d --build   # also run Ollama in a container (NVIDIA GPU; pulls qwen3.5:4b once)
docker compose down                   # stop (volumes, wallet and models are kept); add -v to wipe them
```

- Two images: `ifit-api` (Python 3.13, FastAPI, analytics + agent client) and `ifit-web` (Next.js standalone, non-root).
- **First start** of the API container downloads the datasets and trains the ML models into named volumes (about 3 minutes);
  later starts are instant. The demo wallet (SQLite) lives in the `ifit-data` volume and survives restarts.
- By default the API uses the **Ollama running on your machine** (`host.docker.internal:11434`). With `--profile ollama`
  set `OLLAMA_HOST=http://ollama:11434` in `.env` (copy `.env.example`).
- The browser calls the API directly, so `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`) must be reachable from your
  browser; changing it needs `--build`. Ports: `WEB_PORT` / `API_PORT`.

Other entry points: `python scripts/chat_cli.py` (agent in the terminal), `streamlit run app.py` (legacy Streamlit UI),
`python scripts/generate_report.py` (sample report), `pytest tests -q` (72 tests),
`python scripts/test_agent.py` (23-turn end-to-end agent test, needs Ollama), `python scripts/test_api.py` (REST smoke test).

### Web UI (`web/`: Next.js 16 + TypeScript + Tailwind CSS 4 + shadcn/ui + Recharts)

| Page | What it does |
|---|---|
| Dashboard | market snapshot, current plan, wallet, portfolio alerts |
| AI Agent | streaming chat with Qwen3.5-4B; tool chips; plans, charts and executed orders render inline |
| Simulator | put in an amount (plus an optional monthly SIP), choose any mix of assets, and get the projection graph, a year-by-year table (worst / median / best, chance of profit, vs fixed deposit and NIFTY) and a per-asset breakdown |
| Investment Planner | profile form -> Plan / Strategies / Monte Carlo / Stress / Now-vs-wait-vs-SIP / Backtest, "Invest this plan" |
| Market & Models | regimes, anomalies, correlation heatmap, asset analytics, ML validation |
| Demo Wallet | holdings, buy/sell, auto-manage, rebalance, health check, staged orders, trades, equity curve |

The Python side is a FastAPI service (`ifit/api.py`, docs at http://127.0.0.1:8000/docs) with a streaming SSE chat endpoint.

### Autonomy: the agent invests, sells and manages by itself

- **Autonomous mode (default, top-bar switch):** when you *instruct* the agent ("invest it", "sell all my TCS", "rebalance",
  "manage my portfolio") it executes immediately with demo money. Questions ("should I sell TCS?") and the word "stage" never
  execute - they only analyse or stage. **Ask-first mode** stages every order until you confirm.
- **Portfolio health check / auto-manage:** detects stop-loss (-15 % from cost), concentration drift past the caps, volatility above
  your risk limit, bear-regime equity exposure and idle cash, then sells / trims / de-risks / rebalances / deploys cash.
- **Autopilot (top-bar switch):** runs that review as soon as it is switched on and after every market-data refresh.
- UI buttons are explicit instructions and always execute; everything is demo money only.

## What the agent can do (all tools are real code, the LLM only orchestrates + explains)

| Ask the agent ... | Tool | Proposal module |
|---|---|---|
| "How is the market today?" | `get_market_overview` | 1, 3 (regime, anomaly) |
| "Tell me about TCS" | `analyze_asset` | 2, 4 (beta, CAPM, VaR, ML forecast) |
| "I have Rs 1 lakh, 3 years, medium risk, want 12%, like IT & banking" | `set_profile` | inputs |
| "What should I invest in tomorrow?" | `get_investment_plan` | 5, 8 (allocation, amounts, shares) |
| "Compare the five strategies" | `compare_strategies` | 7 |
| "What's the chance I hit my target? best/worst case?" | `run_monte_carlo` | 6 |
| "Stress test it against a crash / oil / rate shock" | `stress_test` | 4, 6 |
| "Invest now, wait, or SIP?" | `compare_timing` | methodology step 8 |
| "How would this have done over 3 years?" | `run_backtest` | validation |
| "How were the ML models validated?" | `get_model_report` | 3 |
| "Invest it" / "Sell all my TCS" / "Buy Rs 20,000 of gold" | `invest_plan`, `trade` | demo money |
| "Rebalance" / "Check my portfolio" / "Manage my portfolio" | `rebalance_portfolio`, `check_portfolio`, `auto_manage_portfolio` | demo money |
| "Switch to ask-first mode" -> "confirm" | `set_autonomy`, `confirm_pending_order`, `cancel_pending_order` | demo money |
| "Show wallet / history", "add funds", "reset" | `wallet_*`, `add_demo_funds`, `reset_wallet` | demo money |
| "Start a SIP of 10000 for 12 months" / "What would 10000 a month become?" / "Stop my SIP" | `start_sip`, `project_sip`, `sip_status`, `stop_sip` | demo money (instalments run when new monthly data arrives) |

**Safety by construction.** In ask-first mode trades are *staged* and only execute when the user's own next message confirms
(checked in code, not by the LLM); in autonomous mode execution requires an instruction-style user message (checked in code). Wallet reset needs an explicit "reset"+confirm. A small 4B model tends to improvise
numbers, so an **intent guard** forces the relevant tool when a request needs one and buffers any un-grounded text;
the dashboard shows the tool's real tables/charts next to every answer.

## Architecture

```
data.py  -> features.py -> ml.py (regimes, anomalies, return models)
                       -> risk.py (CAPM, Ledoit-Wolf cov, VaR/CVaR, drawdown, stress)
optimizer.py (min-var, max-Sharpe, max-return, target-return, min-CVaR, frontier)
montecarlo.py (fat-tailed + regime switching + shocks, timing comparison)
engine.py  (5 strategies, recommendation rule, plan, backtest)   wallet.py (SQLite paper trading)
tools.py -> agent.py (Qwen3.5-4B tool loop)  -> app.py (Streamlit)  viz.py (Plotly)
```

### Module mapping to the proposal

1. **Data** - 26 NSE stocks (NIFTY 50 members, 12 sectors), 3 ETFs, gold ETF, G-Sec ETF, liquid fund, NIFTY 50, India VIX,
   Brent, USD/INR, US10Y; 12 years daily OHLCV. Cleaning: NSE-calendar alignment, gap fill (<=5d), bad-tick detection
   (found & fixed a wrong-scale print on 19-20 Dec 2019 in 3 ETFs), common-history check.
2. **Features** - returns (1d-252d), volatility, SMA ratios, RSI, MACD, drawdown, rolling beta/corr/skew, market state.
3. **ML** - Gaussian-mixture *market regimes* (Bull/Calm, Neutral, Bear/Volatile), Isolation-Forest *anomaly detection*,
   *return estimation* and *volatility forecasting*, each with hyper-parameters tuned on 2019-20 only and scored on an untouched
   expanding-window walk-forward (2021-26, purged targets; `scripts/model_search.py`). **Volatility is forecastable**: a Ridge model on realised and
   range-based (Parkinson / Garman-Klass / Rogers-Satchell from daily High-Low), long-run-level, seasonal (same window last year, results season),
   asset-class and earnings-calendar features (each stock's projected next results date and its typical result-day jump, from about 20 years of
   quarterly results), blended 85/15 with the trailing quarter's volatility, reaches walk-forward R2 0.60 on log volatility (0.603; error 24.6 %) against 0.50 (29 %) for the best "same as the last quarter" rule and 0.39 (31 %) for "same as last month"; it feeds the
   next-month risk figures. (An earlier 0.72 figure counted the near-constant liquid-fund series and was overstated; it is excluded now. Random
   Forest, XGBoost and LightGBM scored lower than Ridge.) **Returns are barely forecastable**: every fitted model (Ridge, Random Forest, XGBoost,
   LightGBM, GRU) shows no skill on the 2017-20 validation years. What does is a fixed, documented composite of 1-month reversal and 12-1 month
   momentum measured on residual returns (after each stock's beta x market move; nothing fitted): validation IC 0.061 (t 3.2), walk-forward IC 0.046
   (t 2.2), 0.052 over 2017-26. It is used only as a relative tilt weighted by measured IC (23 %) on top of a CAPM + history prior; in a
   monthly-rebalanced backtest it does not pay after trading costs (turnover 4.5x -> 5.9x a year).
   The Monte Carlo itself is checked against reality (`scripts/calibration.py`: 104 one-year forecasts from quarterly dates 2019-25, information as of
   each date): the 90 % band held the outcome 82 % of the time (88 % outside 2020, 55 % for forecasts made in the 2020 crash year), and realised returns beat
   the expected return by 7 % on average. The simulator includes the estimation error of the expected return (sigma/sqrt(5 years), not tuned), a per-path
   volatility level (sd 0.17, measured on pre-2018 data), and the regime model learns from NIFTY/VIX history back to 2008 (both crashes, 2008 and 2020).
4. **Risk** - CAPM (beta, expected return), Ledoit-Wolf covariance, Sharpe, historical VaR/CVaR, max drawdown, stress tests:
   market -2/-5/-10 %, sector crash (-25 %), +100 bp rate shock, +25 % oil shock (data-driven oil betas), and replays of
   COVID-2020, 2018 and 2021-22.
5. **Optimisation** - long-only, per-asset caps by risk profile, preferred-sector universe, efficient frontier (SLSQP/LP).
6. **Monte Carlo** - 10,000 paths; Student-t shocks; 3-state Markov regime switching started from today's regime;
   day-0 shock scenarios; outputs P(positive), P(target), VaR/CVaR, drawdown, best/median/worst, fan chart.
7. **Strategies** - Max Return, Min Risk, Max Sharpe, **Goal-Based** (frontier point with highest simulated P(target)),
   **Crash-Resistant** (min-CVaR over history *plus* all stress scenarios). Recommendation rule: best P(target) among
   strategies inside the user's risk limits (vol, worst stress loss, 1-y VaR).
8. **Dashboard** - 8 views (chat, plan, strategies, Monte Carlo, stress, timing/backtest, market & models, wallet).

## Evaluation

Full, reproducible out-of-sample evaluation of every layer is in [`reports/evaluation.md`](reports/evaluation.md)
(`scripts/eval_models.py`, `eval_risk.py`, `eval_portfolio.py`, `eval_report.py`; settings chosen on 2019-20, scored on 2021-26):

- **Return signal** - residual reversal + momentum composite (round 7): IC 0.046 (t 2.2) on 2021-26, 0.061 (t 3.2) on the 2017-20 validation,
  0.052 over all ten years. Fitted models (Ridge IC 0.027, trees, GRU, LightGBM ranker) have no skill on validation.
- **Volatility** - R2 0.603 vs 0.503 for the best naive rule (within-asset 0.216), ahead of it in every year; seasonal (round 6), asset-class
  (round 7) and earnings-calendar (round 9) features. Post-earnings drift was tested for returns and shows no skill here. GARCH and implied-volatility features, log-VIX terms, recency weighting, Elastic Net, Huber, boosted trees and a 63-day target do not beat it on validation.
- **Nested selection and ensembles** (round 8, re-checked after round 9) - choosing the best candidate, a top-3 average or stacking weights each year from
  earlier years only does not beat the fixed models on 2021-26 (volatility R2 0.597-0.600 vs 0.603; return IC 0.036-0.046 vs 0.046).
- **Monte Carlo** - 50/75/90/95/99% intervals hold 52/74/82/88/97% (44/69/81/84/93% before adding parameter and volatility uncertainty and the 2008- regime history); fatter tails or a block
  bootstrap do not fix the outer tails (the miss is the 2020 crash).
- **Regimes / anomalies** - both act as risk labels: after a Neutral regime a 5% market drawdown within 21 days is 35% likely vs 13% after Calm;
  anomaly flags precede much higher volatility (21-23% vs 13%) but not lower returns.
- **Portfolio (walk-forward, monthly, 0.10% costs)** - the volatility model improves risk-adjusted return (Sharpe 0.60 -> 0.80 in the max-Sharpe
  family) and the regime overlay cuts drawdown (full system Sharpe 0.77, -13.2%); the return tilt costs more in turnover than it earns (Sharpe 0.80 -> 0.75). Half-step rebalancing halves turnover but lowers Sharpe. Every variant beats the NIFTY ETF on Sharpe, but an
  equal-weight basket of the 26 stocks matches the full system in this one bull-market sample.

## Assumptions & limitations (all in `ifit/config.py`)

- Risk-free 6 % p.a.; ERP blends history with a 5.5 % prior; expected returns = 0.6 CAPM + 0.4 (clipped 5y history) + ML tilt.
- Rate-shock sensitivities per sector and G-Sec duration (8) are assumptions; oil/market betas are estimated.
- The Liquid-fund series is rebuilt from the approximate RBI repo path (Yahoo's NAV excludes distributions);
  the G-Sec ETF is thinly traded, so tight bad-print filtering is applied.
- Prices are Yahoo's adjusted closes; orders fill at the latest close with 0.05 % brokerage + 0.05 % slippage.
- Index (`^NSEI`) vs ETF timing noise gives NIFTYBEES a beta of ~0.89 instead of 1.
- Qwen3.5-4B is small: it occasionally mislabels a ticker in prose. The structured tables/charts under each answer are authoritative.
