"""Download the raw datasets (Yahoo Finance) and build the cleaned panel.

    python scripts/download_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ifit import data  # noqa: E402

if __name__ == "__main__":
    print("== Downloading datasets from Yahoo Finance ==")
    status = data.download_all()
    failed = [s for s, v in status.items() if v.startswith("FAILED")]
    print("\n== Cleaning / aligning ==")
    md = data.build_dataset()
    print(f"panel: {md.prices.shape[0]} days x {md.prices.shape[1]} assets, "
          f"{md.prices.index[0].date()} -> {md.last_date.date()}")
    print(f"first date with all assets: {md.report['first_common_date']}")
    if md.report["dropped"]:
        print("dropped:", md.report["dropped"])
    if failed:
        print("FAILED downloads:", failed)
    print("
== Quarterly results (earnings calendar) ==")
    try:
        from ifit import earnings
        print(earnings.download(verbose=False), "stocks")
    except Exception as e:                      # the models still work without it (earnings features become 0)
        print("earnings download failed:", e)
