# @Developed & Documented by Glass Box Solutions, Inc.
# Multi-stage build — Phase 4 complete implementation
# No secrets in the image — all credentials come from env vars at runtime.
#
# Build:
#   docker build -t insurance-claims-case-generator .
#
# Run CLI (generate):
#   docker run --rm insurance-claims-case-generator generate --scenario standard_claim --seed 42
#
# Run seed:
#   docker run --rm \
#     -e ADJUDICLAIMS_URL=https://staging.adjudiclaims.com \
#     -e ADJUDICLAIMS_EMAIL=seed@example.com \
#     -e ADJUDICLAIMS_PASSWORD=secret \
#     insurance-claims-case-generator seed --scenario standard_claim --env staging
#
# Run API server:
#   docker run --rm -p 8001:8001 insurance-claims-case-generator api

# ---------------------------------------------------------------------------
# Stage 1: Builder
# ---------------------------------------------------------------------------
FROM python:3.12 AS builder

WORKDIR /build

# Install build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy only what's needed to build the wheel
COPY pyproject.toml setup.py* ./
COPY src/ src/

# Install runtime dependencies into a prefix directory so we can copy them cleanly
RUN pip install --no-cache-dir --prefix=/install .

# ---------------------------------------------------------------------------
# Stage 2: Runtime (slim image)
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy installed packages and scripts from builder
COPY --from=builder /install/lib /usr/local/lib
COPY --from=builder /install/bin /usr/local/bin

# Copy the source tree (needed for editable-style imports and the loader)
COPY --from=builder /build/src/ /app/src/

# Add src/ to PYTHONPATH so claims_generator is importable
ENV PYTHONPATH="/app/src:${PYTHONPATH}"

# Non-root user — principle of least privilege
RUN useradd --create-home --no-log-init --uid 1001 claimsgen \
    && chown -R claimsgen:claimsgen /app

USER claimsgen

# Expose the FastAPI port
EXPOSE 8001

# Default entrypoint — override CMD to use a sub-command
ENTRYPOINT ["claims-gen"]
CMD ["--help"]
