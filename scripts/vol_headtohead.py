"""Controlled comparison of volatility feature sets / models on IDENTICAL rows (same train, same test)."""
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ifit import data, ml  # noqa: E402
import model_search_v2 as V2  # noqa: E402


def score(y, p):
    return V2.r2(np.asarray(y), np.asarray(p)), float(np.mean(np.abs(np.exp(np.asarray(p) - np.asarray(y)) - 1)))


def main():
    md = data.load()
    p1 = ml.vol_panel(md)
    p2 = V2.vol_panel(md)
    f1 = ml.VOL_FEATURES
    f2 = [c for c in p2.columns if c != "y"]
    d = p1[f1 + ["log_fvol"]].join(p2[f2 + ["y"]], how="inner", rsuffix="_v2")
    d = d.dropna(subset=f1 + f2 + ["y"])
    print("common rows:", len(d), "| log_fvol == y:", bool(np.allclose(d["log_fvol"], d["y"])))
    f2_only = [c for c in f2 if c not in f1]
    sets = {"round-1 features": f1, "round-2 features": f2, "both": list(dict.fromkeys(f1 + f2))}

    results = {}
    for yr, trn, te in V2.split(d, V2.TEST_YEARS):
        for sname, cols in sets.items():
            for mname, prm in (("Ridge a=3000", ("HAR-Ridge", dict(alpha=3000))), ("Ridge a=300", ("HAR-Ridge", dict(alpha=300))),
                               ("Ridge a=30", ("HAR-Ridge", dict(alpha=30)))):
                m = V2.vol_model(*prm).fit(trn[cols].values[::3], trn["y"].values[::3])
                results.setdefault((sname, mname), []).append(pd.DataFrame({"y": te["y"].values, "p": m.predict(te[cols].values)}, index=te.index))
        # production ensemble on round-1 features (Ridge + RF + XGB)
        ens = []
        for mn in ml._vol_models().values():
            mn.fit(trn[f1].values[::3], trn["y"].values[::3])
            ens.append(mn.predict(te[f1].values))
        results.setdefault(("round-1 features", "Production ensemble (Ridge+RF+XGB)"), []).append(pd.DataFrame({"y": te["y"].values, "p": np.mean(ens, axis=0)}, index=te.index))
        # same ensemble on round-2 features
        ens2 = []
        for nm, prm in (("HAR-Ridge", dict(alpha=3000)), ("Random Forest", dict(n_estimators=200, max_depth=12, min_samples_leaf=50, max_features=0.5)),
                        ("XGBoost", dict(n_estimators=700, max_depth=4, learning_rate=0.03, subsample=0.7, colsample_bytree=0.7, min_child_weight=200, reg_lambda=10.0))):
            ens2.append(V2.vol_model(nm, prm).fit(trn[f2].values[::3], trn["y"].values[::3]).predict(te[f2].values))
        results.setdefault(("round-2 features", "Ensemble (Ridge+RF+XGB)"), []).append(pd.DataFrame({"y": te["y"].values, "p": np.mean(ens2, axis=0)}, index=te.index))

    print(f"\n{'features':20s} {'model':38s} {'R2':>7s} {'err%':>7s}")
    rows = []
    for (s, m), parts in results.items():
        df = pd.concat(parts)
        r, e = score(df.y, df.p)
        rows.append((s, m, r, e))
    te_all = d[d.index.get_level_values(0) >= "2021-01-01"]
    for nm, col in (("Naive trailing 21d", "log_vol_21d"), ("Naive trailing 63d", "log_vol_63d")):
        r, e = score(te_all["y"], te_all[col])
        rows.append(("baseline", nm, r, e))
    for s, m, r, e in sorted(rows, key=lambda x: -x[2]):
        print(f"{s:20s} {m:38s} {r:7.4f} {e * 100:6.1f}%")


if __name__ == "__main__":
    main()
