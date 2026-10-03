"""Central configuration for *If I Invest Tomorrow* - the financial decision simulator.

Everything that is an *assumption* (risk-free rate, risk-tolerance limits, shock sizes,
sector rate-sensitivities ...) lives here so it is easy to audit and change.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROC = ROOT / "data" / "processed"
MODELS_DIR = ROOT / "models"
REPORTS_DIR = ROOT / "reports"
DB_PATH = ROOT / "data" / "demo_wallet.sqlite"

for _p in (DATA_RAW, DATA_PROC, MODELS_DIR, REPORTS_DIR):
    _p.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------- #
# LLM agent
# --------------------------------------------------------------------------- #
LLM_MODEL = os.environ.get("IFIT_LLM_MODEL", "qwen3.5:4b")          # served locally by Ollama
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
LLM_TEMPERATURE = 0.2
LLM_NUM_CTX = 16384
AGENT_MAX_STEPS = 8                # max tool-call rounds for one user message

# --------------------------------------------------------------------------- #
# Market / data
# --------------------------------------------------------------------------- #
HISTORY_YEARS = 12
MARKET_SYMBOL = "^NSEI"            # NIFTY 50 - the CAPM market proxy
TRADING_DAYS = 252
RISK_FREE = 0.06                   # annual risk-free rate, ~ India 10Y G-Sec (assumption)
EQUITY_RISK_PREMIUM_PRIOR = 0.055  # long-run ERP prior blended with history (assumption)

MACRO = {
    "^INDIAVIX": "India VIX",
    "BZ=F": "Brent crude (USD)",
    "USDINR=X": "USD/INR",
    "^TNX": "US 10Y yield (%)",
    "^NSEBANK": "NIFTY Bank index",
}

# Long history (Yahoo "max", NIFTY from 2007, VIX from 2008) used ONLY by the regime model, so it learns the 2008 crash as
# well as 2020. Calibration backtest: mean interval-coverage gap 0.051 -> 0.037 (scripts/extended_data.py mc).
REGIME_LONG_SYMBOLS = {MARKET_SYMBOL: "market", "^INDIAVIX": "vix"}

# symbol -> (display name, sector, asset class)
# asset classes: stock | etf | gold | bond | cash
UNIVERSE: dict[str, tuple[str, str, str]] = {
    # --- Equities (NIFTY 50 constituents across sectors)
    "RELIANCE.NS":   ("Reliance Industries",   "Energy",    "stock"),
    "ONGC.NS":       ("ONGC",                  "Energy",    "stock"),
    "COALINDIA.NS":  ("Coal India",            "Energy",    "stock"),
    "TCS.NS":        ("Tata Consultancy Svcs", "IT",        "stock"),
    "INFY.NS":       ("Infosys",               "IT",        "stock"),
    "HCLTECH.NS":    ("HCL Technologies",      "IT",        "stock"),
    "HDFCBANK.NS":   ("HDFC Bank",             "Banking",   "stock"),
    "ICICIBANK.NS":  ("ICICI Bank",            "Banking",   "stock"),
    "SBIN.NS":       ("State Bank of India",   "Banking",   "stock"),
    "KOTAKBANK.NS":  ("Kotak Mahindra Bank",   "Banking",   "stock"),
    "BAJFINANCE.NS": ("Bajaj Finance",         "Finance",   "stock"),
    "ITC.NS":        ("ITC",                   "FMCG",      "stock"),
    "HINDUNILVR.NS": ("Hindustan Unilever",    "FMCG",      "stock"),
    "NESTLEIND.NS":  ("Nestle India",          "FMCG",      "stock"),
    "LT.NS":         ("Larsen & Toubro",       "Infra",     "stock"),
    "ULTRACEMCO.NS": ("UltraTech Cement",      "Infra",     "stock"),
    "NTPC.NS":       ("NTPC",                  "Power",     "stock"),
    "POWERGRID.NS":  ("Power Grid Corp",       "Power",     "stock"),
    "SUNPHARMA.NS":  ("Sun Pharma",            "Pharma",    "stock"),
    "DRREDDY.NS":    ("Dr Reddy's Labs",       "Pharma",    "stock"),
    "CIPLA.NS":      ("Cipla",                 "Pharma",    "stock"),
    "MARUTI.NS":     ("Maruti Suzuki",         "Auto",      "stock"),
    "M&M.NS":        ("Mahindra & Mahindra",   "Auto",      "stock"),
    "BHARTIARTL.NS": ("Bharti Airtel",         "Telecom",   "stock"),
    "TITAN.NS":      ("Titan Company",         "Consumer",  "stock"),
    "TATASTEEL.NS":  ("Tata Steel",            "Metals",    "stock"),
    # --- ETFs / index funds
    "NIFTYBEES.NS":  ("Nippon NIFTY 50 BeES",  "Broad Market", "etf"),
    "JUNIORBEES.NS": ("Nippon Nifty Next 50",  "Broad Market", "etf"),
    "BANKBEES.NS":   ("Nippon Bank BeES",      "Banking",   "etf"),
    # --- Gold / bonds / cash proxies
    "GOLDBEES.NS":   ("Nippon Gold BeES",      "Gold",      "gold"),
    "LTGILTBEES.NS": ("Nippon Gilt ETF (G-Sec)", "Bonds",   "bond"),
    "LIQUIDBEES.NS": ("Nippon Liquid BeES",    "Cash",      "cash"),
}

BENCH_SYMBOLS = [MARKET_SYMBOL]

# Liquid-fund (cash) proxy: the traded LIQUIDBEES NAV is flat (~Rs.1000) with distributions that
# Yahoo does not capture, so its return series is rebuilt from the approximate RBI repo-rate path
# minus a 0.35 % expense/spread. (effective-from date, repo rate % p.a.) - approximate history.
REPO_RATE_HISTORY = [
    ("2014-01-01", 8.00), ("2015-01-15", 7.75), ("2015-03-04", 7.50), ("2015-06-02", 7.25),
    ("2015-09-29", 6.75), ("2016-04-05", 6.50), ("2016-10-04", 6.25), ("2017-08-02", 6.00),
    ("2018-06-06", 6.25), ("2018-08-01", 6.50), ("2019-02-07", 6.25), ("2019-04-04", 6.00),
    ("2019-06-06", 5.75), ("2019-08-07", 5.40), ("2019-10-04", 5.15), ("2020-03-27", 4.40),
    ("2020-05-22", 4.00), ("2022-05-04", 4.40), ("2022-06-08", 4.90), ("2022-08-05", 5.40),
    ("2022-09-30", 5.90), ("2022-12-07", 6.25), ("2023-02-08", 6.50), ("2025-02-07", 6.25),
    ("2025-04-09", 6.00), ("2025-06-06", 5.50),
]
LIQUID_SPREAD = 0.0035
DEFENSIVE_CLASSES = {"gold", "bond", "cash"}
SECTORS = sorted({v[1] for v in UNIVERSE.values() if v[2] == "stock"})

# --------------------------------------------------------------------------- #
# Risk tolerance profiles (diversification caps + loss limits used to *recommend*)
# --------------------------------------------------------------------------- #
RISK_PROFILES = {
    "low": dict(
        stock_cap=0.08, etf_cap=0.30, gold_cap=0.25, bond_cap=0.40, cash_cap=0.40,
        max_annual_vol=0.11, max_stress_loss=0.10, max_var95_1y=0.08,
    ),
    "medium": dict(
        stock_cap=0.15, etf_cap=0.35, gold_cap=0.20, bond_cap=0.30, cash_cap=0.25,
        max_annual_vol=0.15, max_stress_loss=0.18, max_var95_1y=0.15,
    ),
    "high": dict(
        stock_cap=0.25, etf_cap=0.40, gold_cap=0.15, bond_cap=0.20, cash_cap=0.15,
        max_annual_vol=0.22, max_stress_loss=0.30, max_var95_1y=0.28,
    ),
}
MIN_PREFERRED_CLASS_WEIGHT = 0.10   # if user explicitly prefers Gold / Bonds
MIN_WEIGHT_THRESHOLD = 0.01         # weights below this are dropped from the plan

# --------------------------------------------------------------------------- #
# Stress-test assumptions
# --------------------------------------------------------------------------- #
MARKET_SHOCKS = [-0.02, -0.05, -0.10]
SECTOR_CRASH = -0.25                # shock to every stock in the crashing sector
OIL_SHOCK = 0.25                    # +25 % Brent move
RATE_SHOCK_BPS = 100                # +100 bps parallel shift
# sensitivity of 1 % ... expressed as % price change per +100bps (assumption, from
# typical rate-sensitivity of the sector's earnings / valuation multiples)
SECTOR_RATE_SENSITIVITY = {
    "Banking": -0.04, "Finance": -0.07, "Auto": -0.05, "Infra": -0.05, "Power": -0.04,
    "Consumer": -0.04, "Broad Market": -0.03, "Telecom": -0.03, "Energy": -0.015,
    "Metals": -0.02, "Pharma": -0.01, "IT": -0.005, "FMCG": -0.015,
    "Gold": -0.015, "Cash": 0.0,
}
BOND_DURATION = 8.0                 # effective duration of the G-Sec ETF (years)
HISTORICAL_CRASHES = {
    "COVID crash (Jan-Mar 2020)": ("2020-01-20", "2020-03-23"),
    "Taper/IL&FS stress (Sep-Oct 2018)": ("2018-09-03", "2018-10-26"),
    "Global rate-hike selloff (Oct 2021-Jun 2022)": ("2021-10-18", "2022-06-17"),
}

# --------------------------------------------------------------------------- #
# Monte Carlo
# --------------------------------------------------------------------------- #
MC_PATHS = 10_000
MC_T_DOF = 5                        # Student-t degrees of freedom for fat tails
MC_PARAM_UNCERTAINTY = True        # draw a per-path error in the expected return (standard error sigma/sqrt(lookback years))
COV_LOOKBACK_YEARS = 5

# --------------------------------------------------------------------------- #
# Demo wallet (paper trading)
# --------------------------------------------------------------------------- #
DEMO_STARTING_CASH = 1_000_000.0    # Rs.10 lakh of virtual money
BROKERAGE_RATE = 0.0005             # 0.05 %
SLIPPAGE_RATE = 0.0005              # 0.05 %
CURRENCY = "Rs."
