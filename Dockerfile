FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Zeabur sets PORT env var - our app must listen on it
ENV PORT=8501
ENV PYTHONUNBUFFERED=1

# Start with gunicorn, reading PORT from env
CMD exec gunicorn --bind "0.0.0.0:${PORT}" --workers 1 --timeout 120 app:app
