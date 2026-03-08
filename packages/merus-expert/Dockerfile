# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
# Multi-stage build for merus-expert

# ─────────────────────────────────────────────────────
# Stage 1: Frontend — build React app
# ─────────────────────────────────────────────────────
FROM node:20-slim AS frontend

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ─────────────────────────────────────────────────────
# Stage 2: Builder — compile Python wheel
# ─────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools
RUN pip install --no-cache-dir build wheel setuptools

# Copy project files for build
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Build wheel
RUN python -m build --wheel --outdir /dist

# ─────────────────────────────────────────────────────
# Stage 3: Runtime
# ─────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install wheel from builder
COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Copy service layer and knowledge
COPY service/ ./service/
COPY knowledge/ ./knowledge/
COPY persistence/ ./persistence/
COPY setup/schema.sql ./setup/schema.sql

# Copy frontend build output
COPY --from=frontend /frontend/dist ./static/

# Create runtime directories
RUN mkdir -p /data /logs

# Non-root user for security
RUN useradd -m -u 1000 merus && chown -R merus:merus /app /data /logs
USER merus

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
