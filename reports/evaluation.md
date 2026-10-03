# Evaluation of the model stack

Everything is out-of-sample: settings chosen on 2019-20, scored on a 2021-26 expanding-window walk-forward with purged targets; regime and anomaly models are refit each year on pre-year data. The liquid fund (a flat accrual) is excluded from all model scores.

## 1. Return signal (21-day relative return)

| Features / target | mean IC | median | sd | IR | % days > 0 | t (Newey-West) | t (independent windows) | IC on 2019-20 validation |
|---|---|---|---|---|---|---|---|---|
| base / relative return (production) | +0.027 | +0.022 | 0.223 | +0.12 | 55% | +1.38 | +1.22 | -0.012 |
| base / excess vs NIFTY | +0.045 | +0.040 | 0.230 | +0.19 | 56% | +2.31 | +1.45 | -0.018 |
| base / sector-neutral | +0.008 | +0.001 | 0.246 | +0.03 | 50% | +0.38 | +0.50 | +0.004 |
| base / volatility-adjusted | +0.014 | +0.031 | 0.235 | +0.06 | 55% | +0.68 | +0.79 | -0.022 |
| base / cross-sectional rank | +0.032 | +0.027 | 0.237 | +0.14 | 54% | +1.50 | +1.54 | -0.018 |
| base + relative strength / relative return (production) | +0.041 | +0.041 | 0.208 | +0.20 | 56% | +2.22 | +1.61 | -0.023 |
| base + relative strength / excess vs NIFTY | +0.052 | +0.061 | 0.201 | +0.26 | 61% | +3.06 | +1.82 | -0.024 |
| base + relative strength / sector-neutral | +0.014 | +0.022 | 0.188 | +0.07 | 54% | +0.87 | +1.01 | +0.010 |
| base + relative strength / volatility-adjusted | +0.031 | +0.039 | 0.217 | +0.14 | 56% | +1.59 | +1.39 | -0.028 |
| base + relative strength / cross-sectional rank | +0.040 | +0.046 | 0.211 | +0.19 | 58% | +2.13 | +1.79 | -0.019 |
| base + RS + cross-sectional ranks / relative return (production) | +0.042 | +0.054 | 0.200 | +0.21 | 59% | +2.36 | +1.79 | -0.006 |
| base + RS + cross-sectional ranks / excess vs NIFTY | +0.014 | +0.017 | 0.211 | +0.07 | 53% | +0.78 | +0.68 | -0.007 |
| base + RS + cross-sectional ranks / sector-neutral | +0.014 | +0.014 | 0.181 | +0.08 | 53% | +0.92 | +1.28 | +0.011 |
| base + RS + cross-sectional ranks / volatility-adjusted | +0.027 | +0.043 | 0.204 | +0.13 | 57% | +1.50 | +1.43 | -0.017 |
| base + RS + cross-sectional ranks / cross-sectional rank | +0.040 | +0.046 | 0.205 | +0.19 | 58% | +2.17 | +1.92 | -0.006 |

The IC on the 2019-20 validation window is at or below zero for every configuration, so validation cannot pick a winner (it picked `base + RS + cross-sectional ranks / sector-neutral`, out-of-sample IC +0.014). Adding relative-strength features (vs index and vs sector) lifts the out-of-sample IC from 0.027 to 0.041 (t 2.2 Newey-West, 1.6 on independent windows) and helps on all five targets (stacking cross-sectional ranks on top does not help consistently), but it is not significant at 5% on independent windows and was not confirmed by the validation window, so it is a candidate, not adopted. Sector-neutral targets are weaker: most of the little signal is cross-sector.

### By year (production model)

| Year | IC | IC t-stat | RMSE | RMSE of historical mean | Direction |
|---|---|---|---|---|---|
| 2021 | +0.007 | +0.17 | 0.0688 | 0.0688 | 43.8% |
| 2022 | +0.052 | +1.05 | 0.0559 | 0.0559 | 48.6% |
| 2023 | +0.075 | +1.27 | 0.0481 | 0.0481 | 47.8% |
| 2024 | -0.042 | -1.17 | 0.0560 | 0.0560 | 49.2% |
| 2025 | +0.017 | +0.45 | 0.0491 | 0.0491 | 48.1% |
| 2026 | +0.067 | +1.35 | 0.0598 | 0.0599 | 48.2% |

| Rolling IC window | min | median | max | share of windows > 0 |
|---|---|---|---|---|
| 3-month | -0.156 | +0.037 | +0.262 | 64% |
| 6-month | -0.120 | +0.032 | +0.136 | 78% |
| 12-month | -0.062 | +0.030 | +0.119 | 74% |

## 2. Volatility model

| Model | R2 | within-asset R2 | avg. error | correlation |
|---|---|---|---|---|
| Ridge (production) | 0.570 | 0.170 | 25.0% | 0.756 |
| Elastic Net | 0.567 | 0.156 | 24.9% | 0.754 |
| Huber regression | 0.574 | 0.171 | 24.2% | 0.758 |
| Ridge, target = forward 63-day vol | 0.493 | 0.106 | 29.7% | 0.732 |

Elastic Net and Huber regression are statistically tied with Ridge (differences of a few thousandths of R2), so the simpler model stays. A 63-day target is a worse predictor of the next 21 days. (Rows here need a full 63-day look-ahead, so the final weeks of 2026 drop out and R2 reads 0.570 against 0.583 in the production meta file.)

| Year | model R2 | same as last quarter | same as last month | avg. error |
|---|---|---|---|---|
| 2021 | 0.628 | 0.521 | 0.440 | 25.2% |
| 2022 | 0.482 | 0.465 | 0.338 | 24.9% |
| 2023 | 0.450 | 0.454 | 0.274 | 26.3% |
| 2024 | 0.410 | 0.241 | -0.046 | 24.2% |
| 2025 | 0.626 | 0.581 | 0.459 | 26.3% |
| 2026 | 0.547 | 0.274 | 0.277 | 22.0% |

| Asset class | R2 within class | avg. error | n |
|---|---|---|---|
| stock | 0.255 | 24.0% | 33670 |
| etf | 0.263 | 29.2% | 3327 |
| gold | 0.363 | 28.3% | 1148 |
| bond | 0.006 | 44.8% | 808 |

The model beats the naive rules in every year except 2023 (a tie with last-quarter). Within a class, R2 is lower because much of the pooled R2 is knowing which assets are riskier.

## 3. Monte Carlo calibration (1-year horizon, 104 forecasts per method)

| Simulator | 50% interval | 75% | 90% | 95% | 99% | 90% excl. 2020 origins | 90% for 2020 origins | mean error of expected return |
|---|---|---|---|---|---|---|---|---|
| Block bootstrap of own history (21-day blocks) | 50% | 70% | 81% | 84% | 91% | 88% | 50% | +6.3% |
| Current (Student-t dof 5, regime switching) | 44% | 69% | 81% | 84% | 93% | 88% | 50% | +7.4% |
| Student-t dof 3 (fatter tails) | 43% | 67% | 80% | 83% | 93% | 87% | 50% | +7.4% |

Fatter tails (dof 3) and a block bootstrap of the portfolio's own history do not fix the tails. The miss is concentrated in forecasts made in 2020 (COVID crash and rebound: coverage 50%), and realised returns beat the expected return by 6-7% on average, which shifts the whole distribution. Outside 2020 the 90% band holds 88%.

## 4. Regime model

Transition matrices (full-sample labels):

| Daily from \ to | Bull / Calm | Neutral / Sideways | Bear / Volatile |
|---|---|---|---|
| Bull / Calm | 0.963 | 0.037 | 0.000 |
| Neutral / Sideways | 0.050 | 0.949 | 0.001 |
| Bear / Volatile | 0.000 | 0.015 | 0.985 |

| 21-day from \ to | Bull / Calm | Neutral / Sideways | Bear / Volatile |
|---|---|---|---|
| Bull / Calm | 0.817 | 0.178 | 0.006 |
| Neutral / Sideways | 0.250 | 0.740 | 0.010 |
| Bear / Volatile | 0.000 | 0.323 | 0.677 |

Point-in-time outcomes after each regime (2021-26; the point-in-time model never entered the Bear state because 2021-26 had no crash):

| Regime | days | next-21d market vol | next-21d worst drawdown | P(drawdown >= 5%) | next-21d return | P(21d loss) |
|---|---|---|---|---|---|---|
| Bull / Calm | 747 | 11.0% | -3.2% | 13% | +0.44% | 43% |
| Neutral / Sideways | 674 | 15.6% | -4.1% | 35% | +1.23% | 37% |

Regime probabilities as extra inputs to the volatility model change R2 from 0.5827 to 0.5792: no gain, because VIX and market volatility already carry the information. The regime is useful as a risk label (drawdown probability 13% vs 35%), not as an input to the volatility forecast.

## 5. Anomaly detector

**top 2% (production setting)**: 3 flagged days in 2 episodes

|  | days | next-21d vol | next-21d worst drawdown | P(drawdown >= 5%) | next-21d return | P(21d loss > 3%) |
|---|---|---|---|---|---|---|
| flagged | 3 | 20.6% | -3.2% | 0% | +6.73% | 0% |
| normal | 1397 | 13.1% | -3.6% | 24% | +0.80% | 15% |

**top 5%**: 40 flagged days in 8 episodes

|  | days | next-21d vol | next-21d worst drawdown | P(drawdown >= 5%) | next-21d return | P(21d loss > 3%) |
|---|---|---|---|---|---|---|
| flagged | 40 | 22.7% | -5.1% | 65% | +3.12% | 8% |
| normal | 1360 | 12.8% | -3.6% | 22% | +0.74% | 16% |

**top 10%**: 104 flagged days in 20 episodes

|  | days | next-21d vol | next-21d worst drawdown | P(drawdown >= 5%) | next-21d return | P(21d loss > 3%) |
|---|---|---|---|---|---|---|
| flagged | 104 | 20.9% | -5.1% | 61% | +1.74% | 15% |
| normal | 1296 | 12.5% | -3.5% | 21% | +0.73% | 15% |

The 2% production setting flags only 3 days in 2021-26 (too few to test). At the 5% and 10% settings, flagged days are followed by much higher volatility (about 21-23% vs 13%) and a 5% drawdown 60-65% of the time against 21%, but not by lower returns (markets tended to rebound). So the detector is a volatility/drawdown warning, not a return signal. Flagged days cluster into 8-20 episodes, so the p-values overstate significance.

## 6. Portfolio backtest (walk-forward, monthly rebalance, 0.10% costs)

2021-01-29 to 2026-10-01, 69 rebalances. Long-only, 'medium' risk caps. Annualised turnover is the sum of one-way trades.

| Strategy | CAGR | Vol | Sharpe | Sortino | Max DD | Calmar | Turnover/yr | Cumulative costs (% of start) | Hit rate (months) | Downside dev | VaR95 1d | CVaR95 1d | vs NIFTY (CAGR) | Info ratio |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A  Min-variance, trailing covariance | 11.5% | 5.7% | 0.96 | 0.92 | -6.1% | 1.87 | 0.8x | 0.6% | 74% | 5.9% | 0.51% | 0.82% | +1.1% | +0.03 |
| B  Min-variance + volatility model | 10.7% | 5.3% | 0.87 | 0.83 | -5.9% | 1.79 | 3.1x | 2.3% | 75% | 5.6% | 0.53% | 0.78% | +0.3% | -0.05 |
| B+ B + regime overlay | 9.8% | 4.5% | 0.85 | 0.82 | -4.9% | 2.00 | 3.5x | 2.6% | 78% | 4.7% | 0.44% | 0.64% | -0.6% | -0.14 |
| C  Max-Sharpe, prior returns | 12.8% | 11.4% | 0.60 | 0.58 | -16.1% | 0.80 | 3.3x | 2.7% | 59% | 11.7% | 1.12% | 1.62% | +2.4% | +0.27 |
| C+ C + volatility model | 14.5% | 11.3% | 0.75 | 0.74 | -15.2% | 0.95 | 4.6x | 4.5% | 64% | 11.5% | 1.13% | 1.60% | +4.1% | +0.50 |
| D  C+ + 13.5% return tilt | 15.3% | 12.1% | 0.77 | 0.76 | -16.5% | 0.93 | 4.7x | 4.6% | 61% | 12.2% | 1.16% | 1.69% | +5.0% | +0.61 |
| E  Full system (D + regime overlay) | 14.1% | 10.1% | 0.80 | 0.79 | -13.6% | 1.04 | 5.0x | 4.5% | 62% | 10.2% | 0.99% | 1.39% | +3.7% | +0.41 |
| NIFTY 50 ETF (benchmark) | 10.4% | 12.8% | 0.34 | 0.34 | -16.1% | 0.64 | 0.2x | 0.1% | 59% | 13.0% | 1.30% | 1.86% | +0.0% |  |
| Equal-weight stocks (monthly) | 16.6% | 13.0% | 0.82 | 0.80 | -15.0% | 1.11 | 0.7x | 0.7% | 68% | 13.4% | 1.25% | 1.84% | +6.3% | +1.20 |

Reading it like-for-like: in the max-Sharpe family the volatility model lifts Sharpe 0.60 -> 0.75, the return tilt adds a little more (0.77, +0.8% CAGR, within noise), and the regime overlay trades about 1 point of return for lower volatility and drawdown (12.1% -> 10.1% vol, -16.5% -> -13.6%). In the minimum-variance family the volatility model does not help (Sharpe 0.96 -> 0.87) and costs 4x more turnover. Every strategy beats the NIFTY 50 ETF on risk-adjusted return, but an equal-weight basket of the 26 stocks (Sharpe 0.82, CAGR 16.6%) matches or beats the full system, so in this one bull-market sample the models add risk control, not return. Caveat: 5.7 years, one regime; nothing here is statistically significant.
