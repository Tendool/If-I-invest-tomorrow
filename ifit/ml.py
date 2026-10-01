"""Module 3 - Market analysis & ML prediction.

* market-regime clustering (Gaussian mixture on market state variables)
* anomaly detection (Isolation Forest)
* forward-return estimation: Ridge / Random Forest / XGBoost (+ optional GRU), validated with an
  expanding-window walk-forward scheme and blended with CAPM only to the extent that the model
  shows genuine out-of-sample skill (information coefficient).
"""
from __future__ import annotations

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


def fit_regimes(md: MarketData, k: int = 3, seed: int = 7) -> RegimeModel:
    mf = F.market_features(md)[F.REGIME_COLS].dropna()
    scaler = StandardScaler().fit(mf.values)
    Z = scaler.transform(mf.values)
    gmm = GaussianMixture(n_components=k, covariance_type="full", n_init=5, random_state=seed).fit(Z)
    raw = gmm.predict(Z)
    post = gmm.predict_proba(Z)

    # order clusters: bear = highest vol & lowest return, bull = best return / lowest vol
    mret = md.market.pct_change().reindex(mf.index).fillna(0.0)
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
    return RegimeModel(labels=labels, probs=probs, stats=st, transition=T, current=cur,
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
    import xgboost as xgb
    return {
        "Ridge (Linear)": make_pipeline(StandardScaler(), Ridge(alpha=50.0)),
        "Random Forest": RandomForestRegressor(n_estimators=150, max_depth=6, min_samples_leaf=200,
                                               max_features=0.5, n_jobs=-1, random_state=7),
        "XGBoost": xgb.XGBRegressor(n_estimators=250, max_depth=3, learning_rate=0.04, subsample=0.7,
                                    colsample_bytree=0.7, min_child_weight=100, reg_lambda=10.0,
                                    n_jobs=-1, random_state=7, verbosity=0),
    }


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


def walk_forward(md: MarketData, test_years: tuple[int, ...] = (2021, 2022, 2023, 2024, 2025, 2026),
                 include_gru: bool = False, verbose: bool = False) -> tuple[pd.DataFrame, dict]:
    """Expanding-window walk-forward evaluation. Returns (metrics table, out-of-sample predictions)."""
    panel = F.build_panel(md).dropna()
    feats = F.feature_columns(panel)
    dates = panel.index.get_level_values(0)
    models = _models()
    oos: dict[str, list[pd.DataFrame]] = {n: [] for n in models}
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
    # GRU is reported for comparison; the production model is chosen among Ridge / RF / XGBoost
    cand = table.drop(index=["Historical mean (baseline)", "GRU"], errors="ignore")
    best = cand["ic_cross_section"].astype(float).idxmax()
    ic = float(cand.loc[best, "ic_cross_section"])
    # Skill weight: zero when the model shows no cross-sectional skill, capped at 0.5.
    lam = float(np.clip(5.0 * ic, 0.0, 0.5))

    panel = F.build_panel(md)
    feats = F.feature_columns(panel)
    train = panel.dropna()
    train = train.iloc[::3]
    mdl = _models().get(best) or _models()["XGBoost"]
    mdl.fit(train[feats].values, train["target"].values)

    last_date = panel.index.get_level_values(0).max()
    latest = panel.xs(last_date, level=0)[feats]
    latest = latest.fillna(latest.median())
    pred = pd.Series(mdl.predict(latest.values), index=latest.index)
    imp = None
    if hasattr(mdl, "feature_importances_"):
        imp = pd.Series(mdl.feature_importances_, index=feats).sort_values(ascending=False)
    est = ReturnEstimator(best, table, lam, pred, imp)
    if save:
        joblib.dump(dict(model=mdl, features=feats, best=best), C.MODELS_DIR / "return_model.joblib")
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
