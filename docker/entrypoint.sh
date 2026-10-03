#!/bin/sh
# First start: download the datasets and train the ML models if the volumes are empty.
set -e
cd /app

if [ ! -f data/raw/_NSEI.csv ]; then
  echo "[ifit] no market data found - downloading datasets from Yahoo Finance (1-2 min)..."
  python scripts/download_data.py
fi

if [ ! -f data/raw/long__NSEI.csv ] || [ ! -f data/raw/long__INDIAVIX.csv ]; then
  echo "[ifit] downloading the long NIFTY / India VIX history for the regime model..."
  python -c "from ifit import config as C, data
for s in C.REGIME_LONG_SYMBOLS:
    data._download_one(s, 0, period='max').to_csv(C.DATA_RAW / ('long_' + data._fname(s) + '.csv'))" || true
fi

if [ ! -f data/processed/prices.csv ]; then
  python -c "from ifit import data; data.build_dataset()"
fi

if [ ! -f models/return_model_meta.json ] || [ ! -f models/vol_model_meta.json ] \
   || ! grep -q '"version": 3' models/vol_model_meta.json; then
  echo "[ifit] training and validating the ML models (about 2 min)..."
  python scripts/train_models.py
fi

echo "[ifit] Ollama host: ${OLLAMA_HOST:-http://localhost:11434}  model: ${IFIT_LLM_MODEL:-qwen3.5:4b}"
exec "$@"
