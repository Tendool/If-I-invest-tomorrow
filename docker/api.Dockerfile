# syntax=docker/dockerfile:1
# Python API (FastAPI + analytics engine + Qwen agent client)
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# libgomp: required by xgboost / scikit-learn wheels; curl: healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-api.txt .
RUN pip install -r requirements-api.txt

COPY ifit ./ifit
COPY scripts ./scripts
COPY docker/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh \
    && mkdir -p data/raw data/processed models reports

# state that must survive container restarts: market data, trained models, the demo wallet (SQLite)
VOLUME ["/app/data", "/app/models", "/app/reports"]

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=240s --retries=10 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "ifit.api:app", "--host", "0.0.0.0", "--port", "8000"]
