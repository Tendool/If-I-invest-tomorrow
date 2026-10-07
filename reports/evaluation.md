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

Round 6 (section 9) replaced the fitted Ridge model in production with a fixed reversal + momentum composite, the first signal with skill on the 2017-20 validation; round 7 (section 10) moved it to residual returns and round 10 (section 13) added reversal relative to the asset's sector. The tables in this section are the study of fitted models (Ridge, alpha 300000) that led there.

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
| Ridge (production) | 0.591 | 0.208 | 24.5% | 0.771 |
| Ridge alone (no blend) | 0.583 | 0.194 | 24.7% | 0.765 |
| Elastic Net | 0.585 | 0.198 | 24.7% | 0.767 |
| Huber regression | 0.586 | 0.195 | 23.9% | 0.767 |
| Ridge, target = forward 63-day vol | 0.494 | 0.114 | 29.9% | 0.737 |

Production = Ridge on realised, range-based, long-run-level, seasonal, asset-class and earnings-calendar features, blended 85/15 with trailing 63-day volatility (features and blend weight chosen on a 2017-20 walk-forward validation, rounds 4, 6, 7 and 9; trained on every day since round 10). Elastic Net and Huber regression are statistically tied with plain Ridge, so the simpler model stays; a 63-day target is a worse predictor of the next 21 days. (Rows here need a full 63-day look-ahead, so the final weeks of 2026 drop out and R2 reads slightly lower than the 0.604 in the production meta file.)

| Year | model R2 | same as last quarter | same as last month | avg. error |
|---|---|---|---|---|
| 2021 | 0.622 | 0.521 | 0.440 | 25.2% |
| 2022 | 0.517 | 0.465 | 0.338 | 24.5% |
| 2023 | 0.475 | 0.454 | 0.274 | 25.8% |
| 2024 | 0.442 | 0.241 | -0.046 | 23.8% |
| 2025 | 0.655 | 0.581 | 0.459 | 24.6% |
| 2026 | 0.584 | 0.274 | 0.277 | 21.3% |

| Asset class | R2 within class | avg. error | n |
|---|---|---|---|
| stock | 0.281 | 24.1% | 33670 |
| etf | 0.340 | 26.9% | 3327 |
| gold | 0.369 | 26.5% | 1148 |
| bond | 0.202 | 28.1% | 808 |

The model beats both naive rules in every year. Within a class, R2 is lower because much of the pooled R2 is knowing which assets are riskier.

## 3. Monte Carlo calibration (1-year horizon, 104 forecasts per method)

| Simulator | 50% interval | 75% | 90% | 95% | 99% | 90% excl. 2020 origins | 90% for 2020 origins | mean error of expected return |
|---|---|---|---|---|---|---|---|---|
| Block bootstrap of own history (21-day blocks) | 50% | 70% | 81% | 84% | 91% | 88% | 50% | +6.3% |
| Production (Student-t dof 5, regime switching, parameter and volatility uncertainty) | 49% | 74% | 84% | 89% | 100% | 89% | 60% | +6.6% |
| Round 5 (no volatility uncertainty) | 53% | 74% | 81% | 88% | 96% | 88% | 50% | +6.6% |
| Round 9 (volatility uncertainty 0.17) | 52% | 74% | 82% | 88% | 97% | 88% | 55% | +6.6% |
| Student-t dof 3 (fatter tails) | 49% | 72% | 82% | 89% | 100% | 88% | 55% | +6.3% |

The production simulator draws a per-path error in the expected return (standard error sigma/sqrt(5 years), not tuned), which moved coverage from 44/69/81/84/93% to 49/73/82/84/93%; letting the regime model learn from 2008- (not just 2014-) moved it to 53/74/81/88/96%. Round 6 added a per-path volatility level (log-normal, sd 0.17); round 10 raised it to 0.35, chosen on 1-year NIFTY forecasts from 2009-17 (section 13), which moved the 90% band from 82% to 84% here. Fatter tails (dof 3) and a block bootstrap of the portfolio's own history do not fix the outer tails. The remaining miss is concentrated in forecasts made in 2020 (COVID crash and rebound), and realised returns beat the expected return by about 6-7% on average, which shifts the whole distribution. Outside 2020 the 90% band holds 89%. Of the 17 forecasts outside the 90% band, 8 are gold (its 2019 and 2024-25 rallies; it beat its expected return by 17% a year and its band held 69%, against 85-92% for the NIFTY ETF, the balanced portfolio and the 8 stocks), 7 are the rebound after the 2020 crash and 2 are falls (2019-20, 2025-26). Closing the gap would mean raising expected returns to match 2019-25, i.e. fitting the test.

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

## 6. Portfolio backtest (walk-forward, monthly rebalance, realistic costs)

Costs per asset class (ifit/costs.py, approximate 2025 NSE schedule): stocks 0.17% to buy and 0.15% to sell (STT 0.1% each way, stamp duty, exchange and SEBI fees with GST, half bid-ask spread 0.05%); equity ETFs about 0.06%; gold and gilt ETFs about 0.11%. Trades happen at the rebalance date's close.

2021-01-29 to 2026-10-01, 69 rebalances. Long-only, 'medium' risk caps. Annualised turnover is the sum of one-way trades.

| Strategy | CAGR | Vol | Sharpe | Sortino | Max DD | Calmar | Turnover/yr | Cumulative costs (% of start) | Hit rate (months) | Downside dev | VaR95 1d | CVaR95 1d | vs NIFTY (CAGR) | Info ratio |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A  Min-variance, trailing covariance | 11.5% | 5.7% | 0.95 | 0.90 | -7.0% | 1.64 | 0.8x | 0.7% | 74% | 6.1% | 0.51% | 0.83% | +0.8% | +0.01 |
| B  Min-variance + volatility model | 11.1% | 5.4% | 0.95 | 0.91 | -6.0% | 1.84 | 2.7x | 2.3% | 77% | 5.6% | 0.52% | 0.79% | +0.5% | -0.02 |
| B+ B + regime overlay | 10.2% | 4.5% | 0.93 | 0.89 | -5.1% | 2.00 | 3.1x | 2.3% | 78% | 4.7% | 0.46% | 0.65% | -0.4% | -0.11 |
| C  Max-Sharpe, prior returns | 12.2% | 11.5% | 0.54 | 0.53 | -16.7% | 0.73 | 3.3x | 3.8% | 61% | 11.7% | 1.12% | 1.63% | +1.6% | +0.17 |
| C+ C + volatility model | 14.3% | 11.4% | 0.73 | 0.72 | -14.9% | 0.96 | 4.7x | 6.4% | 64% | 11.5% | 1.13% | 1.63% | +3.6% | +0.43 |
| D  C+ + return tilt | 14.4% | 10.4% | 0.80 | 0.77 | -16.2% | 0.89 | 7.5x | 9.3% | 67% | 10.8% | 1.03% | 1.54% | +3.7% | +0.43 |
| E  Full system (D + regime overlay) | 13.0% | 8.6% | 0.80 | 0.78 | -12.2% | 1.06 | 7.4x | 8.0% | 67% | 9.0% | 0.84% | 1.24% | +2.3% | +0.22 |
| B  Min-variance + volatility model (half-step rebalancing) | 10.9% | 5.5% | 0.90 | 0.85 | -6.2% | 1.77 | 1.4x | 1.2% | 75% | 5.8% | 0.55% | 0.81% | +0.3% | -0.04 |
| E  Full system (D + regime overlay) (half-step rebalancing) | 12.7% | 8.7% | 0.78 | 0.75 | -12.2% | 1.04 | 3.5x | 3.7% | 65% | 9.0% | 0.86% | 1.26% | +2.1% | +0.20 |
| NIFTY 50 ETF (benchmark) | 10.6% | 12.8% | 0.36 | 0.36 | -16.1% | 0.66 | 0.2x | 0.1% | 59% | 13.0% | 1.30% | 1.86% | +0.0% |  |
| Equal-weight stocks (monthly) | 16.9% | 13.0% | 0.84 | 0.82 | -15.1% | 1.12 | 0.7x | 1.1% | 68% | 13.4% | 1.25% | 1.84% | +6.3% | +1.19 |

Reading it like-for-like (round-10 models, realistic costs): in the max-Sharpe family the volatility model lifts Sharpe 0.54 -> 0.73; in the minimum-variance family it is neutral (0.95 -> 0.95). The return tilt (residual reversal + momentum + sector-relative reversal, weight 0.29) adds 0.73 -> 0.80 although it raises turnover from 4.7x to 7.5x a year (costs 6.4% -> 9.3% of capital over the period). The regime overlay trades return for lower volatility and drawdown (full system Sharpe 0.80, max drawdown -12.2%). Until round 10 this backtest credited each rebalance with that day's own return (weights chosen at a close earned the move into that close): the one-day look-ahead flattered the max-Sharpe strategies by about 0.07 and penalised the reversal tilt, which is why earlier versions read 0.60 -> 0.80 and showed the tilt hurting. Every strategy beats the NIFTY 50 ETF (0.36) on risk-adjusted return; an equal-weight basket of the 26 stocks (Sharpe 0.84, CAGR 16.9%) matches the full system. Caveat: 5.7 years, one regime; section 14 tests other periods, cost levels and confidence intervals.

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

## 11. Round 8: nested selection and ensembles (scripts/model_search_v7.py)

Every candidate makes walk-forward predictions for 2017-26; for each test year the choice (best single, top-3 average, or non-negative stacking weights / IC weights) is learned from earlier years only, so the 2021-26 score stays honest however many candidates are tried. Re-run after round 9 (every candidate now has the earnings-calendar features); the round-8 run against the round-7 model is in brackets. Rule, fixed before the re-run: adopt a nested procedure only if it scores strictly higher than the fixed production model on 2021-26.

| Procedure | Volatility R2 (2021-26) | Return IC (2021-26) |
|---|---|---|
| Production, fixed | **0.603** (round 7: 0.597) | **0.046** (t 2.2) |
| Best single candidate, chosen each year on earlier years | 0.600 (0.594) | 0.046 (picks production every year: a tie, not a gain) |
| Top-3 average | 0.597 (0.591) | 0.036 |
| Stacking with non-negative weights / IC-weighted factor mix | 0.600 (0.596) | 0.037 |
| Best individual alternatives | Ridge + implied/log-VIX 0.603, Huber 0.599 (error 23.7%), LightGBM 0.53-0.56 | reversal + momentum 0.051, residual reversal 0.050 |

No nested procedure beats the production models in either run, so nothing changed. Choosing a single candidate by its 2021-26 score (e.g. Ridge + implied/log-VIX, 0.6030 vs 0.6026, whose features were rejected on validation in rounds 6 and 7) would be selection on the test years and is not done. The best-single choices are unblended Ridge forecasts, while production blends Ridge 85/15 with last quarter's volatility; stacking can learn such a blend, but its weights move from year to year (LightGBM 0.16-0.30, EWMA volatility 0.16-0.25). With this data (daily prices, VIX, macro series and quarterly results for 32 assets) the models are at the accuracy that an honest, automatic search can reach; further gains would need new information (company fundamentals, options-implied volatility per stock, intraday prices with long history).

## 12. Round 9: earnings data (scripts/download_earnings.py, ifit/earnings.py, scripts/model_search_v8.py)

New information: every quarterly result of the 26 stocks since about 2005 (Yahoo Finance: date, EPS estimate, reported EPS, surprise). A result is used only from the first trading day after its announcement date; the next results date is projected from past dates (median gap), never read from the published schedule. A unit test checks that no feature sees a result early. Rules as in round 7: adopt only what beats the model in use on 2017-20.

| Idea | Validation 2017-20 | Test 2021-26 | Decision |
|---|---|---|---|
| Volatility: + projected results window and the stock's typical result-day jump | R2 0.5375 -> 0.5411 | R2 0.597 -> 0.603, within-asset 0.202 -> 0.216, stocks 0.265 -> 0.278, error 24.9% -> 24.6%; better in 5 of 6 years | adopted |
| Volatility: window x jump only | R2 0.5403 | R2 0.601 | rejected: below the full set |
| Returns: earnings surprise (post-earnings drift) | IC 0.026 (t 1.2) | IC 0.003 | rejected |
| Returns: earnings-announcement return | IC 0.036 (t 0.5) | IC -0.012 | rejected |
| Returns: incumbent + surprise + announcement return | IC 0.074 (t 2.6) | IC 0.030 | rejected: validation t below the incumbent's 3.2 (and lower on test) |

Post-earnings drift, one of the best-documented anomalies in US data, shows no skill on these large, heavily followed NSE stocks. The earnings calendar does help volatility: the model now knows when each stock's next results are due and how much that stock usually moves on them. In the portfolio backtest (before the round-10 look-ahead fix) every volatility-model strategy improved slightly (max-Sharpe 0.79 -> 0.80, min-variance 0.95 -> 0.97, full system 0.75 -> 0.77).

## 13. Round 10 (scripts/model_search_v9.py; rules fixed before running: beat the model in use on 2017-20)

### Volatility

| Idea | Validation R2 2017-20 | Test R2 2021-26 | within-asset | stocks | Decision |
|---|---|---|---|---|---|
| A production (round 9) | 0.5411 | 0.6027 | 0.216 | 0.278 | in use |
| B train on 25% range-based target | 0.5408 | 0.6038 | 0.219 | 0.280 | rejected |
| B train on 50% range-based target | 0.5401 | 0.6052 | 0.223 | 0.282 | rejected |
| B train on 75% range-based target | 0.5389 | 0.6059 | 0.226 | 0.284 | rejected |
| B train on 100% range-based target | 0.5372 | 0.6062 | 0.228 | 0.284 | rejected |
| C every day in training | 0.5524 | 0.6040 | 0.217 | 0.279 | adopted |
| D error correction on [A production (round 9)] | 0.5419 | 0.6027 | 0.209 | 0.276 | rejected |
| D error correction on [B train on 25% range-based target] | 0.5427 | 0.6041 | 0.213 | 0.279 | rejected |
| C + B 25% range-based target | 0.5491 | 0.6057 | 0.222 | 0.282 | rejected |
| C + B 50% range-based target | 0.5439 | 0.6070 | 0.227 | 0.284 | rejected |
| C + D error correction | 0.5499 | 0.6040 | 0.211 | 0.277 | rejected |

Adopted: training on every day instead of every third (validation 0.541 -> 0.552, test 0.603 -> 0.604). The early validation years had little history, so three times the rows helped there more than in the test years. Training on a cleaner range-based measure of the same 21 days (intraday Garman-Klass + overnight return, stocks only, ETF high/low prints are unreliable) raised the test R2 to 0.606 but lowered validation, so it was rejected. Correcting each asset with its own past errors added nothing out of sample.

**How high can R2 go?** The target, the volatility of the next 21 daily returns, is itself a noisy measurement. Splitting each window into odd and even days gives two independent measurements of the same month; their agreement (split-half reliability, Spearman-Brown) shows that only 84% of the target's variation is true volatility for all assets and 63% for single stocks. A forecaster that knew next month's true volatility exactly would score about that; ours reaches 0.60 (all assets). Against the cleaner range-based measure of the same 21 days, our stock forecasts score R2 0.36 instead of 0.28: part of the apparent error is noise in the target (Andersen & Bollerslev 1998). Reaching 0.65 would need new information (options-implied volatility per stock, intraday data), not a better fit.

### Monte Carlo (1-year NIFTY forecasts from the long 2007- history)

| Setting | 2009-17 origins: 50/75/90/95/99% bands held | error | 2019-25 origins | error |
|---|---|---|---|---|
| vol_unc 0.17, extra drift 0.00 (production before) | 63/95/100/100/100 | 0.099 | 60/80/86/94/100 | 0.042 |
| vol_unc 0.17, extra drift 0.03 | 64/95/100/100/100 | 0.100 | 60/80/86/95/100 | 0.040 |
| vol_unc 0.17, extra drift 0.06 | 65/95/100/100/100 | 0.102 | 62/80/88/95/100 | 0.042 |
| vol_unc 0.25, extra drift 0.00 | 61/95/100/100/100 | 0.095 | 56/80/86/95/100 | 0.032 |
| vol_unc 0.25, extra drift 0.03 | 61/95/100/100/100 | 0.095 | 60/80/86/95/100 | 0.040 |
| vol_unc 0.25, extra drift 0.06 | 64/95/100/100/100 | 0.100 | 61/81/88/96/100 | 0.045 |
| vol_unc 0.35, extra drift 0.00 (chosen) | 60/95/100/100/100 | 0.093 | 55/80/86/95/100 | 0.030 |
| vol_unc 0.35, extra drift 0.03 | 60/95/100/100/100 | 0.093 | 56/80/86/95/100 | 0.032 |
| vol_unc 0.35, extra drift 0.06 | 61/95/100/100/100 | 0.095 | 61/80/88/98/100 | 0.045 |

On 2009-17 origins the bands were too wide (90% band held 100%); on 2019-25 too narrow. Higher volatility uncertainty fits both better (its heavier tails and narrower centre), extra drift uncertainty does not. Chosen: 0.35, in line with how much next-year NIFTY volatility moved against its trailing 5-year estimate (sd of the log ratio 0.25 on 2009-17 origins, 0.45 on 2019-25). On the standard 104-forecast test (section 3) the 90% band moves from 82% to 84% and the 99% band from 97% to 100%.

### Return signal

| Signal | Validation IC (t) 2017-20 | Test IC (t) 2021-26 |
|---|---|---|
| residual reversal + momentum (incumbent) | +0.0611 (+3.19) | +0.0455 (+2.15) |
| 1-week reversal | +0.0147 (+0.95) | +0.0113 (+0.40) |
| incumbent + 1-week reversal | +0.0540 (+3.55) | +0.0396 (+1.74) |
| MAX effect (low max daily return) | -0.0149 (+0.56) | -0.0071 (+0.30) |
| incumbent + MAX effect (low max daily return) | +0.0360 (+2.64) | +0.0280 (+1.43) |
| low idiosyncratic volatility | -0.0130 (-0.52) | -0.0151 (-0.73) |
| incumbent + low idiosyncratic volatility | +0.0353 (+2.27) | +0.0242 (+1.33) |
| abnormal volume | -0.0165 (-1.92) | -0.0081 (-0.12) |
| incumbent + abnormal volume | +0.0398 (+1.68) | +0.0244 (+1.65) |
| low beta | -0.0388 (-0.85) | -0.0150 (-0.52) |
| incumbent + low beta | +0.0298 (+1.40) | +0.0241 (+1.16) |
| within-sector residual reversal | +0.0359 (+2.40) | +0.0431 (+1.77) |
| incumbent + within-sector residual reversal **(adopted)** | +0.0610 (+3.95) | +0.0571 (+2.68) |
| sector-adjusted reversal + residual momentum | +0.0615 (+2.26) | +0.0420 (+2.11) |

Adopted: adding the residual 1-month return relative to the asset's own sector (a stock that fell more than its sector tends to recover; Da, Liu & Schaumburg 2014). Validation t 3.19 -> 3.95 (same IC 0.061); test IC 0.046 -> 0.057, R2 against a zero forecast +0.22% (Gu-Kelly-Xiu definition; the round-7 signal had +0.09%, fitted Ridge -0.24%), direction right 51.5% of the time. Skill weight 0.23 -> 0.29. The other documented signals (1-week reversal, MAX, idiosyncratic volatility, abnormal volume, low beta) have no skill here on their own.

## 14. Robustness: other periods, realistic costs, confidence intervals (scripts/eval_robustness.py)

Monthly walk-forward from 2017-01-31 to 2026-10-01 (117 rebalances), every model refit each year on earlier data. 2017-20 were the validation years on which model choices were made, so they are not a clean test.

Sharpe ratio by period, realistic costs:

| Strategy | 2017-18 | 2019-20 | 2021-22 | 2023-24 | 2025-26 | 2017-20 (validation years) | 2021-26 (test years) | 2017-26 (all) |
|---|---|---|---|---|---|---|---|---|
| C  Max-Sharpe, prior returns | 1.37 | 0.76 | 0.00 | 1.79 | -0.20 | 0.92 | 0.45 | 0.66 |
| C+ C + volatility model | 1.20 | 0.75 | 0.48 | 1.77 | -0.17 | 0.87 | 0.62 | 0.73 |
| D  C+ + return tilt | 1.39 | 0.54 | 0.67 | 1.70 | -0.09 | 0.81 | 0.70 | 0.74 |
| E  Full system (D + regime overlay) | 1.35 | 0.76 | 0.70 | 1.66 | -0.12 | 1.01 | 0.71 | 0.84 |
| B  Min-variance + volatility model | 1.18 | 1.05 | 0.67 | 2.09 | 0.11 | 1.03 | 0.84 | 0.91 |
| NIFTY 50 ETF (buy and hold) | 0.86 | 0.44 | 0.62 | 0.92 | -0.64 | 0.53 | 0.31 | 0.41 |
| Equal-weight stocks (monthly) | 1.13 | 0.65 | 1.12 | 1.58 | -0.52 | 0.74 | 0.76 | 0.75 |

Sharpe ratio 2021-26 by cost level (calendar years; the section-6 table starts at the first rebalance, end of January 2021):

| Strategy | flat 0.10% (previous assumption) | realistic | realistic x2 (stress) | realistic x3 (stress) | realistic + DP charges, Rs 10 lakh | realistic + DP charges, Rs 1 lakh |
|---|---|---|---|---|---|---|
| C  Max-Sharpe, prior returns | 0.46 | 0.45 | 0.41 | 0.37 | 0.45 | 0.40 |
| C+ C + volatility model | 0.64 | 0.62 | 0.56 | 0.49 | 0.61 | 0.58 |
| D  C+ + return tilt | 0.73 | 0.70 | 0.59 | 0.48 | 0.70 | 0.65 |
| E  Full system (D + regime overlay) | 0.74 | 0.71 | 0.60 | 0.48 | 0.71 | 0.64 |
| B  Min-variance + volatility model | 0.85 | 0.84 | 0.78 | 0.72 | 0.83 | 0.73 |
| NIFTY 50 ETF (buy and hold) | 0.31 | 0.31 | 0.31 | 0.31 | 0.31 | 0.31 |
| Equal-weight stocks (monthly) | 0.76 | 0.76 | 0.75 | 0.74 | 0.75 | 0.69 |

90% intervals for Sharpe differences (stationary block bootstrap of daily returns, mean block 21 days, 2000 draws, realistic costs):

| Difference | 2021-26 point [90% interval], share > 0 | 2017-26 point [90% interval], share > 0 |
|---|---|---|
| volatility model, max-Sharpe (C+ - C) | +0.17 [-0.04, +0.41], 90% | +0.07 [-0.07, +0.23], 79% |
| volatility model, min-variance (B - A) | +0.00 [-0.22, +0.24], 54% | -0.05 [-0.19, +0.09], 29% |
| full system vs NIFTY ETF (E - NIFTY) | +0.40 [-0.08, +0.87], 92% | +0.43 [+0.01, +0.83], 95% |
| max-Sharpe + vol model vs NIFTY ETF (C+ - NIFTY) | +0.30 [-0.16, +0.78], 86% | +0.32 [-0.03, +0.69], 93% |
| full system vs equal weight (E - EW) | -0.05 [-0.49, +0.43], 42% | +0.10 [-0.31, +0.50], 64% |

What survives: every strategy keeps a higher Sharpe ratio than the NIFTY ETF in every cost scenario, and the full system beats NIFTY in every 2-year block; over 2017-26 its advantage over NIFTY (+0.43) is the one difference whose 90% interval excludes zero (+0.01 to +0.83). What does not: the volatility model's gain in the max-Sharpe family comes mostly from 2021-22 and its 90% interval includes zero; in the minimum-variance family it gains nothing over 2017-26; the full system does not beat an equal-weight basket of the stocks with any confidence. A 5-6 year Sharpe ratio is also fragile: starting the 2021-26 window one month later (end of January instead of 1 January) moves the max-Sharpe + volatility model from 0.62 to 0.73. Costs matter for small accounts: the fixed depository charge (Rs 15.93 per security sold) costs a Rs 1 lakh account rebalanced monthly 0.04-0.15 of Sharpe.

### The app's plans from many start dates

The five strategies chosen with data up to each quarter-end (Rs 1 lakh, medium risk, 12% target, no ML, as in the app's backtest), held with quarterly rebalancing and realistic costs:

| Holding | Strategy | start dates | median return | median per year | worst | best | beat NIFTY ETF | median Sharpe |
|---|---|---|---|---|---|---|---|---|
| 1y | Crash-Resistant | 34 | +14% | +13.9% | +5% | +30% | 62% | 1.35 |
| 1y | Goal-Based | 34 | +14% | +14.4% | +2% | +37% | 62% | 1.01 |
| 1y | Max Return | 34 | +16% | +16.2% | -12% | +82% | 79% | 0.68 |
| 1y | Max Sharpe | 34 | +17% | +16.7% | -3% | +36% | 59% | 0.94 |
| 1y | Min Risk | 34 | +13% | +12.9% | +6% | +30% | 56% | 1.25 |
| 3y | Crash-Resistant | 26 | +51% | +14.8% | +42% | +66% | 54% | 1.11 |
| 3y | Goal-Based | 26 | +47% | +13.8% | +27% | +70% | 35% | 0.73 |
| 3y | Max Return | 26 | +64% | +18.0% | +18% | +106% | 65% | 0.58 |
| 3y | Max Sharpe | 26 | +53% | +15.2% | +27% | +76% | 58% | 0.61 |
| 3y | Min Risk | 26 | +50% | +14.5% | +42% | +61% | 50% | 1.14 |
| 1y | NIFTY 50 ETF | 34 | +11% | +11.2% | -21% | +73% |  |  |
| 3y | NIFTY 50 ETF | 26 | +52% | +15.0% | +5% | +110% |  |  |

Over 1 year every plan's median return beat the NIFTY ETF's (12.9-16.7% vs 11.2%) and their worst year was far milder (-12% to +6% vs -21%). Over 3 years no plan lost money from any of the 26 start dates (worst +18% to +42%, NIFTY ETF worst +5%), but on return only Max Return clearly beat the NIFTY ETF (median 18.0% vs 15.0% a year); the recommended Goal-Based plan beat it in 35% of the windows. The plans' edge is smaller losses, not higher returns. The single Oct 2023 window in the slides (+55% vs +15%) was a favourable one.

## 15. Why 84% and not 90%? (scripts/eval_calibration_check.py)

Scores that reward calibration and sharpness together (Gneiting & Raftery 2007): the 90% interval score (band width + 20 x the distance of an outcome outside the band; lower is better, so a band that is too wide pays for its width) and the CRPS. Rule fixed before running: adopt a candidate only if it lowers the interval score on origins before 2019 in both samples.

| Sample | Candidate | n | 90% band held | 50% band held | mean 90% width | interval score | CRPS | mean error |
|---|---|---|---|---|---|---|---|---|
| 4 portfolios, before 2019 | + drift uncertainty 0.03 | 48 | 98% | 56% | 0.491 | 0.496 | 0.0711 | +7.5% |
| 4 portfolios, before 2019 | + drift uncertainty 0.06 | 48 | 100% | 60% | 0.523 | 0.523 | 0.0722 | +7.5% |
| 4 portfolios, before 2019 | + drift uncertainty 0.10 | 48 | 100% | 65% | 0.595 | 0.595 | 0.0751 | +7.5% |
| 4 portfolios, before 2019 | production | 48 | 98% | 56% | 0.478 | 0.487 | 0.0708 | +7.5% |
| 4 portfolios, before 2019 | recentred by past errors (point in time) | 48 | 98% | 52% | 0.499 | 0.508 | 0.0660 | +2.5% |
| 4 portfolios, 2019-25 | + drift uncertainty 0.03 | 104 | 84% | 51% | 0.595 | 1.052 | 0.1180 | +6.6% |
| 4 portfolios, 2019-25 | + drift uncertainty 0.06 | 104 | 86% | 54% | 0.625 | 1.032 | 0.1180 | +6.6% |
| 4 portfolios, 2019-25 | + drift uncertainty 0.10 | 104 | 87% | 61% | 0.691 | 1.004 | 0.1186 | +6.5% |
| 4 portfolios, 2019-25 | production | 104 | 84% | 49% | 0.584 | 1.061 | 0.1181 | +6.6% |
| 4 portfolios, 2019-25 | recentred by past errors (point in time) | 104 | 84% | 49% | 0.625 | 0.926 | 0.1159 | -1.3% |
| NIFTY, 2009-17 origins | + drift uncertainty 0.03 | 103 | 100% | 60% | 0.938 | 0.938 | 0.1064 | +6.3% |
| NIFTY, 2009-17 origins | + drift uncertainty 0.06 | 103 | 100% | 61% | 0.955 | 0.955 | 0.1073 | +6.3% |
| NIFTY, 2009-17 origins | + drift uncertainty 0.10 | 103 | 100% | 68% | 0.995 | 0.995 | 0.1095 | +6.3% |
| NIFTY, 2009-17 origins | production | 103 | 100% | 60% | 0.931 | 0.931 | 0.1061 | +6.3% |
| NIFTY, 2009-17 origins | recentred by past errors (point in time) | 103 | 98% | 63% | 1.002 | 1.015 | 0.1126 | -1.9% |
| NIFTY, 2018-25 origins | + drift uncertainty 0.03 | 92 | 88% | 59% | 0.715 | 0.905 | 0.1075 | +1.1% |
| NIFTY, 2018-25 origins | + drift uncertainty 0.06 | 92 | 89% | 64% | 0.740 | 0.893 | 0.1079 | +1.1% |
| NIFTY, 2018-25 origins | + drift uncertainty 0.10 | 92 | 92% | 68% | 0.797 | 0.900 | 0.1090 | +1.1% |
| NIFTY, 2018-25 origins | production | 92 | 88% | 58% | 0.706 | 0.909 | 0.1074 | +1.1% |
| NIFTY, 2018-25 origins | recentred by past errors (point in time) | 92 | 90% | 52% | 0.739 | 0.911 | 0.1151 | -4.4% |

1. **84% is within sampling error of 90%.** The 104 outcomes come from 26 overlapping 1-year windows of 4 portfolios that move together; a block bootstrap over the origin dates (blocks of one year) puts the 90% band's coverage between 72% and 94%.
2. **The misses are about location, not width.** 8 of the 17 misses are gold (it beat its expected return by 17% a year in 2019-25) and 7 are the rebound after the 2020 crash; without gold the band held 69 of 78 outcomes (88%).
3. **Earlier periods show the opposite error.** On 2016-18 origins the same bands held 98% of outcomes and on 2009-17 NIFTY origins 100%: they were too wide. Adding drift uncertainty raises 2019-25 coverage (up to 87%) but worsens the interval score before 2019; recentring on past forecast errors fixes the 2019-25 bias (interval score 1.061 -> 0.926) but worsens it before 2019 (0.487 -> 0.508; NIFTY 0.931 -> 1.015), i.e. it chases the last regime.

Decision: no change. The models are frozen at the round-10 settings; closing the gap further would mean tuning to 2019-25.
