# Quotation Bot API (Beta) - enterprise deployment image
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY frontend ./frontend
COPY rules ./rules
COPY quotation_snapshot.json ./

# Run as a non-root user.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# Data artifacts are eagerly loaded at startup; /health doubles as readiness.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
