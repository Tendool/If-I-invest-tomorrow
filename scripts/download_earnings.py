"""Download quarterly earnings dates with EPS estimate, reported EPS and surprise for the NSE stocks (Yahoo Finance).

    python scripts/download_earnings.py        # -> data/earnings/<SYMBOL>.csv

Used by the volatility model's earnings-calendar features (ifit/earnings.py). Also run by scripts/download_data.py.
"""
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

from ifit import earnings  # noqa: E402

if __name__ == "__main__":
    print(earnings.download(), "stocks written to", earnings.EARN_DIR)
