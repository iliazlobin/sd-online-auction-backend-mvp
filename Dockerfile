# ── Builder stage ──────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# System deps for psycopg2 / asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Create venv and install deps
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the app package itself
COPY pyproject.toml .
COPY src/ ./src/
RUN pip install --no-cache-dir .

# ── Runtime stage ─────────────────────────────────────────────────
FROM python:3.12-slim

# Copy venv (includes uvicorn, alembic, and all deps + the app package)
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Runtime-only system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY alembic.ini alembic/ ./alembic/

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "auction_app.main:create_app()", "--host", "0.0.0.0", "--port", "8000"]
