FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV CIVIC_WAREHOUSE_ROOT=data/public_api/normalized
ENV CIVIC_RAW_ROOT=data/raw

WORKDIR /app

COPY pyproject.toml README.md ./
COPY civic_data ./civic_data
COPY api ./api
COPY data/config ./data/config
COPY data/geo ./data/geo
COPY data/public_api ./data/public_api
COPY registry ./registry

RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
