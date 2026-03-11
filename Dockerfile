# -----------------------------------------------------------------------------
# Multi-stage build: base (Python deps) -> frontend (SPA built in container) -> production
# -----------------------------------------------------------------------------

# Stage 1: Python dependencies only
FROM python:3.12-slim AS base
RUN apt-get update && apt-get install -y \
    libminizip1t64 \
    curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Build frontend inside container (no host build required)
FROM node:20-slim AS frontend
WORKDIR /app
COPY app/ ./app/
COPY frontend/ ./frontend/
WORKDIR /app/frontend
RUN npm ci && npm run build
# Output: /app/app/static/spa/ (index.html, assets/)

# Stage 3: Production image; Python loads SPA dir at runtime (Config.get_spa_dir())
FROM python:3.12-slim
RUN apt-get update && apt-get install -y \
    libminizip1t64 \
    curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY --from=base /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=base /usr/local/bin /usr/local/bin
COPY --from=frontend /app/app/ ./app/
COPY config.py run.py ./

COPY bin/zsign /usr/local/bin/zsign
RUN chmod +x /usr/local/bin/zsign

RUN mkdir -p certs /tmp/cook-ipa-profiles

ENV PORT=5005
EXPOSE 5005

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5005/ || exit 1

CMD ["python", "run.py"]
