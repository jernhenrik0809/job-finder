# Job Finder — container image
FROM python:3.13-slim

# Don't write .pyc, unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JOBFINDER_HOST=0.0.0.0 \
    JOBFINDER_PORT=8000 \
    JOBFINDER_DATA_DIR=/data

WORKDIR /app

# Install deps first for layer caching. `anthropic` is bundled so the optional
# Claude drafting path works the moment a user supplies ANTHROPIC_API_KEY.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt anthropic

# App code
COPY jobfinder/ ./jobfinder/
COPY run.py .

# Persist the SQLite store on a volume so the Outbox survives container restarts.
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"

CMD ["python", "run.py"]
