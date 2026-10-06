"""Realistic costs of delivery trades on the NSE, per asset class (approximate 2025 fee schedule; brokers differ, check yours).

Per side, as a fraction of the traded value:
  stocks            STT 0.1% (buy and sell), stamp duty 0.015% (buy), NSE transaction charge 0.00297%, SEBI fee 0.0001%,
                    GST 18% on the exchange and SEBI fees, brokerage 0 (discount broker, delivery), half bid-ask spread 0.05%
  equity ETFs       STT 0.001% (sell only), stamp duty 0.015% (buy), exchange and SEBI fees + GST, half spread 0.05%
  gold / gilt ETFs  no STT, stamp duty 0.015% (buy), exchange and SEBI fees + GST, half spread 0.10% (thinner order books)
  liquid ETF        stamp duty 0.015% (buy), exchange and SEBI fees + GST, half spread 0.01%
Fixed: a depository (DP) charge of about Rs 15.93 (Rs 13.50 + GST) for each security sold on a day, whatever the amount;
it matters for small accounts that rebalance often.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

EXCH = 0.0000297 + 0.000001                     # NSE transaction charge + SEBI turnover fee
GST = 0.18
STAMP_BUY = 0.00015
DP_CHARGE_RS = 15.93

_STT = {"stock": (0.001, 0.001), "etf": (0.0, 0.00001), "gold": (0.0, 0.0), "bond": (0.0, 0.0), "cash": (0.0, 0.0)}
_SPREAD = {"stock": 0.0005, "etf": 0.0005, "gold": 0.0010, "bond": 0.0010, "cash": 0.0001}


def per_side(cls: str) -> tuple[float, float]:
    """(buy, sell) cost as a fraction of the traded value for an asset class."""
    stt_b, stt_s = _STT[cls]
    fees = EXCH * (1 + GST)
    return stt_b + STAMP_BUY + fees + _SPREAD[cls], stt_s + fees + _SPREAD[cls]


def rates(symbols) -> tuple[pd.Series, pd.Series]:
    """Buy and sell cost rates per symbol."""
    b = {s: per_side(C.UNIVERSE[s][2])[0] for s in symbols}
    s_ = {s: per_side(C.UNIVERSE[s][2])[1] for s in symbols}
    return pd.Series(b), pd.Series(s_)


def trade_cost(trade_w: pd.Series, buy: pd.Series, sell: pd.Series, mult: float = 1.0) -> float:
    """Cost of a rebalance as a fraction of the portfolio, for weight changes `trade_w` (+ buy, - sell)."""
    t = trade_w.values
    return float(mult * (np.clip(t, 0, None) @ buy.reindex(trade_w.index).values + np.clip(-t, 0, None) @ sell.reindex(trade_w.index).values))
