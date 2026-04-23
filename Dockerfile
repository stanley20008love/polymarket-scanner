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

# Use a start script that reads PORT env var dynamically
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]
