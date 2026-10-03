# Model search (walk-forward 2021-2026, hyper-parameters tuned on 2019-2020 only)

## A. Relative return: does the model rank assets correctly over the next 21 days?

| Model | IC | ICIR | Days IC>0 | Direction hit | Top-quintile beats avg | Top-minus-bottom 21d | t-stat |
|---|---|---|---|---|---|---|---|
| Ridge | 0.026 | 0.12 | 56% | 51.4% | 49.7% | +0.58% | 1.3 |
| Random Forest | 0.011 | 0.06 | 51% | 51.2% | 49.7% | +0.15% | 0.4 |
| XGBoost | -0.002 | -0.01 | 48% | 50.2% | 47.4% | -0.12% | -0.3 |
| Ensemble (mean) | 0.003 | 0.02 | 50% | 50.4% | 48.5% | +0.04% | 0.1 |
| Momentum baseline (12m rank) | 0.009 | 0.04 | 53% | 47.3% | 49.5% | -0.02% | -0.0 |
| Reversal baseline (1m rank) | 0.049 | 0.21 | 56% | 52.4% | 51.2% | +0.77% | 1.5 |
| Low-vol baseline | -0.025 | -0.11 | 44% | 52.5% | 43.2% | -1.10% | -2.0 |

## B. Volatility: forecast of next-21-day realised volatility (log scale)

| Model | R2 | Correlation | Mean abs % error |
|---|---|---|---|
| Ridge | 0.712 | 0.846 | 25.5% |
| Random Forest | 0.700 | 0.839 | 26.1% |
| XGBoost | 0.708 | 0.844 | 25.9% |
| Ensemble (mean) | 0.719 | 0.849 | 25.4% |
| Trailing 21d vol (naive) | 0.585 | 0.793 | 30.7% |
| Trailing 63d vol (naive) | 0.658 | 0.824 | 29.0% |