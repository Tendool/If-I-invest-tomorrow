# Short-horizon volatility models (hour / day / week)

Volatility measured by the high-low range (Parkinson) of the bars inside each period; R2 on log volatility, pooled over the
30 stocks/ETFs (cash and the gilt ETF excluded), walk-forward out-of-sample. Settings chosen on a validation period that
precedes the test period. Free Yahoo intraday data limits the hour model to 29 test days.

| Horizon | Model in use | R2 | Within-asset R2 | Avg. error | Best simple rule (R2) | Test | Source |
|---|---|---|---|---|---|---|---|
| Next hour | Ridge + LightGBM average (HAR, time of day, range, market) | **0.629** | 0.500 | 20.7% | 0.521 (usual level for this hour) | 29 days, 5,220 forecasts | `scripts/short_horizon_search.py hour` |
| Next day | Ridge (HAR, range, overnight gap, market, VIX, weekday) | **0.536** | 0.315 | 22.8% | 0.485 (last 5 days) | 431 days, 12,925 forecasts | `scripts/intraday_models.py day --range` |
| Next week | Ridge + 35% "last month" (production features + yesterday's / 2-week range, weekday) | **0.420** | 0.330 | 24.5% | 0.308 (last month) | 2021-26, 39,941 forecasts | `scripts/weekly_model.py` |
| Next month (in the app) | Ridge + 20% "last quarter" | **0.589** | 0.189 | 25.3% | 0.503 (last quarter) | 2021-26, 40,423 forecasts | `models/vol_model_meta.json` |

Round-6 tuning (`reports/short_search_*.json`): the hour model gained 0.622 -> 0.629 from averaging Ridge with LightGBM; the week
model 0.412 -> 0.420 from yesterday's and the 2-week range; for the day model, 12-year daily-bar features did not help (R2 0.536 -> 0.525,
error 22.8% -> 22.4%), so it is unchanged. Measured close-to-close instead of by range, the same models score 0.42 (hour), 0.26 (day)
and 0.25 (week): the target is noisier, not the model worse.
