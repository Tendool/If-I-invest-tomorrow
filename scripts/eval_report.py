"""Assemble reports/evaluation.md and the slide figures from the eval_* JSON files.

    python scripts/eval_report.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ifit import config as C  # noqa: E402

R = C.REPORTS_DIR
FIG = ROOT / "presentation" / "figures"
INK, MUTED, FAINT, RULE, BRAND = "#17160f", "#6b685e", "#9b978b", "#d6d2c6", "#0e5a43"
C1, C2, C3, C4, C7 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#4a3aa7"
plt.rcParams.update({
    "font.family": "Segoe UI", "font.size": 8, "axes.edgecolor": RULE, "axes.labelcolor": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.spines.left": False, "axes.grid": True, "axes.grid.axis": "y", "grid.color": "#e6e3da", "grid.linestyle": (0, (2, 3)), "xtick.color": FAINT,
    "ytick.color": FAINT, "xtick.major.size": 0, "ytick.major.size": 0, "legend.frameon": False, "legend.fontsize": 7, "text.color": INK,
    "figure.facecolor": "none", "axes.facecolor": "none", "savefig.facecolor": "none", "pdf.fonttype": 42, "axes.axisbelow": True,
})


def load(n):
    return json.loads((R / n).read_text(encoding="utf-8"))


def figures(ret, vol, cal, port):
    FIG.mkdir(parents=True, exist_ok=True)
    # equity curves
    cur = pd.read_csv(R / "eval_portfolio_curves.csv", index_col=0, parse_dates=True)
    fig, ax = plt.subplots(figsize=(5.4, 2.9))
    pick = {"E  Full system (D + regime overlay)": (BRAND, 1.9, "Full system"), "D  C+ + return tilt": (C3, 1.1, "Volatility + return tilt"),
            "B  Min-variance + volatility model": (C1, 1.1, "Min-variance + volatility model"),
            "NIFTY 50 ETF (benchmark)": (MUTED, 1.4, "NIFTY 50 ETF"), "Equal-weight stocks (monthly)": (C4, 1.1, "Equal-weight stocks")}
    for k, (col, lw, lab) in pick.items():
        ax.plot(cur.index, cur[k] * 100, color=col, lw=lw, label=lab)
    ax.set_ylabel("Value of 100 invested (after costs)")
    ax.legend(loc="upper left", ncol=2)
    fig.savefig(FIG / "eval_curves.pdf", bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    # year-by-year IC and vol R2
    yrs = sorted(ret["by_year"])
    fig, axs = plt.subplots(1, 2, figsize=(5.6, 2.2))
    ic = [ret["by_year"][y]["ic"] for y in yrs]
    axs[0].bar(yrs, ic, color=[BRAND if v > 0 else "#b3361f" for v in ic], width=0.6)
    axs[0].axhline(0, color=RULE, lw=0.8)
    axs[0].set_title("Return signal: IC by year", fontsize=8, color=INK, loc="left")
    vy = vol["by_year"]
    x = np.arange(len(yrs))
    axs[1].bar(x - 0.2, [vy[y]["r2"] for y in yrs], 0.38, color=BRAND, label="Model")
    axs[1].bar(x + 0.2, [vy[y]["naive_63d_r2"] for y in yrs], 0.38, color=FAINT, label="Same as last quarter")
    axs[1].set_xticks(x, yrs)
    axs[1].set_title("Volatility model: R² by year", fontsize=8, color=INK, loc="left")
    axs[1].set_ylim(0, 0.85); axs[1].legend(loc="upper left", ncol=2, fontsize=6)
    fig.tight_layout()
    fig.savefig(FIG / "eval_by_year.pdf", bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    # calibration curve
    levels = [0.5, 0.75, 0.9, 0.95, 0.99]
    fig, ax = plt.subplots(figsize=(3.4, 2.9))
    ax.plot([0.45, 1], [0.45, 1], color=FAINT, lw=1, ls="--", label="Perfect")
    for (m, v), col in zip(cal.items(), (C1, C2, C3)):
        ax.plot(levels, [v[str(int(q * 100))] for q in levels], marker="o", ms=3, lw=1.3, color=col, label=m.split(" (")[0].replace("Current", "Current model"))
    ax.set_xlabel("Stated probability")
    ax.set_ylabel("Outcomes inside interval")
    ax.legend(loc="upper left", fontsize=6.3)
    fig.savefig(FIG / "eval_calibration.pdf", bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def md_table(rows, header):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(map(str, r)) + " |" for r in rows]
    return "\n".join(out)


def report(ret, vol, cal, reg, ano, port):
    L = ["# Evaluation of the model stack", "",
         "Everything is out-of-sample: settings chosen on 2019-20, scored on a 2021-26 expanding-window walk-forward with purged targets; regime and anomaly models "
         "are refit each year on pre-year data. The liquid fund (a flat accrual) is excluded from all model scores.", "",
         "## 1. Return signal (21-day relative return)", ""]
    rows = []
    for k, v in ret["configs"].items():
        rows.append([k.replace(" | ", " / "), f"{v['mean']:+.3f}", f"{v['median']:+.3f}", f"{v['sd']:.3f}", f"{v['ir']:+.2f}", f"{v['pct_pos']:.0%}", f"{v['t_newey_west']:+.2f}", f"{v['t_nonoverlap']:+.2f}", f"{v['inner_ic']:+.3f}"])
    L += [md_table(rows, ["Features / target", "mean IC", "median", "sd", "IR", "% days > 0", "t (Newey-West)", "t (independent windows)", "IC on 2019-20 validation"]), "",
          f"The IC on the 2019-20 validation window is at or below zero for every configuration, so validation cannot pick a winner (it picked `{ret['selected_on_validation'].replace(' | ', ' / ')}`, "
          f"out-of-sample IC {ret['selected_on_validation_oos_ic']:+.3f}). Adding relative-strength features (vs index and vs sector) lifts the out-of-sample IC from 0.027 to 0.041 "
          "(t 2.2 Newey-West, 1.6 on independent windows) and helps on all five targets (stacking cross-sectional ranks on top does not help consistently), but it is not significant at 5% on independent windows and was not confirmed "
          "by the validation window, so it is a candidate, not adopted. Sector-neutral targets are weaker: most of the little signal is cross-sector.", "",
          "Round 6 (section 9) replaced the fitted Ridge model in production with a fixed reversal + momentum composite, the first signal with skill on the 2017-20 validation; "
          "round 7 (section 10) moved it to residual returns and round 10 (section 13) added reversal relative to the asset's sector. "
          "The tables in this section are the study of fitted models (Ridge, alpha 300000) that led there.", "",
          "### By year (Ridge study model)", ""]
    rows = [[y, f"{v['ic']:+.3f}", "" if v["ic_t_nw"] is None else f"{v['ic_t_nw']:+.2f}", f"{v['rmse']:.4f}", f"{v['rmse_mean_baseline']:.4f}", f"{v['dir_acc']:.1%}"] for y, v in ret["by_year"].items()]
    L += [md_table(rows, ["Year", "IC", "IC t-stat", "RMSE", "RMSE of historical mean", "Direction"]), ""]
    rr = ret["rolling"]
    L += [md_table([[k, f"{v['min']:+.3f}", f"{v['median']:+.3f}", f"{v['max']:+.3f}", f"{v['share_positive']:.0%}"] for k, v in rr.items()],
                   ["Rolling IC window", "min", "median", "max", "share of windows > 0"]), "",
          "## 2. Volatility model", ""]
    L += [md_table([[k, f"{v['r2']:.3f}", f"{v['within_asset_r2']:.3f}", f"{v['err']:.1%}", f"{v['corr']:.3f}"] for k, v in vol["models"].items() if "Parkinson" not in k],
                   ["Model", "R2", "within-asset R2", "avg. error", "correlation"]), "",
          "Production = Ridge on realised, range-based, long-run-level, seasonal, asset-class and earnings-calendar features, blended 85/15 with trailing 63-day volatility (features and blend weight chosen on a 2017-20 walk-forward validation, rounds 4, 6, 7 and 9; trained on every day since round 10). "
          "Elastic Net and Huber regression are statistically tied with plain Ridge, so the simpler model stays; a 63-day target is a worse predictor of the next 21 days. "
          "(Rows here need a full 63-day look-ahead, so the final weeks of 2026 drop out and R2 reads slightly lower than the 0.604 in the production meta file.)", "",
          md_table([[y, f"{v['r2']:.3f}", f"{v['naive_63d_r2']:.3f}", f"{v['naive_21d_r2']:.3f}", f"{v['err']:.1%}"] for y, v in vol["by_year"].items()],
                   ["Year", "model R2", "same as last quarter", "same as last month", "avg. error"]), "",
          md_table([[k, f"{v['r2']:.3f}", f"{v['err']:.1%}", v["n"]] for k, v in vol["by_class"].items()], ["Asset class", "R2 within class", "avg. error", "n"]), "",
          "The model beats both naive rules in every year. Within a class, R2 is lower because much of the pooled R2 is knowing which assets are riskier.", "",
          "## 3. Monte Carlo calibration (1-year horizon, 104 forecasts per method)", ""]
    cols = ["50", "75", "90", "95", "99"]
    L += [md_table([[m] + [f"{v[c]:.0%}" for c in cols] + [f"{v['cover90_excl_2020']:.0%}", f"{v['cover90_2020_origins']:.0%}", f"{v['mean_error']:+.1%}"] for m, v in cal.items()],
                   ["Simulator", "50% interval", "75%", "90%", "95%", "99%", "90% excl. 2020 origins", "90% for 2020 origins", "mean error of expected return"]), "",
          "The production simulator draws a per-path error in the expected return (standard error sigma/sqrt(5 years), not tuned), which moved coverage from 44/69/81/84/93% to 49/73/82/84/93%; letting the regime model learn from 2008- (not just 2014-) moved it to 53/74/81/88/96%. "
          "Round 6 added a per-path volatility level (log-normal, sd 0.17); round 10 raised it to 0.35, chosen on 1-year NIFTY forecasts from 2009-17 (section 13), which moved the 90% band "
          "from 82% to 84% here. "
          "Fatter tails (dof 3) and a block bootstrap of the portfolio's own history do not fix the outer tails. The remaining miss is concentrated in forecasts made in 2020 (COVID crash and "
          "rebound), and realised returns beat the expected return by about 6-7% on average, which shifts the whole distribution. Outside 2020 the 90% band holds 89%. "
          "Of the 17 forecasts outside the 90% band, 8 are gold (its 2019 and 2024-25 rallies; it beat its expected return by 17% a year and its band held 69%, "
          "against 85-92% for the NIFTY ETF, the balanced portfolio and the 8 stocks), 7 are the rebound after the 2020 crash and 2 are falls (2019-20, 2025-26). "
          "Closing the gap would mean raising expected returns to match 2019-25, i.e. fitting the test.", "",
          "## 4. Regime model", "",
          "Transition matrices (full-sample labels):", ""]
    T = reg["daily_transition"]
    L += [md_table([[a] + [f"{T[b][a]:.3f}" for b in T] for a in T], ["Daily from \\ to"] + list(T)), ""]
    T = reg["transition_21d"]
    L += [md_table([[a] + [f"{T[b][a]:.3f}" for b in T] for a in T], ["21-day from \\ to"] + list(T)), "",
          "Point-in-time outcomes after each regime (2021-26; the point-in-time model never entered the Bear state because 2021-26 had no crash):", ""]
    L += [md_table([[k, v["days"], f"{v['vol_next_21d']:.1%}", f"{v['mdd_next_21d']:.1%}", f"{v['p_drawdown_5pct']:.0%}", f"{v['ret_21d_mean']:+.2%}", f"{v['p_loss_21d']:.0%}"]
                    for k, v in reg["conditional_pit"].items() if v["days"]],
                   ["Regime", "days", "next-21d market vol", "next-21d worst drawdown", "P(drawdown >= 5%)", "next-21d return", "P(21d loss)"]), "",
          f"Regime probabilities as extra inputs to the volatility model change R2 from {reg['vol_with_regime']['r2_without_regime']:.4f} to {reg['vol_with_regime']['r2_with_regime']:.4f}: "
          "no gain, because VIX and market volatility already carry the information. The regime is useful as a risk label (drawdown probability 13% vs 35%), not as an input to the volatility forecast.", "",
          "## 5. Anomaly detector", ""]
    for k, v in ano.items():
        L += [f"**{k}**: {v['flagged']['days']} flagged days in {v['episodes']} episodes", "",
              md_table([[lab, v[lab]["days"], f"{v[lab]['vol_next_21d']:.1%}", f"{v[lab]['mdd_next_21d']:.1%}", f"{v[lab]['p_drawdown_5pct']:.0%}", f"{v[lab]['ret_21d_mean']:+.2%}", f"{v[lab]['p_21d_loss_gt_3pct']:.0%}"]
                        for lab in ("flagged", "normal")], ["", "days", "next-21d vol", "next-21d worst drawdown", "P(drawdown >= 5%)", "next-21d return", "P(21d loss > 3%)"]), ""]
    L += ["The 2% production setting flags only 3 days in 2021-26 (too few to test). At the 5% and 10% settings, flagged days are followed by much higher volatility "
          "(about 21-23% vs 13%) and a 5% drawdown 60-65% of the time against 21%, but not by lower returns (markets tended to rebound). So the detector is a volatility/drawdown warning, not a return signal. "
          "Flagged days cluster into 8-20 episodes, so the p-values overstate significance.", "",
          "## 6. Portfolio backtest (walk-forward, monthly rebalance, realistic costs)", "",
          "Costs per asset class (ifit/costs.py, approximate 2025 NSE schedule): stocks 0.17% to buy and 0.15% to sell (STT 0.1% each way, stamp duty, exchange "
          "and SEBI fees with GST, half bid-ask spread 0.05%); equity ETFs about 0.06%; gold and gilt ETFs about 0.11%. Trades happen at the rebalance date's close.", "",
          f"{port['start']} to {port['end']}, {port['rebalances']} rebalances. Long-only, 'medium' risk caps. Annualised turnover is the sum of one-way trades.", ""]
    rows = []
    for n, v in port["table"].items():
        rows.append([n, f"{v['cagr']:.1%}", f"{v['vol']:.1%}", f"{v['sharpe']:.2f}", f"{v['sortino']:.2f}", f"{v['max_drawdown']:.1%}", f"{v['calmar']:.2f}", f"{v['turnover_ann']:.1f}x",
                     f"{v['costs_pct_of_start']:.1%}", f"{v['hit_rate_monthly']:.0%}", f"{v['downside_dev']:.1%}", f"{v['var95_1d']:.2%}", f"{v['cvar95_1d']:.2%}",
                     f"{v['vs_benchmark_cagr']:+.1%}", "" if v["info_ratio"] is None else f"{v['info_ratio']:+.2f}"])
    L += [md_table(rows, ["Strategy", "CAGR", "Vol", "Sharpe", "Sortino", "Max DD", "Calmar", "Turnover/yr", "Cumulative costs (% of start)", "Hit rate (months)", "Downside dev", "VaR95 1d", "CVaR95 1d",
                          "vs NIFTY (CAGR)", "Info ratio"]), "",
          "Reading it like-for-like (round-10 models, realistic costs): in the max-Sharpe family the volatility model lifts Sharpe 0.54 -> 0.73; in the minimum-variance family it is "
          "neutral (0.95 -> 0.95). The return tilt (residual reversal + momentum + sector-relative reversal, weight 0.29) adds 0.73 -> 0.80 although it raises turnover from 4.7x to "
          "7.5x a year (costs 6.4% -> 9.3% of capital over the period). The regime overlay trades return for lower volatility and drawdown (full system Sharpe 0.80, max drawdown -12.2%). "
          "Until round 10 this backtest credited each rebalance with that day's own return (weights chosen at a close earned the move into that close): the one-day look-ahead "
          "flattered the max-Sharpe strategies by about 0.07 and penalised the reversal tilt, which is why earlier versions read 0.60 -> 0.80 and showed the tilt hurting. "
          "Every strategy beats the NIFTY 50 ETF (0.36) on risk-adjusted return; an equal-weight basket of the 26 stocks (Sharpe 0.84, CAGR 16.9%) matches the full system. "
          "Caveat: 5.7 years, one regime; section 14 tests other periods, cost levels and confidence intervals.", "",
          "## 7. Round 4 (selection on a 2017-20 walk-forward validation; this protocol change was made after 2021-26 had been seen, so gains are tentative)", "",
          "| Idea | Validation 2017-20 | Test 2021-26 | Decision |", "|---|---|---|---|",
          "| Volatility: + long-run level, blended 80/20 with last quarter | R2 0.504 -> 0.533 | R2 0.583 -> 0.589, within-asset 0.177 -> 0.189 | adopted |",
          "| Volatility: + GARCH(1,1) forecast as a feature | R2 0.504 -> 0.477 | 0.585 | rejected |",
          "| Returns: any feature set / target (relative strength, ranks, excess vs NIFTY) | IC between -0.011 and +0.006 | 0.026 to 0.052 | rejected: no skill in 2017-20 |",
          "| Monte Carlo: parameter uncertainty in the expected return (not tuned) | - | mean coverage gap 0.078 -> 0.051 | adopted |",
          "| Monte Carlo: online recalibration of the spread | - | gap 0.031, but driven by a distribution shortcut | rejected |",
          "| Drawdown warning: logistic model on VIX, regime, anomaly and market features | AUC 0.41 (VIX alone 0.66) | AUC 0.49 (VIX alone 0.74) | rejected |",
          "| Portfolio: half-step rebalancing | - | turnover halved, Sharpe 0.77 -> 0.75 | rejected |", "",
          "AUC of each score for 'NIFTY falls 5% or more within the next 21 days' (test 2021-26): VIX level 0.74, regime P(not calm) 0.69, Isolation-Forest anomaly score 0.61.", "",
          "## 8. Round 5: more data (scripts/extended_data.py)", "",
          "Longer history (Yahoo 'max': NIFTY from 2007, VIX from 2008, stocks from 1996-2010) and a wider universe (+45 large NSE stocks). Models trained on the "
          "extended data, scored on exactly the production test rows (31 assets, 2021-26). The extra stocks are today's large caps (survivorship bias).", "",
          "| Experiment | Validation 2017-20 | Test 2021-26 | Decision |", "|---|---|---|---|",
          "| Volatility, longer history (alpha and blend re-chosen on validation) | R2 0.533 -> 0.526 | R2 0.589 -> 0.601, within-asset 0.189 -> 0.226 | rejected: better in 5 of 10 years only |",
          "| Volatility, wider universe | R2 0.533 -> 0.525 | 0.589 -> 0.586 | rejected |",
          "| Volatility, longer + wider | R2 0.533 -> 0.519 | 0.589 -> 0.600 | rejected |",
          "| Returns, longer history | IC -0.015 -> -0.006 | 0.028 -> 0.043 | rejected: still no skill on validation |",
          "| Returns, wider universe | IC -0.015 -> -0.042 | 0.028 -> 0.035 | rejected |",
          "| Regime model learns from 2008- (incl. the 2008 crash), only for the regime model | - | MC coverage gap 0.051 -> 0.037 (same seeds), better or equal at all 5 levels | adopted |", "",
          "With 2008 included, the Bear/Volatile state is learned from 394 days (2008-09 and 2020) instead of 65. Its average return is positive (+17% p.a.) because crisis "
          "periods include the violent rebounds; it is defined by 45% volatility, VIX 42 and a -35% average drawdown.", "",
          "## 9. Round 6 (scripts/model_search_v5.py; selection on 2017-20 validation, test 2021-26 reported once)", "",
          "| Idea | Validation 2017-20 | Test 2021-26 | Decision |", "|---|---|---|---|",
          "| Volatility: + seasonal features (same window last year, results-season share), blend 85/15 | R2 0.533 -> 0.536 | R2 0.589 -> 0.592, within-asset 0.189 -> 0.192; better in 4 of 6 years | adopted |",
          "| Volatility: + implied systematic vol (beta x India VIX + idiosyncratic) | R2 0.533 -> 0.530 | 0.595 | rejected on validation |",
          "| Volatility: seasonal + implied systematic | R2 0.533 -> 0.533 | 0.598 | rejected on validation |",
          "| Volatility: boosted trees on Ridge residuals / trees alone | R2 0.525 / 0.474 | 0.591 / 0.594 | rejected |",
          "| Returns: 1-month reversal (no fitting) | IC +0.015 (t 1.9) | IC +0.049 | - |",
          "| Returns: 12-1 month momentum (no fitting) | IC +0.052 (t 1.2) | IC +0.024 | picked by the pre-set rule (highest mean IC) |",
          "| Returns: reversal + momentum composite (no fitting) | IC +0.049 (t 2.3) | IC +0.052 (t 2.4), R2 vs zero +0.24% (Ridge -0.24%); positive in 4 of 6 years | adopted (see note) |",
          "| Returns: LightGBM ranker on rank features | IC -0.015 | IC +0.036 | rejected |",
          "| Monte Carlo: volatility uncertainty, sd 0.17 measured on pre-2018 data | - | mean coverage gap 0.045 -> 0.039; 90% band 81% -> 82% | adopted |",
          "| Plan: whole-share rounding gives positions too small for one share to the rest of the plan | - | Rs 1 lakh medium plan invests 97.0% (was 92.6%) | adopted |", "",
          "Note on the return signal: the rule fixed before the run (highest mean validation IC) picks momentum alone; momentum and the composite are tied on mean IC (0.052 vs 0.049), and the composite "
          "is far more consistent (t 2.3 vs 1.2), which is why it is used. That choice was made after the test numbers had been seen, so its test IC is tentative. It is the first return signal in six rounds "
          "with skill on the validation years; every fitted model (Ridge, Random Forest, XGBoost, LightGBM, GRU) stays at or below zero there. In the portfolio backtest it does not pay after costs "
          "(section 6). Round 7 replaced it with the residual version (section 10).", "",
          "## 10. Round 7 (scripts/model_search_v6.py; rules fixed before running: a candidate must beat the incumbent on validation)", "",
          "The 2017-20 validation years had been used in earlier rounds, so the bar was raised from 'positive' to 'better than the model in use'. The Monte Carlo was "
          "decided on 2016-18 forecast origins, which no earlier decision had used.", "",
          "| Idea | Validation | Test | Decision |", "|---|---|---|---|",
          "| Volatility: + asset-class effects (ETF, gold, bond dummies and interactions) | R2 0.5361 -> 0.5375 | R2 0.592 -> 0.597, within-asset 0.192 -> 0.202, error 25.2% -> 24.9%; bonds 0.14 -> 0.22 | adopted |",
          "| Volatility: + log-VIX nonlinearity | 0.5352 | 0.592 | rejected |",
          "| Volatility: recency-weighted training (half-life 3 years) | 0.5330 | 0.585 | rejected |",
          "| Volatility: log VIX + asset class (+ recency) | 0.5370 (0.5345) | 0.598 (0.595) | rejected: below the adopted variant on validation |",
          "| Returns: residual reversal + residual momentum (Blitz, Huij & Martens) | IC 0.061 (t 3.2) | IC 0.046 (t 2.2); 2017-26 pooled 0.052 vs 0.051 for round 6 | adopted |",
          "| Returns: reversal + momentum + seasonality (Heston & Sadka) | IC 0.058 (t 2.8) | IC 0.039 | rejected: lower validation t |",
          "| Returns: residual reversal alone / residual momentum alone | t 2.8 / 1.3 | IC 0.050 / 0.016 | rejected |",
          "| Returns: 52-week high (George & Hwang) | IC 0.013 (t -0.2) | IC -0.058 | rejected |",
          "| Returns: all six factors equal weight / Ridge fitted on them | t 2.4 / -0.1 | IC 0.023 / 0.030 | rejected |",
          "| Monte Carlo: Student-t dof 4 or 8 | gap 0.057 -> 0.049 (identical for 4 and 8) | gap 0.037 / 0.033 | rejected: opposite tail changes score the same, a random-number effect |",
          "| Monte Carlo: uncertainty in the CAPM/history blend weight | gap 0.057 (no change) | 0.037 | rejected |", "",
          "Following the rule cost a little on the test years for returns (IC 0.052 -> 0.046) and gained over the full ten years (0.051 -> 0.052); the decision was not revisited. "
          "On 2016-18 origins the simulated bands were too wide (90% band held 98%), on 2019-25 too narrow (82%): the two periods disagree, so no change was made.", "",
          "## 11. Round 8: nested selection and ensembles (scripts/model_search_v7.py)", "",
          "Every candidate makes walk-forward predictions for 2017-26; for each test year the choice (best single, top-3 average, or non-negative stacking weights / IC weights) "
          "is learned from earlier years only, so the 2021-26 score stays honest however many candidates are tried. "
          "Re-run after round 9 (every candidate now has the earnings-calendar features); the round-8 run against the round-7 model is in brackets. "
          "Rule, fixed before the re-run: adopt a nested procedure only if it scores strictly higher than the fixed production model on 2021-26.", "",
          "| Procedure | Volatility R2 (2021-26) | Return IC (2021-26) |", "|---|---|---|",
          "| Production, fixed | **0.603** (round 7: 0.597) | **0.046** (t 2.2) |",
          "| Best single candidate, chosen each year on earlier years | 0.600 (0.594) | 0.046 (picks production every year: a tie, not a gain) |",
          "| Top-3 average | 0.597 (0.591) | 0.036 |",
          "| Stacking with non-negative weights / IC-weighted factor mix | 0.600 (0.596) | 0.037 |",
          "| Best individual alternatives | Ridge + implied/log-VIX 0.603, Huber 0.599 (error 23.7%), LightGBM 0.53-0.56 | reversal + momentum 0.051, residual reversal 0.050 |", "",
          "No nested procedure beats the production models in either run, so nothing changed. Choosing a single candidate by its 2021-26 score "
          "(e.g. Ridge + implied/log-VIX, 0.6030 vs 0.6026, whose features were rejected on validation in rounds 6 and 7) would be selection on the test years and is not done. "
          "The best-single choices are unblended Ridge forecasts, while production blends Ridge 85/15 with last quarter's volatility; stacking can learn "
          "such a blend, but its weights move from year to year (LightGBM 0.16-0.30, EWMA volatility 0.16-0.25). "
          "With this data (daily prices, VIX, macro series and quarterly results for 32 assets) the models are at the "
          "accuracy that an honest, automatic search can reach; further gains would need new information (company fundamentals, "
          "options-implied volatility per stock, intraday prices with long history).", "",
          "## 12. Round 9: earnings data (scripts/download_earnings.py, ifit/earnings.py, scripts/model_search_v8.py)", "",
          "New information: every quarterly result of the 26 stocks since about 2005 (Yahoo Finance: date, EPS estimate, reported EPS, surprise). A result is "
          "used only from the first trading day after its announcement date; the next results date is projected from past dates (median gap), never read from the "
          "published schedule. A unit test checks that no feature sees a result early. Rules as in round 7: adopt only what beats the model in use on 2017-20.", "",
          "| Idea | Validation 2017-20 | Test 2021-26 | Decision |", "|---|---|---|---|",
          "| Volatility: + projected results window and the stock's typical result-day jump | R2 0.5375 -> 0.5411 | R2 0.597 -> 0.603, within-asset 0.202 -> 0.216, stocks 0.265 -> 0.278, error 24.9% -> 24.6%; better in 5 of 6 years | adopted |",
          "| Volatility: window x jump only | R2 0.5403 | R2 0.601 | rejected: below the full set |",
          "| Returns: earnings surprise (post-earnings drift) | IC 0.026 (t 1.2) | IC 0.003 | rejected |",
          "| Returns: earnings-announcement return | IC 0.036 (t 0.5) | IC -0.012 | rejected |",
          "| Returns: incumbent + surprise + announcement return | IC 0.074 (t 2.6) | IC 0.030 | rejected: validation t below the incumbent's 3.2 (and lower on test) |", "",
          "Post-earnings drift, one of the best-documented anomalies in US data, shows no skill on these large, heavily followed NSE stocks. "
          "The earnings calendar does help volatility: the model now knows when each stock's next results are due and how much that stock usually moves on them. "
          "In the portfolio backtest (before the round-10 look-ahead fix) every volatility-model strategy improved slightly (max-Sharpe 0.79 -> 0.80, min-variance 0.95 -> 0.97, full system 0.75 -> 0.77).", ""]
    L += round10_sections()
    L += calibration_check_section()
    (R / "evaluation.md").write_text("\n".join(L), encoding="utf-8")


def calibration_check_section():
    """Section 15: why the 90% band holds 84%, and whether it can be fixed without needlessly wide bands."""
    j = lambda n: json.loads((R / n).read_text(encoding="utf-8"))
    pf, nf = j("calibration_check_portfolios.json"), j("calibration_check_nifty.json")
    L = ["## 15. Why 84% and not 90%? (scripts/eval_calibration_check.py)", "",
         "Scores that reward calibration and sharpness together (Gneiting & Raftery 2007): the 90% interval score (band width + 20 x the distance "
         "of an outcome outside the band; lower is better, so a band that is too wide pays for its width) and the CRPS. Rule fixed before running: "
         "adopt a candidate only if it lowers the interval score on origins before 2019 in both samples.", "",
         "| Sample | Candidate | n | 90% band held | 50% band held | mean 90% width | interval score | CRPS | mean error |", "|---|---|---|---|---|---|---|---|---|"]
    for lab, src in (("4 portfolios", pf), ("NIFTY", nf)):
        for period, d in src.items():
            if not isinstance(d, dict) or not all(isinstance(v, dict) and "n" in v for v in d.values()):
                continue
            for c, v in d.items():
                L.append(f"| {lab}, {period} | {c} | {v['n']} | {v['cover90']:.0%} | {v['cover50']:.0%} | {v['width90']:.3f} | {v['is90']:.3f} | {v['crps']:.4f} | {v['mean_error']:+.1%} |")
    lo, hi = pf["production_2019_25_cover90_ci"]
    L += ["",
          f"1. **84% is within sampling error of 90%.** The 104 outcomes come from 26 overlapping 1-year windows of 4 portfolios that move together; a "
          f"block bootstrap over the origin dates (blocks of one year) puts the 90% band's coverage between {lo:.0%} and {hi:.0%}.",
          "2. **The misses are about location, not width.** 8 of the 17 misses are gold (it beat its expected return by 17% a year in 2019-25) and 7 "
          "are the rebound after the 2020 crash; without gold the band held 69 of 78 outcomes (88%).",
          "3. **Earlier periods show the opposite error.** On 2016-18 origins the same bands held 98% of outcomes and on 2009-17 NIFTY origins 100%: "
          "they were too wide. Adding drift uncertainty raises 2019-25 coverage (up to 87%) but worsens the interval score before 2019; recentring on "
          "past forecast errors fixes the 2019-25 bias (interval score 1.061 -> 0.926) but worsens it before 2019 (0.487 -> 0.508; NIFTY 0.931 -> 1.015), "
          "i.e. it chases the last regime.",
          "",
          "Decision: no change. The models are frozen at the round-10 settings; closing the gap further would mean tuning to 2019-25.", ""]
    return L


def round10_sections():
    """Sections 13 (round-10 search) and 14 (robustness), built from the saved results."""
    j = lambda n: json.loads((R / n).read_text(encoding="utf-8"))
    sv, sc, ce, mc, rt = j("model_search_v9_vol.json"), j("model_search_v9_vol_combos.json"), j("model_search_v9_ceiling.json"), j("model_search_v9_mc.json"), j("model_search_v9_returns.json")
    wf, pl = j("eval_robustness_walkforward.json"), j("eval_robustness_plans.json")
    L = ["## 13. Round 10 (scripts/model_search_v9.py; rules fixed before running: beat the model in use on 2017-20)", "",
         "### Volatility", "",
         "| Idea | Validation R2 2017-20 | Test R2 2021-26 | within-asset | stocks | Decision |", "|---|---|---|---|---|---|"]
    rows = dict(sv["results"])
    rows.update({k: v for k, v in sc["results"].items() if k.startswith("C +")})
    for k, v in rows.items():
        dec = "in use" if k.startswith("A ") else ("adopted" if k == "C every day in training" else "rejected")
        L.append(f"| {k} | {v['val_r2']:.4f} | {v['test_r2']:.4f} | {v['test_within']:.3f} | {v['test_stock_r2']:.3f} | {dec} |")
    L += ["",
          "Adopted: training on every day instead of every third (validation 0.541 -> 0.552, test 0.603 -> 0.604). The early validation years had little history, so three "
          "times the rows helped there more than in the test years. Training on a cleaner range-based measure of the same 21 days (intraday Garman-Klass + overnight return, "
          "stocks only, ETF high/low prints are unreliable) raised the test R2 to 0.606 but lowered validation, so it was rejected. Correcting each asset with its own past "
          "errors added nothing out of sample.", "",
          "**How high can R2 go?** The target, the volatility of the next 21 daily returns, is itself a noisy measurement. Splitting each window into odd and even days gives two "
          f"independent measurements of the same month; their agreement (split-half reliability, Spearman-Brown) shows that only {ce['all assets']['reliability']:.0%} of the "
          f"target's variation is true volatility for all assets and {ce['stocks']['reliability']:.0%} for single stocks. A forecaster that knew next month's true volatility "
          "exactly would score about that; ours reaches 0.60 (all assets). Against the cleaner range-based measure of the same 21 days, our stock forecasts score "
          f"R2 {ce['stocks_production_vs_range_based']:.2f} instead of {ce['stocks_production_vs_close_to_close']:.2f}: part of the apparent error is noise in the target "
          "(Andersen & Bollerslev 1998). Reaching 0.65 would need new information (options-implied volatility per stock, intraday data), not a better fit.", "",
          "### Monte Carlo (1-year NIFTY forecasts from the long 2007- history)", "",
          "| Setting | 2009-17 origins: 50/75/90/95/99% bands held | error | 2019-25 origins | error |", "|---|---|---|---|---|"]
    for k, v in mc["results"].items():
        f = lambda c: "/".join(f"{c[q] * 100:.0f}" for q in ("0.5", "0.75", "0.9", "0.95", "0.99"))
        L.append(f"| {k}{' (production before)' if k == mc['production'] else ''}{' (chosen)' if k == mc['chosen'] else ''} | {f(v['choice_coverage'])} | {v['choice_err']:.3f} | {f(v['report_coverage'])} | {v['report_err']:.3f} |")
    L += ["",
          "On 2009-17 origins the bands were too wide (90% band held 100%); on 2019-25 too narrow. Higher volatility uncertainty fits both better (its heavier tails "
          "and narrower centre), extra drift uncertainty does not. Chosen: 0.35, in line with how much next-year NIFTY volatility moved against its trailing 5-year "
          "estimate (sd of the log ratio 0.25 on 2009-17 origins, 0.45 on 2019-25). On the standard 104-forecast test (section 3) the 90% band moves from 82% to 84% "
          "and the 99% band from 97% to 100%.", "",
          "### Return signal", "",
          "| Signal | Validation IC (t) 2017-20 | Test IC (t) 2021-26 |", "|---|---|---|"]
    for k, v in rt["results"].items():
        L.append(f"| {k}{' **(adopted)**' if k == rt['chosen'] else ''} | {v['val_ic']:+.4f} ({v['val_t']:+.2f}) | {v['test_ic']:+.4f} ({v['test_t']:+.2f}) |")
    L += ["",
          "Adopted: adding the residual 1-month return relative to the asset's own sector (a stock that fell more than its sector tends to recover; Da, Liu & Schaumburg 2014). "
          "Validation t 3.19 -> 3.95 (same IC 0.061); test IC 0.046 -> 0.057, R2 against a zero forecast +0.22% (Gu-Kelly-Xiu definition; the round-7 signal had +0.09%, "
          "fitted Ridge -0.24%), direction right 51.5% of the time. Skill weight 0.23 -> 0.29. The other documented signals (1-week reversal, MAX, idiosyncratic volatility, "
          "abnormal volume, low beta) have no skill here on their own.", "",
          "## 14. Robustness: other periods, realistic costs, confidence intervals (scripts/eval_robustness.py)", "",
          f"Monthly walk-forward from {wf['start']} to {wf['end']} ({wf['rebalances']} rebalances), every model refit each year on earlier data. 2017-20 were the "
          "validation years on which model choices were made, so they are not a clean test.", ""]
    R0 = wf["results"]["realistic"]
    show = ["C  Max-Sharpe, prior returns", "C+ C + volatility model", "D  C+ + return tilt", "E  Full system (D + regime overlay)", "B  Min-variance + volatility model",
            "NIFTY 50 ETF (buy and hold)", "Equal-weight stocks (monthly)"]
    per = list(wf["periods"])
    L += ["Sharpe ratio by period, realistic costs:", "", "| Strategy | " + " | ".join(per) + " |", "|---|" + "---|" * len(per)]
    for n in show:
        L.append(f"| {n} | " + " | ".join(f"{R0[n][q]['sharpe']:.2f}" for q in per) + " |")
    L += ["", "Sharpe ratio 2021-26 by cost level (calendar years; the section-6 table starts at the first rebalance, end of January 2021):", "",
          "| Strategy | " + " | ".join(wf["results"]) + " |", "|---|" + "---|" * len(wf["results"])]
    for n in show:
        L.append(f"| {n} | " + " | ".join(f"{wf['results'][sname][n]['2021-26 (test years)']['sharpe']:.2f}" for sname in wf["results"]) + " |")
    L += ["", "90% intervals for Sharpe differences (stationary block bootstrap of daily returns, mean block 21 days, 2000 draws, realistic costs):", "",
          "| Difference | 2021-26 point [90% interval], share > 0 | 2017-26 point [90% interval], share > 0 |", "|---|---|---|"]
    for k in [x for x in wf["bootstrap"]["2021-26 (test years)"] if x.startswith("DIFF ")]:
        a, b = wf["bootstrap"]["2021-26 (test years)"][k], wf["bootstrap"]["2017-26 (all)"][k]
        L.append(f"| {k[5:]} | {a['point']:+.2f} [{a['lo']:+.2f}, {a['hi']:+.2f}], {a['share_above_0']:.0%} | {b['point']:+.2f} [{b['lo']:+.2f}, {b['hi']:+.2f}], {b['share_above_0']:.0%} |")
    L += ["",
          "What survives: every strategy keeps a higher Sharpe ratio than the NIFTY ETF in every cost scenario, and the full system beats NIFTY in every 2-year block; "
          "over 2017-26 its advantage over NIFTY (+0.43) is the one difference whose 90% interval excludes zero (+0.01 to +0.83). "
          "What does not: the volatility model's gain in the max-Sharpe family comes mostly from 2021-22 and its 90% interval includes zero; in the minimum-variance family "
          "it gains nothing over 2017-26; the full system does not beat an equal-weight basket of the stocks with any confidence. A 5-6 year Sharpe ratio is also fragile: "
          "starting the 2021-26 window one month later (end of January instead of 1 January) moves the max-Sharpe + volatility model from 0.62 to 0.73. Costs matter for "
          "small accounts: the fixed depository charge (Rs 15.93 per security sold) costs a Rs 1 lakh account rebalanced monthly 0.04-0.15 of Sharpe.", "",
          "### The app's plans from many start dates", "",
          f"The five strategies chosen with data up to each quarter-end ({pl['profile']}, no ML, as in the app's backtest), held with quarterly rebalancing and realistic costs:", "",
          "| Holding | Strategy | start dates | median return | median per year | worst | best | beat NIFTY ETF | median Sharpe |", "|---|---|---|---|---|---|---|---|---|"]
    for k, v in pl["summary"].items():
        h, name = k.split(" ", 1)
        L.append(f"| {h} | {name} | {v['starts']} | {v['median_net']:+.0%} | {v['median_ann']:+.1%} | {v['worst_net']:+.0%} | {v['best_net']:+.0%} | "
                 f"{'' if 'share_beat_nifty' not in v else format(v['share_beat_nifty'], '.0%')} | {'' if 'median_sharpe' not in v else format(v['median_sharpe'], '.2f')} |")
    L += ["",
          "Over 1 year every plan's median return beat the NIFTY ETF's (12.9-16.7% vs 11.2%) and their worst year was far milder (-12% to +6% vs -21%). "
          "Over 3 years no plan lost money from any of the 26 start dates (worst +18% to +42%, NIFTY ETF worst +5%), but on return only Max Return clearly beat the "
          "NIFTY ETF (median 18.0% vs 15.0% a year); the recommended Goal-Based plan beat it in 35% of the windows. The plans' edge is smaller losses, not higher returns. "
          "The single Oct 2023 window in the slides (+55% vs +15%) was a favourable one.", ""]
    return L


if __name__ == "__main__":
    ret, vol, cal, reg, ano, port = (load(n) for n in ("eval_returns.json", "eval_vol.json", "eval_calibration.json", "eval_regimes.json", "eval_anomalies.json", "eval_portfolio.json"))
    figures(ret, vol, cal, port)
    report(ret, vol, cal, reg, ano, port)
    print("wrote reports/evaluation.md and 3 figures")
