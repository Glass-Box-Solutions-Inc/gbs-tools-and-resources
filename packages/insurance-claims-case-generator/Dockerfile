# @Developed & Documented by Glass Box Solutions, Inc.
# Multi-stage build skeleton — Phase 1 scaffold
# Full implementation in Phase 4

# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN pip install --no-cache-dir build wheel

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Build the package
RUN pip install --no-cache-dir -e .

# Stage 2: Runtime
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/claims-gen /usr/local/bin/claims-gen
COPY --from=builder /build/src/ src/

# Non-root user for security
RUN useradd --create-home --no-log-init claimsgen && chown -R claimsgen:claimsgen /app
USER claimsgen

# Phase 3+: expose API port 8001
EXPOSE 8001

# Default: show help
ENTRYPOINT ["claims-gen"]
CMD ["--help"]
