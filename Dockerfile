# api, worker ve migrate servislerinin ortak imajı.
# GRIB çözümü pip'teki eccodes + eccodeslib ikili paketiyle (libaec/CCSDS dahil); apt gerekmez.
FROM python:3.12.16-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system hava \
    && useradd --system --gid hava --home-dir /app hava \
    && mkdir -p /data/grib /data/parquet \
    && chown -R hava:hava /data

# Bağımlılıklar ayrı katmanda: yalnız pyproject değişince yeniden kurulur.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install -e .

COPY alembic.ini ./
COPY alembic ./alembic
COPY config ./config

USER hava
EXPOSE 8000
CMD ["uvicorn", "hava.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
