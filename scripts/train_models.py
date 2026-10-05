"""Train + walk-forward-validate the return signal and the volatility model, and write the reports.

    python scripts/train_models.py            # reversal + momentum signal (in use) vs Ridge / Random Forest / XGBoost
    python scripts/train_models.py --gru      # also the optional GRU
"""
import sys, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")
import pandas as pd
from ifit import data, ml

if __name__ == "__main__":
    md = data.load()
    est = ml.train_return_model(md, include_gru="--gru" in sys.argv)
    pd.set_option("display.width", 200)
    print(est.metrics.round(4))
    print(f"\nselected: {est.model_name}  skill weight (lambda) = {est.skill_weight:.2f}")
    print()
    print("training the volatility forecaster (Ridge on realised, range-based and seasonal features, 85/15 blend with last quarter) ...")
    fc = ml.train_vol_model(md)
    print(fc.round(3).sort_values(ascending=False).head(8).to_string())
    reg = ml.fit_regimes(md)
    print("\nregimes:\n", reg.stats.round(3))
    reg.stats.to_csv(data.C.REPORTS_DIR / "regime_stats.csv")
