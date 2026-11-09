FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN python -m pip install --no-cache-dir uv

COPY api/requirements.txt ./requirements.txt

RUN uv pip install --system --no-cache \
    -r requirements.txt \
    "celery>=5.7.0" \
    "redis>=8.1.0" \
    "sqlmodel>=0.0.48" \
    "psycopg2-binary>=2.9.13" \
    && mkdir -p /app/data /app/uis/backoffice

COPY . ./services
COPY --from=repo /packages/shared ./packages/shared
COPY --from=repo /scripts ./scripts
COPY --from=repo /data ./data

EXPOSE 8000

CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]