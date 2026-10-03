"""Round 5: does MORE DATA help? Longer history (back to 2007, incl. the 2008 crash) and a wider universe (+~45 large NSE stocks).

    python scripts/extended_data.py download      # -> data/raw_ext (production data/raw is untouched)
    python scripts/extended_data.py vol
    python scripts/extended_data.py returns
    python scripts/extended_data.py mc

Models are trained on the extended data but scored on exactly the production test rows: the original 31 assets, 2021-26.
Selection still uses the 2017-20 walk-forward validation. Caveat: the extra stocks are today's large caps (survivorship bias),
which matters for return prediction more than for volatility.
"""
import dataclasses
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.linear_model import Ridge  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from ifit import config as C, data, features as F, ml  # noqa: E402

RAW_EXT = ROOT / "data" / "raw_ext"
ORIG = dict(C.UNIVERSE)
EXTRA = {s + ".NS": (s.title(), sec, "stock") for s, sec in [
    ("AXISBANK", "Banking"), ("INDUSINDBK", "Banking"), ("BANKBARODA", "Banking"), ("PNB", "Banking"), ("CANBK", "Banking"),
    ("BAJAJFINSV", "Finance"), ("ASIANPAINT", "Consumer"), ("BERGEPAINT", "Consumer"), ("PIDILITIND", "Consumer"), ("HAVELLS", "Consumer"),
    ("BAJAJ-AUTO", "Auto"), ("EICHERMOT", "Auto"), ("HEROMOTOCO", "Auto"), ("BOSCHLTD", "Auto"), ("MRF", "Auto"),
    ("BPCL", "Energy"), ("IOC", "Energy"), ("GAIL", "Energy"), ("TATAPOWER", "Power"), ("BHEL", "Infra"),
    ("BRITANNIA", "FMCG"), ("DABUR", "FMCG"), ("GODREJCP", "FMCG"), ("MARICO", "FMCG"), ("COLPAL", "FMCG"), ("TATACONSUM", "FMCG"),
    ("DIVISLAB", "Pharma"), ("LUPIN", "Pharma"), ("AUROPHARMA", "Pharma"), ("APOLLOHOSP", "Pharma"),
    ("GRASIM", "Infra"), ("SHREECEM", "Infra"), ("AMBUJACEM", "Infra"), ("ACC", "Infra"), ("DLF", "Infra"), ("ADANIPORTS", "Infra"), ("SIEMENS", "Infra"),
    ("HINDALCO", "Metals"), ("JSWSTEEL", "Metals"), ("VEDL", "Metals"), ("SAIL", "Metals"), ("NMDC", "Metals"),
    ("TECHM", "IT"), ("WIPRO", "IT"), ("CUMMINSIND", "Infra"),
]}
VAL_YEARS = (2017, 2018, 2019, 2020)
TEST_YEARS = (2021, 2022, 2023, 2024, 2025, 2026)
PURGE = pd.Timedelta(days=int(F.FWD_DAYS * 1.5))


def download():
    RAW_EXT.mkdir(parents=True, exist_ok=True)
    syms = list(ORIG) + list(EXTRA) + [C.MARKET_SYMBOL] + list(C.MACRO)
    for s in syms:
        try:
            import yfinance as yf
            df = yf.Ticker(s).history(period="max", interval="1d", auto_adjust=False)
            df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
            df = df[~df.index.duplicated(keep="last")][[c for c in data.FIELDS if c in df.columns]]
            df.to_csv(RAW_EXT / f"{data._fname(s)}.csv")
            print(f"{s:16s} {len(df):5d} rows from {df.index[0].date()}", flush=True)
        except Exception as e:
            print(f"{s:16s} FAILED {e}", flush=True)


def load_variant(longer: bool, wider: bool):
    """MarketData for a variant. longer -> data/raw_ext (max history); wider -> + EXTRA stocks."""
    C.DATA_RAW = RAW_EXT if (longer or wider) else ROOT / "data" / "raw"
    C.UNIVERSE = dict(ORIG, **EXTRA) if wider else dict(ORIG)
    md = data.clean()
    if not longer:                                           # wider-only: keep the production start date
        start = pd.Timestamp("2014-10-01")
        md = dataclasses.replace(md, prices=md.prices.loc[start:], volume=md.volume.loc[start:], market=md.market.loc[start:], macro=md.macro.loc[start:])
    keep = [c for c in md.prices.columns if C.UNIVERSE[c][2] != "cash"]
    md = dataclasses.replace(md, prices=md.prices[keep].dropna(how="all", axis=1), volume=md.volume[keep])
    md = dataclasses.replace(md, volume=md.volume[md.prices.columns])
    return md


VARIANTS = {"production data (31 assets, 2014-)": (False, False), "longer history (31 assets, 2007-)": (True, False),
            "wider universe (76 assets, 2014-)": (False, True), "longer + wider (76 assets, 2007-)": (True, True)}


def r2(y, p):
    return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def within(df):
    g = df.groupby(level=1)
    wy, wp = df.y - g.y.transform("mean"), df.p - g.p.transform("mean")
    return float(1 - ((wy - wp) ** 2).sum() / (wy ** 2).sum())


def run_vol():
    orig_risky = [s for s in ORIG if ORIG[s][2] != "cash"]
    res = {}
    for name, (lo, wi) in VARIANTS.items():
        md = load_variant(lo, wi)
        panel = ml.vol_panel(md)
        feats = ml.vol_features(panel)
        d = panel.dropna(subset=feats + ["y"])
        dates = d.index.get_level_values(0)
        out = {"val": [], "test": []}
        for yr in VAL_YEARS + TEST_YEARS:
            a, b = pd.Timestamp(f"{yr}-01-01"), pd.Timestamp(f"{yr}-12-31")
            tr = d[dates < a - PURGE]
            te = d[(dates >= a) & (dates <= b)]
            te = te[te.index.get_level_values(1).isin(orig_risky)]          # always score on the production assets
            m = make_pipeline(StandardScaler(), Ridge(alpha=ml.VOL_ALPHA)).fit(tr[feats].values[::3], tr["y"].values[::3])
            out["val" if yr in VAL_YEARS else "test"].append(pd.DataFrame({"y": te.y, "p": ml._blend(m.predict(te[feats].values), te.rv_63.values)}, index=te.index))
        v, t = pd.concat(out["val"]), pd.concat(out["test"])
        res[name] = dict(val_r2=r2(v.y, v.p), test_r2=r2(t.y, t.p), test_within=within(t), test_err=float(np.mean(np.abs(np.exp(t.p - t.y) - 1))),
                         test_rows=len(t), train_rows_2026=int((d.index.get_level_values(0) < "2026-01-01").sum()))
        r = res[name]
        print(f"{name:38s} val R2 {r['val_r2']:.4f} | test R2 {r['test_r2']:.4f} within {r['test_within']:.4f} err {r['test_err'] * 100:.1f}% "
              f"(test rows {r['test_rows']}, train rows {r['train_rows_2026']})", flush=True)
    (C.REPORTS_DIR / "extended_data_vol.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


def run_returns():
    from eval_models import build_return_panel, daily_ic, ic_stats
    orig_risky = [s for s in ORIG if ORIG[s][2] != "cash"]
    res = {}
    for name, (lo, wi) in VARIANTS.items():
        md = load_variant(lo, wi)
        panel, sets = build_return_panel(md)
        cols = sets["base"]
        d = panel.dropna(subset=cols + ["y_rel"])
        dates = d.index.get_level_values(0)
        out = {"val": [], "test": []}
        for yr in VAL_YEARS + TEST_YEARS:
            a, b = pd.Timestamp(f"{yr}-01-01"), pd.Timestamp(f"{yr}-12-31")
            tr = d[dates < a - PURGE]
            te = d[(dates >= a) & (dates <= b)]
            te = te[te.index.get_level_values(1).isin(orig_risky)]
            m = make_pipeline(StandardScaler(), Ridge(alpha=3000.0)).fit(tr[cols].values[::3], tr["y_rel"].values[::3])
            # re-centre the target on the 31 scored assets so IC is comparable
            y = te.y_rel - te.groupby(level=0).y_rel.transform("mean")
            out["val" if yr in VAL_YEARS else "test"].append(pd.DataFrame({"y": y, "p": m.predict(te[cols].values)}, index=te.index))
        vi, ti = daily_ic(pd.concat(out["val"])), daily_ic(pd.concat(out["test"]))
        st = ic_stats(ti)
        res[name] = dict(val_ic=float(vi.mean()), test_ic=st["mean"], test_t_nw=st["t_newey_west"], test_t_ind=st["t_nonoverlap"], test_pct_pos=st["pct_pos"])
        r = res[name]
        print(f"{name:38s} val IC {r['val_ic']:+.4f} | test IC {r['test_ic']:+.4f} tNW {r['test_t_nw']:+.2f} tIND {r['test_t_ind']:+.2f}", flush=True)
    (C.REPORTS_DIR / "extended_data_returns.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


def run_mc():
    """Same 104 calibration forecasts (2019-25 origins, production portfolios), but the regime model may learn from
    2007- (incl. the 2008 crash) instead of 2014-. Risk model / expected returns unchanged (5-year look-back)."""
    from calibration import HORIZON, PORTFOLIOS
    from ifit import montecarlo as MC, risk
    levels = (0.5, 0.75, 0.9, 0.95, 0.99)
    md_prod = data.load()
    C.DATA_RAW = RAW_EXT
    C.UNIVERSE = dict(ORIG)
    md_long = data.clean()
    idx = md_prod.prices.index
    res = {}
    for lab, md_reg in (("regimes learned from 2014-", md_prod), ("regimes learned from 2007- (incl. 2008)", md_long)):
        pits = []
        for q in pd.date_range("2019-03-31", "2025-09-30", freq="QE"):
            pos = idx.searchsorted(q, side="right") - 1
            if pos + HORIZON >= len(idx):
                continue
            t = idx[pos]
            md_t = dataclasses.replace(md_prod, prices=md_prod.prices.loc[:t], volume=md_prod.volume.loc[:t], market=md_prod.market.loc[:t], macro=md_prod.macro.loc[:t])
            mr = dataclasses.replace(md_reg, prices=md_reg.prices.loc[:t], volume=md_reg.volume.loc[:t], market=md_reg.market.loc[:t], macro=md_reg.macro.loc[:t])
            rm = risk.build_risk_model(md_t)
            mu = ml.expected_returns(rm, None)["expected"]
            regime = ml.fit_regimes(mr)
            for name, wd in PORTFOLIOS.items():
                w = pd.Series(wd).reindex(rm.symbols).fillna(0.0)
                if w.sum() < 0.999:
                    continue
                st = risk.portfolio_stats(w, mu, rm.cov, rm.beta)
                sim = MC.simulate_paths(st["exp_return"], st["volatility"], st["beta"], regime, 1, n_paths=3000, steps_per_year=252, seed=11)[:, -1] - 1
                rets = md_prod.prices.pct_change().iloc[pos + 1: pos + 1 + HORIZON]
                real = float((1 + (rets * w.reindex(rets.columns).fillna(0.0)).sum(axis=1)).prod() - 1)
                pits.append(float((sim < real).mean()))
        p = np.array(pits)
        res[lab] = {str(int(q * 100)): float(((p >= (1 - q) / 2) & (p <= 1 - (1 - q) / 2)).mean()) for q in levels}
        res[lab]["mean_gap"] = float(np.mean([abs(res[lab][str(int(q * 100))] - q) for q in levels]))
        res[lab]["n"] = len(p)
        print(f"{lab:42s} " + "  ".join(f"{k}%:{v:.0%}" for k, v in res[lab].items() if k.isdigit()) + f"   mean gap {res[lab]['mean_gap']:.3f}  n={len(p)}", flush=True)
    (C.REPORTS_DIR / "extended_data_mc.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"download": download, "vol": run_vol, "returns": run_returns, "mc": run_mc}[sys.argv[1]]()
