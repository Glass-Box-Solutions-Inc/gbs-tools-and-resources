# =============================================================================
# Specticales - Human-Sight Browser Automation Agent
# Cloud Run Dockerfile with AI Reasoning Engine
# =============================================================================

# Stage 1: Download sentence-transformers model
FROM python:3.12-slim as model-stage

RUN pip install --no-cache-dir sentence-transformers==2.3.1
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Stage 2: Production image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080

WORKDIR /app

# Copy model cache from model-stage (Hugging Face cache)
COPY --from=model-stage /root/.cache/huggingface /root/.cache/huggingface

# Install system dependencies for image processing (PII blur)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Skip Playwright browser install - we use Browserless.io for browser automation
# For local development, run: playwright install chromium

# Copy application code
COPY . .

# Create Qdrant storage directory
RUN mkdir -p ./qdrant_storage

# Create non-root user for security
RUN useradd -m -u 1000 spectacles && \
    chown -R spectacles:spectacles /app
USER spectacles

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Expose port
EXPOSE 8080

# Run the application
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
