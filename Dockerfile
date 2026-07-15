FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (excludes patterns in .dockerignore)
COPY . .

# Create runtime directories
RUN mkdir -p data/db data/faiss data/chroma data/documents data/backups logs && \
    useradd --create-home --uid 10001 rapid && chown -R rapid:rapid /app

# Environment
ENV PYTHONUNBUFFERED=1
ENV RAPID_ENV=production

# Expose API port
EXPOSE 8000

USER rapid

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production: gunicorn with uvicorn workers (2 workers per CPU core)
# Override CMD in docker-compose for development: uvicorn main:app --reload
CMD ["gunicorn", "main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "2", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
