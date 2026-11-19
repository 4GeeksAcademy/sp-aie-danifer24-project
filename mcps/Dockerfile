FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN python -m pip install --no-cache-dir uv
COPY services/api/requirements.txt /app/api-requirements.txt
RUN uv pip install --system --no-cache \
    -r /app/api-requirements.txt \
    "sqlmodel>=0.0.48" \
    "psycopg2-binary>=2.9.13" \
    "fastmcp>=4.1.8" \
    "httpx2>=2.14.0"

COPY services /app/services
COPY mcps /app/mcps
COPY packages/shared /app/packages/shared
COPY data /app/data

EXPOSE 8010
CMD ["python", "-m", "mcps.nexova_mcp.server"]
