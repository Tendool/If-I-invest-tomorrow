"""Module 3 - Market analysis & ML prediction.

* market-regime clustering (Gaussian mixture on market state variables)
* anomaly detection (Isolation Forest)
* forward-return estimation: Ridge / Random Forest / XGBoost (+ optional GRU), validated with an
  expanding-window walk-forward scheme and blended with CAPM only to the extent that the model
  shows genuine out-of-sample skill (information coefficient).
"""
from __future__ import annotations

import dataclasses
import json
import warnings
from dataclasses import dataclass, field

import joblib
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import IsolationForest, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.mixture import GaussianMixture
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import config as C
from . import data as _data
from . import features as F
from .data import MarketData

warnings.filterwarnings("ignore")

REGIME_NAMES = ["Bull / Calm", "Neutral / Sideways", "Bear / Volatile"]


# --------------------------------------------------------------------------- #
# Regime clustering
# --------------------------------------------------------------------------- #
@dataclass
class RegimeModel:
    labels: pd.Series                 # per-day regime id (0 = bull, 1 = neutral, 2 = bear)
    probs: pd.DataFrame               # posterior probabilities per day
    stats: pd.DataFrame               # per-regime descriptive statistics
    transition: np.ndarray            # 3x3 daily transition matrix
    current: int
    current_probs: np.ndarray
    names: list[str] = field(default_factory=lambda: list(REGIME_NAMES))
    mkt_mean_daily: np.ndarray = None  # mean NIFTY daily return per regime
    mkt_vol_daily: np.ndarray = None

    @property
    def current_name(self) -> str:
        return self.names[self.current]


def _regime_inputs(md: MarketData) -> tuple[pd.DataFrame, pd.Series]:
    """Regime-model inputs and market level. Uses the long NIFTY/VIX history (2007-, incl. the 2008 crash) when it is
    available, cut at md's last date so that point-in-time backtests stay point-in-time."""
    long = getattr(md, "regime_long", None)
    if long is not None:
        long = long.loc[:md.market.index[-1]]
        if len(long) > 0 and long.index[0] <= md.market.index[0]:
            return F.regime_state(long["market"], long["vix"]).dropna(), long["market"]
    return F.market_features(md)[F.REGIME_COLS].dropna(), md.market


def fit_regimes(md: MarketData, k: int = 3, seed: int = 7) -> RegimeModel:
    mf, mkt = _regime_inputs(md)
    scaler = StandardScaler().fit(mf.values)
    Z = scaler.transform(mf.values)
    gmm = GaussianMixture(n_components=k, covariance_type="full", n_init=5, random_state=seed).fit(Z)
    raw = gmm.predict(Z)
    post = gmm.predict_proba(Z)

    # order clusters: bear = highest vol & lowest return, bull = best return / lowest vol
    mret = mkt.pct_change().reindex(mf.index).fillna(0.0)
    score = []
    for c in range(k):
        m = raw == c
        score.append(mret[m].mean() * 252 - 1.5 * mret[m].std() * np.sqrt(252))
    order = np.argsort(score)[::-1]          # best -> worst
    remap = {int(old): new for new, old in enumerate(order)}
    labels = pd.Series([remap[int(x)] for x in raw], index=mf.index, name="regime")
    probs = pd.DataFrame(post[:, order], index=mf.index, columns=range(k))

    # transition matrix from consecutive daily labels (+ tiny smoothing)
    T = np.full((k, k), 1e-3)
    for a, b in zip(labels.values[:-1], labels.values[1:]):
        T[a, b] += 1
    T = T / T.sum(axis=1, keepdims=True)

    rows = []
    for c in range(k):
        m = labels == c
        r = mret[m]
        rows.append(dict(
            regime=REGIME_NAMES[c], days=int(m.sum()), share=float(m.mean()),
            ann_return=float(r.mean() * 252), ann_vol=float(r.std() * np.sqrt(252)),
            avg_vix=float(mf.loc[m, "vix"].mean()), avg_drawdown=float(mf.loc[m, "mkt_dd"].mean()),
        ))
    st = pd.DataFrame(rows).set_index("regime")
    cur = int(labels.iloc[-1])
    # statistics and transitions use the whole history; the label/probability series are reported on md's own calendar
    on_cal = labels.index.isin(md.market.index)
    return RegimeModel(labels=labels[on_cal], probs=probs[on_cal], stats=st, transition=T, current=cur,
                       current_probs=probs.iloc[-1].values,
                       mkt_mean_daily=np.array([mret[labels == c].mean() for c in range(k)]),
                       mkt_vol_daily=np.array([mret[labels == c].std() for c in range(k)]))


# --------------------------------------------------------------------------- #
# Anomaly detection
# --------------------------------------------------------------------------- #
@dataclass
class AnomalyReport:
    market_score: pd.Series          # higher = more anomalous
    market_flags: pd.Series          # bool series
    today_is_anomalous: bool
    today_score_percentile: float
    asset_alerts: pd.DataFrame       # assets with unusual moves today


def detect_anomalies(md: MarketData, contamination: float = 0.02, seed: int = 7) -> AnomalyReport:
    mf = F.market_features(md).dropna()
    iso = IsolationForest(n_estimators=300, contamination=contamination, random_state=seed)
    iso.fit(mf.values)
    score = pd.Series(-iso.score_samples(mf.values), index=mf.index, name="anomaly_score")
    flags = pd.Series(iso.predict(mf.values) == -1, index=mf.index)
    pct = float((score <= score.iloc[-1]).mean())

    r = md.returns
    z = (r.iloc[-1] - r.iloc[-253:-1].mean()) / r.iloc[-253:-1].std()
    alerts = pd.DataFrame({"z_score": z, "ret_today": r.iloc[-1]})
    alerts = alerts[alerts["z_score"].abs() >= 2.5].sort_values("z_score")
    return AnomalyReport(score, flags, bool(flags.iloc[-1]), pct, alerts)


# --------------------------------------------------------------------------- #
# Return estimation - walk-forward model comparison
# --------------------------------------------------------------------------- #
def _models() -> dict:
    """Return-model candidates; settings selected on 2019-2020 only (scripts/model_search.py)."""
    import xgboost as xgb
    return {
        "Ridge (Linear)": make_pipeline(StandardScaler(), Ridge(alpha=3000.0)),
        "Random Forest": RandomForestRegressor(n_estimators=150, max_depth=6, min_samples_leaf=100,
                                               max_features=0.5, n_jobs=-1, random_state=7),
        "XGBoost": xgb.XGBRegressor(n_estimators=400, max_depth=4, learning_rate=0.03, subsample=0.7,
                                    colsample_bytree=0.7, min_child_weight=50, reg_lambda=10.0,
                                    n_jobs=-1, random_state=7, verbosity=0),
    }


def relative_panel(md: MarketData) -> pd.DataFrame:
    """Feature panel whose target is the *relative* 21d return (minus the cross-sectional mean).

    The market's common move is noise for stock selection; what can be ranked is who beats the rest."""
    panel = F.build_panel(md)
    panel["target"] = panel["target"] - panel.groupby(level=0)["target"].transform("mean")
    return panel


def _metrics(df: pd.DataFrame) -> dict:
    """df has columns y, pred, indexed by (date, symbol)."""
    err = df["y"] - df["pred"]
    ic_by_date = df.groupby(level=0).apply(lambda g: stats.spearmanr(g["y"], g["pred"])[0] if len(g) > 5 else np.nan)
    ts_corr = stats.spearmanr(df["y"], df["pred"])[0]
    return dict(
        rmse=float(np.sqrt((err ** 2).mean())),
        mae=float(err.abs().mean()),
        dir_acc=float((np.sign(df["y"]) == np.sign(df["pred"])).mean()),
        ic_cross_section=float(ic_by_date.mean()),
        ic_pooled=float(ts_corr),
        n_test=int(len(df)),
    )


# Return signal: a fixed, documented factor composite, nothing fitted. Every fitted model (Ridge, RF, XGBoost, LightGBM
# ranker, GRU, a Ridge on factor ranks) has validation IC at or below ~0 on 2017-20.
# Round 6 (scripts/model_search_v5.py): 1-month reversal + 12-1 momentum, validation IC 0.049 (t 2.3), test 0.052.
# Round 7 (scripts/model_search_v6.py, rule fixed in advance: beat the incumbent's validation t): the same two effects measured
# on *residual* returns (after removing each stock's beta x market move; Blitz, Huij & Martens 2011) - validation IC 0.061
# (t 3.2), test 0.046 (t 2.2); over all ten years 2017-26 IC 0.052 vs 0.051 for the round-6 signal.
FACTOR_NAME = "Residual reversal + momentum"
FACTOR_VAL_IC = 0.061


def residual_factors(md: MarketData) -> pd.DataFrame:
    """(date, symbol) residual momentum (months t-12..t-1, risk-scaled) and residual 1-month return, point in time."""
    r = md.prices.pct_change()
    mr = md.market.pct_change().reindex(r.index)
    beta = r.rolling(252, min_periods=126).cov(mr).div(mr.rolling(252, min_periods=126).var(), axis=0)
    resid = r - beta.shift(1).mul(mr, axis=0)                       # yesterday's beta: no look-ahead
    s231 = resid.rolling(231, min_periods=120)
    res_mom = s231.sum().shift(21) / (s231.std().shift(21) * np.sqrt(231))
    res_rev = resid.rolling(21).sum()
    out = pd.concat([res_mom.stack().rename("res_mom"), res_rev.stack().rename("res_rev")], axis=1)
    out.index.names = ["date", "symbol"]
    return out.replace([np.inf, -np.inf], np.nan)


def factor_score(fx: pd.DataFrame) -> pd.Series:
    """Cross-sectional z-score of residual momentum + residual reversal (date by date; higher = expected to beat the rest)."""
    rk = lambda x: x.groupby(level=0).rank(pct=True) - 0.5
    raw = (rk(fx["res_mom"]) - rk(fx["res_rev"])) / 2
    sd = raw.groupby(level=0).transform("std").replace(0, np.nan)
    return ((raw - raw.groupby(level=0).transform("mean")) / sd).fillna(0.0)


def factor_forecast(fx: pd.DataFrame, cs_sd: float) -> pd.Series:
    """Score -> expected relative 21-day return, Grinold's refined forecast: IC x cross-sectional volatility x score."""
    return FACTOR_VAL_IC * cs_sd * factor_score(fx)


def walk_forward(md: MarketData, test_years: tuple[int, ...] = (2021, 2022, 2023, 2024, 2025, 2026),
                 include_gru: bool = False, verbose: bool = False) -> tuple[pd.DataFrame, dict]:
    """Expanding-window walk-forward evaluation. Returns (metrics table, out-of-sample predictions)."""
    panel = relative_panel(md).dropna()
    feats = F.feature_columns(panel)
    dates = panel.index.get_level_values(0)
    models = _models()
    oos: dict[str, list[pd.DataFrame]] = {n: [] for n in models}
    oos[FACTOR_NAME] = []
    fx = residual_factors(md)
    if include_gru:
        oos["GRU"] = []
    base_oos = []

    for yr in test_years:
        start, end = pd.Timestamp(f"{yr}-01-01"), pd.Timestamp(f"{yr}-12-31")
        purge = start - pd.Timedelta(days=int(F.FWD_DAYS * 1.5))   # avoid target overlap leakage
        tr = panel[dates < purge]
        te = panel[(dates >= start) & (dates <= end)]
        if len(te) < 100 or len(tr) < 5000:
            continue
        tr_s = tr.iloc[::3]          # sub-sample: overlapping 21d targets are highly autocorrelated
        for name, mdl in models.items():
            mdl.fit(tr_s[feats].values, tr_s["target"].values)
            p = mdl.predict(te[feats].values)
            oos[name].append(pd.DataFrame({"y": te["target"].values, "pred": p}, index=te.index))
        base_oos.append(pd.DataFrame({"y": te["target"].values, "pred": tr["target"].mean()}, index=te.index))
        fte = fx.reindex(te.index)
        oos[FACTOR_NAME].append(pd.DataFrame({"y": te["target"].values,
                                              "pred": factor_forecast(fte, float(tr["target"].std())).reindex(te.index).fillna(0.0).values},
                                             index=te.index))
        if include_gru:
            try:
                from .gru import fit_predict_gru
                p = fit_predict_gru(tr, te, feats)
                oos["GRU"].append(pd.DataFrame({"y": te["target"].values, "pred": p}, index=te.index))
            except Exception as e:      # pragma: no cover
                print("GRU failed:", e)
        if verbose:
            print("fold", yr, "done")

    rows = {}
    for name, parts in oos.items():
        if parts:
            rows[name] = _metrics(pd.concat(parts))
    rows["Historical mean (baseline)"] = _metrics(pd.concat(base_oos))
    table = pd.DataFrame(rows).T
    return table, {k: pd.concat(v) for k, v in oos.items() if v}


@dataclass
class ReturnEstimator:
    model_name: str
    metrics: pd.DataFrame
    skill_weight: float                  # lambda: weight given to the ML view vs. the CAPM/historical prior
    ml_forecast_21d: pd.Series           # latest forward-21d return forecast per asset
    feature_importance: pd.Series | None = None

    @property
    def ml_tilt_annual(self) -> pd.Series:
        """ML view expressed as an annualised *relative* tilt (cross-sectionally demeaned, clipped).

        Absolute monthly forecasts are too noisy to trust, so the model is only used to rank
        assets: assets forecast above the cross-sectional average get a positive tilt.
        """
        f = self.ml_forecast_21d.clip(-0.12, 0.12)
        return ((f - f.mean()) * (C.TRADING_DAYS / F.FWD_DAYS)).clip(-0.15, 0.15)


def train_return_model(md: MarketData, include_gru: bool = False, save: bool = True) -> ReturnEstimator:
    table, _ = walk_forward(md, include_gru=include_gru)
    # Production signal: the residual reversal + momentum composite, chosen on the 2017-20 validation (round 7). The fitted models
    # (Ridge, RF, XGBoost, GRU) stay in the table for comparison.
    best = FACTOR_NAME
    ic = float(table.loc[best, "ic_cross_section"])
    # Skill weight: zero when the signal shows no cross-sectional skill, capped at 0.5.
    lam = float(np.clip(5.0 * ic, 0.0, 0.5))

    panel = relative_panel(md)
    cs_sd = float(panel["target"].dropna().std())
    last_date = panel.index.get_level_values(0).max()
    fx = residual_factors(md)
    pred = factor_forecast(fx.loc[[last_date]], cs_sd).droplevel(0).reindex(panel.xs(last_date, level=0).index).fillna(0.0)
    est = ReturnEstimator(best, table, lam, pred, None)
    if save:
        joblib.dump(dict(model=None, kind="factor", features=["res_mom", "res_rev"], best=best, val_ic=FACTOR_VAL_IC, cs_sd=cs_sd),
                    C.MODELS_DIR / "return_model.joblib")
        table.to_csv(C.REPORTS_DIR / "ml_walk_forward_metrics.csv")
        json.dump(dict(best=best, ic=ic, skill_weight=lam, asof=str(last_date.date())),
                  open(C.MODELS_DIR / "return_model_meta.json", "w"), indent=2)
        pred.to_csv(C.MODELS_DIR / "latest_forecast_21d.csv")
    return est


def load_return_estimator(md: MarketData) -> ReturnEstimator:
    """Load the trained estimator (fast path) - trains it if nothing is cached."""
    meta_p = C.MODELS_DIR / "return_model_meta.json"
    tab_p = C.REPORTS_DIR / "ml_walk_forward_metrics.csv"
    fc_p = C.MODELS_DIR / "latest_forecast_21d.csv"
    if meta_p.exists() and tab_p.exists() and fc_p.exists():
        meta = json.load(open(meta_p))
        table = pd.read_csv(tab_p, index_col=0)
        fc = pd.read_csv(fc_p, index_col=0).iloc[:, 0]
        imp = None
        try:
            bundle = joblib.load(C.MODELS_DIR / "return_model.joblib")
            m = bundle["model"]
            if hasattr(m, "feature_importances_"):
                imp = pd.Series(m.feature_importances_, index=bundle["features"]).sort_values(ascending=False)
        except Exception:
            pass
        return ReturnEstimator(meta["best"], table, meta["skill_weight"], fc, imp)
    return train_return_model(md)


# --------------------------------------------------------------------------- #
# Expected returns = CAPM / history prior, tilted by ML view
# --------------------------------------------------------------------------- #
def expected_returns(rm, est: ReturnEstimator | None) -> pd.DataFrame:
    """Final annual expected-return vector: (CAPM + history) prior tilted by the ML view."""
    capm = rm.capm
    hist = capm["hist_return"].clip(-0.05, 0.30)
    prior = 0.6 * capm["capm_return"] + 0.4 * hist
    lam = est.skill_weight if est is not None else 0.0
    tilt = est.ml_tilt_annual.reindex(capm.index).fillna(0.0) if est is not None else pd.Series(0.0, index=capm.index)
    final = prior + lam * tilt
    out = pd.DataFrame(dict(capm=capm["capm_return"], hist=hist, prior=prior, ml_tilt=tilt, expected=final))
    for s in out.index:       # cash earns ~ the risk-free rate less a spread
        if C.UNIVERSE[s][2] == "cash":
            out.loc[s, ["capm", "prior", "expected"]] = C.RISK_FREE - 0.005
            out.loc[s, "ml_tilt"] = 0.0
    return out


# --------------------------------------------------------------------------- #
# Volatility forecasting (the one forecast with large, validated skill)
# --------------------------------------------------------------------------- #
_ANN = np.sqrt(C.TRADING_DAYS)
VOL_ALPHA = 3000.0
VOL_NAIVE_WEIGHT = 0.15       # forecast = 0.85 x Ridge + 0.15 x trailing 63-day vol (weight chosen on 2017-20 walk-forward validation, round 6)
VOL_TEST_YEARS = (2021, 2022, 2023, 2024, 2025, 2026)


def _load_ohlc(md):
    """High/Low/Open aligned to the cleaned calendar (raw files; ratios within a day are split-proof)."""
    out = {k: {} for k in ("open", "high", "low", "close")}
    for sym in md.prices.columns:
        raw = _data._read_raw(sym)
        if raw is None:
            continue
        raw = raw.reindex(md.prices.index)
        for k, col in (("open", "Open"), ("high", "High"), ("low", "Low"), ("close", "Close")):
            out[k][sym] = raw[col]
    return {k: pd.DataFrame(v) for k, v in out.items()}


RESULTS_MONTHS = (1, 2, 4, 5, 7, 8, 10, 11)       # months in which Indian companies mostly report quarterly results


def _results_season_share(panel: pd.DataFrame) -> np.ndarray:
    """Share of the next 21 business days that fall in a results month (known in advance); 0 for non-stocks."""
    dates = panel.index.get_level_values(0)
    udates = pd.DatetimeIndex(dates.unique())
    share = pd.Series([np.isin(pd.bdate_range(d + pd.Timedelta(days=1), periods=21).month, RESULTS_MONTHS).mean() for d in udates],
                      index=udates)
    is_stock = np.array([C.UNIVERSE[s][2] == "stock" for s in panel.index.get_level_values(1)], dtype=float)
    return share.reindex(dates).values * is_stock


def vol_panel(md: MarketData) -> pd.DataFrame:
    """(date, symbol) panel of range-based + realised-volatility features and the log forward-21d realised volatility."""
    r = md.returns
    o = _load_ohlc(md)
    hl = np.log(o["high"] / o["low"]).clip(0, 0.25)                       # ln(H/L); NSE circuit limits keep this small
    co = np.log(o["close"] / o["open"]).clip(-0.25, 0.25)
    ho = np.log(o["high"] / o["open"]).clip(0, 0.25)
    lo = np.log(o["low"] / o["open"]).clip(-0.25, 0)
    gk = (0.5 * hl ** 2 - (2 * np.log(2) - 1) * co ** 2).clip(lower=0)    # Garman-Klass variance
    rs = (ho * (ho - co) + lo * (lo - co)).clip(lower=0)                  # Rogers-Satchell variance
    park = hl ** 2 / (4 * np.log(2))                                      # Parkinson variance
    gap = np.log(o["open"] / o["close"].shift(1)).clip(-0.25, 0.25)
    vol = md.volume.replace(0, np.nan)

    feats: dict[str, pd.DataFrame] = {}
    for k in (1, 5, 10, 21, 63, 126, 252):
        feats[f"rv_{k}"] = np.log((r.rolling(k, min_periods=max(2, k // 2)).std() * _ANN).clip(lower=0.01)) if k > 1 else np.log((r.abs() * _ANN).clip(lower=0.01))
    for k in (5, 21, 63):
        feats[f"park_{k}"] = np.log(np.sqrt(park.rolling(k).mean() * C.TRADING_DAYS).clip(lower=0.01))
    feats["gk_21"] = np.log(np.sqrt(gk.rolling(21).mean() * C.TRADING_DAYS).clip(lower=0.01))
    feats["gk_5"] = np.log(np.sqrt(gk.rolling(5).mean() * C.TRADING_DAYS).clip(lower=0.01))
    feats["rs_21"] = np.log(np.sqrt(rs.rolling(21).mean() * C.TRADING_DAYS).clip(lower=0.01))
    for lam in (0.94, 0.985):
        feats[f"ewma_{lam}"] = np.log(np.sqrt((r ** 2).ewm(alpha=1 - lam, adjust=False).mean() * C.TRADING_DAYS).clip(lower=0.01))
    feats["semi_dn_21"] = np.log((np.sqrt((r.clip(upper=0) ** 2).rolling(21).mean()) * _ANN).clip(lower=0.01))
    feats["semi_up_21"] = np.log((np.sqrt((r.clip(lower=0) ** 2).rolling(21).mean()) * _ANN).clip(lower=0.01))
    feats["maxabs_21"] = r.abs().rolling(21).max()
    feats["gap_21"] = gap.abs().rolling(21).mean()
    feats["volofvol_63"] = (r.rolling(5).std() * _ANN).rolling(63).std() / (r.rolling(63).std() * _ANN)
    feats["ret_1"] = r
    feats["ret_21"] = md.prices.pct_change(21)
    feats["ret_63"] = md.prices.pct_change(63)
    feats["dd_252"] = md.prices / md.prices.rolling(252, min_periods=60).max() - 1
    feats["vlm_ratio"] = np.log(vol.rolling(5).mean() / vol.rolling(63).mean())
    feats["rv5_over_63"] = feats["rv_5"] - feats["rv_63"]
    feats["rv21_over_252"] = feats["rv_21"] - feats["rv_252"]

    frames = {k: v.stack().rename(k) for k, v in feats.items()}
    panel = pd.concat(frames.values(), axis=1)
    panel.index.names = ["date", "symbol"]

    mf = F.market_features(md)
    mr = md.market.pct_change()
    mk = pd.DataFrame({
        "m_rv_5": np.log((mr.rolling(5).std() * _ANN).clip(lower=0.01)),
        "m_rv_21": np.log((mr.rolling(21).std() * _ANN).clip(lower=0.01)),
        "m_rv_63": np.log((mr.rolling(63).std() * _ANN).clip(lower=0.01)),
        "vix": md.macro["vix"] / 100, "vix_chg_5": md.macro["vix"].pct_change(5), "vix_chg_21": md.macro["vix"].pct_change(21),
        "vix_rv_gap": np.log(md.macro["vix"] / 100) - np.log((mr.rolling(21).std() * _ANN).clip(lower=0.01)),
        "m_dd": mf["mkt_dd"], "usdinr_21": mf["usdinr_ret_21d"], "brent_21": mf["brent_ret_21d"],
    })
    panel = panel.join(mk, on="date")
    # cross-sectional context: average log vol of the whole universe today
    panel["cs_mean_rv21"] = panel.groupby(level=0)["rv_21"].transform("mean")
    panel["rv21_vs_cs"] = panel["rv_21"] - panel["cs_mean_rv21"]
    # each asset's own long-run (3-year) level of log volatility: volatility mean-reverts towards it
    lr = np.log((r.rolling(21).std() * _ANN).clip(lower=0.01)).rolling(756, min_periods=252).mean()
    panel["lr_level"] = lr.stack().reindex(panel.index)
    panel["rv21_vs_lr"] = panel["rv_21"] - panel["lr_level"]
    # seasonality (round 6, chosen on 2017-20 validation): quarterly results make each stock's volatility repeat by calendar
    seas = np.log((r.rolling(21).std().shift(231) * _ANN).clip(lower=0.01))      # vol in the same 21-day window a year ago
    panel["rv_seas"] = seas.stack().reindex(panel.index)
    panel["rv_seas_vs_252"] = panel["rv_seas"] - panel["rv_252"]
    panel["results_season"] = _results_season_share(panel)
    # asset-class effects (round 7, chosen on 2017-20 validation): ETFs, gold and bonds follow different volatility dynamics
    cls = np.array([C.UNIVERSE[s][2] for s in panel.index.get_level_values(1)])
    for c in ("etf", "gold", "bond"):
        dmy = (cls == c).astype(float)
        panel[f"is_{c}"] = dmy
        for f in ("rv_21", "rv_63", "m_rv_21", "lr_level"):
            panel[f"{f}_x_{c}"] = panel[f] * dmy

    fvol = r.rolling(21).std().shift(-21) * _ANN
    panel["y"] = np.log(fvol.stack().rename("y").clip(lower=0.01)).reindex(panel.index)
    return panel.replace([np.inf, -np.inf], np.nan)


def _is_cash(sym: str) -> bool:
    return C.UNIVERSE[sym][2] == "cash"


def _blend(model_pred, log_rv63):
    return (1 - VOL_NAIVE_WEIGHT) * model_pred + VOL_NAIVE_WEIGHT * log_rv63


def _vol_model():
    return make_pipeline(StandardScaler(), Ridge(alpha=VOL_ALPHA))


def vol_features(panel: pd.DataFrame) -> list[str]:
    return [c for c in panel.columns if c != "y"]


def vol_walk_forward(panel: pd.DataFrame) -> dict:
    """Expanding-window walk-forward (test years 2021-26, 1.5x-horizon purge) of the volatility model on the non-cash
    assets, scored against 'same as the last month / quarter'. R2 is on log volatility; 'within-asset' removes each
    asset's own average so it measures month-to-month timing rather than just which assets are riskier."""
    feats = vol_features(panel)
    dates = panel.index.get_level_values(0)
    purge = pd.Timedelta(days=int(F.FWD_DAYS * 1.5))
    parts = []
    for yr in VOL_TEST_YEARS:
        a, b = pd.Timestamp(f"{yr}-01-01"), pd.Timestamp(f"{yr}-12-31")
        trn = panel[dates < a - purge].dropna(subset=feats + ["y"]).iloc[::3]
        te = panel[(dates >= a) & (dates <= b)].dropna(subset=feats + ["y"])
        if len(trn) < 2000 or te.empty:
            continue
        m = _vol_model().fit(trn[feats].values, trn["y"].values)
        parts.append(pd.DataFrame({"y": te["y"], "p": _blend(m.predict(te[feats].values), te["rv_63"].values),
                                   "n21": te["rv_21"], "n63": te["rv_63"]}))
    df = pd.concat(parts)

    def r2(y, p):
        return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())

    err = lambda col: float(np.mean(np.abs(np.exp(df[col] - df["y"]) - 1)))
    g = df.groupby(level=1)
    dm = lambda s: s - g[s.name].transform("mean")
    wy = dm(df["y"]); wp = dm(df["p"])
    return dict(rows=int(len(df)), years=f"{VOL_TEST_YEARS[0]}-{VOL_TEST_YEARS[-1]}", r2=r2(df["y"], df["p"]),
                naive_21d_r2=r2(df["y"], df["n21"]), naive_63d_r2=r2(df["y"], df["n63"]),
                err=err("p"), naive_21d_err=err("n21"), naive_63d_err=err("n63"),
                within_asset_r2=float(1 - ((wy - wp) ** 2).sum() / (wy ** 2).sum()),
                corr=float(np.corrcoef(df["y"], df["p"])[0, 1]))


def train_vol_model(md: MarketData, save: bool = True) -> pd.Series:
    """Fit the volatility model (Ridge on HAR-style realised + range-based features, selected on 2019-20 validation) on all
    history and forecast next-21-day annualised volatility for every asset (as of the last date). The liquid fund (a flat
    accrual) is not modelled: its trailing volatility is used. Honest walk-forward numbers are written to the meta file."""
    risky = [c for c in md.prices.columns if not _is_cash(c)]
    sub = dataclasses.replace(md, prices=md.prices[risky], volume=md.volume[risky])
    panel = vol_panel(sub)
    feats = vol_features(panel)
    metrics = vol_walk_forward(panel)
    train = panel.dropna(subset=feats + ["y"]).iloc[::3]
    model = _vol_model().fit(train[feats].values, train["y"].values)
    last = panel.index.get_level_values(0).max()
    X = panel.xs(last, level=0)[feats]
    X = X.fillna(X.median())
    pred = pd.Series(np.exp(_blend(model.predict(X.values), X["rv_63"].values)), index=X.index, name="vol_forecast_21d")
    fc = pd.Series(index=md.prices.columns, dtype=float, name="vol_forecast_21d")
    fc.update(pred)
    trailing = md.returns.iloc[-63:].std() * _ANN
    fc = fc.fillna(trailing).clip(lower=0.01)
    if save:
        joblib.dump(dict(model=model, features=feats, naive_weight=VOL_NAIVE_WEIGHT), C.MODELS_DIR / "vol_model.joblib")
        fc.to_csv(C.MODELS_DIR / "latest_vol_forecast.csv")
        json.dump(dict(asof=str(last.date()), version=5, model="Ridge on realised, range-based, seasonal and asset-class volatility features, blended 85/15 with last quarter",
                       features=len(feats), **metrics), open(C.MODELS_DIR / "vol_model_meta.json", "w"), indent=2)
    return fc


def load_vol_forecast(md: MarketData) -> pd.Series:
    """Cached next-month volatility forecast per asset (trains the model if nothing is cached)."""
    p = C.MODELS_DIR / "latest_vol_forecast.csv"
    if p.exists() and (C.MODELS_DIR / "vol_model_meta.json").exists():
        return pd.read_csv(p, index_col=0).iloc[:, 0]
    return train_vol_model(md)
