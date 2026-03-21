# Multi-stage Dockerfile for MerusCase WC Test Data Generator
# Serves FastAPI (port 5520) + Next.js standalone (port 3000)
#
# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

# Stage 1: Build Next.js frontend
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --ignore-scripts
COPY frontend/ .
RUN npm run build

# Stage 2: Python runtime
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install Node.js for Next.js standalone server
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Python source
COPY main.py config.py ./
COPY data/ data/
COPY orchestration/ orchestration/
COPY pdf_templates/ pdf_templates/
COPY service/ service/
COPY scripts/ scripts/

# Copy Next.js standalone build
COPY --from=frontend-builder /app/frontend/.next/standalone ./frontend-standalone/
COPY --from=frontend-builder /app/frontend/.next/static ./frontend-standalone/.next/static
COPY --from=frontend-builder /app/frontend/public ./frontend-standalone/public

# Create output and logs dirs
RUN mkdir -p output logs

# Startup script
COPY <<'EOF' /app/start.sh
#!/bin/sh
set -e

# Start Next.js standalone server in background
cd /app/frontend-standalone && PORT=3000 node server.js &

# Start FastAPI server
cd /app && python3 main.py serve --port 5520 --host 0.0.0.0
EOF
RUN chmod +x /app/start.sh

EXPOSE 3000 5520

CMD ["/app/start.sh"]
