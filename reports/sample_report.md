# If I Invest Tomorrow - sample report

*Data as of 2026-10-01 - Rs.100,000 for 3 year(s), medium risk, target 12.0% p.a., preferred sectors: none*

**Market:** NIFTY 22,422 (-0.88% today, -10.9% 1y), India VIX 14.5, regime **Neutral / Sideways**, anomaly today: False

## Tomorrow's Investment Plan - Goal-Based (recommended)
Goal-Based stays within your medium-risk limits and has the best chance (58%) of reaching the 12% target.

| Asset | Sector | Weight | Amount | Shares @ price |
|---|---|---|---|---|
| GOLDBEES - Nippon Gold BeES | Gold | 20.0% | Rs.20,000 | 164 @ Rs.121.43 |
| SUNPHARMA - Sun Pharma | Pharma | 15.0% | Rs.15,000 | 8 @ Rs.1,801.00 |
| M&M - Mahindra & Mahindra | Auto | 15.0% | Rs.15,000 | 5 @ Rs.2,860.00 |
| BHARTIARTL - Bharti Airtel | Telecom | 15.0% | Rs.15,000 | 8 @ Rs.1,741.10 |
| COALINDIA - Coal India | Energy | 13.8% | Rs.13,780 | 33 @ Rs.420.40 |
| SBIN - State Bank of India | Banking | 9.8% | Rs.9,760 | 10 @ Rs.954.10 |
| NTPC - NTPC | Power | 8.4% | Rs.8,362 | 26 @ Rs.315.10 |
| TITAN - Titan Company | Consumer | 3.1% | Rs.3,099 | 1 @ Rs.4,515.70 |

## Financial insights
- Expected return **14.4%**, expected volatility **12.9%**, Sharpe 0.65, beta 0.74
- Probability of positive return **96%**, probability of achieving 12% target **58%**
- Expected max drawdown 14.5% (95th pct 28.2%); 1y VaR95 7.3%, CVaR95 13.9%
- Outcomes after 3y: worst 5% Rs.101,941 | median Rs.146,925 | best 5% Rs.206,622

## Stress tests
| Scenario | Portfolio return | P&L | Within loss limit |
|---|---|---|---|
| Market -2% shock | -1.5% | Rs.-1,487 | yes |
| Market -5% shock | -3.7% | Rs.-3,718 | yes |
| Market -10% shock | -7.4% | Rs.-7,436 | yes |
| Pharma sector crash (-25%) | -4.4% | Rs.-4,409 | yes |
| Interest-rate shock (+100bps) | -2.7% | Rs.-2,706 | yes |
| Oil-price shock (+25% Brent) | +0.2% | Rs.181 | yes |
| Replay: COVID crash (Jan-Mar 2020) | -26.8% | Rs.-26,756 | NO |
| Replay: Taper/IL&FS stress (Sep-Oct 2018) | -10.8% | Rs.-10,841 | yes |
| Replay: Global rate-hike selloff (Oct 2021-Jun 2022) | +0.5% | Rs.491 | yes |

## Five strategies compared
| Strategy | Exp. return | Volatility | Sharpe | P(positive) | P(target) | Median final | Within limits |
|---|---|---|---|---|---|---|---|
| Max Return | 14.8% | 14.2% | 0.62 | 94% | 58% | Rs.147,461 | yes |
| Min Risk | 7.1% | 4.9% | 0.22 | 99% | 4% | Rs.122,476 | yes |
| Max Sharpe | 12.4% | 9.5% | 0.67 | 98% | 50% | Rs.140,605 | yes |
| Goal-Based * | 14.4% | 12.9% | 0.65 | 96% | 58% | Rs.146,925 | yes |
| Crash-Resistant | 7.4% | 5.5% | 0.25 | 99% | 7% | Rs.123,409 | yes |

## Monte Carlo after a day-0 shock
| Scenario | Day-0 impact | Median final | P(target) |
|---|---|---|---|
| No shock (base case) | +0.0% | Rs.147,278 | 59% |
| Market -2% shock | -1.5% | Rs.145,088 | 56% |
| Market -5% shock | -3.7% | Rs.137,454 | 47% |
| Market -10% shock | -7.4% | Rs.132,146 | 41% |
| Pharma sector crash (-25%) | -4.4% | Rs.136,467 | 46% |
| Interest-rate shock (+100bps) | -2.7% | Rs.138,899 | 48% |
| Oil-price shock (+25% Brent) | +0.2% | Rs.147,545 | 60% |

## Invest now vs wait vs SIP
| Option | Median final | P(profit) | P(beats lump sum) |
|---|---|---|---|
| Invest now (lump sum) | Rs.146,205 | 96% | - |
| Wait 1 month, then invest | Rs.145,444 | 96% | 44% |
| Wait 3 months, then invest | Rs.143,725 | 96% | 38% |
| Wait 6 months, then invest | Rs.141,197 | 96% | 34% |
| SIP over 6 months | Rs.144,301 | 96% | 37% |
| SIP over 12 months | Rs.142,120 | 96% | 32% |

## Walk-forward backtest 2023-10-03 -> 2026-10-01
| Strategy | Total return | CAGR | Vol | Sharpe | Max DD |
|---|---|---|---|---|---|
| Max Return | +50.8% | 15.0% | 16.1% | 0.56 | -15.0% |
| Min Risk | +39.1% | 11.9% | 5.9% | 1.00 | -6.8% |
| Max Sharpe | +58.8% | 17.1% | 10.3% | 1.07 | -9.3% |
| Goal-Based | +55.1% | 16.1% | 8.9% | 1.14 | -8.1% |
| Crash-Resistant | +38.1% | 11.6% | 6.0% | 0.95 | -6.3% |
| NIFTY 50 (benchmark) | +14.8% | 4.8% | 13.3% | -0.09 | -15.8% |
| Equal-weight stocks | +30.3% | 9.5% | 12.6% | 0.27 | -14.9% |

## ML validation (walk-forward 2021-2026)
|                            |   rmse |    mae |   dir_acc |   ic_cross_section |   ic_pooled |   n_test |
|:---------------------------|-------:|-------:|----------:|-------------------:|------------:|---------:|
| Ridge (Linear)             | 0.0674 | 0.0514 |    0.5173 |             0.0231 |     -0.0156 |    43400 |
| Random Forest              | 0.0673 | 0.0512 |    0.5444 |             0.0211 |      0.004  |    43400 |
| XGBoost                    | 0.069  | 0.0526 |    0.5272 |             0.0213 |     -0.0109 |    43400 |
| GRU                        | 0.0794 | 0.0604 |    0.5105 |             0.0327 |     -0.0093 |    43400 |
| Historical mean (baseline) | 0.0658 | 0.05   |    0.574  |           nan      |     -0.0179 |    43400 |

Selected: Ridge (Linear); ML weight in expected returns 12%.

*Model-based simulation on historical data - not investment advice; no real money is used.*