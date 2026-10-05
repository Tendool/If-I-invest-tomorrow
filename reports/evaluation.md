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

Round 6 (section 9) replaced the fitted Ridge model in production with a fixed reversal + momentum composite, the first signal with skill on the 2017-20 validation; round 7 (section 10) moved it to residual returns. The tables in this section are the study of fitted models (Ridge, alpha 300000) that led there.

### By year (Ridge study model)

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
| Ridge (production) | 0.583 | 0.192 | 24.7% | 0.765 |
| Ridge alone (no blend) | 0.576 | 0.181 | 24.9% | 0.761 |
| Elastic Net | 0.572 | 0.170 | 25.1% | 0.758 |
| Huber regression | 0.579 | 0.182 | 24.0% | 0.762 |
| Ridge, target = forward 63-day vol | 0.496 | 0.111 | 29.8% | 0.737 |

Production = Ridge on realised, range-based, long-run-level, seasonal and asset-class features, blended 85/15 with trailing 63-day volatility (features and blend weight chosen on a 2017-20 walk-forward validation, rounds 4, 6 and 7). Elastic Net and Huber regression are statistically tied with plain Ridge, so the simpler model stays; a 63-day target is a worse predictor of the next 21 days. (Rows here need a full 63-day look-ahead, so the final weeks of 2026 drop out and R2 reads slightly lower than the 0.597 in the production meta file.)

| Year | model R2 | same as last quarter | same as last month | avg. error |
|---|---|---|---|---|
| 2021 | 0.609 | 0.521 | 0.440 | 25.8% |
| 2022 | 0.521 | 0.465 | 0.338 | 24.4% |
| 2023 | 0.475 | 0.454 | 0.274 | 25.6% |
| 2024 | 0.429 | 0.241 | -0.046 | 24.4% |
| 2025 | 0.653 | 0.581 | 0.459 | 24.5% |
| 2026 | 0.548 | 0.274 | 0.277 | 22.2% |

| Asset class | R2 within class | avg. error | n |
|---|---|---|---|
| stock | 0.266 | 24.2% | 33670 |
| etf | 0.340 | 27.2% | 3327 |
| gold | 0.302 | 29.7% | 1148 |
| bond | 0.218 | 27.9% | 808 |

The model beats both naive rules in every year. Within a class, R2 is lower because much of the pooled R2 is knowing which assets are riskier.

## 3. Monte Carlo calibration (1-year horizon, 104 forecasts per method)

| Simulator | 50% interval | 75% | 90% | 95% | 99% | 90% excl. 2020 origins | 90% for 2020 origins | mean error of expected return |
|---|---|---|---|---|---|---|---|---|
| Block bootstrap of own history (21-day blocks) | 50% | 70% | 81% | 84% | 91% | 88% | 50% | +6.3% |
| Production (Student-t dof 5, regime switching, parameter and volatility uncertainty) | 52% | 74% | 82% | 88% | 97% | 88% | 55% | +6.6% |
| Round 5 (no volatility uncertainty) | 53% | 74% | 81% | 88% | 96% | 88% | 50% | +6.6% |
| Student-t dof 3 (fatter tails) | 49% | 74% | 81% | 88% | 99% | 88% | 50% | +6.3% |

The production simulator draws a per-path error in the expected return (standard error sigma/sqrt(5 years), not tuned), which moved coverage from 44/69/81/84/93% to 49/73/82/84/93%; letting the regime model learn from 2008- (not just 2014-) moved it to 53/74/81/88/96%. Round 6 adds a per-path volatility level (log-normal, sd 0.17 = the spread of next-year vs trailing-year volatility measured on pre-2018 data, not tuned on these outcomes). Fatter tails (dof 3) and a block bootstrap of the portfolio's own history do not fix the outer tails. The remaining miss is concentrated in forecasts made in 2020 (COVID crash and rebound), and realised returns beat the expected return by about 6-7% on average, which shifts the whole distribution. Outside 2020 the 90% band holds 88%.

## 4. Regime model

Transition matrices (full-sample labels):

| Daily from \ to | Bull / Calm | Neutral / Sideways | Bear / Volatile |
|---|---|---|---|
| Bull / Calm | 0.964 | 0.036 | 0.000 |
| Neutral / Sideways | 0.036 | 0.955 | 0.008 |
| Bear / Volatile | 0.000 | 0.046 | 0.954 |

| 21-day from \ to | Bull / Calm | Neutral / Sideways | Bear / Volatile |
|---|---|---|---|
| Bull / Calm | 0.829 | 0.164 | 0.007 |
| Neutral / Sideways | 0.299 | 0.692 | 0.009 |
| Bear / Volatile | 0.000 | 0.361 | 0.639 |

Point-in-time outcomes after each regime (2021-26; the point-in-time model never entered the Bear state because 2021-26 had no crash):

| Regime | days | next-21d market vol | next-21d worst drawdown | P(drawdown >= 5%) | next-21d return | P(21d loss) |
|---|---|---|---|---|---|---|
| Bull / Calm | 747 | 11.0% | -3.2% | 13% | +0.44% | 43% |
| Neutral / Sideways | 674 | 15.6% | -4.1% | 35% | +1.23% | 37% |

Regime probabilities as extra inputs to the volatility model change R2 from 0.5820 to 0.5799: no gain, because VIX and market volatility already carry the information. The regime is useful as a risk label (drawdown probability 13% vs 35%), not as an input to the volatility forecast.

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
| B  Min-variance + volatility model | 11.1% | 5.3% | 0.95 | 0.91 | -5.8% | 1.90 | 2.5x | 1.9% | 75% | 5.5% | 0.52% | 0.77% | +0.7% | -0.01 |
| B+ B + regime overlay | 10.1% | 4.4% | 0.93 | 0.89 | -4.9% | 2.06 | 3.0x | 2.2% | 77% | 4.6% | 0.45% | 0.63% | -0.3% | -0.11 |
| C  Max-Sharpe, prior returns | 12.8% | 11.4% | 0.60 | 0.58 | -16.1% | 0.80 | 3.3x | 2.7% | 59% | 11.7% | 1.12% | 1.62% | +2.4% | +0.27 |
| C+ C + volatility model | 15.0% | 11.4% | 0.79 | 0.78 | -15.6% | 0.96 | 4.5x | 4.3% | 62% | 11.6% | 1.11% | 1.62% | +4.6% | +0.56 |
| D  C+ + return tilt | 13.7% | 10.5% | 0.73 | 0.71 | -17.5% | 0.78 | 5.9x | 5.2% | 65% | 10.9% | 1.05% | 1.54% | +3.3% | +0.38 |
| E  Full system (D + regime overlay) | 12.6% | 8.7% | 0.75 | 0.73 | -13.1% | 0.96 | 6.0x | 5.1% | 64% | 8.9% | 0.84% | 1.24% | +2.2% | +0.20 |
| B  Min-variance + volatility model (half-step rebalancing) | 10.8% | 5.4% | 0.88 | 0.83 | -6.0% | 1.80 | 1.3x | 1.0% | 75% | 5.7% | 0.55% | 0.80% | +0.4% | -0.04 |
| E  Full system (D + regime overlay) (half-step rebalancing) | 12.3% | 8.7% | 0.72 | 0.69 | -13.2% | 0.93 | 3.0x | 2.5% | 64% | 9.1% | 0.87% | 1.27% | +1.9% | +0.17 |
| NIFTY 50 ETF (benchmark) | 10.4% | 12.8% | 0.34 | 0.34 | -16.1% | 0.64 | 0.2x | 0.1% | 59% | 13.0% | 1.30% | 1.86% | +0.0% |  |
| Equal-weight stocks (monthly) | 16.6% | 13.0% | 0.82 | 0.80 | -15.0% | 1.11 | 0.7x | 0.7% | 68% | 13.4% | 1.25% | 1.84% | +6.3% | +1.20 |

Reading it like-for-like (round-7 models): in the max-Sharpe family the volatility model lifts Sharpe 0.60 -> 0.79; in the minimum-variance family it is about neutral (Sharpe 0.96 -> 0.95; it was 0.89 before round 6). The return tilt (residual reversal + momentum, weight 0.23) lowers Sharpe 0.79 -> 0.73: its reversal half flips every month, raising turnover from 4.5x to 5.9x a year and costs from 4.3% to 5.2% of capital, which outweighs its small gross gain. The regime overlay trades return for lower volatility and drawdown (full system Sharpe 0.75, max drawdown -13.1%). App plans are bought and held rather than rebalanced monthly, so the turnover cost applies less there. Every strategy beats the NIFTY 50 ETF on risk-adjusted return, but an equal-weight basket of the 26 stocks (Sharpe 0.82, CAGR 16.6%) matches or beats the full system, so in this one bull-market sample the models add risk control, not return. Caveat: 5.7 years, one regime; nothing here is statistically significant.

## 7. Round 4 (selection on a 2017-20 walk-forward validation; this protocol change was made after 2021-26 had been seen, so gains are tentative)

| Idea | Validation 2017-20 | Test 2021-26 | Decision |
|---|---|---|---|
| Volatility: + long-run level, blended 80/20 with last quarter | R2 0.504 -> 0.533 | R2 0.583 -> 0.589, within-asset 0.177 -> 0.189 | adopted |
| Volatility: + GARCH(1,1) forecast as a feature | R2 0.504 -> 0.477 | 0.585 | rejected |
| Returns: any feature set / target (relative strength, ranks, excess vs NIFTY) | IC between -0.011 and +0.006 | 0.026 to 0.052 | rejected: no skill in 2017-20 |
| Monte Carlo: parameter uncertainty in the expected return (not tuned) | - | mean coverage gap 0.078 -> 0.051 | adopted |
| Monte Carlo: online recalibration of the spread | - | gap 0.031, but driven by a distribution shortcut | rejected |
| Drawdown warning: logistic model on VIX, regime, anomaly and market features | AUC 0.41 (VIX alone 0.66) | AUC 0.49 (VIX alone 0.74) | rejected |
| Portfolio: half-step rebalancing | - | turnover halved, Sharpe 0.77 -> 0.75 | rejected |

AUC of each score for 'NIFTY falls 5% or more within the next 21 days' (test 2021-26): VIX level 0.74, regime P(not calm) 0.69, Isolation-Forest anomaly score 0.61.

## 8. Round 5: more data (scripts/extended_data.py)

Longer history (Yahoo 'max': NIFTY from 2007, VIX from 2008, stocks from 1996-2010) and a wider universe (+45 large NSE stocks). Models trained on the extended data, scored on exactly the production test rows (31 assets, 2021-26). The extra stocks are today's large caps (survivorship bias).

| Experiment | Validation 2017-20 | Test 2021-26 | Decision |
|---|---|---|---|
| Volatility, longer history (alpha and blend re-chosen on validation) | R2 0.533 -> 0.526 | R2 0.589 -> 0.601, within-asset 0.189 -> 0.226 | rejected: better in 5 of 10 years only |
| Volatility, wider universe | R2 0.533 -> 0.525 | 0.589 -> 0.586 | rejected |
| Volatility, longer + wider | R2 0.533 -> 0.519 | 0.589 -> 0.600 | rejected |
| Returns, longer history | IC -0.015 -> -0.006 | 0.028 -> 0.043 | rejected: still no skill on validation |
| Returns, wider universe | IC -0.015 -> -0.042 | 0.028 -> 0.035 | rejected |
| Regime model learns from 2008- (incl. the 2008 crash), only for the regime model | - | MC coverage gap 0.051 -> 0.037 (same seeds), better or equal at all 5 levels | adopted |

With 2008 included, the Bear/Volatile state is learned from 394 days (2008-09 and 2020) instead of 65. Its average return is positive (+17% p.a.) because crisis periods include the violent rebounds; it is defined by 45% volatility, VIX 42 and a -35% average drawdown.

## 9. Round 6 (scripts/model_search_v5.py; selection on 2017-20 validation, test 2021-26 reported once)

| Idea | Validation 2017-20 | Test 2021-26 | Decision |
|---|---|---|---|
| Volatility: + seasonal features (same window last year, results-season share), blend 85/15 | R2 0.533 -> 0.536 | R2 0.589 -> 0.592, within-asset 0.189 -> 0.192; better in 4 of 6 years | adopted |
| Volatility: + implied systematic vol (beta x India VIX + idiosyncratic) | R2 0.533 -> 0.530 | 0.595 | rejected on validation |
| Volatility: seasonal + implied systematic | R2 0.533 -> 0.533 | 0.598 | rejected on validation |
| Volatility: boosted trees on Ridge residuals / trees alone | R2 0.525 / 0.474 | 0.591 / 0.594 | rejected |
| Returns: 1-month reversal (no fitting) | IC +0.015 (t 1.9) | IC +0.049 | - |
| Returns: 12-1 month momentum (no fitting) | IC +0.052 (t 1.2) | IC +0.024 | picked by the pre-set rule (highest mean IC) |
| Returns: reversal + momentum composite (no fitting) | IC +0.049 (t 2.3) | IC +0.052 (t 2.4), R2 vs zero +0.24% (Ridge -0.24%); positive in 4 of 6 years | adopted (see note) |
| Returns: LightGBM ranker on rank features | IC -0.015 | IC +0.036 | rejected |
| Monte Carlo: volatility uncertainty, sd 0.17 measured on pre-2018 data | - | mean coverage gap 0.045 -> 0.039; 90% band 81% -> 82% | adopted |
| Plan: whole-share rounding gives positions too small for one share to the rest of the plan | - | Rs 1 lakh medium plan invests 97.0% (was 92.6%) | adopted |

Note on the return signal: the rule fixed before the run (highest mean validation IC) picks momentum alone; momentum and the composite are tied on mean IC (0.052 vs 0.049), and the composite is far more consistent (t 2.3 vs 1.2), which is why it is used. That choice was made after the test numbers had been seen, so its test IC is tentative. It is the first return signal in six rounds with skill on the validation years; every fitted model (Ridge, Random Forest, XGBoost, LightGBM, GRU) stays at or below zero there. In the portfolio backtest it does not pay after costs (section 6). Round 7 replaced it with the residual version (section 10).

## 10. Round 7 (scripts/model_search_v6.py; rules fixed before running: a candidate must beat the incumbent on validation)

The 2017-20 validation years had been used in earlier rounds, so the bar was raised from 'positive' to 'better than the model in use'. The Monte Carlo was decided on 2016-18 forecast origins, which no earlier decision had used.

| Idea | Validation | Test | Decision |
|---|---|---|---|
| Volatility: + asset-class effects (ETF, gold, bond dummies and interactions) | R2 0.5361 -> 0.5375 | R2 0.592 -> 0.597, within-asset 0.192 -> 0.202, error 25.2% -> 24.9%; bonds 0.14 -> 0.22 | adopted |
| Volatility: + log-VIX nonlinearity | 0.5352 | 0.592 | rejected |
| Volatility: recency-weighted training (half-life 3 years) | 0.5330 | 0.585 | rejected |
| Volatility: log VIX + asset class (+ recency) | 0.5370 (0.5345) | 0.598 (0.595) | rejected: below the adopted variant on validation |
| Returns: residual reversal + residual momentum (Blitz, Huij & Martens) | IC 0.061 (t 3.2) | IC 0.046 (t 2.2); 2017-26 pooled 0.052 vs 0.051 for round 6 | adopted |
| Returns: reversal + momentum + seasonality (Heston & Sadka) | IC 0.058 (t 2.8) | IC 0.039 | rejected: lower validation t |
| Returns: residual reversal alone / residual momentum alone | t 2.8 / 1.3 | IC 0.050 / 0.016 | rejected |
| Returns: 52-week high (George & Hwang) | IC 0.013 (t -0.2) | IC -0.058 | rejected |
| Returns: all six factors equal weight / Ridge fitted on them | t 2.4 / -0.1 | IC 0.023 / 0.030 | rejected |
| Monte Carlo: Student-t dof 4 or 8 | gap 0.057 -> 0.049 (identical for 4 and 8) | gap 0.037 / 0.033 | rejected: opposite tail changes score the same, a random-number effect |
| Monte Carlo: uncertainty in the CAPM/history blend weight | gap 0.057 (no change) | 0.037 | rejected |

Following the rule cost a little on the test years for returns (IC 0.052 -> 0.046) and gained over the full ten years (0.051 -> 0.052); the decision was not revisited. On 2016-18 origins the simulated bands were too wide (90% band held 98%), on 2019-25 too narrow (82%): the two periods disagree, so no change was made.
