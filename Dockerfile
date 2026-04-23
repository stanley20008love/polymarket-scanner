FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed for numpy/pandas
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8501

# Environment
ENV PORT=8501
ENV PYTHONUNBUFFERED=1

# Use gunicorn for production reliability
CMD ["gunicorn", "--bind", "0.0.0.0:8501", "--workers", "1", "--timeout", "120", "app:app"]
